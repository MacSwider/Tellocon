from djitellopy import Tello
import logging
import time
import socket
import traceback

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
            
            battery = self.get_battery()
            success_msg = f"Connected! Battery: {battery}%"
            return True, success_msg
            
        except socket.timeout as e:
            self.connected = False
            return False, f"Connection timeout: {str(e)}"
            
        except socket.error as e:
            self.connected = False
            return False, f"Socket error: {str(e)}"
            
        except OSError as e:
            self.connected = False
            return False, f"OS error: {str(e)}"
            
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
            except Exception as e:
                logging.error(f"Error during disconnect: {e}")
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

    def configure_wifi(self, ssid, password):
        """
        Configure Tello drone to connect to a WiFi hotspot.
        This works the same way as swarm preparation:
        1. Connect to Tello's hotspot (TELLO-XXXX)
        2. Send 'ap' command with SSID and password
        3. Drone reboots and attempts to connect to the hotspot
        
        Args:
            ssid: WiFi network SSID (e.g., 'MurderDroneTest')
            password: WiFi network password (e.g., '54fatTTT')
            
        Returns:
            tuple: (success: bool, message: str)
        """
        temp_tello = None
        try:
            # Validate inputs
            if not ssid or not password:
                return False, "SSID and password cannot be empty"
            
            if len(ssid) > 32:
                return False, "SSID must be 32 characters or less"
            
            if len(password) > 64:
                return False, "Password must be 64 characters or less"
            
            # Check for problematic characters
            if any(char in ssid for char in [' ', '\t', '\n']):
                return False, "SSID cannot contain spaces or tabs"
            
            # Create a temporary connection to send the command
            # This assumes we're already connected to TELLO-XXXX hotspot
            logging.info("Connecting to Tello to configure WiFi...")
            temp_tello = Tello()
            temp_tello.connect()
            
            # Wait a moment for connection to stabilize
            time.sleep(1.5)
            
            # Use the built-in connect_to_wifi method which uses 'ap' command
            # This is the same method used for swarm preparation
            # Format: "ap SSID password"
            logging.info(f"Sending WiFi configuration command: ap {ssid} ****")
            
            # The connect_to_wifi method uses send_control_command internally
            # which waits for "ok" response with retry logic
            # The drone will reboot after receiving this command
            try:
                # Use the built-in method which handles the command properly
                temp_tello.connect_to_wifi(ssid, password)
                logging.info("WiFi credentials sent successfully - received OK response")
            except Exception as cmd_error:
                # The command might still have been sent even if we get an exception
                # because the drone reboots quickly after receiving the command
                error_str = str(cmd_error)
                logging.warning(f"Command sent (drone rebooting): {error_str}")
                # Check if we got an OK response before the reboot
                # If not, the command might have failed
                if "ok" not in error_str.lower() and "timeout" not in error_str.lower():
                    # This might be a real error - re-raise it
                    raise
            
            # Close the connection
            try:
                temp_tello.end()
            except:
                pass
            
            temp_tello = None
            
            # The drone will reboot now
            logging.info("WiFi credentials sent. Drone is rebooting and will attempt to connect...")
            
            return True, (f"✓ WiFi credentials sent successfully!\n\n"
                          f"Drone received the command and is rebooting...\n\n"
                          f"CRITICAL NEXT STEPS:\n"
                          f"1. RE-ENABLE your hotspot if it was paused\n"
                          f"2. Verify hotspot is 2.4GHz (NOT 5GHz) - CHECK THIS!\n"
                          f"3. Verify SSID matches exactly: '{ssid}'\n"
                          f"4. Verify password matches exactly\n"
                          f"5. Wait 60-90 seconds\n"
                          f"6. Check hotspot connected devices\n\n"
                          f"If drone shows as 'unknown device' and keeps blinking:\n"
                          f"• Hotspot is likely 5GHz - MUST be 2.4GHz!\n"
                          f"• SSID/password mismatch - check case sensitivity\n"
                          f"• Try resetting drone (hold power 5-10 seconds) and retry\n"
                          f"• LED should turn SOLID GREEN when connected (not blinking)")
            
        except socket.timeout:
            # This is actually expected - the drone reboots after receiving the command
            # which causes the connection to timeout
            if temp_tello:
                try:
                    temp_tello.end()
                except:
                    pass
            return True, f"✓ WiFi credentials sent!\n\nDrone is rebooting and will attempt to connect to '{ssid}'.\n\nPlease wait 30-60 seconds and check your hotspot's connected devices."
            
        except Exception as e:
            error_msg = str(e)
            logging.error(f"WiFi configuration error: {error_msg}")
            
            if temp_tello:
                try:
                    temp_tello.end()
                except:
                    pass
            
            # Check for specific error messages
            if "Connection refused" in error_msg or "timed out" in error_msg.lower() or "No response" in error_msg:
                return False, (f"❌ Could not connect to Tello.\n\n"
                              f"Make sure:\n"
                              f"1. You're connected to TELLO-XXXX hotspot (not your computer's hotspot)\n"
                              f"2. The drone is powered on\n"
                              f"3. The drone is in range\n"
                              f"4. No firewall is blocking UDP port 8889")
            elif "invalid" in error_msg.lower() or "error" in error_msg.lower():
                return False, (f"❌ Command error: {error_msg}\n\n"
                              f"Make sure:\n"
                              f"1. SSID and password are valid (no special characters or spaces)\n"
                              f"2. SSID is 32 characters or less\n"
                              f"3. Password is 64 characters or less")
            else:
                return False, (f"❌ WiFi configuration failed: {error_msg}\n\n"
                              f"Troubleshooting:\n"
                              f"1. Reset drone (hold power 5-10 seconds)\n"
                              f"2. Ensure hotspot is 2.4GHz\n"
                              f"3. Verify SSID/password are correct")
