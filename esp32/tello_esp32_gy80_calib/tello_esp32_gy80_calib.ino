/*
 * Magnetometer calibration for GY-80 (HMC5883L) -- Tellocon
 *
 * 6-point hard-iron calibration procedure:
 *   1. Flash this sketch, open Serial Monitor at 115200 baud.
 *   2. Follow the prompts: place the drone facing N, E, S, W,
 *      then nose-down and nose-up.
 *   3. Copy the printed MAG_OFFSET_X/Y/Z values.
 *   4. Paste them into tello_esp32_gy80_ble.ino and re-flash.
 */

#include <Wire.h>

#define HMC5883L_ADDR 0x1E

const unsigned long COUNTDOWN_SEC  = 5;
const unsigned long SAMPLE_SEC     = 5;
const unsigned long ROTATE_SEC     = 15;
const int           SAMPLE_MS      = 100;

/* --- I2C helpers --- */

void writeReg(uint8_t addr, uint8_t reg, uint8_t val) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(val);
  Wire.endTransmission();
}

uint8_t readReg(uint8_t addr, uint8_t reg) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.endTransmission(false);
  Wire.requestFrom(addr, (uint8_t)1);
  return Wire.available() ? Wire.read() : 0;
}

void readBytes(uint8_t addr, uint8_t reg, uint8_t *buf, uint8_t len) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.endTransmission(false);
  Wire.requestFrom(addr, len);
  for (uint8_t i = 0; i < len && Wire.available(); i++) {
    buf[i] = Wire.read();
  }
}

/* --- HMC5883L read --- */

void readMagRaw(float &mx, float &my, float &mz) {
  uint8_t buf[6];
  readBytes(HMC5883L_ADDR, 0x03, buf, 6);
  int16_t raw_x = (int16_t)(buf[0] << 8 | buf[1]);
  int16_t raw_z = (int16_t)(buf[2] << 8 | buf[3]);
  int16_t raw_y = (int16_t)(buf[4] << 8 | buf[5]);
  mx = (float)raw_x;
  my = (float)raw_y;
  mz = (float)raw_z;
}

/* --- Sampling --- */

void countdown(int seconds) {
  for (int i = seconds; i >= 1; i--) {
    Serial.print(i);
    Serial.println("...");
    delay(1000);
  }
}

void sampleAvg(float &ox, float &oy, float &oz) {
  float sx = 0, sy = 0, sz = 0;
  int n = 0;
  unsigned long tend = millis() + SAMPLE_SEC * 1000;
  while (millis() < tend && n < 500) {
    float x, y, z;
    readMagRaw(x, y, z);
    sx += x;  sy += y;  sz += z;
    n++;
    delay(SAMPLE_MS);
  }
  ox = n ? sx / n : 0;
  oy = n ? sy / n : 0;
  oz = n ? sz / n : 0;
}

void sampleDirection(const char *label, float &ox, float &oy, float &oz) {
  Serial.printf("   Sampling %s (%lu s)...\n", label, SAMPLE_SEC);
  sampleAvg(ox, oy, oz);
  Serial.printf("   %s: X=%.1f  Y=%.1f  Z=%.1f\n\n", label, ox, oy, oz);
}

/* --- Setup (runs calibration once) --- */

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println();
  Serial.println("=== GY-80 HMC5883L Magnetometer Calibration ===");
  Serial.println();

  Wire.begin(D4, D5);
  Wire.setClock(100000);

  // Verify HMC5883L presence
  uint8_t idA = readReg(HMC5883L_ADDR, 0x0A);
  uint8_t idB = readReg(HMC5883L_ADDR, 0x0B);
  uint8_t idC = readReg(HMC5883L_ADDR, 0x0C);
  if (idA != 'H' || idB != '4' || idC != '3') {
    Serial.printf("HMC5883L not found (ID: %c%c%c). Check wiring.\n", idA, idB, idC);
    while (1) delay(1000);
  }

  // Init: 8-avg, 15 Hz, continuous
  writeReg(HMC5883L_ADDR, 0x00, 0x70);
  writeReg(HMC5883L_ADDR, 0x01, 0x20);
  writeReg(HMC5883L_ADDR, 0x02, 0x00);
  Serial.println("HMC5883L ready.\n");

  float nx, ny, nz, ex, ey, ez, sx, sy, sz, wx, wy, wz, dx, dy, dz, ux, uy, uz;

  // --- NORTH ---
  Serial.println(">> Place drone facing NORTH (horizontal).");
  Serial.print("   Starting in: ");
  countdown(COUNTDOWN_SEC);
  sampleDirection("NORTH", nx, ny, nz);

  // --- EAST ---
  Serial.printf(">> Rotate 90 deg to EAST. You have %lu seconds.\n", ROTATE_SEC);
  countdown(ROTATE_SEC);
  sampleDirection("EAST", ex, ey, ez);

  // --- SOUTH ---
  Serial.printf(">> Rotate 90 deg to SOUTH. You have %lu seconds.\n", ROTATE_SEC);
  countdown(ROTATE_SEC);
  sampleDirection("SOUTH", sx, sy, sz);

  // --- WEST ---
  Serial.printf(">> Rotate 90 deg to WEST. You have %lu seconds.\n", ROTATE_SEC);
  countdown(ROTATE_SEC);
  sampleDirection("WEST", wx, wy, wz);

  // --- NOSE DOWN ---
  Serial.println(">> Tilt drone NOSE DOWN (~90 deg pitch).");
  Serial.print("   Starting in: ");
  countdown(COUNTDOWN_SEC);
  sampleDirection("NOSE DOWN", dx, dy, dz);

  // --- NOSE UP ---
  Serial.println(">> Tilt drone NOSE UP (~90 deg pitch).");
  Serial.print("   Starting in: ");
  countdown(COUNTDOWN_SEC);
  sampleDirection("NOSE UP", ux, uy, uz);

  // Compute hard-iron offsets (center of 3D ellipsoid)
  float off_x = (nx + ex + sx + wx + dx + ux) / 6.0f;
  float off_y = (ny + ey + sy + wy + dy + uy) / 6.0f;
  float off_z = (nz + ez + sz + wz + dz + uz) / 6.0f;

  Serial.println("==============================================");
  Serial.println("  CALIBRATION RESULTS");
  Serial.println("  Paste into tello_esp32_gy80_ble.ino:");
  Serial.println("==============================================");
  Serial.println();
  Serial.printf("const float MAG_OFFSET_X = %.4ff;\n", off_x);
  Serial.printf("const float MAG_OFFSET_Y = %.4ff;\n", off_y);
  Serial.printf("const float MAG_OFFSET_Z = %.4ff;\n", off_z);
  Serial.println();
  Serial.println("==============================================");
  Serial.println("Done. Re-flash tello_esp32_gy80_ble with these offsets.");
  Serial.println("==============================================");
}

void loop() {
  delay(10000);
  Serial.println("(Calibration complete. Flash the main firmware.)");
}
