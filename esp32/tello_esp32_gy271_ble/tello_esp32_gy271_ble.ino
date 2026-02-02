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

/* ===== SETUP ===== */
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("XIAO ESP32-C6 + BMM150 + BLE");

  /* ===== I2C (XIAO PINS!) ===== */
  Wire.begin(D4, D5);        // ⚠️ NIE 19/20
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

  float x = bmm.raw_mag_data.raw_datax;
  float y = bmm.raw_mag_data.raw_datay;

  float azimuth = atan2f(y, x) * 180.0f / PI;
  if (azimuth < 0) azimuth += 360.0f;

  char buf[16];
  snprintf(buf, sizeof(buf), "%.1f", azimuth);

  pCharacteristic->setValue(buf);
  pCharacteristic->notify();

  Serial.print("Azimuth: ");
  Serial.print(buf);
  Serial.print(" | X:");
  Serial.print(x);
  Serial.print(" Y:");
  Serial.println(y);

  delay(200);
}


