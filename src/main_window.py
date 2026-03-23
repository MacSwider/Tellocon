import math
import sys
import time
import logging
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QFrame, QTextEdit,
                             QDialog, QLineEdit, QMessageBox)
from PyQt5.QtCore import QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont

from src.tello_controller import TelloController
from src.gamepad_handler import GamepadHandler
from src.camera_widget import CameraWidget
from src.video_thread import VideoThread
from src.bluetooth_handler import BluetoothHandler

# Configure logging
logging.basicConfig(level=logging.WARNING)


def tilt_compensated_heading(mx, my, mz, pitch_deg, roll_deg):
    """
    Oblicza azymut (0-359) z wektora magnetycznego (mx, my, mz) z kompensacją przechylenia.
    pitch_deg, roll_deg: kąty z Tellera w stopniach (pitch = nos w górę/dół, roll = skrzydło).
    Formuła NXP: rzut wektora B z układu pochylonego na płaszczyznę poziomą, potem atan2.
    """
    pitch_deg = pitch_deg if pitch_deg is not None else 0
    roll_deg = roll_deg if roll_deg is not None else 0
    theta = math.radians(pitch_deg)
    phi = math.radians(roll_deg)
    # Poziome składowe wektora B (roll=φ wokół X, pitch=θ wokół Y)
    x_level = (
        mx * math.cos(theta)
        + my * math.sin(theta) * math.sin(phi)
        + mz * math.sin(theta) * math.cos(phi)
    )
    y_level = my * math.cos(phi) - mz * math.sin(phi)
    h = math.degrees(math.atan2(y_level, x_level))
    if h < 0:
        h += 360.0
    return h


class FlipThread(QThread):
    """Thread to execute flip maneuvers without blocking the UI"""
    finished = pyqtSignal(str)
    
    def __init__(self, tello_controller, direction):
        super().__init__()
        self.tello_controller = tello_controller
        self.direction = direction
    
    def run(self):
        try:
            if self.direction == 'left':
                success, message = self.tello_controller.flip_left()
                if success:
                    self.finished.emit("✓ Performed barrel roll left")
                else:
                    self.finished.emit(f"✗ {message}")
            elif self.direction == 'right':
                success, message = self.tello_controller.flip_right()
                if success:
                    self.finished.emit("✓ Performed barrel roll right")
                else:
                    self.finished.emit(f"✗ {message}")
        except Exception as e:
            self.finished.emit(f"✗ Flip error: {str(e)}")


class WiFiConfigThread(QThread):
    """Thread to configure WiFi without blocking the UI"""
    finished = pyqtSignal(bool, str)
    
    def __init__(self, tello_controller, ssid, password):
        super().__init__()
        self.tello_controller = tello_controller
        self.ssid = ssid
        self.password = password
    
    def run(self):
        try:
            success, message = self.tello_controller.configure_wifi(self.ssid, self.password)
            self.finished.emit(success, message)
        except Exception as e:
            self.finished.emit(False, f"WiFi configuration error: {str(e)}")


class WiFiConfigDialog(QDialog):
    """Dialog for WiFi configuration"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Tello WiFi")
        self.setModal(True)
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        info_label = QLabel(
            "<b>Configure Tello to connect to your computer's hotspot</b><br/><br/>"
            "<b>Your Setup:</b><br/>"
            "✓ LAN/Ethernet connected (for internet)<br/>"
            "✓ WiFi hotspot active (broadcasting)<br/><br/>"
            "<b>⚠️ IMPORTANT STEPS:</b><br/>"
            "1. Keep your hotspot ACTIVE (SSID: MurderDroneTest, 2.4GHz)<br/>"
            "2. Connect PC to TELLO-XXXX hotspot (this may pause your hotspot)<br/>"
            "3. Enter hotspot credentials below<br/>"
            "4. Click Configure - command will be sent to drone<br/>"
            "5. Drone reboots and tries to connect to your hotspot<br/>"
            "6. Re-enable your hotspot if it was paused<br/>"
            "7. Wait 60-90 seconds - check hotspot connected devices<br/><br/>"
            "<b>Note:</b> If hotspot pauses when connecting to TELLO-XXXX,<br/>"
            "you may need a USB WiFi dongle for TELLO-XXXX connection."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("padding: 10px; background-color: #e3f2fd; border: 1px solid #2196F3;")
        layout.addWidget(info_label)
        
        layout.addSpacing(10)
        
        ssid_label = QLabel("Hotspot SSID:")
        layout.addWidget(ssid_label)
        self.ssid_input = QLineEdit()
        self.ssid_input.setText("MurderDroneTest")
        self.ssid_input.setPlaceholderText("Enter your hotspot SSID")
        layout.addWidget(self.ssid_input)
        
        password_label = QLabel("Hotspot Password:")
        layout.addWidget(password_label)
        self.password_input = QLineEdit()
        self.password_input.setText("54fatTTT")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter your hotspot password")
        layout.addWidget(self.password_input)
        
        layout.addSpacing(10)
        
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("Configure WiFi")
        self.ok_button.setStyleSheet("font-size: 14px; padding: 8px; background-color: #4CAF50; color: white;")
        self.ok_button.clicked.connect(self.accept)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet("font-size: 14px; padding: 8px;")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def get_credentials(self):
        return self.ssid_input.text().strip(), self.password_input.text().strip()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.tello_controller = TelloController()
        self.gamepad = GamepadHandler()
        
        self.video_thread = None
        self.current_throttle = 0
        self.current_rc_values = [0, 0, 0, 0]
        self.flip_thread = None
        self.wifi_config_thread = None
        self.bluetooth_handler = None
        self.current_heading = None
        self.filtered_heading = None
        self.raw_mag = None  # (mx, my, mz) from ESP32 for tilt-compensated heading
        self.demo_active = False
        self.demo_start_heading = None
        self.demo_start_time = None
        self.demo_last_time = None

        # ── DEMO orbit parameters (tune these for your environment) ──
        self.DEMO_YAW_RATE = 12.0           # deg/s – heading change rate (360/12 = 30s per circle)
        self.DEMO_FORWARD_RC = 30           # forward RC value (≈ forward speed; higher = wider circle)
        self.DEMO_TARGET_HEIGHT = 80        # cm – lower is more stable for Tello
        self.DEMO_STABILIZE_TIME = 3.0      # seconds to hover before orbit starts
        self.DEMO_K_YAW = 0.6              # P-gain: heading error → yaw command
        self.DEMO_K_ALT = 0.5              # P-gain: altitude error → up/down
        self.DEMO_MAX_YAW_CMD = 35         # max abs yaw RC command
        self.DEMO_MAX_ALT_CMD = 30         # max abs altitude RC command
        self.DEMO_MAX_HEADING_ERR = 45.0   # clamp heading error to prevent violent corrections
        self.DEMO_RC_SMOOTH = 0.3          # RC output EMA smoothing (0 = none, higher = smoother)
        self.demo_cumulative_turn = 0.0    # total degrees turned (for circle counting)
        self.demo_prev_heading = None

        self.debug_log_file = None
        self.debug_log_header_written = False

        self.demo_timer = QTimer()
        self.demo_timer.timeout.connect(self.update_demo)

        self.init_ui()
        self.init_bluetooth()
        self.init_gamepad()

        self._init_debug_log()

    def _init_debug_log(self):
        """Initialize CSV log file for DEMO + magnetometer debug."""
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"demo_mag_log_{ts}.csv"
            self.debug_log_file = open(filename, "w", encoding="utf-8")
            header = (
                "timestamp,demo_active,"
                "pitch,roll,yaw_tello,"
                "mx,my,mz,heading,"
                "height,tof,speed_z,"
                "rc_left_right,rc_forward_back,rc_up_down,rc_yaw\n"
            )
            self.debug_log_file.write(header)
            self.debug_log_file.flush()
            self.debug_log_header_written = True
            self.log(f"Debug log file created: {filename}")
        except Exception as e:
            self.log(f"Debug log init failed: {e}")

    def _write_debug_log_row(
        self,
        pitch,
        roll,
        yaw_tello,
        mx,
        my,
        mz,
        heading,
        height,
        tof,
        speed_z,
        rc_left_right,
        rc_forward_back,
        rc_up_down,
        rc_yaw,
    ):
        """Write one line of debug data to CSV (only used when DEMO is active)."""
        if not self.debug_log_file:
            return
        try:
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            line = (
                f"{ts},{int(self.demo_active)},"
                f"{pitch},{roll},{yaw_tello},"
                f"{mx},{my},{mz},{heading},"
                f"{height},{tof},{speed_z},"
                f"{rc_left_right},{rc_forward_back},{rc_up_down},{rc_yaw}\n"
            )
            self.debug_log_file.write(line)
            # lekkie flush, żeby w razie kraksy mieć dane
            self.debug_log_file.flush()
        except Exception:
            pass
    
    def init_gamepad(self):
        """Initialize gamepad handler after UI is ready"""
        try:
            # Delay gamepad initialization to avoid conflicts with PyQt5
            QTimer.singleShot(500, self._init_gamepad_delayed)
        except Exception as e:
            logging.error(f"Error scheduling gamepad init: {e}")
    
    def _init_gamepad_delayed(self):
        """Delayed gamepad initialization"""
        try:
            self.gamepad = GamepadHandler()
            self.gamepad_timer = QTimer()
            self.gamepad_timer.timeout.connect(self.update_gamepad_input)
            self.gamepad_timer.start(50)
            if self.gamepad.is_connected():
                self.log("Gamepad controller connected")
            else:
                self.log("No gamepad controller detected")
        except Exception as e:
            logging.error(f"Error initializing gamepad: {e}")
            self.log(f"Warning: Gamepad initialization failed: {e}")
            # Create a dummy gamepad handler to prevent crashes
            self.gamepad = type('DummyGamepad', (), {'is_connected': lambda: False, 'get_inputs': lambda: None})()

    def init_ui(self):
        self.setWindowTitle("Tellocon - version 0.9")
        self.setGeometry(100, 100, 1200, 800)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout()

        control_panel = self.create_control_panel()
        main_layout.addWidget(control_panel, 1)

        right_panel = QVBoxLayout()
        self.camera_widget = CameraWidget()
        right_panel.addWidget(self.camera_widget)

        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(150)
        self.log_text.setReadOnly(True)
        right_panel.addWidget(self.log_text)

        main_layout.addLayout(right_panel, 2)
        main_widget.setLayout(main_layout)

        self.log("Tellocon application ready")
        self.log("1. Connect Dualshock 4 controller to PC")
        self.log("2. Connect PC to drone's WiFi (TELLO-XXXX)")
        self.log("3. Click 'Connect with Drone'")
        self.log("4. ESP32-C6 Bluetooth will connect automatically")

    def create_control_panel(self):
        panel = QFrame()
        panel.setMaximumWidth(300)
        panel.setStyleSheet("background-color: #f0f0f0; padding: 10px;")
        layout = QVBoxLayout()

        title = QLabel("Drone Control")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        layout.addSpacing(20)

        self.connect_btn = QPushButton("Connect with Drone")
        self.connect_btn.clicked.connect(self.toggle_connection)
        self.connect_btn.setStyleSheet("font-size: 14px; padding: 10px; background-color: #4CAF50; color: white;")
        layout.addWidget(self.connect_btn)

        self.wifi_config_btn = QPushButton("Configure WiFi to Hotspot")
        self.wifi_config_btn.clicked.connect(self.configure_wifi)
        self.wifi_config_btn.setStyleSheet("font-size: 14px; padding: 10px; background-color: #FF9800; color: white;")
        layout.addWidget(self.wifi_config_btn)

        layout.addSpacing(10)

        self.takeoff_btn = QPushButton("Takeoff")
        self.takeoff_btn.clicked.connect(self.takeoff)
        self.takeoff_btn.setEnabled(False)
        self.takeoff_btn.setStyleSheet("font-size: 14px; padding: 10px; background-color: #2196F3; color: white;")
        layout.addWidget(self.takeoff_btn)

        self.land_btn = QPushButton("Land")
        self.land_btn.clicked.connect(self.land)
        self.land_btn.setEnabled(False)
        self.land_btn.setStyleSheet("font-size: 14px; padding: 10px; background-color: #f44336; color: white;")
        layout.addWidget(self.land_btn)

        # DEMO button – autonomous orbit using compass
        self.demo_btn = QPushButton("DEMO")
        self.demo_btn.clicked.connect(self.toggle_demo)
        self.demo_btn.setEnabled(False)
        self.demo_btn.setStyleSheet("font-size: 14px; padding: 10px; background-color: #9C27B0; color: white;")
        layout.addWidget(self.demo_btn)

        layout.addSpacing(30)

        status_title = QLabel("Status:")
        status_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(status_title)

        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("font-size: 12px; color: red;")
        layout.addWidget(self.status_label)
        
        self.bluetooth_status_label = QLabel("ESP32-C6: Disconnected")
        self.bluetooth_status_label.setStyleSheet("font-size: 12px; color: red;")
        layout.addWidget(self.bluetooth_status_label)
        layout.addSpacing(20)

        instructions = QLabel(
            "<b>Controls:</b><br/>"
            "• Left stick: Ascend/Descend, Rotate<br/>"
            "• Right stick: Forward/Backward, Left/Right<br/>"
            "• R1: Takeoff<br/>"
            "• L1: Landing<br/>"
            "• R2: Barrel Roll Right <br/>"
            "• L2: Barrel Roll Left <br/>"
        )
        instructions.setStyleSheet("font-size: 11px; padding: 10px; background-color: white; border: 1px solid #ccc;")
        layout.addWidget(instructions)

        layout.addStretch()

        panel.setLayout(layout)
        return panel

    def toggle_connection(self):
        if not self.tello_controller.connected:
            try:
                success, message = self.tello_controller.connect()
                self.log(message)
            except Exception as e:
                self.log(f"❌ Connection failed: {str(e)}")
                self.status_label.setText("Connection Error")
                self.status_label.setStyleSheet("font-size: 12px; color: red;")
                return

            if success:
                self.connect_btn.setText("Disconnect Drone")
                self.takeoff_btn.setEnabled(True)
                self.land_btn.setEnabled(True)
                self.demo_btn.setEnabled(True)
                self.status_label.setText("Connected")
                self.status_label.setStyleSheet("font-size: 12px; color: green;")
                self.start_video_stream()
            else:
                self.status_label.setText("Connection Error")
                self.status_label.setStyleSheet("font-size: 12px; color: red;")
        else:
            self.disconnect_drone()

    def disconnect_drone(self):
        if self.video_thread:
            self.video_thread.stop()
            self.video_thread = None

        self.tello_controller.disconnect()
        
        self.connect_btn.setText("Connect with Drone")
        self.takeoff_btn.setEnabled(False)
        self.land_btn.setEnabled(False)
        self.demo_btn.setEnabled(False)
        self.demo_btn.setText("DEMO")
        self.demo_active = False
        if self.demo_timer.isActive():
            self.demo_timer.stop()
        self.status_label.setText("Disconnected")
        self.status_label.setStyleSheet("font-size: 12px; color: red;")

        if hasattr(self.camera_widget, 'clear'):
            self.camera_widget.clear()
        
        self.log("Disconnected from drone")

    def start_video_stream(self):
        if self.video_thread is None and self.tello_controller.connected:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(1000, self._start_video_thread)

    def _start_video_thread(self):
        if self.tello_controller.connected:
            try:
                self.video_thread = VideoThread(self.tello_controller.tello)
                
                # Use QueuedConnection to ensure UI updates happen in main thread
                from PyQt5.QtCore import Qt
                self.video_thread.frame_signal.connect(self.update_frame, Qt.QueuedConnection)
                
                self.video_thread.start()
                self.log("Video stream started")
            except Exception as e:
                logging.error(f"Error starting video stream: {str(e)}")
                self.log(f"Error starting video stream: {str(e)}")

    def update_frame(self, frame):
        self.camera_widget.set_frame(frame)

        try:
            battery = self.tello_controller.get_battery()
        except Exception:
            battery = 0
        
        try:
            height = self.tello_controller.get_height()
        except Exception:
            height = 0
        
        try:
            tof_distance = self.tello_controller.get_distance_tof()
        except Exception:
            tof_distance = 0
        
        try:
            temp = self.tello_controller.get_temp()
        except Exception:
            temp = 0
        
        try:
            speed_z = self.tello_controller.get_speed_z()
        except Exception:
            speed_z = 0
        
        try:
            pitch = self.tello_controller.get_pitch()
        except Exception:
            pitch = 0
        
        try:
            roll = self.tello_controller.get_roll()
        except Exception:
            roll = 0
        
        try:
            yaw_angle = self.tello_controller.get_yaw_angle()
        except Exception:
            yaw_angle = 0
        
        try:
            left_right, forward_back, up_down, yaw = self.current_rc_values
        except Exception:
            left_right, forward_back, up_down, yaw = [0, 0, 0, 0]

        # Tilt-compensated heading from magnetometer vector + Tello pitch/roll
        if self.raw_mag is not None:
            try:
                if abs(pitch) <= 25 and abs(roll) <= 25:
                    h = tilt_compensated_heading(
                        self.raw_mag[0], self.raw_mag[1], self.raw_mag[2],
                        pitch, roll
                    )
                    h = int(round(h)) % 360
                    self.current_heading = h
                    if self.filtered_heading is None:
                        self.filtered_heading = float(h)
                    else:
                        alpha = 0.12
                        diff = ((h - self.filtered_heading + 540) % 360) - 180
                        step = alpha * diff
                        max_step = 3.0
                        step = max(min(step, max_step), -max_step)
                        self.filtered_heading = (self.filtered_heading + step) % 360
            except Exception:
                pass

        # Debug log: tylko podczas DEMO, żeby zobaczyć co robi kompas i sterowanie
        if self.demo_active:
            if self.raw_mag is not None:
                mx, my, mz = self.raw_mag
            else:
                mx = my = mz = ""
            self._write_debug_log_row(
                pitch=pitch,
                roll=roll,
                yaw_tello=yaw_angle,
                mx=mx,
                my=my,
                mz=mz,
                heading=self.current_heading if self.current_heading is not None else "",
                height=height,
                tof=tof_distance,
                speed_z=speed_z,
                rc_left_right=left_right,
                rc_forward_back=forward_back,
                rc_up_down=up_down,
                rc_yaw=yaw,
            )

        self.camera_widget.set_ui_info({
            'battery': battery,
            'height': height,
            'tof': tof_distance,
            'temp': temp,
            'throttle': up_down,
            'speed': speed_z,
            'pitch': pitch,
            'roll': roll,
            'yaw': yaw_angle,
            'rc_pitch': forward_back,  # RC control forward/back (pitch)
            'rc_roll': left_right,     # RC control left/right (roll)
            'rc_yaw': yaw,             # RC control yaw
            'status': 'Active',
            'controller': self.gamepad.is_connected() if self.gamepad else False,
            'flying_mode': 'autopilot' if self.demo_active else 'manual',
            'heading': int(round(self.filtered_heading)) % 360 if self.filtered_heading is not None else self.current_heading
        })

    def toggle_demo(self):
        """Toggle DEMO mode: autonomous orbit using compass heading."""
        if not self.tello_controller.connected:
            self.log("DEMO: Drone not connected")
            return

        if not self.demo_active:
            # ── Start DEMO ──
            try:
                height = self.tello_controller.get_height()
            except Exception:
                height = 0

            if height < 20:
                self.log("DEMO: Takeoff")
                try:
                    self.tello_controller.takeoff()
                except Exception as e:
                    self.log(f"DEMO: Takeoff failed: {e}")
                    return

            self.demo_active = True
            self.demo_btn.setText("Stop DEMO")
            self.demo_start_time = time.time()
            self.demo_last_time = self.demo_start_time
            self.demo_cumulative_turn = 0.0
            self.demo_prev_heading = None

            heading = self.filtered_heading if self.filtered_heading is not None else self.current_heading
            self.demo_start_heading = heading if heading is not None else 0

            if not self.demo_timer.isActive():
                self.demo_timer.start(50)

            self.log(f"DEMO: Orbit started  heading={self.demo_start_heading:.0f}°  "
                     f"yaw_rate={self.DEMO_YAW_RATE}°/s  fwd={self.DEMO_FORWARD_RC}")
        else:
            # ── Stop DEMO and land ──
            self.demo_active = False
            self.demo_btn.setText("DEMO")
            if self.demo_timer.isActive():
                self.demo_timer.stop()
            self.demo_last_time = None
            try:
                self.tello_controller.send_rc_control(0, 0, 0, 0)
            except Exception:
                pass
            turns = abs(self.demo_cumulative_turn) / 360.0
            if self.tello_controller.connected:
                try:
                    self.tello_controller.land()
                    self.log(f"DEMO: Stopped and landed  ({turns:.1f} circles)")
                except Exception as e:
                    self.log(f"DEMO: Landing failed: {e}")

    def update_demo(self):
        """Compass-driven orbit: constant forward + heading tracking = circle.

        The drone flies forward at constant speed while turning at a steady
        yaw rate controlled by the compass heading.  R = v / ω  gives the
        orbit radius.  No XY odometry needed.
        """
        if not self.demo_active or not self.tello_controller.connected:
            return

        try:
            height = self.tello_controller.get_height()
        except Exception:
            height = 0

        heading = self.filtered_heading if self.filtered_heading is not None else self.current_heading
        if heading is None:
            heading = self.demo_start_heading

        now = time.time()
        if self.demo_last_time is None:
            dt = 0.05
        else:
            dt = max(min(now - self.demo_last_time, 0.2), 0.01)
        self.demo_last_time = now

        t_rel = now - self.demo_start_time

        # ── Altitude hold ──
        h_err = self.DEMO_TARGET_HEIGHT - height
        up_down = int(max(min(self.DEMO_K_ALT * h_err, self.DEMO_MAX_ALT_CMD),
                         -self.DEMO_MAX_ALT_CMD))

        # ── Phase 1: Stabilise at target height before orbiting ──
        if t_rel < self.DEMO_STABILIZE_TIME:
            left_right, forward_back, yaw = 0, 0, 0
        else:
            # ── Phase 2: Orbit ──
            orbit_t = t_rel - self.DEMO_STABILIZE_TIME

            target_heading = (self.demo_start_heading
                              + self.DEMO_YAW_RATE * orbit_t) % 360.0

            err = target_heading - heading
            if err > 180:
                err -= 360
            elif err < -180:
                err += 360

            err = max(min(err, self.DEMO_MAX_HEADING_ERR),
                      -self.DEMO_MAX_HEADING_ERR)

            deadband = 4.0
            if abs(err) < deadband:
                err = 0.0

            yaw_raw = self.DEMO_K_YAW * err
            yaw = int(max(min(yaw_raw, self.DEMO_MAX_YAW_CMD),
                          -self.DEMO_MAX_YAW_CMD))

            fwd_scale = max(0.65, 1.0 - abs(err) / 90.0)
            forward_back = int(self.DEMO_FORWARD_RC * fwd_scale)
            left_right = 0

        # ── Track cumulative turn for circle counting ──
        if self.demo_prev_heading is not None and heading is not None:
            dh = ((heading - self.demo_prev_heading + 540) % 360) - 180
            self.demo_cumulative_turn += dh
        self.demo_prev_heading = heading

        # ── Smooth RC outputs (EMA) ──
        s = self.DEMO_RC_SMOOTH
        prev = self.current_rc_values
        left_right   = int(prev[0] * s + left_right   * (1 - s))
        forward_back = int(prev[1] * s + forward_back * (1 - s))
        up_down      = int(prev[2] * s + up_down      * (1 - s))
        yaw          = int(prev[3] * s + yaw          * (1 - s))

        self.current_rc_values = [left_right, forward_back, up_down, yaw]
        try:
            self.tello_controller.send_rc_control(left_right, forward_back,
                                                  up_down, yaw)
        except Exception as e:
            self.log(f"DEMO: RC error: {e}")

    def takeoff(self):
        if self.tello_controller.connected:
            self.tello_controller.takeoff()
            self.log("Drone took off")

    def land(self):
        if self.tello_controller.connected:
            self.tello_controller.land()
            self.log("Drone landed")

    def execute_flip(self, direction):
        """Execute a flip maneuver in a separate thread"""
        if not self.tello_controller.connected:
            return
        
        # Don't start a new flip if one is already in progress
        if self.flip_thread and self.flip_thread.isRunning():
            return
        
        self.flip_thread = FlipThread(self.tello_controller, direction)
        self.flip_thread.finished.connect(self.on_flip_completed)
        self.flip_thread.start()
    
    def on_flip_completed(self, message):
        """Called when flip maneuver completes"""
        self.log(message)

    def configure_wifi(self):
        """Open WiFi configuration dialog and configure the drone"""
        # Show instructions for the setup
        reply = QMessageBox.information(
            self, 
            "WiFi Configuration Setup",
            "Your Setup: LAN connected + WiFi hotspot active\n\n"
            "IMPORTANT STEPS:\n"
            "1. Ensure your hotspot is ACTIVE (MurderDroneTest, 2.4GHz)\n"
            "2. Connect PC to TELLO-XXXX hotspot\n"
            "   (Note: This may pause your hotspot temporarily)\n"
            "3. Enter hotspot credentials in the dialog\n"
            "4. After configuration, re-enable hotspot if needed\n"
            "5. Wait 60-90 seconds for drone to connect\n\n"
            "Are you ready to proceed?\n"
            "(Make sure you're connected to TELLO-XXXX)",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Ok
        )
        
        if reply != QMessageBox.Ok:
            self.log("WiFi configuration cancelled")
            return
        
        # Disconnect from drone if connected (we need to connect to TELLO-XXXX)
        was_connected = self.tello_controller.connected
        if was_connected:
            self.disconnect_drone()
            self.log("Disconnected from drone. Make sure you're connected to TELLO-XXXX hotspot.")
            time.sleep(1)
        
        dialog = WiFiConfigDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            ssid, password = dialog.get_credentials()
            
            if not ssid or not password:
                QMessageBox.warning(self, "Invalid Input", "SSID and password cannot be empty!")
                return
            
            self.log(f"Starting WiFi configuration for SSID: {ssid}")
            self.wifi_config_btn.setEnabled(False)
            self.wifi_config_btn.setText("Configuring...")
            
            # Create and start WiFi configuration thread
            self.wifi_config_thread = WiFiConfigThread(self.tello_controller, ssid, password)
            self.wifi_config_thread.finished.connect(self.on_wifi_config_completed)
            self.wifi_config_thread.start()

    def on_wifi_config_completed(self, success, message):
        """Called when WiFi configuration completes"""
        self.wifi_config_btn.setEnabled(True)
        self.wifi_config_btn.setText("Configure WiFi to Hotspot")
        
        # Show message in log and as message box
        self.log(message)
        
        if success:
            QMessageBox.information(self, "WiFi Configuration", 
                                  message.replace('\n', '<br/>'))
        else:
            QMessageBox.critical(self, "WiFi Configuration Failed", 
                               message.replace('\n', '<br/>'))

    def update_gamepad_input(self):
        if not self.tello_controller.connected or self.demo_active:
            return
        
        if self.gamepad is None:
            return

        try:
            inputs = self.gamepad.get_inputs()
            if inputs is None:
                return

            # Safely access inputs with defaults
            buttons = inputs.get('buttons', {})
            if not buttons:
                return

            if not hasattr(self, "_last_buttons"):
                self._last_buttons = {name: 0 for name in buttons}

            if buttons.get('r1') and not self._last_buttons.get('r1', 0):
                self.takeoff()
            if buttons.get('l1') and not self._last_buttons.get('l1', 0):
                self.land()
            if buttons.get('r2') and not self._last_buttons.get('r2', 0):
                self.execute_flip('right')
            if buttons.get('l2') and not self._last_buttons.get('l2', 0):
                self.execute_flip('left')

            for key in ['r1', 'l1', 'r2', 'l2']:
                self._last_buttons[key] = buttons.get(key, 0)

            left_stick = inputs.get('left_stick', (0, 0))
            right_stick = inputs.get('right_stick', (0, 0))
            up_down = int(left_stick[1] * 100) if len(left_stick) > 1 else 0
            yaw = int(left_stick[0] * 100) if len(left_stick) > 0 else 0
            forward_back = int(-right_stick[1] * 100) if len(right_stick) > 1 else 0
            left_right = int(right_stick[0] * 100) if len(right_stick) > 0 else 0
            self.current_rc_values = [left_right, forward_back, up_down, yaw]

            self.tello_controller.send_rc_control(left_right, forward_back, up_down, yaw)
        except Exception as e:
            # Silently handle gamepad errors to prevent crashes
            logging.error(f"Gamepad input error: {e}")
            pass

    def init_bluetooth(self):
        """Initialize Bluetooth handler for ESP32-C6"""
        try:
            self.bluetooth_handler = BluetoothHandler(device_name_pattern="XIAO")
            self.bluetooth_handler.mag_received.connect(self.on_mag_received)
            self.bluetooth_handler.heading_received.connect(self.on_heading_received)
            self.bluetooth_handler.connection_status.connect(self.on_bluetooth_status)
            self.bluetooth_handler.start()
            self.log("Bluetooth handler started - searching for XIAO...")
        except Exception as e:
            logging.error(f"Error initializing Bluetooth handler: {e}")
            self.log(f"Warning: Bluetooth initialization failed: {e}")
    
    def on_mag_received(self, mx, my, mz):
        """Store magnetometer vector from ESP32 for tilt-compensated heading"""
        self.raw_mag = (mx, my, mz)

    def on_heading_received(self, heading):
        """Handle heading data from ESP32 (fallback when M: not sent)"""
        self.current_heading = heading
    
    def on_bluetooth_status(self, connected, message):
        """Handle Bluetooth connection status updates"""
        if connected:
            self.bluetooth_status_label.setText(f"ESP32-C6: Connected")
            self.bluetooth_status_label.setStyleSheet("font-size: 12px; color: green;")
        else:
            self.bluetooth_status_label.setText(f"ESP32-C6: Disconnected")
            self.bluetooth_status_label.setStyleSheet("font-size: 12px; color: red;")
        self.log(f"Bluetooth: {message}")

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")

    def closeEvent(self, event):
        try:
            # Stop gamepad timer
            if hasattr(self, 'gamepad_timer') and self.gamepad_timer:
                self.gamepad_timer.stop()
            
            # Stop flip thread if running
            if self.flip_thread and self.flip_thread.isRunning():
                self.flip_thread.terminate()
                if not self.flip_thread.wait(2000):  # Wait max 2 seconds
                    self.log("Warning: Flip thread did not stop gracefully")
            
            # Stop WiFi config thread if running
            if self.wifi_config_thread and self.wifi_config_thread.isRunning():
                self.wifi_config_thread.terminate()
                if not self.wifi_config_thread.wait(2000):  # Wait max 2 seconds
                    self.log("Warning: WiFi config thread did not stop gracefully")
            
            # Stop Bluetooth handler
            if self.bluetooth_handler:
                try:
                    self.bluetooth_handler.stop()
                except Exception as e:
                    logging.error(f"Error stopping Bluetooth handler: {e}")
            
            # Stop video thread
            if self.video_thread:
                try:
                    self.video_thread.stop()
                except Exception as e:
                    logging.error(f"Error stopping video thread: {e}")
            
            # Disconnect drone
            if self.tello_controller.connected:
                try:
                    self.disconnect_drone()
                except Exception as e:
                    logging.error(f"Error disconnecting drone: {e}")
            
            # Cleanup gamepad
            if self.gamepad:
                try:
                    import pygame
                    pygame.quit()
                except:
                    pass
            # Close debug log file
            if self.debug_log_file:
                try:
                    self.debug_log_file.close()
                except Exception:
                    pass
        except Exception as e:
            logging.error(f"Error in closeEvent: {e}")
        finally:
            event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

