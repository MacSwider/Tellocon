"""
gamepad_test.py
Tests your controller mapping (no infinite loop spam).
Prints button or stick changes only when they happen.
"""

from src.gamepad_handler import GamepadHandler
import pygame
import time

# Initialize gamepad handler
handler = GamepadHandler()

if not handler.is_connected():
    exit("[ERROR] No controller detected!")

print("\n[OK] Gamepad ready - move sticks or press buttons to see changes.\n")
print("Press CTRL+C or close the window to exit.\n")

# Keep track of previous state
prev_buttons = {}
prev_axes = {}

# Init pygame event system
pygame.display.init()
pygame.display.set_mode((200, 100))  # tiny window to keep pygame active

try:
    while True:
        pygame.event.pump()
        data = handler.get_inputs()
        if not data:
            continue

        # Compare buttons
        for name, value in data["buttons"].items():
            prev_val = prev_buttons.get(name)
            if prev_val != value:
                state = "pressed" if value else "released"
                print(f"[BUTTON] {name.upper()} {state}")
                prev_buttons[name] = value

        # Compare sticks / triggers with small tolerance
        for axis_name, val in {
            "LX": data["left_stick"][0],
            "LY": data["left_stick"][1],
            "RX": data["right_stick"][0],
            "RY": data["right_stick"][1],
            "L2": data["l2"],
            "R2": data["r2"],
        }.items():
            prev_val = prev_axes.get(axis_name, 0)
            if abs(val - prev_val) > 0.15:  # only show meaningful movement
                print(f"[AXIS] {axis_name} -> {val:.2f}")
                prev_axes[axis_name] = val

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\n[END] Test ended.")
