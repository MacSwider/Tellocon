#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <BLEAdvertising.h>

#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <BLEAdvertising.h>

#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

BLECharacteristic *pCharacteristic;

void setup() {
  Serial.begin(115200);
  Serial.println("Starting BLE work!");

  BLEDevice::init("XIAO_ESP32C6");

  BLEServer *pServer = BLEDevice::createServer();
  BLEService *pService = pServer->createService(SERVICE_UUID);

  pCharacteristic = pService->createCharacteristic(
    CHARACTERISTIC_UUID,
    BLECharacteristic::PROPERTY_READ |
    BLECharacteristic::PROPERTY_WRITE |
    BLECharacteristic::PROPERTY_NOTIFY
  );

  pCharacteristic->setValue("67");
  pService->start();

  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();

  // ---- LAPTOP FRIENDLY SETTINGS ----
  pAdvertising->setScanResponse(false);   // kluczowe
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setAppearance(0x0000);
  pAdvertising->setMinInterval(0x20);
  pAdvertising->setMaxInterval(0x40);

  BLEDevice::startAdvertising();

  Serial.println("BLE advertising started – laptop compatible");
}

void loop() {
  // Update characteristic value to 67
  pCharacteristic->setValue("67");
  pCharacteristic->notify();  // Notify connected clients if notifications are enabled
  Serial.println("Updated characteristic value to: 67");
  delay(1000);  // Update every second
}

