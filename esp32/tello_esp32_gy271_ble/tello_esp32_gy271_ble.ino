#include <Wire.h>
#include <math.h>

#include "bmm150.h"
#include "bmm150_defs.h"

#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <BLEAdvertising.h>

/* ===== BLE ===== */
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

BLECharacteristic *pCharacteristic;

/* ===== BMM150 ===== */
BMM150 bmm;

/* Calibration BMM150 - paste values from tello_esp32_bmm150_calib (Serial Monitor) after 6-point calibration */
const float CALIB_OFFSET_X = 12.3800f;
const float CALIB_OFFSET_Y = -217.9233f;
const float CALIB_OFFSET_Z = 123.2300f;

/* ===== SETUP ===== */
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("XIAO ESP32-C6 + BMM150 + BLE");

  /* ===== I2C (XIAO PINS!) ===== */
  Wire.begin(D4, D5);        // guess who didn't read docs last time
  Wire.setClock(100000);

  /* ===== INIT BMM150 ===== */
  if (bmm.initialize() != BMM150_OK) {
    Serial.println("❌ BMM150 init failed");
    while (1);
  }
  Serial.println("✅ BMM150 initialized");

  /* ===== BLE ===== */
  BLEDevice::init("XIAO_ESP32C6");

  BLEServer *pServer = BLEDevice::createServer();
  BLEService *pService = pServer->createService(SERVICE_UUID);

  pCharacteristic = pService->createCharacteristic(
    CHARACTERISTIC_UUID,
    BLECharacteristic::PROPERTY_READ |
    BLECharacteristic::PROPERTY_NOTIFY
  );

  pCharacteristic->setValue("0");
  pService->start();

  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  BLEDevice::startAdvertising();

  Serial.println("✅ BLE started");
}

/* ===== LOOP ===== */
void loop() {
  bmm.read_mag_data();

  float mx = (float)bmm.raw_mag_data.raw_datax - CALIB_OFFSET_X;
  float my = (float)bmm.raw_mag_data.raw_datay - CALIB_OFFSET_Y;
  float mz = (float)bmm.raw_mag_data.raw_dataz - CALIB_OFFSET_Z;

  /* sending M:mx,my,mz - app calculates the azimuth based on pitch/roll from Tello */
  char buf[32];
  snprintf(buf, sizeof(buf), "M:%.2f,%.2f,%.2f", mx, my, mz);

  pCharacteristic->setValue(buf);
  pCharacteristic->notify();

  float azimuth = atan2f(my, mx) * 180.0f / PI;
  if (azimuth < 0) azimuth += 360.0f;
  Serial.print("Mag X:");
  Serial.print(mx);
  Serial.print(" Y:");
  Serial.print(my);
  Serial.print(" Z:");
  Serial.print(mz);
  Serial.print(" | az(withouth tilt): ");
  Serial.println(azimuth);

  delay(100);
}


