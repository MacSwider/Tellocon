"""
Main application window for Tellocon.

Provides GUI for drone connection, takeoff/land, stabilised hover
(heading-hold via BMM150 magnetometer) and autonomous orbit demo.
"""

import math
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

        # Magnetometer / heading state
        self.raw_mag = None
        self.current_heading = None
        self.filtered_heading = None

        # -- Heading-hold hover (active after takeoff) --
        self.hover_active = False
        self.hover_heading = None
        self.HOVER_K_YAW = 0.5
        self.HOVER_K_ALT = 0.5
        self.HOVER_TARGET_HEIGHT = 80
        self.HOVER_MAX_CMD = 25
        self.HOVER_DEADBAND = 4.0

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
        self.debug_log_header_written = False

        # Timers
        self.hover_timer = QTimer()
        self.hover_timer.timeout.connect(self._update_hover)

        self.demo_timer = QTimer()
        self.demo_timer.timeout.connect(self._update_demo)

        self._init_ui()
        self._init_bluetooth()
        self._init_debug_log()

    # ------------------------------------------------------------------
    # Debug CSV log
    # ------------------------------------------------------------------

    def _init_debug_log(self):
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"demo_mag_log_{ts}.csv"
            self.debug_log_file = open(filename, "w", encoding="utf-8")
            self.debug_log_file.write(
                "timestamp,demo_active,"
                "pitch,roll,yaw_tello,"
                "mx,my,mz,heading,"
                "height,tof,speed_z,"
                "rc_left_right,rc_forward_back,rc_up_down,rc_yaw\n")
            self.debug_log_file.flush()
            self.debug_log_header_written = True
            self._log(f"Debug log: {filename}")
        except Exception as e:
            self._log(f"Debug log init failed: {e}")

    def _write_debug_row(self, **kw):
        if not self.debug_log_file:
            return
        try:
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.debug_log_file.write(
                f"{ts},{int(self.demo_active)},"
                f"{kw.get('pitch','')},{kw.get('roll','')},{kw.get('yaw_tello','')},"
                f"{kw.get('mx','')},{kw.get('my','')},{kw.get('mz','')},{kw.get('heading','')},"
                f"{kw.get('height','')},{kw.get('tof','')},{kw.get('speed_z','')},"
                f"{kw.get('rc_lr','')},{kw.get('rc_fb','')},{kw.get('rc_ud','')},{kw.get('rc_yaw','')}\n")
            self.debug_log_file.flush()
        except Exception:
            pass

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
        self._log("3. ESP32-C6 magnetometer connects automatically via BLE")

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
            "ESP32-C6 + BMM150 magnetometer via BLE<br/>"
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

    def _on_frame(self, frame):
        self.camera_widget.set_frame(frame)

        battery = self._tello_get(self.tello_controller.get_battery)
        height = self._tello_get(self.tello_controller.get_height)
        tof = self._tello_get(self.tello_controller.get_distance_tof)
        temp = self._tello_get(self.tello_controller.get_temp)
        speed_z = self._tello_get(self.tello_controller.get_speed_z)
        pitch = self._tello_get(self.tello_controller.get_pitch)
        roll = self._tello_get(self.tello_controller.get_roll)
        yaw_tello = self._tello_get(self.tello_controller.get_yaw_angle)

        lr, fb, ud, yaw = self.current_rc_values

        # -- Heading filter (BMM150 + tilt compensation from Tello IMU) --
        if self.raw_mag is not None:
            try:
                if abs(pitch) <= 25 and abs(roll) <= 25:
                    h = tilt_compensated_heading(
                        self.raw_mag[0], self.raw_mag[1], self.raw_mag[2],
                        pitch, roll)
                    h = int(round(h)) % 360
                    self.current_heading = h
                    if self.filtered_heading is None:
                        self.filtered_heading = float(h)
                    else:
                        alpha = 0.12
                        diff = wrap_angle_error(h, self.filtered_heading)
                        step = max(min(alpha * diff, 3.0), -3.0)
                        self.filtered_heading = (self.filtered_heading + step) % 360
            except Exception:
                pass

        # -- Debug CSV (written during demo) --
        if self.demo_active:
            mx, my, mz = self.raw_mag if self.raw_mag else ("", "", "")
            self._write_debug_row(
                pitch=pitch, roll=roll, yaw_tello=yaw_tello,
                mx=mx, my=my, mz=mz,
                heading=self.current_heading if self.current_heading is not None else "",
                height=height, tof=tof, speed_z=speed_z,
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
        self.tello_controller.takeoff()
        self._log("Takeoff")

        heading = (self.filtered_heading if self.filtered_heading is not None
                   else self.current_heading)
        self.hover_heading = heading
        self.hover_active = True
        if not self.hover_timer.isActive():
            self.hover_timer.start(50)
        self._log(f"Heading-hold hover active (target={self.hover_heading})")

    def _land(self):
        if not self.tello_controller.connected:
            return
        self._stop_hover()
        self._stop_demo()
        self.tello_controller.land()
        self._log("Landed")

    def _stop_hover(self):
        self.hover_active = False
        if self.hover_timer.isActive():
            self.hover_timer.stop()
        try:
            self.tello_controller.send_rc_control(0, 0, 0, 0)
        except Exception:
            pass

    def _update_hover(self):
        """Heading-hold + altitude-hold while hovering."""
        if not self.hover_active or not self.tello_controller.connected:
            return
        if self.demo_active:
            return

        height = self._tello_get(self.tello_controller.get_height)
        heading = (self.filtered_heading if self.filtered_heading is not None
                   else self.current_heading)

        # Altitude hold
        h_err = self.HOVER_TARGET_HEIGHT - height
        ud = int(max(min(self.HOVER_K_ALT * h_err, self.HOVER_MAX_CMD),
                      -self.HOVER_MAX_CMD))

        # Yaw hold
        yaw = 0
        if heading is not None and self.hover_heading is not None:
            err = wrap_angle_error(self.hover_heading, heading)
            if abs(err) >= self.HOVER_DEADBAND:
                yaw = int(max(min(self.HOVER_K_YAW * err, self.HOVER_MAX_CMD),
                               -self.HOVER_MAX_CMD))

        self.current_rc_values = [0, 0, ud, yaw]
        try:
            self.tello_controller.send_rc_control(0, 0, ud, yaw)
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
    # Bluetooth (ESP32 + BMM150)
    # ------------------------------------------------------------------

    def _init_bluetooth(self):
        try:
            self.bluetooth_handler = BluetoothHandler(device_name_pattern="XIAO")
            self.bluetooth_handler.mag_received.connect(self._on_mag)
            self.bluetooth_handler.heading_received.connect(self._on_heading)
            self.bluetooth_handler.connection_status.connect(self._on_bt_status)
            self.bluetooth_handler.start()
            self._log("BLE: searching for XIAO ESP32-C6...")
        except Exception as e:
            logging.error(f"Bluetooth init error: {e}")
            self._log(f"BLE init failed: {e}")

    def _on_mag(self, mx, my, mz):
        self.raw_mag = (mx, my, mz)

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
