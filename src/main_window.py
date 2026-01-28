
import sys
import time
import logging
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

        self.init_ui()
        self.init_bluetooth()
        self.init_gamepad()
    
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
        
        self.esp32_message_label = QLabel("ESP32 Message: -")
        self.esp32_message_label.setStyleSheet("font-size: 11px; color: #666; padding: 5px; background-color: white; border: 1px solid #ddd; border-radius: 3px;")
        self.esp32_message_label.setWordWrap(True)
        layout.addWidget(self.esp32_message_label)
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
            'heading': self.current_heading  # Heading from ESP32 GY-271
        })

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
        if not self.tello_controller.connected:
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
            self.bluetooth_handler.heading_received.connect(self.on_heading_received)
            self.bluetooth_handler.message_received.connect(self.on_esp32_message)
            self.bluetooth_handler.connection_status.connect(self.on_bluetooth_status)
            self.bluetooth_handler.start()
            self.log("Bluetooth handler started - searching for XIAO...")
        except Exception as e:
            logging.error(f"Error initializing Bluetooth handler: {e}")
            self.log(f"Warning: Bluetooth initialization failed: {e}")
    
    def on_heading_received(self, heading):
        """Handle heading data from ESP32"""
        self.current_heading = heading
    
    def on_esp32_message(self, message):
        """Handle raw message from ESP32 - messages are printed to console"""
        # Messages are now printed to terminal/console instead of UI
        # This method is kept for potential future use but doesn't update UI
        pass
    
    def on_bluetooth_status(self, connected, message):
        """Handle Bluetooth connection status updates"""
        if connected:
            self.bluetooth_status_label.setText(f"ESP32-C6: Connected")
            self.bluetooth_status_label.setStyleSheet("font-size: 12px; color: green;")
            print(f"[ESP32C6] Connection status: {message}")
        else:
            self.bluetooth_status_label.setText(f"ESP32-C6: Disconnected")
            self.bluetooth_status_label.setStyleSheet("font-size: 12px; color: red;")
            print(f"[ESP32C6] Connection status: {message}")
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
        except Exception as e:
            logging.error(f"Error in closeEvent: {e}")
        finally:
            event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

