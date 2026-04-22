"""
Main application window for Tellocon.

Provides GUI for drone connection, takeoff/land, stabilised hover
(heading-hold via GY-80 9-DOF IMU) and autonomous orbit demo.

Heading estimation uses a complementary filter that fuses:
  - L3G4200D gyroscope (gz) for short-term rate integration, and
  - HMC5883L magnetometer for long-term north reference.
Pitch/roll for tilt compensation come from the Tello's internal IMU
(vibration-dampened).

Hover mode additionally applies velocity damping using Tello's
speed_x/speed_y telemetry to counteract XY drift.
"""

import math
import os
import sys
import time
import logging
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QTextEdit,
)
from PyQt5.QtCore import QTimer, Qt

from src.tello_controller import TelloController
from src.camera_widget import CameraWidget
from src.video_thread import VideoThread
from src.bluetooth_handler import BluetoothHandler

logging.basicConfig(level=logging.WARNING)


# ---------------------------------------------------------------------------
# Heading helpers
# ---------------------------------------------------------------------------

def tilt_compensated_heading(mx, my, mz, pitch_deg, roll_deg):
    """Compute heading (0-359) from magnetic vector with tilt compensation.

    Uses the NXP algorithm: project the magnetic-field vector from the
    tilted body frame onto the horizontal plane, then compute atan2.

    Args:
        mx, my, mz: Raw magnetometer readings (calibrated).
        pitch_deg:   Pitch angle from Tello IMU (nose-up positive) [deg].
        roll_deg:    Roll angle from Tello IMU (right-wing-down positive) [deg].

    Returns:
        Heading in degrees [0, 360).
    """
    pitch_deg = pitch_deg if pitch_deg is not None else 0
    roll_deg = roll_deg if roll_deg is not None else 0
    theta = math.radians(pitch_deg)
    phi = math.radians(roll_deg)

    x_h = (mx * math.cos(theta)
           + my * math.sin(theta) * math.sin(phi)
           + mz * math.sin(theta) * math.cos(phi))
    y_h = my * math.cos(phi) - mz * math.sin(phi)

    h = math.degrees(math.atan2(y_h, x_h))
    if h < 0:
        h += 360.0
    return h


def wrap_angle_error(target, actual):
    """Return shortest signed angular error (target - actual), wrapped to [-180, 180]."""
    err = target - actual
    if err > 180:
        err -= 360
    elif err < -180:
        err += 360
    return err


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.tello_controller = TelloController()
        self.video_thread = None
        self.bluetooth_handler = None

        # Current RC commands sent to the drone [lr, fb, ud, yaw]
        self.current_rc_values = [0, 0, 0, 0]

        # IMU state (GY-80: mag + accel + gyro)
        self.raw_mag = None
        self.raw_accel = None
        self.raw_gyro = None
        self.current_heading = None
        self.filtered_heading = None
        self._heading_last_time = None
        self._heading_dt = 0.0
        self._gyro_available = False
        # Heading filter robustness against vibration spikes
        self.HEADING_BLEND_BASE = 0.02
        self.HEADING_BLEND_LOW = 0.006
        self.HEADING_GYRO_GATE_DPS = 120.0
        self.HEADING_GYRO_HARD_DPS = 220.0
        self.HEADING_MAX_STEP_DEG = 3.0
        self.HEADING_MAX_CORR_DEG = 25.0
        # -- Heading-hold hover (active after takeoff) --
        self.hover_active = False
        self.hover_heading = None
        self.HOVER_K_YAW = 0.35
        self.HOVER_K_ALT = 0.5
        self.HOVER_TARGET_HEIGHT = 80
        self.HOVER_MAX_YAW_CMD = 20
        self.HOVER_MAX_ALT_CMD = 25
        self.HOVER_DEADBAND = 6.0
        self.HOVER_ERR_FAILSAFE = 35.0
        self.HOVER_ERR_FAILSAFE_TICKS = 10
        self._hover_err_bad_ticks = 0
        self.HOVER_TILT_FAILSAFE_DEG = 30.0
        self.HOVER_TILT_FAILSAFE_TICKS = 3
        self.HOVER_TILT_AUTOLAND = True
        self._hover_tilt_bad_ticks = 0
        # Telemetry validity gates
        self.HOVER_HEIGHT_MIN_VALID = 0
        self.HOVER_HEIGHT_MAX_VALID = 300
        self.HOVER_HEIGHT_JUMP_MAX = 60
        self._hover_prev_height = None

        # --- PID prędkości do anty-dryfu (optical flow z Tello) ---
        self.VEL_KP = 0.9
        self.VEL_KI = 0.02
        self.VEL_KD = 0.25
        self.vel_int_x = 0.0
        self.vel_int_y = 0.0
        self.vel_prev_x = 0.0
        self.vel_prev_y = 0.0

        # -- DEMO orbit parameters --
        self.demo_active = False
        self.demo_start_heading = None
        self.demo_start_time = None
        self.demo_last_time = None
        self.demo_cumulative_turn = 0.0
        self.demo_prev_heading = None

        self.DEMO_YAW_RATE = 12.0
        self.DEMO_FORWARD_RC = 30
        self.DEMO_TARGET_HEIGHT = 80
        self.DEMO_STABILIZE_TIME = 3.0
        self.DEMO_K_YAW = 0.6
        self.DEMO_K_ALT = 0.5
        self.DEMO_MAX_YAW_CMD = 35
        self.DEMO_MAX_ALT_CMD = 30
        self.DEMO_MAX_HEADING_ERR = 45.0
        self.DEMO_RC_SMOOTH = 0.3

        # Debug CSV log
        self.debug_log_file = None
        self.debug_log_path = None
        self.debug_log_header_written = False
        self.debug_used_hover = False
        self.debug_used_demo = False
        self._telemetry_snapshot = {}

        # Timers
        self.hover_timer = QTimer()
        self.hover_timer.timeout.connect(self._update_hover)

        self.demo_timer = QTimer()
        self.demo_timer.timeout.connect(self._update_demo)

        self._init_ui()
        self._init_bluetooth()

    # ------------------------------------------------------------------
    # Debug CSV log
    # ------------------------------------------------------------------

    def _init_debug_log(self):
        # Start a fresh debug log for each drone connection session.
        if self.debug_log_file:
            try:
                self.debug_log_file.close()
            except Exception:
                pass
            self.debug_log_file = None
            self.debug_log_path = None
            self.debug_log_header_written = False
            self.debug_used_hover = False
            self.debug_used_demo = False
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"demo_mag_log_{ts}_connected.csv"
            self.debug_log_path = filename
            self.debug_log_file = open(self.debug_log_path, "w", encoding="utf-8")
            self.debug_log_file.write(
                "timestamp,mode,event,telemetry_valid,invalid_reason,"
                "pitch,roll,yaw_tello,"
                "mx,my,mz,heading_raw,heading_filt,heading_target,heading_err,"
                "ax,ay,az,gx,gy,gz,dt,"
                "height,tof,speed_x,speed_y,speed_z,"
                "rc_left_right,rc_forward_back,rc_up_down,rc_yaw\n")
            self.debug_log_file.flush()
            self.debug_log_header_written = True
            self.debug_used_hover = False
            self.debug_used_demo = False
            self._log(f"Debug log: {self.debug_log_path}")
        except Exception as e:
            self._log(f"Debug log init failed: {e}")

    def _write_debug_row(self, **kw):
        if not self.debug_log_file:
            return
        try:
            mode = kw.get('mode', '')
            if mode == "hover":
                self.debug_used_hover = True
            elif mode == "demo":
                self.debug_used_demo = True
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.debug_log_file.write(
                f"{ts},{mode},{kw.get('event','')},{kw.get('telemetry_valid','')},{kw.get('invalid_reason','')},"
                f"{kw.get('pitch','')},{kw.get('roll','')},{kw.get('yaw_tello','')},"
                f"{kw.get('mx','')},{kw.get('my','')},{kw.get('mz','')},"
                f"{kw.get('heading_raw','')},{kw.get('heading_filt','')},{kw.get('heading_target','')},{kw.get('heading_err','')},"
                f"{kw.get('ax','')},{kw.get('ay','')},{kw.get('az','')},"
                f"{kw.get('gx','')},{kw.get('gy','')},{kw.get('gz','')},{kw.get('dt','')},"
                f"{kw.get('height','')},{kw.get('tof','')},{kw.get('speed_x','')},{kw.get('speed_y','')},{kw.get('speed_z','')},"
                f"{kw.get('rc_lr','')},{kw.get('rc_fb','')},{kw.get('rc_ud','')},{kw.get('rc_yaw','')}\n")
            self.debug_log_file.flush()
        except Exception:
            pass

    def _write_debug_event(self, name):
        if not self.debug_log_file:
            return
        self._write_debug_row(mode="event", event=name)

    def _finalize_debug_log_name(self):
        if not self.debug_log_path:
            return
        try:
            parts = ["connected"]
            if self.debug_used_hover:
                parts.append("hover")
            if self.debug_used_demo:
                parts.append("demo")
            if not self.debug_used_hover and not self.debug_used_demo:
                parts.append("idle")

            if self.debug_log_path.endswith("_connected.csv"):
                final_path = self.debug_log_path.replace(
                    "_connected.csv", f"_{'-'.join(parts)}.csv"
                )
            else:
                root, ext = os.path.splitext(self.debug_log_path)
                final_path = f"{root}_{'-'.join(parts)}{ext}"

            if final_path != self.debug_log_path:
                os.replace(self.debug_log_path, final_path)
                self.debug_log_path = final_path
                self._log(f"Debug log saved: {self.debug_log_path}")
        except Exception as e:
            self._log(f"Debug log rename failed: {e}")

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self):
        self.setWindowTitle("Tellocon v2.0")
        self.setGeometry(100, 100, 1200, 800)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout()

        root.addWidget(self._build_control_panel(), 1)

        right = QVBoxLayout()
        self.camera_widget = CameraWidget()
        right.addWidget(self.camera_widget)

        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(150)
        self.log_text.setReadOnly(True)
        right.addWidget(self.log_text)

        root.addLayout(right, 2)
        central.setLayout(root)

        self._log("Tellocon ready")
        self._log("1. Connect PC to drone WiFi (TELLO-XXXX)")
        self._log("2. Click 'Connect'")
        self._log("3. ESP32-C6 + GY-80 IMU connects automatically via BLE")

    def _build_control_panel(self):
        panel = QFrame()
        panel.setMaximumWidth(300)
        panel.setStyleSheet("background-color: #f0f0f0; padding: 10px;")
        layout = QVBoxLayout()

        title = QLabel("Drone Control")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        layout.addSpacing(20)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._toggle_connection)
        self.connect_btn.setStyleSheet(
            "font-size: 14px; padding: 10px; background-color: #4CAF50; color: white;")
        layout.addWidget(self.connect_btn)

        layout.addSpacing(10)

        self.takeoff_btn = QPushButton("Takeoff (heading-hold)")
        self.takeoff_btn.clicked.connect(self._takeoff)
        self.takeoff_btn.setEnabled(False)
        self.takeoff_btn.setStyleSheet(
            "font-size: 14px; padding: 10px; background-color: #2196F3; color: white;")
        layout.addWidget(self.takeoff_btn)

        self.land_btn = QPushButton("Land")
        self.land_btn.clicked.connect(self._land)
        self.land_btn.setEnabled(False)
        self.land_btn.setStyleSheet(
            "font-size: 14px; padding: 10px; background-color: #f44336; color: white;")
        layout.addWidget(self.land_btn)

        self.demo_btn = QPushButton("DEMO orbit")
        self.demo_btn.clicked.connect(self._toggle_demo)
        self.demo_btn.setEnabled(False)
        self.demo_btn.setStyleSheet(
            "font-size: 14px; padding: 10px; background-color: #9C27B0; color: white;")
        layout.addWidget(self.demo_btn)

        layout.addSpacing(30)

        lbl = QLabel("Status:")
        lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(lbl)

        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("font-size: 12px; color: red;")
        layout.addWidget(self.status_label)

        self.bt_status_label = QLabel("ESP32-C6: Disconnected")
        self.bt_status_label.setStyleSheet("font-size: 12px; color: red;")
        layout.addWidget(self.bt_status_label)

        layout.addSpacing(20)

        info = QLabel(
            "<b>Modes:</b><br/>"
            "Takeoff -- stabilised hover with heading-hold<br/>"
            "DEMO -- autonomous orbit using compass<br/><br/>"
            "<b>Architecture:</b><br/>"
            "ESP32-C6 + GY-80 (9-DOF IMU) via BLE<br/>"
            "Tello Edu controlled over WiFi"
        )
        info.setStyleSheet(
            "font-size: 11px; padding: 10px; background-color: white; border: 1px solid #ccc;")
        layout.addWidget(info)

        layout.addStretch()
        panel.setLayout(layout)
        return panel

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _toggle_connection(self):
        if not self.tello_controller.connected:
            try:
                success, message = self.tello_controller.connect()
                self._log(message)
            except Exception as e:
                self._log(f"Connection failed: {e}")
                self.status_label.setText("Connection Error")
                self.status_label.setStyleSheet("font-size: 12px; color: red;")
                return

            if success:
                self._init_debug_log()
                self._write_debug_event("CONNECT_OK")
                self.connect_btn.setText("Disconnect")
                self.takeoff_btn.setEnabled(True)
                self.land_btn.setEnabled(True)
                self.demo_btn.setEnabled(True)
                self.status_label.setText("Connected")
                self.status_label.setStyleSheet("font-size: 12px; color: green;")
                self._start_video_stream()
            else:
                self.status_label.setText("Connection Error")
                self.status_label.setStyleSheet("font-size: 12px; color: red;")
        else:
            self._disconnect()

    def _disconnect(self):
        self._stop_hover()
        self._stop_demo()

        if self.video_thread:
            self.video_thread.stop()
            self.video_thread = None

        self.tello_controller.disconnect()

        self.connect_btn.setText("Connect")
        for btn in (self.takeoff_btn, self.land_btn, self.demo_btn):
            btn.setEnabled(False)
        self.demo_btn.setText("DEMO orbit")
        self.status_label.setText("Disconnected")
        self.status_label.setStyleSheet("font-size: 12px; color: red;")
        self._write_debug_event("DISCONNECT")
        if self.debug_log_file:
            try:
                self.debug_log_file.close()
            except Exception:
                pass
            self._finalize_debug_log_name()
            self.debug_log_file = None
            self.debug_log_path = None
            self.debug_log_header_written = False
            self.debug_used_hover = False
            self.debug_used_demo = False

        if hasattr(self.camera_widget, 'clear'):
            self.camera_widget.clear()
        self._log("Disconnected")

    # ------------------------------------------------------------------
    # Video stream
    # ------------------------------------------------------------------

    def _start_video_stream(self):
        if self.video_thread is None and self.tello_controller.connected:
            QTimer.singleShot(1000, self._launch_video_thread)

    def _launch_video_thread(self):
        if not self.tello_controller.connected:
            return
        try:
            self.video_thread = VideoThread(self.tello_controller.tello)
            self.video_thread.frame_signal.connect(
                self._on_frame, Qt.QueuedConnection)
            self.video_thread.start()
            self._log("Video stream started")
        except Exception as e:
            logging.error(f"Video start error: {e}")
            self._log(f"Video start error: {e}")

    # ------------------------------------------------------------------
    # Frame callback -- telemetry + heading filter
    # ------------------------------------------------------------------

    def _capture_telemetry_snapshot(self):
        snap = {
            'ts': time.time(),
            'battery': self._tello_get(self.tello_controller.get_battery),
            'height': self._tello_get(self.tello_controller.get_height),
            'tof': self._tello_get(self.tello_controller.get_distance_tof),
            'temp': self._tello_get(self.tello_controller.get_temp),
            'speed_z': self._tello_get(self.tello_controller.get_speed_z),
            'speed_x': self._tello_get(self.tello_controller.get_speed_x),
            'speed_y': self._tello_get(self.tello_controller.get_speed_y),
            'pitch': self._tello_get(self.tello_controller.get_pitch),
            'roll': self._tello_get(self.tello_controller.get_roll),
            'yaw_tello': self._tello_get(self.tello_controller.get_yaw_angle),
        }
        self._telemetry_snapshot = snap
        return snap

    def _get_telemetry_snapshot(self, max_age_s=0.25):
        snap = self._telemetry_snapshot
        if snap and (time.time() - snap.get('ts', 0.0)) <= max_age_s:
            return snap
        return self._capture_telemetry_snapshot()

    def _on_frame(self, frame):
        self.camera_widget.set_frame(frame)

        snap = self._capture_telemetry_snapshot()
        battery = snap['battery']
        height = snap['height']
        tof = snap['tof']
        temp = snap['temp']
        speed_z = snap['speed_z']
        pitch = snap['pitch']
        roll = snap['roll']
        yaw_tello = snap['yaw_tello']

        lr, fb, ud, yaw = self.current_rc_values

        # -- Tilt angles from Tello IMU (vibration-dampened) --
        tilt_pitch = pitch
        tilt_roll = roll

        # -- Magnetometer reference heading --
        mag_heading = None
        if self.raw_mag is not None:
            try:
                if abs(tilt_pitch) <= 25 and abs(tilt_roll) <= 25:
                    h = tilt_compensated_heading(
                        self.raw_mag[0], self.raw_mag[1], self.raw_mag[2],
                        tilt_pitch, tilt_roll)
                    mag_heading = h % 360.0
                    self.current_heading = int(round(mag_heading)) % 360
            except Exception:
                pass

        # -- Complementary filter: gyro (short-term) + mag (long-term) --
        now = time.time()
        if self._heading_last_time is None:
            self._heading_last_time = now

        dt = now - self._heading_last_time
        self._heading_last_time = now
        dt = max(min(dt, 0.2), 0.001)
        self._heading_dt = dt

        if self.raw_gyro is not None and mag_heading is not None:
            gz = self.raw_gyro[2]
            if not self._gyro_available:
                self._gyro_available = True
                self._log("Heading: complementary filter active (gyro + mag)")

            if self.filtered_heading is None:
                self.filtered_heading = mag_heading
            else:
                gx, gy, _ = self.raw_gyro
                gyro_norm = math.sqrt(gx * gx + gy * gy + gz * gz)

                # High gyro norm + near-level attitude usually means vibration, not true yaw motion.
                likely_vibration = (
                    abs(tilt_pitch) <= 6 and
                    abs(tilt_roll) <= 6 and
                    (gyro_norm > self.HEADING_GYRO_GATE_DPS or abs(gz) > self.HEADING_GYRO_HARD_DPS)
                )

                if likely_vibration:
                    predicted = self.filtered_heading
                    blend = self.HEADING_BLEND_BASE
                else:
                    # Gyro prediction (negate gz: positive gyro = CCW, heading CW = positive)
                    predicted = (self.filtered_heading - gz * dt) % 360.0
                    blend = (
                        self.HEADING_BLEND_BASE
                        if gyro_norm < self.HEADING_GYRO_GATE_DPS
                        else self.HEADING_BLEND_LOW
                    )

                mag_correction = wrap_angle_error(mag_heading, predicted)
                mag_correction = max(
                    min(mag_correction, self.HEADING_MAX_CORR_DEG),
                    -self.HEADING_MAX_CORR_DEG
                )
                candidate = (predicted + blend * mag_correction) % 360.0

                # Rate-limit heading update to avoid filter runaway on sensor spikes.
                step = wrap_angle_error(candidate, self.filtered_heading)
                step = max(min(step, self.HEADING_MAX_STEP_DEG), -self.HEADING_MAX_STEP_DEG)
                self.filtered_heading = (self.filtered_heading + step) % 360.0

        elif mag_heading is not None:
            # Fallback: simple IIR if no gyro data (old BMM150 firmware)
            if self.filtered_heading is None:
                self.filtered_heading = mag_heading
            else:
                diff = wrap_angle_error(mag_heading, self.filtered_heading)
                step = max(min(0.08 * diff, 2.0), -2.0)
                self.filtered_heading = (self.filtered_heading + step) % 360.0

        # -- Debug CSV (written continuously while connected) --
        if self.tello_controller.connected and self.debug_log_file:
            mx, my, mz = self.raw_mag if self.raw_mag else ("", "", "")
            ax, ay, az = self.raw_accel if self.raw_accel else ("", "", "")
            gx, gy, gz = self.raw_gyro if self.raw_gyro else ("", "", "")
            speed_x = snap['speed_x']
            speed_y = snap['speed_y']

            mode = "demo" if self.demo_active else ("hover" if self.hover_active else "idle")
            h_raw = self.current_heading if self.current_heading is not None else ""
            h_filt = f"{self.filtered_heading:.1f}" if self.filtered_heading is not None else ""

            # Target heading and error for the active controller
            h_target = ""
            h_err = ""
            filt = self.filtered_heading
            if self.demo_active and self.demo_start_time is not None:
                orbit_t = max(0, time.time() - self.demo_start_time - self.DEMO_STABILIZE_TIME)
                tgt = (self.demo_start_heading + self.DEMO_YAW_RATE * orbit_t) % 360.0
                h_target = f"{tgt:.1f}"
                if filt is not None:
                    h_err = f"{wrap_angle_error(tgt, filt):.1f}"
            elif self.hover_active and self.hover_heading is not None:
                h_target = f"{self.hover_heading:.1f}" if isinstance(self.hover_heading, float) else str(self.hover_heading)
                if filt is not None:
                    h_err = f"{wrap_angle_error(self.hover_heading, filt):.1f}"

            self._write_debug_row(
                mode=mode,
                telemetry_valid="",
                invalid_reason="",
                pitch=pitch, roll=roll, yaw_tello=yaw_tello,
                mx=mx, my=my, mz=mz,
                heading_raw=h_raw, heading_filt=h_filt,
                heading_target=h_target, heading_err=h_err,
                ax=ax, ay=ay, az=az, gx=gx, gy=gy, gz=gz,
                dt=f"{self._heading_dt:.4f}",
                height=height, tof=tof,
                speed_x=speed_x, speed_y=speed_y, speed_z=speed_z,
                rc_lr=lr, rc_fb=fb, rc_ud=ud, rc_yaw=yaw)

        # -- HUD overlay --
        mode = "demo" if self.demo_active else ("hover" if self.hover_active else "idle")
        heading_display = (int(round(self.filtered_heading)) % 360
                           if self.filtered_heading is not None
                           else self.current_heading)
        self.camera_widget.set_ui_info({
            'battery': battery,
            'height': height,
            'tof': tof,
            'temp': temp,
            'throttle': ud,
            'speed': speed_z,
            'pitch': pitch,
            'roll': roll,
            'yaw': yaw_tello,
            'rc_pitch': fb,
            'rc_roll': lr,
            'rc_yaw': yaw,
            'status': 'Active',
            'flying_mode': mode,
            'heading': heading_display,
        })

    @staticmethod
    def _tello_get(fn):
        try:
            return fn()
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Takeoff / Land  (with heading-hold hover)
    # ------------------------------------------------------------------

    def _takeoff(self):
        if not self.tello_controller.connected:
            return
        self._write_debug_event("TAKEOFF_CMD")
        self.tello_controller.takeoff()
        self._log("Takeoff")

        heading = (self.filtered_heading if self.filtered_heading is not None
                   else self.current_heading)
        self.hover_heading = heading
        self.vel_int_x = 0.0
        self.vel_int_y = 0.0
        self.vel_prev_x = 0.0
        self.vel_prev_y = 0.0
        self._hover_tilt_bad_ticks = 0
        self._hover_prev_height = None
        self.hover_active = True
        if not self.hover_timer.isActive():
            self.hover_timer.start(50)
        self._log(f"Heading-hold hover active (target={self.hover_heading})")

    def _land(self):
        if not self.tello_controller.connected:
            return
        self._write_debug_event("LAND_CMD")
        self._stop_hover()
        self._stop_demo()
        self.tello_controller.land()
        self._log("Landed")

    def _stop_hover(self):
        self.hover_active = False
        if self.hover_timer.isActive():
            self.hover_timer.stop()
        self.vel_int_x = 0.0
        self.vel_int_y = 0.0
        self.vel_prev_x = 0.0
        self.vel_prev_y = 0.0
        self._hover_err_bad_ticks = 0
        self._hover_tilt_bad_ticks = 0
        self._hover_prev_height = None
        try:
            self.tello_controller.send_rc_control(0, 0, 0, 0)
        except Exception:
            pass

    def _update_hover(self):
        """Heading-hold + altitude-hold + PID velocity damping while hovering."""
        if not self.hover_active or not self.tello_controller.connected:
            return
        if self.demo_active:
            return

        snap = self._get_telemetry_snapshot()
        height = snap['height']
        pitch = snap['pitch']
        roll = snap['roll']
        heading = (self.filtered_heading if self.filtered_heading is not None
                   else self.current_heading)

        # Safety: abort hover controller if drone tilts hard for multiple ticks.
        if (
            abs(pitch) >= self.HOVER_TILT_FAILSAFE_DEG or
            abs(roll) >= self.HOVER_TILT_FAILSAFE_DEG
        ):
            self._hover_tilt_bad_ticks += 1
        else:
            self._hover_tilt_bad_ticks = max(0, self._hover_tilt_bad_ticks - 1)
        if self._hover_tilt_bad_ticks >= self.HOVER_TILT_FAILSAFE_TICKS:
            self._write_debug_event("TILT_FAILSAFE")
            self._log(
                f"Hover safety stop: excessive tilt "
                f"(pitch={pitch}, roll={roll})"
            )
            self._stop_hover()
            if self.HOVER_TILT_AUTOLAND:
                try:
                    self.tello_controller.land()
                    self._log("Hover safety: auto-land triggered")
                except Exception:
                    pass
            return

        height_valid = self.HOVER_HEIGHT_MIN_VALID <= height <= self.HOVER_HEIGHT_MAX_VALID
        if self._hover_prev_height is not None and abs(height - self._hover_prev_height) > self.HOVER_HEIGHT_JUMP_MAX:
            height_valid = False

        if self._hover_prev_height is None or height_valid:
            self._hover_prev_height = height

        # Altitude hold
        safe_height = height if height_valid else self.HOVER_TARGET_HEIGHT
        h_err = self.HOVER_TARGET_HEIGHT - safe_height
        ud = int(max(min(self.HOVER_K_ALT * h_err, self.HOVER_MAX_ALT_CMD),
                      -self.HOVER_MAX_ALT_CMD))

        # Yaw hold
        yaw = 0
        if heading is not None and self.hover_heading is not None:
            err = wrap_angle_error(self.hover_heading, heading)
            if abs(err) > self.HOVER_ERR_FAILSAFE:
                self._hover_err_bad_ticks += 1
            else:
                self._hover_err_bad_ticks = max(0, self._hover_err_bad_ticks - 1)

            # If heading diverges for sustained period, re-lock target and avoid spiral chasing.
            if self._hover_err_bad_ticks >= self.HOVER_ERR_FAILSAFE_TICKS:
                self.hover_heading = heading
                self._hover_err_bad_ticks = 0
                self._log(f"Hover heading re-lock at {heading:.1f}° (anti-spike)")
                err = 0.0

            if abs(err) >= self.HOVER_DEADBAND:
                yaw = int(max(min(self.HOVER_K_YAW * err, self.HOVER_MAX_YAW_CMD),
                               -self.HOVER_MAX_YAW_CMD))

        # Velocity damping -- counteract XY drift measured by Tello optical flow
        speed_x = snap['speed_x']
        speed_y = snap['speed_y']
        dt = 0.05  # hover_timer = 50 ms

        # --- PID lewo/prawo (likwidacja dryfu bocznego) ---
        err_y = -float(speed_y)   # chcemy speed_y = 0
        self.vel_int_y += err_y * dt
        der_y = (err_y - self.vel_prev_y) / dt
        self.vel_prev_y = err_y

        lr = (
            self.VEL_KP * err_y +
            self.VEL_KI * self.vel_int_y +
            self.VEL_KD * der_y
        )

        # --- PID przód/tył ---
        err_x = -float(speed_x)   # chcemy speed_x = 0
        self.vel_int_x += err_x * dt
        der_x = (err_x - self.vel_prev_x) / dt
        self.vel_prev_x = err_x

        fb = (
            self.VEL_KP * err_x +
            self.VEL_KI * self.vel_int_x +
            self.VEL_KD * der_x
        )

        # ograniczenia jak w Tello
        lr = int(max(min(lr, 20), -20))
        fb = int(max(min(fb, 20), -20))

        self.current_rc_values = [lr, fb, ud, yaw]
        try:
            self.tello_controller.send_rc_control(lr, fb, ud, yaw)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # DEMO orbit
    # ------------------------------------------------------------------

    def _toggle_demo(self):
        if not self.tello_controller.connected:
            self._log("DEMO: drone not connected")
            return

        if not self.demo_active:
            height = self._tello_get(self.tello_controller.get_height)
            if height < 20:
                self._log("DEMO: taking off first")
                try:
                    self.tello_controller.takeoff()
                except Exception as e:
                    self._log(f"DEMO: takeoff failed: {e}")
                    return

            self.demo_active = True
            self.demo_btn.setText("Stop DEMO")
            self.demo_start_time = time.time()
            self.demo_last_time = self.demo_start_time
            self.demo_cumulative_turn = 0.0
            self.demo_prev_heading = None

            heading = (self.filtered_heading if self.filtered_heading is not None
                       else self.current_heading)
            self.demo_start_heading = heading if heading is not None else 0

            if not self.demo_timer.isActive():
                self.demo_timer.start(50)

            self._log(f"DEMO: orbit started  heading={self.demo_start_heading:.0f}"
                      f"  yaw_rate={self.DEMO_YAW_RATE}/s  fwd={self.DEMO_FORWARD_RC}")
        else:
            self._stop_demo()
            if self.tello_controller.connected:
                try:
                    self.tello_controller.land()
                    turns = abs(self.demo_cumulative_turn) / 360.0
                    self._log(f"DEMO: stopped and landed ({turns:.1f} circles)")
                except Exception as e:
                    self._log(f"DEMO: landing failed: {e}")

    def _stop_demo(self):
        self.demo_active = False
        self.demo_btn.setText("DEMO orbit")
        if self.demo_timer.isActive():
            self.demo_timer.stop()
        self.demo_last_time = None
        try:
            self.tello_controller.send_rc_control(0, 0, 0, 0)
        except Exception:
            pass

    def _update_demo(self):
        """Compass-driven orbit: constant forward + heading tracking = circle.

        R = v / omega gives the orbit radius.
        """
        if not self.demo_active or not self.tello_controller.connected:
            return

        height = self._tello_get(self.tello_controller.get_height)
        heading = (self.filtered_heading if self.filtered_heading is not None
                   else self.current_heading)
        if heading is None:
            heading = self.demo_start_heading

        now = time.time()
        dt = max(min(now - (self.demo_last_time or now), 0.2), 0.01)
        self.demo_last_time = now
        t_rel = now - self.demo_start_time

        # Altitude hold
        h_err = self.DEMO_TARGET_HEIGHT - height
        ud = int(max(min(self.DEMO_K_ALT * h_err, self.DEMO_MAX_ALT_CMD),
                      -self.DEMO_MAX_ALT_CMD))

        if t_rel < self.DEMO_STABILIZE_TIME:
            lr, fb, yaw = 0, 0, 0
        else:
            orbit_t = t_rel - self.DEMO_STABILIZE_TIME
            target = (self.demo_start_heading + self.DEMO_YAW_RATE * orbit_t) % 360.0

            err = wrap_angle_error(target, heading)
            err = max(min(err, self.DEMO_MAX_HEADING_ERR), -self.DEMO_MAX_HEADING_ERR)

            if abs(err) < 4.0:
                err = 0.0

            yaw = int(max(min(self.DEMO_K_YAW * err, self.DEMO_MAX_YAW_CMD),
                           -self.DEMO_MAX_YAW_CMD))

            fwd_scale = max(0.65, 1.0 - abs(err) / 90.0)
            fb = int(self.DEMO_FORWARD_RC * fwd_scale)
            lr = 0

        # Cumulative turn counter
        if self.demo_prev_heading is not None and heading is not None:
            self.demo_cumulative_turn += wrap_angle_error(heading, self.demo_prev_heading)
        self.demo_prev_heading = heading

        # EMA smoothing on all RC channels
        s = self.DEMO_RC_SMOOTH
        prev = self.current_rc_values
        lr  = int(prev[0] * s + lr  * (1 - s))
        fb  = int(prev[1] * s + fb  * (1 - s))
        ud  = int(prev[2] * s + ud  * (1 - s))
        yaw = int(prev[3] * s + yaw * (1 - s))

        self.current_rc_values = [lr, fb, ud, yaw]
        try:
            self.tello_controller.send_rc_control(lr, fb, ud, yaw)
        except Exception as e:
            self._log(f"DEMO: RC error: {e}")

    # ------------------------------------------------------------------
    # Bluetooth (ESP32 + GY-80 9-DOF IMU)
    # ------------------------------------------------------------------

    def _init_bluetooth(self):
        try:
            self.bluetooth_handler = BluetoothHandler(device_name_pattern="XIAO")
            self.bluetooth_handler.mag_received.connect(self._on_mag)
            self.bluetooth_handler.accel_received.connect(self._on_accel)
            self.bluetooth_handler.gyro_received.connect(self._on_gyro)
            self.bluetooth_handler.heading_received.connect(self._on_heading)
            self.bluetooth_handler.connection_status.connect(self._on_bt_status)
            self.bluetooth_handler.start()
            self._log("BLE: searching for XIAO ESP32-C6...")
        except Exception as e:
            logging.error(f"Bluetooth init error: {e}")
            self._log(f"BLE init failed: {e}")

    def _on_mag(self, mx, my, mz):
        self.raw_mag = (mx, my, mz)

    def _on_accel(self, ax, ay, az):
        self.raw_accel = (ax, ay, az)

    def _on_gyro(self, gx, gy, gz):
        self.raw_gyro = (gx, gy, gz)

    def _on_heading(self, heading):
        self.current_heading = heading

    def _on_bt_status(self, connected, message):
        if connected:
            self.bt_status_label.setText("ESP32-C6: Connected")
            self.bt_status_label.setStyleSheet("font-size: 12px; color: green;")
        else:
            self.bt_status_label.setText("ESP32-C6: Disconnected")
            self.bt_status_label.setStyleSheet("font-size: 12px; color: red;")
        self._log(f"BLE: {message}")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(self, message):
        ts = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{ts}] {message}")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        try:
            self._stop_hover()
            self._stop_demo()

            if self.bluetooth_handler:
                try:
                    self.bluetooth_handler.stop()
                except Exception:
                    pass
            if self.video_thread:
                try:
                    self.video_thread.stop()
                except Exception:
                    pass
            if self.tello_controller.connected:
                try:
                    self._disconnect()
                except Exception:
                    pass
            if self.debug_log_file:
                try:
                    self.debug_log_file.close()
                except Exception:
                    pass
        except Exception as e:
            logging.error(f"closeEvent error: {e}")
        finally:
            event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
