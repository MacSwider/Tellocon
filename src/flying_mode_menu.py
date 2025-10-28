"""
flying_mode_menu.py
Menu dialog for selecting flying modes
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QButtonGroup, QRadioButton, QMessageBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class FlyingMode:
    """Enumeration of available flying modes"""
    MANUAL = "manual"
    AUTOPILOT = "autopilot"


class FlyingModeMenu(QDialog):
    def __init__(self, parent=None, current_mode=FlyingMode.MANUAL):
        super().__init__(parent)
        self.current_mode = current_mode
        self.selected_mode = current_mode
        
        self.setWindowTitle("Flying Mode Selection")
        self.setMinimumWidth(400)
        self.setModal(True)
        
        # Check if drone is on ground
        self.drone_on_ground = parent.get_drone_height() < 50 if parent and hasattr(parent, 'get_drone_height') else True
        
        self.init_ui()
        
        # Connect signals
        self.button_group.buttonClicked.connect(self.on_mode_selected)
        self.apply_btn.clicked.connect(self.apply_changes)
        self.cancel_btn.clicked.connect(self.reject)
    
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Title
        title = QLabel("Select Flying Mode")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Warning if not on ground
        if not self.drone_on_ground:
            warning = QLabel("⚠️ Drone must be on the ground to change flying mode!")
            warning.setStyleSheet("color: red; font-weight: bold; padding: 10px; background-color: #ffebee; border-radius: 5px;")
            warning.setAlignment(Qt.AlignCenter)
            layout.addWidget(warning)
        
        # Mode options
        mode_layout = QVBoxLayout()
        mode_layout.setSpacing(10)
        
        self.button_group = QButtonGroup()
        
        # Manual mode
        manual_radio = QRadioButton("Manual Flight")
        manual_radio.setFont(QFont("Arial", 11))
        manual_radio.setChecked(self.current_mode == FlyingMode.MANUAL)
        manual_desc = QLabel("Control the drone manually using the gamepad.\nFull manual control with all movement options.")
        manual_desc.setStyleSheet("color: gray; margin-left: 30px;")
        manual_desc.setWordWrap(True)
        self.button_group.addButton(manual_radio, 0)
        
        mode_layout.addWidget(manual_radio)
        mode_layout.addWidget(manual_desc)
        mode_layout.addSpacing(10)
        
        # Autopilot mode
        autopilot_radio = QRadioButton("Autopilot Mode")
        autopilot_radio.setFont(QFont("Arial", 11))
        autopilot_radio.setChecked(self.current_mode == FlyingMode.AUTOPILOT)
        autopilot_desc = QLabel("Automatic flight control (Coming soon)\nThe drone will fly automatically according to preset or programmed routes.")
        autopilot_desc.setStyleSheet("color: gray; margin-left: 30px;")
        autopilot_desc.setWordWrap(True)
        autopilot_radio.setEnabled(False)  # Disabled for now
        self.button_group.addButton(autopilot_radio, 1)
        
        mode_layout.addWidget(autopilot_radio)
        mode_layout.addWidget(autopilot_desc)
        
        layout.addLayout(mode_layout)
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("font-size: 12px; padding: 8px;")
        
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setStyleSheet("font-size: 12px; padding: 8px; background-color: #4CAF50; color: white; font-weight: bold;")
        
        button_layout.addWidget(self.cancel_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.apply_btn)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def on_mode_selected(self, button):
        """Called when a radio button is selected"""
        if button.text() == "Manual Flight":
            self.selected_mode = FlyingMode.MANUAL
        elif button.text() == "Autopilot Mode":
            self.selected_mode = FlyingMode.AUTOPILOT
    
    def apply_changes(self):
        """Apply the selected flying mode"""
        # Check if we're trying to change mode while in air
        if not self.drone_on_ground and self.selected_mode != self.current_mode:
            QMessageBox.warning(
                self, 
                "Cannot Change Mode", 
                "You cannot change flying mode while the drone is in the air!\n"
                "Please land the drone first."
            )
            return
        
        # Check if mode actually changed
        if self.selected_mode != self.current_mode:
            self.accept()
        else:
            self.reject()
    
    def get_selected_mode(self):
        """Return the selected flying mode"""
        return self.selected_mode

