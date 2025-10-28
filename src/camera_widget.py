import cv2
from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap, QPainter, QFont, QColor

class CameraWidget(QLabel):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(640, 480)
        self.setStyleSheet("background-color: black;")
        self.setAlignment(Qt.AlignCenter)
        self.image = None
        self.ui_info = {}

    def set_frame(self, frame):
        try:
            if frame is None or frame.size == 0 or len(frame.shape) != 3:
                return
            
            if not frame.flags['C_CONTIGUOUS']:
                frame = frame.copy()
            
            h, w, ch = frame.shape
            bytes_per_line = ch * w
            qt_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
            
            if qt_image.isNull():
                return
                
            self.image = qt_image
            scaled_pixmap = QPixmap.fromImage(qt_image).scaled(
                self.width(), self.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.setPixmap(scaled_pixmap)
        except Exception as e:
            print(f"Error in set_frame: {e}")

    def set_ui_info(self, info):
        self.ui_info = info
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.image is None:
            return

        painter = QPainter(self)
        y_offset = 10
        color_white = QColor(255, 255, 255)
        color_red = QColor(255, 100, 100)
        color_green = QColor(100, 255, 100)
        color_yellow = QColor(255, 255, 100)
        painter.setFont(QFont("Arial", 11, QFont.Bold))
        
        if 'battery' in self.ui_info:
            battery = self.ui_info['battery']
            color = color_white if battery > 20 else color_red
            painter.setPen(color)
            painter.drawText(10, y_offset + 20, f"🔋 Battery: {battery}%")
            y_offset += 25
        
        if 'height' in self.ui_info and self.ui_info['height'] > 0:
            painter.setPen(color_white)
            painter.drawText(10, y_offset + 20, f"📏 Height: {self.ui_info['height']} cm")
            y_offset += 25
        
        if 'tof' in self.ui_info and self.ui_info['tof'] > 0:
            painter.setPen(color_white)
            painter.drawText(10, y_offset + 20, f"📡 TOF: {self.ui_info['tof']} cm")
            y_offset += 25
        
        if 'temp' in self.ui_info:
            temp = self.ui_info['temp']
            color = color_green if temp < 60 else color_red
            painter.setPen(color)
            painter.drawText(10, y_offset + 20, f"🌡️ Temp: {temp}°C")
            y_offset += 25
        
        if 'throttle' in self.ui_info:
            throttle = self.ui_info['throttle']
            color = color_white
            if throttle > 5:
                color = color_green
            elif throttle < -5:
                color = color_yellow
            painter.setPen(color)
            painter.drawText(10, y_offset + 20, f"⬆️ Throttle: {throttle:+3d}%")
            y_offset += 25
        
        if 'speed' in self.ui_info:
            speed = self.ui_info['speed']
            if speed != 0:
                painter.setPen(color_white)
                painter.drawText(10, y_offset + 20, f"⚡ Vert Speed: {speed:+3d} cm/s")
                y_offset += 25
        
        if 'pitch' in self.ui_info:
            pitch = self.ui_info['pitch']
            color = color_white
            if abs(pitch) > 5:
                color = color_yellow
            direction = "Fwd" if pitch > 0 else "Back"
            painter.setPen(color)
            painter.drawText(10, y_offset + 20, f"📐 Pitch: {pitch:+3d}° ({direction})")
            y_offset += 25
        
        if 'roll' in self.ui_info:
            roll = self.ui_info['roll']
            color = color_white
            if abs(roll) > 5:
                color = color_yellow
            direction = "Right" if roll > 0 else "Left"
            painter.setPen(color)
            painter.drawText(10, y_offset + 20, f"🔄 Roll: {roll:+3d}° ({direction})")
            y_offset += 25
        
        # Display RC control values (input commands)
        painter.setPen(color_white)
        painter.drawText(10, y_offset + 20, "--- RC Controls ---")
        y_offset += 25
        
        if 'rc_pitch' in self.ui_info:
            rc_pitch = self.ui_info['rc_pitch']
            color = color_white if rc_pitch == 0 else color_green
            painter.setPen(color)
            direction = "Forward" if rc_pitch > 0 else "Backward" if rc_pitch < 0 else "Center"
            painter.drawText(10, y_offset + 20, f"RC Pitch: {rc_pitch:+3d} ({direction})")
            y_offset += 25
        
        if 'rc_roll' in self.ui_info:
            rc_roll = self.ui_info['rc_roll']
            color = color_white if rc_roll == 0 else color_green
            painter.setPen(color)
            direction = "Right" if rc_roll > 0 else "Left" if rc_roll < 0 else "Center"
            painter.drawText(10, y_offset + 20, f"RC Roll: {rc_roll:+3d} ({direction})")
            y_offset += 25
        
        if 'rc_yaw' in self.ui_info:
            rc_yaw = self.ui_info['rc_yaw']
            color = color_white if rc_yaw == 0 else color_green
            painter.setPen(color)
            direction = "Right" if rc_yaw > 0 else "Left" if rc_yaw < 0 else "Center"
            painter.drawText(10, y_offset + 20, f"RC Yaw: {rc_yaw:+3d} ({direction})")
            y_offset += 25
        
        if 'controller' in self.ui_info:
            painter.setPen(color_green if self.ui_info['controller'] else color_red)
            status = "Connected" if self.ui_info['controller'] else "Disconnected"
            painter.drawText(10, y_offset + 20, f"🎮 Controller: {status}")
            y_offset += 25
        
        if 'flying_mode' in self.ui_info:
            mode = self.ui_info['flying_mode']
            mode_text = "Manual" if mode == "manual" else "Autopilot"
            painter.setPen(color_white)
            painter.drawText(10, y_offset + 20, f"✈️ Mode: {mode_text}")

    def clear(self):
        self.setPixmap(QPixmap())
