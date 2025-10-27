
import sys
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QFrame, QTextEdit)
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFont

from src.tello_controller import TelloController
from src.gamepad_handler import GamepadHandler
from src.camera_widget import CameraWidget
from src.video_thread import VideoThread


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tello_controller = TelloController()
        self.gamepad = GamepadHandler()
        self.video_thread = None
        self.current_throttle = 0
        self.current_rc_values = [0, 0, 0, 0]

        self.gamepad_timer = QTimer()
        self.gamepad_timer.timeout.connect(self.update_gamepad_input)
        self.gamepad_timer.start(50)

        self.init_ui()

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

        layout.addSpacing(30)

        status_title = QLabel("Status:")
        status_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(status_title)

        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("font-size: 12px; color: red;")
        layout.addWidget(self.status_label)
        layout.addSpacing(20)

        instructions = QLabel(
            "<b>Controls:</b><br/>"
            "• Left stick: Ascend/Descend, Rotate<br/>"
            "• Right stick: Forward/Backward, Left/Right<br/>"
            "• R1: Takeoff<br/>"
            "• L1: Landing"
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
            self.video_thread = VideoThread(self.tello_controller.tello)
            self.video_thread.frame_signal.connect(self.update_frame)
            self.video_thread.start()
            self.log("Video stream started")

    def update_frame(self, frame):
        self.camera_widget.set_frame(frame)

        battery = self.tello_controller.get_battery()
        height = self.tello_controller.get_height()
        tof_distance = self.tello_controller.get_distance_tof()
        temp = self.tello_controller.get_temp()
        speed_z = self.tello_controller.get_speed_z()
        pitch = self.tello_controller.get_pitch()
        roll = self.tello_controller.get_roll()
        yaw_angle = self.tello_controller.get_yaw_angle()
        left_right, forward_back, up_down, yaw = self.current_rc_values
        
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
            'controller': self.gamepad.is_connected()
        })

    def takeoff(self):
        if self.tello_controller.connected:
            self.tello_controller.takeoff()
            self.log("Drone took off")

    def land(self):
        if self.tello_controller.connected:
            self.tello_controller.land()
            self.log("Drone landed")

    def update_gamepad_input(self):
        if not self.tello_controller.connected:
            return

        inputs = self.gamepad.get_inputs()
        if inputs is None:
            return

        buttons = inputs['buttons']
        if not hasattr(self, "_last_buttons"):
            self._last_buttons = {name: 0 for name in buttons}

        if buttons.get('r1') and not self._last_buttons.get('r1', 0):
            self.takeoff()
        if buttons.get('l1') and not self._last_buttons.get('l1', 0):
            self.land()
        if buttons.get('r2') and not self._last_buttons.get('r2', 0):
            self.tello_controller.rotate_right_90()
        if buttons.get('l2') and not self._last_buttons.get('l2', 0):
            self.tello_controller.rotate_left_90()

        for key in ['r1', 'l1', 'r2', 'l2']:
            self._last_buttons[key] = buttons.get(key, 0)

        left_stick = inputs['left_stick']
        right_stick = inputs['right_stick']
        up_down = int(left_stick[1] * 100)
        yaw = int(left_stick[0] * 100)
        forward_back = int(-right_stick[1] * 100)
        left_right = int(right_stick[0] * 100)
        self.current_rc_values = [left_right, forward_back, up_down, yaw]

        self.tello_controller.send_rc_control(left_right, forward_back, up_down, yaw)

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")

    def closeEvent(self, event):
        if self.tello_controller.connected:
            self.disconnect_drone()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

