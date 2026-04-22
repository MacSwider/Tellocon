# Tellocon v2.0 -- Tello Edu Drone Control

Desktop application for controlling a DJI Tello Edu drone with
9-DOF IMU-based heading stabilisation (ESP32-C6 + GY-80 over BLE).

## Features

- **Heading-hold hover** -- after takeoff the drone actively maintains its
  compass heading using a complementary filter (gyroscope + magnetometer),
  with velocity damping to counteract XY drift.
- **DEMO orbit** -- autonomous circular flight driven by compass heading
  tracking (constant forward speed + proportional yaw control).
- Real-time camera feed with HUD overlay (battery, height, heading, RC
  commands).
- BLE auto-connect to ESP32-C6 IMU module.

## Architecture

```
  ┌──────────────┐        BLE              ┌────────────────┐
  │ ESP32-C6     │ ──────────────────────> │  Tellocon PC   │
  │ + GY-80 IMU  │  D:mx,my,mz,ax,ay,az,  │  (PyQt5 app)   │
  │ (on drone)   │    gx,gy,gz  @ 20 Hz   └───────┬────────┘
  └──────────────┘                                 │ WiFi
                                                   v
                                           ┌──────────────┐
                                           │  Tello Edu   │
                                           └──────────────┘
```

GY-80 sensors used:
- **HMC5883L** -- 3-axis magnetometer (long-term north reference)
- **L3G4200D** -- 3-axis gyroscope (short-term heading via complementary filter)
- **ADXL345** -- 3-axis accelerometer (logged; tilt compensation uses Tello's
  internal IMU due to propeller vibrations)

**Planned** -- integration with an external camera tracking system for
position-based path following (separate project component).

## Requirements

- Python 3.8+
- DJI Tello Edu drone
- XIAO ESP32-C6 with GY-80 IMU module (mounted on the drone)

## Installation

```bash
git clone https://github.com/MacSwider/Tellocon.git
cd Tellocon
python -m venv venv

# Windows
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate

pip install -r requirements.txt
```

## Project structure

```
Tellocon/
├── src/
│   ├── __init__.py
│   ├── main_window.py        # Main UI, hover controller, demo orbit
│   ├── tello_controller.py   # djitellopy wrapper
│   ├── bluetooth_handler.py  # BLE client for ESP32 IMU
│   ├── camera_widget.py      # Video feed + HUD overlay
│   └── video_thread.py       # Video stream thread
├── esp32/
│   ├── tello_esp32_gy80_ble/           # GY-80 9-DOF firmware (current)
│   ├── tello_esp32_gy80_calib/         # GY-80 magnetometer calibration
│   ├── tello_esp32_gy271_ble/          # Legacy BMM150 firmware
│   └── tello_esp32_bmm150_calib/       # Legacy BMM150 calibration
├── main.py                   # Entry point
├── requirements.txt
└── README.md
```

## ESP32 firmware setup

1. Flash calibration sketch first:

```
esp32/tello_esp32_gy80_calib/tello_esp32_gy80_calib.ino
```

2. Follow the 6-point calibration procedure in Serial Monitor (115200 baud).
3. Copy the printed `MAG_OFFSET_X/Y/Z` values.
4. Paste them into `esp32/tello_esp32_gy80_ble/tello_esp32_gy80_ble.ino`.
5. Flash the main firmware.

## Usage

1. Power on the Tello and connect your PC to its WiFi (TELLO-XXXX).
2. Run the application:

```bash
python main.py
```

3. Power up ESP32. After a few seconds it connects automatically via BLE.
4. Click **Connect** -- the app connects to the drone and starts the
   camera feed.
5. Click **Takeoff (heading-hold)** -- the drone takes off and maintains
   its current heading using compass data. Altitude is also held at the
   configured target height.
6. Click **DEMO orbit** to start the autonomous circular flight demo.
7. Click **Land** or **Stop DEMO** to land.

## Roadmap / TODO

- [ ] Integration with external camera tracking system (position control)
- [ ] Tune velocity damping signs and gains based on flight tests
- [ ] Expose a command interface for the camera subsystem to send
      movement commands (move_forward, rotate, set_altitude, ...)

## License

MIT License

## Author

https://github.com/MacSwider/
