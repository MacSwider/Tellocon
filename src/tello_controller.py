from djitellopy import Tello
import logging
import time

logging.getLogger('djitellopy').setLevel(logging.WARNING)

class TelloController:
    def __init__(self):
        self.tello = None
        self.connected = False
        self.flipping = False

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
        if self.tello and not self.flipping:
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

    def flip_left(self):
        """Perform a barrel roll to the left (roll axis spin)"""
        if not self.tello:
            return False, "Drone not connected"
        
        # Check if drone is flying and at sufficient height
        try:
            height = self.get_height()
            if height < 80:
                return False, f"Insufficient height: {height}cm (needs at least 80cm)"
            
            # Set flipping flag to stop RC control
            self.flipping = True
            
            # Stop RC control to allow flip to execute
            self.tello.send_rc_control(0, 0, 0, 0)
            time.sleep(0.3)  # Give drone a moment to stabilize
            
            self.tello.flip('l')
            
            # Reset flipping flag
            self.flipping = False
            return True, "Flip left completed"
        except Exception as e:
            error_msg = str(e)
            logging.error(f"Flip left error: {error_msg}")
            self.flipping = False
            return False, error_msg

    def flip_right(self):
        """Perform a barrel roll to the right (roll axis spin)"""
        if not self.tello:
            return False, "Drone not connected"
        
        # Check if drone is flying and at sufficient height
        try:
            height = self.get_height()
            if height < 80:
                return False, f"Insufficient height: {height}cm (needs at least 80cm)"
            
            # Set flipping flag to stop RC control
            self.flipping = True
            
            # Stop RC control to allow flip to execute
            self.tello.send_rc_control(0, 0, 0, 0)
            time.sleep(0.3)  # Give drone a moment to stabilize
            
            self.tello.flip('r')
            
            # Reset flipping flag
            self.flipping = False
            return True, "Flip right completed"
        except Exception as e:
            error_msg = str(e)
            logging.error(f"Flip right error: {error_msg}")
            self.flipping = False
            return False, error_msg
