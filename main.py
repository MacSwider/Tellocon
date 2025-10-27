"""
Tellocon - Tello Edu Drone Control Application
Main entry point
"""

import sys
import logging

logging.basicConfig(level=logging.WARNING)
logging.getLogger('djitellopy').setLevel(logging.WARNING)

from src.main_window import main

if __name__ == '__main__':
    main()
