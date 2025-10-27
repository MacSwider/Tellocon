import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

class VideoThread(QThread):
    frame_signal = pyqtSignal(np.ndarray)

    def __init__(self, tello):
        super().__init__()
        self.tello = tello
        self.running = False
        self.frame_read = None

    def run(self):
        self.running = True
        try:
            self.tello.streamon()
            self.msleep(200)
            self.frame_read = self.tello.get_frame_read()
        except Exception as e:
            print(f"Error initializing frame read: {e}")
            self.running = False
            return

        while self.running:
            try:
                if self.frame_read and self.frame_read.frame is not None and self.frame_read.frame.size > 0:
                    frame_copy = self.frame_read.frame.copy()
                    if frame_copy is not None and frame_copy.size > 0:
                        self.frame_signal.emit(frame_copy)
                self.msleep(30)
            except Exception as e:
                print(f"Video stream error: {e}")
                break

    def stop(self):
        self.running = False
        try:
            if self.tello:
                self.tello.streamoff()
        except Exception as e:
            print(f"Error stopping stream: {e}")
        self.wait()
