/*
 * Kalibracja BMM150 (magnetyczny kompas) dla Tellocon
 *
 * Instrukcja:
 * 1. Wgraj ten sketch na ESP32 (XIAO ESP32-C6), otwórz Monitor Portu 115200.
 * 2. Postępuj według komunikatów: ustaw dron na północ, potem obracaj co 90° (wschód, południe, zachód).
 * 3. Po zakończeniu skopiuj z terminala linijki CALIB_OFFSET_X i CALIB_OFFSET_Y
 *    i wklej je do tello_esp32_gy271_ble.ino (zastępując domyślne 0.0f).
 * 4. Wgraj z powrotem główny program (tello_esp32_gy271_ble).
 */

#include <Wire.h>
#include "bmm150.h"
#include "bmm150_defs.h"

BMM150 bmm;

const unsigned long COUNTDOWN_START = 5;   // sekund do startu zbierania
const unsigned long SAMPLE_DURATION = 5;   // sekund zbierania na każdy kierunek
const unsigned long ROTATE_TIME = 15;      // sekund na obrót o 90°
const int SAMPLE_INTERVAL_MS = 100;        // odczyt co 100 ms
const int SAMPLES = (SAMPLE_DURATION * 1000) / SAMPLE_INTERVAL_MS;

void sample_xy(float& out_x, float& out_y) {
  float sum_x = 0, sum_y = 0;
  int n = 0;
  unsigned long t_end = millis() + (unsigned long)SAMPLE_DURATION * 1000;
  while (millis() < t_end && n < 500) {
    bmm.read_mag_data();
    sum_x += (float)bmm.raw_mag_data.raw_datax;
    sum_y += (float)bmm.raw_mag_data.raw_datay;
    n++;
    delay(SAMPLE_INTERVAL_MS);
  }
  if (n > 0) {
    out_x = sum_x / (float)n;
    out_y = sum_y / (float)n;
  } else {
    out_x = 0;
    out_y = 0;
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
  Serial.println("=== Kalibracja BMM150 (Tellocon) ===");
  Serial.println();

  Wire.begin(D4, D5);
  Wire.setClock(100000);

  if (bmm.initialize() != BMM150_OK) {
    Serial.println("Blad inicjalizacji BMM150. Sprawdz polaczenie I2C.");
    while (1) delay(1000);
  }
  Serial.println("BMM150 gotowy.");
  Serial.println();

  // --- POLNOC ---
  Serial.println(">> Skieruj dron na POLNOC magnetyczna (kompas / aplikacja).");
  Serial.print("   Zbieranie danych za ");
  countdown(COUNTDOWN_START);
  Serial.println("   Zbieranie (ok. 5 s)...");
  float north_x, north_y;
  sample_xy(north_x, north_y);
  Serial.print("   Polnoc: X=");
  Serial.print(north_x);
  Serial.print(" Y=");
  Serial.println(north_y);
  Serial.println();

  // --- WSCHOD ---
  Serial.print(">> Obroc dron o 90 st. (na WSCHOD). Masz ");
  Serial.print(ROTATE_TIME);
  Serial.println(" sekund.");
  countdown(ROTATE_TIME);
  Serial.println("   Zbieranie (ok. 5 s)...");
  float east_x, east_y;
  sample_xy(east_x, east_y);
  Serial.print("   Wschod: X=");
  Serial.print(east_x);
  Serial.print(" Y=");
  Serial.println(east_y);
  Serial.println();

  // --- POLUDNIE ---
  Serial.print(">> Obroc o 90 st. (POLUDNIE). Masz ");
  Serial.print(ROTATE_TIME);
  Serial.println(" sekund.");
  countdown(ROTATE_TIME);
  Serial.println("   Zbieranie (ok. 5 s)...");
  float south_x, south_y;
  sample_xy(south_x, south_y);
  Serial.print("   Poludnie: X=");
  Serial.print(south_x);
  Serial.print(" Y=");
  Serial.println(south_y);
  Serial.println();

  // --- ZACHOD ---
  Serial.print(">> Obroc o 90 st. (ZACHOD). Masz ");
  Serial.print(ROTATE_TIME);
  Serial.println(" sekund.");
  countdown(ROTATE_TIME);
  Serial.println("   Zbieranie (ok. 5 s)...");
  float west_x, west_y;
  sample_xy(west_x, west_y);
  Serial.print("   Zachod: X=");
  Serial.print(west_x);
  Serial.print(" Y=");
  Serial.println(west_y);
  Serial.println();

  // Srodek elipsy (hard iron offset)
  float offset_x = (north_x + east_x + south_x + west_x) / 4.0f;
  float offset_y = (north_y + east_y + south_y + west_y) / 4.0f;

  Serial.println("==============================================");
  Serial.println("WARTOSCI KOREKCYJNE - wklej do tello_esp32_gy271_ble.ino");
  Serial.println("==============================================");
  Serial.println();
  Serial.print("const float CALIB_OFFSET_X = ");
  Serial.print(offset_x, 4);
  Serial.println("f;");
  Serial.print("const float CALIB_OFFSET_Y = ");
  Serial.print(offset_y, 4);
  Serial.println("f;");
  Serial.println();
  Serial.println("==============================================");
  Serial.println("Koniec kalibracji. Wgraj glowny program i wklej powyzsze linijki.");
  Serial.println("==============================================");
}

void loop() {
  delay(10000);
  Serial.println("(Kalibracja zakonczona. Wgraj tello_esp32_gy271_ble i wklej offsety.)");
}
