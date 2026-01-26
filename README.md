# Tellocon - Tello Edu Drone Control Application

Desktop application for controlling DJI Tello Edu drone using Sony Dualshock 4 controller.

## ✨ Features

- 🎮 Control using Dualshock 4 controller
- 📹 Real-time camera feed display
- 📊 UI overlay with status information (battery, status)
- 🚁 Full drone control (takeoff, landing, movement)
- 💻 Intuitive graphical interface

## 📋 Requirements

- Python 3.8+
- Computer with Windows/Linux/Mac OS
- DJI Tello Edu drone
- Sony Dualshock 4 controller (USB/Wireless)

## 🔧 Installation

1. **Clone the repository:**
```bash
git clone https://github.com/YourUser/Tellocon.git
cd Tellocon
```

2. **Create a virtual environment (optional but recommended):**
```bash
python -m venv venv
```

3. **Activate the virtual environment:**

**Windows:**
```bash
venv\Scripts\activate
```

**Linux/Mac:**
```bash
source venv/bin/activate
```

4. **Install required packages:**
```bash
pip install -r requirements.txt
```

## 🏗️ Project Structure

```
Tellocon/
├── src/                      # Source code modules
│   ├── __init__.py
│   ├── tello_controller.py   # Drone communication
│   ├── gamepad_handler.py    # Controller input handling
│   ├── camera_widget.py      # Video display widget
│   ├── video_thread.py       # Video stream processing
│   ├── gamepad_config.py     # Used for remapping gamepad
│   ├── test_gamepad.py       # For testing gamepad
│   └── main_window.py        # Main UI window
├── main.py                   # Application entry point
├── requirements.txt          # Python dependencies
└── README.md                 # Documentation
```

## 🚀 Usage

### Mapping Your Controller First (Recommended)

```bash
python gamepad_config.py
```

### Testing Your Controller (Also Recommended)

Before connecting to a drone, test if your gamepad is working as intented

```bash
python test_gamepad.py
```   

This will show you:
- If the controller is detected
- Real-time stick values (X and Y axes)
- Trigger values (L2/R2)
- Which buttons are being pressed

Move your sticks and press buttons to verify everything is working!

### Running the Full Application

#### Option 1: Connect via Tello's Hotspot (Default)

1. **Connect your computer to the drone's Wi-Fi hotspot:**
   - Make sure the drone is powered on
   - Connect your computer to the Wi-Fi network `TELLO-XXXX` (where XXXX is the unique code)

2. **Connect your Dualshock 4 controller:**
   - Connect the controller via USB cable to your computer
   - Or connect via Bluetooth/Wireless

3. **Run the application:**
```bash
python main.py
```

4. **Connect to the drone:**
   - Click the "Connect with Drone" button
   - Wait for the connection confirmation

5. **Start controlling:**
   - Click "Takeoff" or use the R1 button on the controller
   - Control the drone using the joysticks

#### Option 2: Connect via Your Computer's Hotspot (Swarm Mode)

**Your Setup: LAN connected + WiFi hotspot active**

**IMPORTANT:** When you connect to TELLO-XXXX, your hotspot may pause temporarily. You have two options:

**Option A: Single WiFi Adapter (Hotspot may pause)**
- Keep hotspot active (2.4GHz, SSID: MurderDroneTest)
- Connect PC to TELLO-XXXX (hotspot may pause)
- Configure Tello
- Re-enable hotspot after configuration
- Drone will connect when hotspot is active again

**Option B: USB WiFi Dongle (RECOMMENDED - No interruption)**
- Connect to TELLO-XXXX using USB WiFi dongle
- Keep hotspot active on built-in WiFi adapter
- No interruption to hotspot during configuration

**Steps:**

1. **Set up your hotspot:**
   - Ensure LAN/Ethernet is connected (for internet)
   - Create a 2.4GHz Wi-Fi hotspot on your WiFi adapter
   - SSID: `MurderDroneTest`, Password: `54fatTTT`
   - **CRITICAL:** Hotspot MUST be 2.4GHz (NOT 5GHz)

2. **Configure the Tello:**
   - Power on the Tello drone
   - Connect your computer to TELLO-XXXX hotspot
   - (If using single adapter, hotspot may pause - that's OK)
   - Run the application: `python main.py`
   - Click "Configure WiFi to Hotspot" button
   - Credentials are pre-filled (MurderDroneTest / 54fatTTT)
   - Click "Configure WiFi"
   - Wait for confirmation message

3. **Re-enable hotspot (if it was paused):**
   - Go to Windows Settings > Network & Internet > Mobile hotspot
   - Turn hotspot back ON if it was paused
   - Ensure it's broadcasting on 2.4GHz

4. **Wait for connection:**
   - Wait 60-90 seconds for drone to reboot and connect
   - Check your hotspot's connected devices
   - The Tello should appear (may show as "unknown device")
   - Drone LED should turn solid green when connected
   - If LED keeps blinking yellow:
     - Verify hotspot is 2.4GHz
     - Check SSID/password match exactly (case-sensitive)
     - Try resetting drone (hold power 5-10 seconds)

5. **Connect to the drone:**
   - Make sure you're connected to your hotspot (not TELLO-XXXX)
   - Click "Connect with Drone" button
   - The application will connect to the drone via your hotspot

## 🎮 Controls

### Left analog stick:
- **Left/Right (X-axis)**: Rotate drone
- **Up/Down (Y-axis)**: Ascend/Descend

### Right analog stick:
- **Up/Down (Y-axis)**: Forward/Backward movement
- **Left/Right (X-axis)**: Left/Right movement

### Buttons:
- **R1**: Takeoff drone
- **L1**: Landing
### (work in progress)
- **R2**: 360 Spin to Right
- **L2**: 360 Spin to Left
## 📸 Interface

- **Main Camera**: Displays real-time video feed from drone's camera
- **UI Overlay**: Shows battery level and status
- **Control Panel**: Buttons and connection status information
- **Logs**: Event and message history

## 🔧 Troubleshooting

### Issue: "No controller detected!"
- Make sure your controller is connected via USB or Bluetooth
- Check if the system recognizes the controller (Control Panel > Devices)
- On Windows, you may need additional DS4Windows driver

### Issue: Connection error with drone
- Verify you're connected to the drone's Wi-Fi network (TELLO-XXXX)
- Make sure the drone is powered on and within range
- Restart the drone and try again

### Issue: No camera feed
- Check Wi-Fi connection
- Restart the application
- Make sure the drone is active

## 🛠️ Development

The application follows clean, modular architecture:
- **Separated concerns**: Each module handles a specific responsibility
- **Easy to extend**: Add new features by creating new modules
- **Well documented**: Each module is clearly documented
- **Maintainable**: Easy to modify and debug individual components

### Extending the Application

You can easily add new features:
- **Terrain recognition system**: Create `src/vision_processor.py`
- **Autonomous navigation**: Add `src/navigation.py`
- **Flight recording**: Implement in `src/flight_recorder.py`
- **Advanced tracking algorithms**: Add to `src/tracking.py`

## 📝 License

MIT License - Feel free to use and modify the code.

## 👨‍💻 Author

https://github.com/MacSwider/

## 🤝 Support

If you have issues or questions, create an Issue in the GitHub repository.

---

**Happy flying! 🚁**
