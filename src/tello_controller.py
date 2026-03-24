"""
Thin wrapper around djitellopy.Tello.

Provides a safe interface with connection state tracking.
"""

import logging
import socket

from djitellopy import Tello

logging.getLogger('djitellopy').setLevel(logging.WARNING)


class TelloController:
    def __init__(self):
        self.tello = None
        self.connected = False

    # ----- Connection -----

    def connect(self):
        try:
            self.tello = Tello()
            self.tello.connect()
            self.connected = True
            battery = self.get_battery()
            return True, f"Connected (battery {battery}%)"
        except socket.timeout as e:
            self.connected = False
            return False, f"Timeout: {e}"
        except socket.error as e:
            self.connected = False
            return False, f"Socket error: {e}"
        except Exception as e:
            self.connected = False
            return False, f"Connection error: {e}"

    def disconnect(self):
        if self.tello:
            try:
                self.tello.end()
            except Exception as e:
                logging.error(f"Disconnect error: {e}")
            self.connected = False
            self.tello = None

    # ----- Flight commands -----

    def takeoff(self):
        if self.tello:
            self.tello.takeoff()

    def land(self):
        if self.tello:
            self.tello.land()

    def send_rc_control(self, left_right, forward_back, up_down, yaw):
        if self.tello:
            self.tello.send_rc_control(
                int(left_right), int(forward_back),
                int(up_down), int(yaw))

    # ----- Telemetry -----

    def get_battery(self):
        return self.tello.get_battery() if self.tello else 0

    def get_height(self):
        return self.tello.get_height() if self.tello else 0

    def get_distance_tof(self):
        return self.tello.get_distance_tof() if self.tello else 0

    def get_temp(self):
        return self.tello.get_temperature() if self.tello else 0

    def get_speed_x(self):
        return self.tello.get_speed_x() if self.tello else 0

    def get_speed_y(self):
        return self.tello.get_speed_y() if self.tello else 0

    def get_speed_z(self):
        return self.tello.get_speed_z() if self.tello else 0

    def get_pitch(self):
        return self.tello.get_pitch() if self.tello else 0

    def get_roll(self):
        return self.tello.get_roll() if self.tello else 0

    def get_yaw_angle(self):
        return self.tello.get_yaw() if self.tello else 0
