"""
Camera widget with HUD overlay for Tellocon.

Displays the live video feed from the Tello and paints a heads-up
display with telemetry, RC commands, and compass heading.
"""

import cv2
from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap, QPainter, QFont, QColor


_DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


class CameraWidget(QLabel):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(640, 480)
        self.setStyleSheet("background-color: black;")
        self.setAlignment(Qt.AlignCenter)
        self.image = None
        self.ui_info = {}

    # ----- Video frame -----

    def set_frame(self, frame):
        try:
            if frame is None or frame.size == 0 or len(frame.shape) != 3:
                return
            if not frame.flags['C_CONTIGUOUS']:
                frame = frame.copy()
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).copy()
            h, w, ch = rgb.shape
            qt_img = QImage(rgb.tobytes(), w, h, ch * w, QImage.Format_RGB888)
            if qt_img.isNull():
                return
            self.image = qt_img.copy()
            self.setPixmap(QPixmap.fromImage(self.image).scaled(
                self.width(), self.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception:
            pass

    # ----- HUD overlay -----

    def set_ui_info(self, info):
        self.ui_info = info
        self.update()

    def paintEvent(self, event):
        try:
            super().paintEvent(event)
            if self.image is None:
                return

            painter = QPainter(self)
            if not painter.isActive():
                return

            white = QColor(255, 255, 255)
            red = QColor(255, 100, 100)
            green = QColor(100, 255, 100)
            yellow = QColor(255, 255, 100)
            painter.setFont(QFont("Arial", 11, QFont.Bold))

            y = 10
            info = self.ui_info

            if 'battery' in info:
                bat = info['battery']
                painter.setPen(white if bat > 20 else red)
                painter.drawText(10, y + 20, f"Battery: {bat}%")
                y += 25

            if info.get('height', 0) > 0:
                painter.setPen(white)
                painter.drawText(10, y + 20, f"Height: {info['height']} cm")
                y += 25

            if info.get('tof', 0) > 0:
                painter.setPen(white)
                painter.drawText(10, y + 20, f"TOF: {info['tof']} cm")
                y += 25

            if 'temp' in info:
                t = info['temp']
                painter.setPen(green if t < 60 else red)
                painter.drawText(10, y + 20, f"Temp: {t} C")
                y += 25

            if 'throttle' in info:
                thr = info['throttle']
                c = green if thr > 5 else (yellow if thr < -5 else white)
                painter.setPen(c)
                painter.drawText(10, y + 20, f"Throttle: {thr:+d}%")
                y += 25

            if info.get('speed', 0) != 0:
                painter.setPen(white)
                painter.drawText(10, y + 20, f"Vert speed: {info['speed']:+d} cm/s")
                y += 25

            if 'pitch' in info:
                p = info['pitch']
                painter.setPen(yellow if abs(p) > 5 else white)
                painter.drawText(10, y + 20,
                                 f"Pitch: {p:+d} ({'Fwd' if p > 0 else 'Back'})")
                y += 25

            if 'roll' in info:
                r = info['roll']
                painter.setPen(yellow if abs(r) > 5 else white)
                painter.drawText(10, y + 20,
                                 f"Roll: {r:+d} ({'Right' if r > 0 else 'Left'})")
                y += 25

            # RC commands section
            painter.setPen(white)
            painter.drawText(10, y + 20, "--- RC ---")
            y += 25

            for key, label in (('rc_pitch', 'Pitch'), ('rc_roll', 'Roll'), ('rc_yaw', 'Yaw')):
                if key in info:
                    v = info[key]
                    painter.setPen(green if v != 0 else white)
                    painter.drawText(10, y + 20, f"RC {label}: {v:+d}")
                    y += 25

            if 'flying_mode' in info:
                mode = info['flying_mode']
                painter.setPen(white)
                painter.drawText(10, y + 20, f"Mode: {mode}")
                y += 25

            if 'heading' in info and info['heading'] is not None:
                hdg = info['heading']
                idx = int((hdg + 22.5) / 45) % 8
                painter.setPen(white)
                painter.drawText(10, y + 20,
                                 f"Heading: {hdg:03d} ({_DIRECTIONS[idx]})")
                y += 25
        except Exception:
            pass

    def clear(self):
        self.setPixmap(QPixmap())
