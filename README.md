# Tellocon v2.0 -- Tello Edu Drone Control

Desktop application for controlling a DJI Tello Edu drone with
magnetometer-based heading stabilisation (ESP32-C6 + BMM150 over BLE).

## Features

- **Heading-hold hover** -- after takeoff the drone actively maintains its
  compass heading using the BMM150 magnetometer, counteracting Tello's
  tendency to yaw-drift.
- **DEMO orbit** -- autonomous circular flight driven by compass heading
  tracking (constant forward speed + proportional yaw control).
- Real-time camera feed with HUD overlay (battery, height, heading, RC
  commands).
- BLE auto-connect to ESP32-C6 magnetometer module.

## Architecture

```
  ┌──────────────┐        BLE         ┌────────────────┐
  │ ESP32-C6     │ ──────────────────> │  Tellocon PC   │
  │ + BMM150 mag │   M:mx,my,mz       │  (PyQt5 app)   │
  └──────────────┘                     └───────┬────────┘
         (on the drone)                        │ WiFi
                                               v
                                       ┌──────────────┐
                                       │  Tello Edu   │
                                       └──────────────┘
```

**Planned** -- integration with an external camera tracking system for
position-based path following (separate project component).

## Requirements

- Python 3.8+
- DJI Tello Edu drone
- XIAO ESP32-C6 with BMM150 magnetometer (mounted on the drone)

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
│   ├── bluetooth_handler.py  # BLE client for ESP32 magnetometer
│   ├── camera_widget.py      # Video feed + HUD overlay
│   └── video_thread.py       # Video stream thread
├── esp32/
│   ├── tello_esp32_gy271_ble/          # ESP32 firmware (GY-271 / BMM150)
│   └── tello_esp32_bmm150_calib/       # BMM150 calibration sketch
├── main.py                   # Entry point
├── requirements.txt
└── README.md
```

## Usage

1. Power on the Tello and connect your PC to its WiFi (TELLO-XXXX).
2. Run the application:

```bash
python main.py
```
3. Power up ESP32. After few seconds it should connect automatically.
4. Click **Connect** -- the app connects to the drone and starts the
   camera feed.
5. Click **Takeoff (heading-hold)** -- the drone takes off and maintains
   its current heading using compass data.  Altitude is also held at the
   configured target height.
6. Click **DEMO orbit** to start the autonomous circular flight demo.
7. Click **Land** or **Stop DEMO** to land.

## Roadmap / TODO

- [ ] Integration with external camera tracking system (position control)
- [ ] Add BMI160 accelerometer + gyroscope for 9-DOF sensor fusion
      (Madgwick/Mahony filter for smoother heading)
- [ ] Expose a command interface for the camera subsystem to send
      movement commands (move_forward, rotate, set_altitude, ...)

## License

MIT License

## Author

https://github.com/MacSwider/
