from djitellopy import Tello
import logging

logging.getLogger('djitellopy').setLevel(logging.WARNING)

class TelloController:
    def __init__(self):
        self.tello = None
        self.connected = False

    def connect(self):
        try:
            self.tello = Tello()
            self.tello.connect()
            self.connected = True
            return True, f"Connected! Battery: {self.get_battery()}%"
        except Exception as e:
            self.connected = False
            return False, f"Connection error: {str(e)}"

    def disconnect(self):
        if self.tello:
            try:
                self.tello.end()
                self.connected = False
                self.tello = None
                return True
            except:
                return False
        return False

    def takeoff(self):
        if self.tello:
            self.tello.takeoff()

    def land(self):
        if self.tello:
            self.tello.land()

    def send_rc_control(self, left_right, forward_back, up_down, yaw):
        if self.tello:
            self.tello.send_rc_control(
                int(left_right),
                int(forward_back),
                int(up_down),
                int(yaw)
            )

    def get_battery(self):
        if self.tello:
            return self.tello.get_battery()
        return 0

    def get_height(self):
        if self.tello:
            return self.tello.get_height()
        return 0

    def get_barometer(self):
        if self.tello:
            return self.tello.get_barometer()
        return 0

    def get_distance_tof(self):
        if self.tello:
            return self.tello.get_distance_tof()
        return 0

    def get_temp(self):
        if self.tello:
            return self.tello.get_temperature()
        return 0

    def get_speed_x(self):
        if self.tello:
            return self.tello.get_speed_x()
        return 0

    def get_speed_y(self):
        if self.tello:
            return self.tello.get_speed_y()
        return 0

    def get_speed_z(self):
        if self.tello:
            return self.tello.get_speed_z()
        return 0

    def get_acceleration(self):
        if self.tello:
            return self.tello.get_acceleration()
        return (0, 0, 0)

    def get_pitch(self):
        if self.tello:
            return self.tello.get_pitch()
        return 0

    def get_roll(self):
        if self.tello:
            return self.tello.get_roll()
        return 0

    def get_yaw_angle(self):
        if self.tello:
            return self.tello.get_yaw()
        return 0

    def rotate_left_90(self):
        if self.tello:
            self.tello.rotate_counter_clockwise(90)

    def rotate_right_90(self):
        if self.tello:
            self.tello.rotate_clockwise(90)
