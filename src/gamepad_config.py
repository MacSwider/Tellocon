"""
gamepad_config.py
Run this once to create button mapping for your gamepad.
Supports DualShock 4, Xbox, and other standard controllers.
"""

import pygame
import json
import time
import os

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "gamepad_config.json")


def wait_for_button_press(joystick):
    prev_states = [0] * joystick.get_numbuttons()
    while True:
        pygame.event.pump()
        for i in range(joystick.get_numbuttons()):
            state = joystick.get_button(i)
            if state and not prev_states[i]:
                return i
            prev_states[i] = state
        time.sleep(0.01)


def calibrate_gamepad():
    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        print("[ERROR] No controller detected!")
        return

    joystick = pygame.joystick.Joystick(0)
    joystick.init()
    print(f"[OK] Controller detected: {joystick.get_name()}")

    logical_buttons = [
        "cross", "circle", "square", "triangle",  # PlayStation buttons or Xbox equivalent
        "l1", "r1", "share", "options", "ps", "l3", "r3"
    ]
    
    # Map to Xbox button names for better clarity
    xbox_names = {
        "cross": "A (or Cross)",
        "circle": "B (or Circle)",
        "square": "X (or Square)",
        "triangle": "Y (or Triangle)",
        "l1": "LB",
        "r1": "RB",
        "share": "View (or Share)",
        "options": "Menu (or Options)",
        "ps": "Xbox/Home",
        "l3": "Left Stick Click",
        "r3": "Right Stick Click"
    }

    mapping = {}
    print("\nStarting calibration:")
    print("Press each requested button when prompted.\n")

    for name in logical_buttons:
        display_name = xbox_names.get(name, name.upper())
        print(f">> Press {display_name} button...")
        idx = wait_for_button_press(joystick)
        mapping[name] = idx
        print(f"  Mapped to index {idx}\n")
        time.sleep(0.3)

    with open(CONFIG_FILE, "w") as f:
        json.dump(mapping, f, indent=2)

    print(f"[OK] Mapping saved to {CONFIG_FILE}")
    return mapping


if __name__ == "__main__":
    calibrate_gamepad()
