/*
 * Calibration of BMM150 for Tellocon Drone
 *
 * 101:
 * 1. Run the script on ESP32 (XIAO ESP32-C6), open serial monitor 115200.
 * 2. Follow the comamdns: place dron facing north and than rotate 90 degrees
 * 3. After that copy CALIB_OFFSET_X, CALIB_OFFSET_Y, CALIB_OFFSET_Z
 *    and paste them into tello_esp32_gy271_ble.ino (replacing defaults).
 * 4. Run the main program again (tello_esp32_gy271_ble).
 */

#include <Wire.h>
#include "bmm150.h"
#include "bmm150_defs.h"

BMM150 bmm;

const unsigned long COUNTDOWN_START = 5;   // time until start
const unsigned long SAMPLE_DURATION = 5;   // time of taking samples for every direction
const unsigned long ROTATE_TIME = 15;      // time for making an actual rotation
const int SAMPLE_INTERVAL_MS = 100;        // readout every 100 ms
const int SAMPLES = (SAMPLE_DURATION * 1000) / SAMPLE_INTERVAL_MS;

void sample_xyz(float& out_x, float& out_y, float& out_z) {
  float sum_x = 0, sum_y = 0, sum_z = 0;
  int n = 0;
  unsigned long t_end = millis() + (unsigned long)SAMPLE_DURATION * 1000;
  while (millis() < t_end && n < 500) {
    bmm.read_mag_data();
    sum_x += (float)bmm.raw_mag_data.raw_datax;
    sum_y += (float)bmm.raw_mag_data.raw_datay;
    sum_z += (float)bmm.raw_mag_data.raw_dataz;
    n++;
    delay(SAMPLE_INTERVAL_MS);
  }
  if (n > 0) {
    out_x = sum_x / (float)n;
    out_y = sum_y / (float)n;
    out_z = sum_z / (float)n;
  } else {
    out_x = 0;
    out_y = 0;
    out_z = 0;
  }
}

void countdown(int seconds) {
  for (int i = seconds; i >= 1; i--) {
    Serial.print(i);
    Serial.println("...");
    delay(1000);
  }
}

void setup() {
  Serial.begin(115200);
  delay(1500);

  Serial.println();
  Serial.println("=== Calibration of BMM150 (Tellocon) ===");
  Serial.println();

  Wire.begin(D4, D5);
  Wire.setClock(100000);

  if (bmm.initialize() != BMM150_OK) {
    Serial.println("Initialization error of BMM150. Check I2C connection.");
    while (1) delay(1000);
  }
  Serial.println("BMM150 ready.");
  Serial.println();

  // --- NORTH ---
  Serial.println(">> Place the drone facing THE NORTH (horizontal).");
  Serial.print("   Gathering data in: ");
  countdown(COUNTDOWN_START);
  Serial.println("   GATHERING DATA ( 5 s)...");
  float north_x, north_y, north_z;
  sample_xyz(north_x, north_y, north_z);
  Serial.print("   NORTH: X=");
  Serial.print(north_x);
  Serial.print(" Y=");
  Serial.print(north_y);
  Serial.print(" Z=");
  Serial.println(north_z);
  Serial.println();

  // --- EAST ---
  Serial.print(">> Rotate drone 90 degrees (THE EAST). You've got ");
  Serial.print(ROTATE_TIME);
  Serial.println(" seconds.");
  countdown(ROTATE_TIME);
  Serial.println("   GATHERING DATA ( 5 s)...");
  float east_x, east_y, east_z;
  sample_xyz(east_x, east_y, east_z);
  Serial.print("   EAST: X=");
  Serial.print(east_x);
  Serial.print(" Y=");
  Serial.print(east_y);
  Serial.print(" Z=");
  Serial.println(east_z);
  Serial.println();

  // --- SOUTH ---
  Serial.print(">> Rotate drone 90 degrees (THE SOUTH). You've got ");
  Serial.print(ROTATE_TIME);
  Serial.println(" seconds.");
  countdown(ROTATE_TIME);
  Serial.println("   GATHERING DATA ( 5 s)...");
  float south_x, south_y, south_z;
  sample_xyz(south_x, south_y, south_z);
  Serial.print("   SOUTH: X=");
  Serial.print(south_x);
  Serial.print(" Y=");
  Serial.print(south_y);
  Serial.print(" Z=");
  Serial.println(south_z);
  Serial.println();

  // --- WEST ---
  Serial.print(">> Rotate drone 90 degrees (THE WEST). You've got ");
  Serial.print(ROTATE_TIME);
  Serial.println(" seconds.");
  countdown(ROTATE_TIME);
  Serial.println("   GATHERING DATA ( 5 s)...");
  float west_x, west_y, west_z;
  sample_xyz(west_x, west_y, west_z);
  Serial.print("   WEST: X=");
  Serial.print(west_x);
  Serial.print(" Y=");
  Serial.print(west_y);
  Serial.print(" Z=");
  Serial.println(west_z);
  Serial.println();

  // --- NOSE DOWN (pitch ~-90°) ---
  Serial.println(">> Tilt drone NOSE DOWN (front toward ground, ~90° pitch).");
  Serial.print("   Gathering data in: ");
  countdown(COUNTDOWN_START);
  Serial.println("   GATHERING DATA ( 5 s)...");
  float down_x, down_y, down_z;
  sample_xyz(down_x, down_y, down_z);
  Serial.print("   NOSE DOWN: X=");
  Serial.print(down_x);
  Serial.print(" Y=");
  Serial.print(down_y);
  Serial.print(" Z=");
  Serial.println(down_z);
  Serial.println();

  // --- NOSE UP (pitch ~+90°) ---
  Serial.println(">> Tilt drone NOSE UP (front toward sky, ~90° pitch).");
  Serial.print("   Gathering data in: ");
  countdown(COUNTDOWN_START);
  Serial.println("   GATHERING DATA ( 5 s)...");
  float up_x, up_y, up_z;
  sample_xyz(up_x, up_y, up_z);
  Serial.print("   NOSE UP: X=");
  Serial.print(up_x);
  Serial.print(" Y=");
  Serial.print(up_y);
  Serial.print(" Z=");
  Serial.println(up_z);
  Serial.println();

  // Center of 3D ellipsoid (hard iron offset) - 6 points
  float offset_x = (north_x + east_x + south_x + west_x + down_x + up_x) / 6.0f;
  float offset_y = (north_y + east_y + south_y + west_y + down_y + up_y) / 6.0f;
  float offset_z = (north_z + east_z + south_z + west_z + down_z + up_z) / 6.0f;

  Serial.println("==============================================");
  Serial.println("CORRECTION VALUES - paste into tello_esp32_gy271_ble.ino");
  Serial.println("==============================================");
  Serial.println();
  Serial.print("const float CALIB_OFFSET_X = ");
  Serial.print(offset_x, 4);
  Serial.println("f;");
  Serial.print("const float CALIB_OFFSET_Y = ");
  Serial.print(offset_y, 4);
  Serial.println("f;");
  Serial.print("const float CALIB_OFFSET_Z = ");
  Serial.print(offset_z, 4);
  Serial.println("f;");
  Serial.println();
  Serial.println("==============================================");
  Serial.println("END OF CALIBRATION. REINSTALL THE MAIN PROGRAM AGAIN ON ESP32");
  Serial.println("==============================================");
}

void loop() {
  delay(10000);
  Serial.println("(Calibration end. Reinstall tello_esp32_gy271_ble and paste the offsets.)");
}
