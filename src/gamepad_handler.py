import pygame
import json
import os

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "gamepad_config.json")


class GamepadHandler:
    def __init__(self):
        self.joystick = None
        self.mapping = {}
        self.pygame_initialized = False
        
        try:
            # Only initialize joystick module, not full pygame (avoids conflicts with PyQt5)
            if not pygame.get_init():
                pygame.init()
                self.pygame_initialized = True
            
            pygame.joystick.init()

            if pygame.joystick.get_count() == 0:
                print("[WARNING] No controller detected! Controller features will be disabled.")
                return

            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            print(f"[OK] Controller connected: {self.joystick.get_name()}")

            if not os.path.exists(CONFIG_FILE):
                print(f"[WARNING] {CONFIG_FILE} not found! Controller buttons may not work correctly.")
                print(f"[INFO] Run gamepad_config.py to calibrate your controller.")
                # Use default empty mapping to prevent crashes
                self.mapping = {}
                return

            with open(CONFIG_FILE, "r") as f:
                self.mapping = json.load(f)
            print(f"[OK] Loaded mapping from {CONFIG_FILE}")
        except Exception as e:
            print(f"[ERROR] Gamepad initialization error: {e}")
            self.joystick = None
            self.mapping = {}

    def is_connected(self):
        return self.joystick is not None

    def get_inputs(self):
        try:
            if not self.pygame_initialized:
                return None
                
            pygame.event.pump()
            if not self.is_connected():
                return None

            if self.joystick is None:
                return None

            num_axes = self.joystick.get_numaxes()
            
            # Standard controller mapping:
            # Axis 0: Left stick X
            # Axis 1: Left stick Y
            # Axis 2: Right stick X
            # Axis 3: Right stick Y
            # Axis 4: Triggers (depending on controller)
            # Axis 5: Triggers (depending on controller)
            
            # Left stick (same for all controllers)
            left_x = self.joystick.get_axis(0) if num_axes > 0 else 0
            left_y = -self.joystick.get_axis(1) if num_axes > 1 else 0
            
            # Right stick (same for all controllers)
            right_x = self.joystick.get_axis(2) if num_axes > 2 else 0
            right_y = -self.joystick.get_axis(3) if num_axes > 3 else 0
            
            # Triggers - read both possible locations
            # Some controllers have triggers on 4,5 (standard)
            # Others might have them at different axes or as separate axes
            l2 = self.joystick.get_axis(4) if num_axes > 4 else 0
            r2 = self.joystick.get_axis(5) if num_axes > 5 else 0
            
            buttons = {}
            # Safely iterate over mapping
            if self.mapping:
                for name, idx in self.mapping.items():
                    try:
                        buttons[name] = self.joystick.get_button(idx)
                    except (pygame.error, IndexError):
                        buttons[name] = 0
            buttons['l2'] = 1 if l2 > 0.5 else 0
            buttons['r2'] = 1 if r2 > 0.5 else 0

            return {
                "left_stick": (left_x, left_y),
                "right_stick": (right_x, -right_y),
                "l2": l2,
                "r2": r2,
                "buttons": buttons,
            }
        except Exception as e:
            print(f"[ERROR] Error reading gamepad inputs: {e}")
            return None
