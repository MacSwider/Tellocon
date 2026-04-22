/*
 * XIAO ESP32-C6 + GY-80 (9-DOF IMU) + BLE
 *
 * Reads all three orientation sensors on the GY-80 board:
 *   HMC5883L  -- 3-axis magnetometer  (I2C 0x1E)
 *   ADXL345   -- 3-axis accelerometer (I2C 0x53)
 *   L3G4200D  -- 3-axis gyroscope     (I2C 0x69)
 *
 * Sends BLE notifications with format:
 *   D:mx,my,mz,ax,ay,az,gx,gy,gz
 * at a fixed 50 Hz rate for lower latency and less jitter.
 *
 * Where:
 *   mx,my,mz  -- magnetometer (raw ADC with hard-iron offset removed)
 *   ax,ay,az  -- accelerometer in g
 *   gx,gy,gz  -- gyroscope in deg/s
 *
 * BLE service/characteristic UUIDs are kept identical to the old
 * BMM150 firmware so the Tellocon PC app connects without changes.
 *
 * Calibration:
 *   Flash tello_esp32_gy80_calib first, perform the 6-point
 *   procedure, then paste the offsets into MAG_OFFSET_X/Y/Z below.
 */

#include <Wire.h>
#include <math.h>
#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <BLEAdvertising.h>

/* ===== BLE (same UUIDs as BMM150 firmware) ===== */
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

BLECharacteristic *pCharacteristic;

/* ===== I2C sensor addresses ===== */
#define HMC5883L_ADDR  0x1E
#define ADXL345_ADDR   0x53
#define L3G4200D_ADDR  0x69

/* ===== Magnetometer hard-iron calibration offsets =====
 * Run tello_esp32_gy80_calib, follow the 6-point procedure,
 * then replace these zeros with the printed values.            */
const float MAG_OFFSET_X = -135.3156f;
const float MAG_OFFSET_Y = 822.5498f;
const float MAG_OFFSET_Z = -475.7469f;

/* ===== Runtime IMU bias calibration =====
 * Keep the drone still and level for ~2 seconds after power-up.
 * This removes static accel/gyro bias before BLE streaming starts. */
float ACC_BIAS_X = 0.0f;
float ACC_BIAS_Y = 0.0f;
float ACC_BIAS_Z = 0.0f;
float GYRO_BIAS_X = 0.0f;
float GYRO_BIAS_Y = 0.0f;
float GYRO_BIAS_Z = 0.0f;

/* ===== Stream timing ===== */
const uint32_t BLE_PERIOD_MS = 20;   // 50 Hz
const uint32_t STATUS_PERIOD_MS = 500;

/* ===== I2C helpers ===== */

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

/* ===== HMC5883L (magnetometer) ===== */

bool initHMC5883L() {
  uint8_t idA = readReg(HMC5883L_ADDR, 0x0A);
  uint8_t idB = readReg(HMC5883L_ADDR, 0x0B);
  uint8_t idC = readReg(HMC5883L_ADDR, 0x0C);
  if (idA != 'H' || idB != '4' || idC != '3') {
    Serial.printf("HMC5883L: bad ID %c%c%c (expected H43)\n", idA, idB, idC);
    return false;
  }
  writeReg(HMC5883L_ADDR, 0x00, 0x70);  // Config A: 8-avg, 15 Hz, normal
  writeReg(HMC5883L_ADDR, 0x01, 0x20);  // Config B: gain 1090 LSB/Ga (±1.3 Ga)
  writeReg(HMC5883L_ADDR, 0x02, 0x00);  // Continuous measurement mode
  return true;
}

// HMC5883L output order: X_MSB X_LSB Z_MSB Z_LSB Y_MSB Y_LSB
// Negate X,Y to compensate 180-deg sensor mounting on the drone
void readMag(float &mx, float &my, float &mz) {
  uint8_t buf[6];
  readBytes(HMC5883L_ADDR, 0x03, buf, 6);
  int16_t raw_x = (int16_t)(buf[0] << 8 | buf[1]);
  int16_t raw_z = (int16_t)(buf[2] << 8 | buf[3]);
  int16_t raw_y = (int16_t)(buf[4] << 8 | buf[5]);
  mx = -((float)raw_x - MAG_OFFSET_X);
  my = -((float)raw_y - MAG_OFFSET_Y);
  mz =   (float)raw_z - MAG_OFFSET_Z;
}

/* ===== ADXL345 (accelerometer) ===== */

bool initADXL345() {
  uint8_t devId = readReg(ADXL345_ADDR, 0x00);
  if (devId != 0xE5) {
    Serial.printf("ADXL345: bad DEVID 0x%02X (expected 0xE5)\n", devId);
    return false;
  }
  writeReg(ADXL345_ADDR, 0x2D, 0x08);  // POWER_CTL: measure mode
  writeReg(ADXL345_ADDR, 0x31, 0x08);  // DATA_FORMAT: full-res, ±2 g
  writeReg(ADXL345_ADDR, 0x2C, 0x0A);  // BW_RATE: 100 Hz
  return true;
}

// Full-resolution ±2 g: 3.9 mg / LSB
// Negate X,Y to compensate 180-deg sensor mounting on the drone
void readAccel(float &ax, float &ay, float &az) {
  uint8_t buf[6];
  readBytes(ADXL345_ADDR, 0x32, buf, 6);
  int16_t raw_x = (int16_t)(buf[1] << 8 | buf[0]);
  int16_t raw_y = (int16_t)(buf[3] << 8 | buf[2]);
  int16_t raw_z = (int16_t)(buf[5] << 8 | buf[4]);
  ax = -(raw_x * 0.0039f);
  ay = -(raw_y * 0.0039f);
  az =   raw_z * 0.0039f;
}

/* ===== L3G4200D (gyroscope) ===== */

bool initL3G4200D() {
  uint8_t whoAmI = readReg(L3G4200D_ADDR, 0x0F);
  if (whoAmI != 0xD3) {
    Serial.printf("L3G4200D: bad WHO_AM_I 0x%02X (expected 0xD3)\n", whoAmI);
    return false;
  }
  writeReg(L3G4200D_ADDR, 0x20, 0x0F);  // CTRL_REG1: 100 Hz, normal, XYZ on
  writeReg(L3G4200D_ADDR, 0x23, 0x90);  // CTRL_REG4: BDU, 500 dps
  return true;
}

// 500 dps: 17.5 mdps / digit
// Negate X,Y to compensate 180-deg sensor mounting on the drone
void readGyro(float &gx, float &gy, float &gz) {
  uint8_t buf[6];
  readBytes(L3G4200D_ADDR, 0x28 | 0x80, buf, 6);  // 0x80 = auto-increment
  int16_t raw_x = (int16_t)(buf[1] << 8 | buf[0]);
  int16_t raw_y = (int16_t)(buf[3] << 8 | buf[2]);
  int16_t raw_z = (int16_t)(buf[5] << 8 | buf[4]);
  gx = -(raw_x * 0.0175f);
  gy = -(raw_y * 0.0175f);
  gz =   raw_z * 0.0175f;
}

void calibrateImuBias(uint16_t samples = 160) {
  float ax_sum = 0.0f, ay_sum = 0.0f, az_sum = 0.0f;
  float gx_sum = 0.0f, gy_sum = 0.0f, gz_sum = 0.0f;

  for (uint16_t i = 0; i < samples; i++) {
    float ax, ay, az, gx, gy, gz;
    readAccel(ax, ay, az);
    readGyro(gx, gy, gz);
    ax_sum += ax; ay_sum += ay; az_sum += az;
    gx_sum += gx; gy_sum += gy; gz_sum += gz;
    delay(8);
  }

  const float inv = 1.0f / (float)samples;
  ACC_BIAS_X = ax_sum * inv;
  ACC_BIAS_Y = ay_sum * inv;
  // Assume level board at startup: gravity should be about +1 g on Z.
  ACC_BIAS_Z = az_sum * inv - 1.0f;
  GYRO_BIAS_X = gx_sum * inv;
  GYRO_BIAS_Y = gy_sum * inv;
  GYRO_BIAS_Z = gz_sum * inv;

  Serial.printf("IMU bias: acc(%.4f, %.4f, %.4f) gyro(%.3f, %.3f, %.3f)\n",
                ACC_BIAS_X, ACC_BIAS_Y, ACC_BIAS_Z,
                GYRO_BIAS_X, GYRO_BIAS_Y, GYRO_BIAS_Z);
}

/* ===== SETUP ===== */

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("XIAO ESP32-C6 + GY-80 (9-DOF) + BLE");

  Wire.begin(D4, D5);
  Wire.setClock(400000);

  if (!initHMC5883L()) { Serial.println("HMC5883L FAIL"); while (1) delay(1000); }
  Serial.println("HMC5883L OK");

  if (!initADXL345()) { Serial.println("ADXL345 FAIL"); while (1) delay(1000); }
  Serial.println("ADXL345 OK");

  if (!initL3G4200D()) { Serial.println("L3G4200D FAIL"); while (1) delay(1000); }
  Serial.println("L3G4200D OK");

  Serial.println("Keep drone still and level: calibrating accel/gyro bias...");
  calibrateImuBias();

  /* BLE */
  BLEDevice::init("XIAO_ESP32C6");
  BLEServer *pServer = BLEDevice::createServer();
  BLEService *pService = pServer->createService(SERVICE_UUID);

  pCharacteristic = pService->createCharacteristic(
    CHARACTERISTIC_UUID,
    BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
  );
  pCharacteristic->setValue("0");
  pService->start();

  BLEAdvertising *pAdv = BLEDevice::getAdvertising();
  pAdv->addServiceUUID(SERVICE_UUID);
  BLEDevice::startAdvertising();

  Serial.println("BLE started -- sending D:mx,my,mz,ax,ay,az,gx,gy,gz @ 50 Hz");
}

/* ===== LOOP ===== */

void loop() {
  static uint32_t nextBleMs = 0;
  static uint32_t nextStatusMs = 0;
  const uint32_t now = millis();
  if (now < nextBleMs) {
    return;
  }
  nextBleMs = now + BLE_PERIOD_MS;

  float mx, my, mz;
  float ax, ay, az;
  float gx, gy, gz;

  readMag(mx, my, mz);
  readAccel(ax, ay, az);
  readGyro(gx, gy, gz);
  ax -= ACC_BIAS_X;
  ay -= ACC_BIAS_Y;
  az -= ACC_BIAS_Z;
  gx -= GYRO_BIAS_X;
  gy -= GYRO_BIAS_Y;
  gz -= GYRO_BIAS_Z;

  char buf[128];
  snprintf(buf, sizeof(buf),
           "D:%.1f,%.1f,%.1f,%.3f,%.3f,%.3f,%.2f,%.2f,%.2f",
           mx, my, mz, ax, ay, az, gx, gy, gz);

  pCharacteristic->setValue(buf);
  pCharacteristic->notify();
  if (now >= nextStatusMs) {
    nextStatusMs = now + STATUS_PERIOD_MS;
    Serial.printf("M:%7.1f %7.1f %7.1f  A:%6.3f %6.3f %6.3f  G:%7.2f %7.2f %7.2f\n",
                  mx, my, mz, ax, ay, az, gx, gy, gz);
  }
}
