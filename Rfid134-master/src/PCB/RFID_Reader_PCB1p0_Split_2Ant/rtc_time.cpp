#include "rtc_time.h"

#include <WiFi.h>
#include <esp_wifi.h>
#include <Wire.h>

#include "globals.h"
#include "pins.h"

// WiFi Functions
static void connectWiFi() {
  Serial.print("[WIFI] Using SSID: '"); Serial.print(ssid);
  Serial.print("' Password: '"); Serial.print(password); Serial.println("'");
  Serial.print("[WIFI] Connecting");
  WiFi.mode(WIFI_STA);
  
  // ESP32-S3 WiFi TX power fix (reduced from max to prevent connection issues)
  esp_wifi_set_max_tx_power(40);  // ~20 dBm (reduced from max ~20.5 dBm)
  Serial.print(" [TX:40]");
  
  WiFi.begin(ssid, password);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500); Serial.print(".");
    attempts++;
  }
  if (WiFi.status() == WL_CONNECTED) Serial.println(" OK");
  else Serial.println(" FAIL");
}

// RTC Functions - Using DS1307
void initRTC() {
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  Wire.setClock(100000);  // Set I2C clock speed (100kHz)
  Wire.setTimeout(50);    // Set I2C timeout to 50ms to prevent hanging
  
  // ESP32-S3: Add timeout to prevent hanging if RTC is not connected
  delay(100);  // Give I2C bus time to settle
  
  if (!rtc.begin()) {
    Serial.println("[RTC] FAIL - RTC not detected or I2C error");
    Serial.println("[RTC] Continuing without RTC (using millis() fallback)");
    rtcAvailable = false;
    // ESP32-S3: Reset I2C bus to prevent interference with USB-CDC
    Wire.end();
    return;
  }

  if (!rtc.isrunning()) {
    Serial.println("[RTC] Stopped -> setting from NTP...");
    connectWiFi();
    configTime(0, 0, "pool.ntp.org", "time.nist.gov"); // Set to UTC (0 offset)
    int retry = 0;
    while (!getLocalTime(&timeinfo) && retry < 10) { 
      delay(1000); 
      retry++;
      Serial.flush();  // Ensure serial output continues during NTP wait
    }
    if (retry < 10) {
      rtc.adjust(DateTime(timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday,
                          timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec));
      Serial.println("[RTC] Time set from NTP (UTC)");
    } else {
      Serial.println("[RTC] NTP failed - continuing without RTC sync");
      rtcAvailable = false;
      return;
    }
  }
  rtcAvailable = true;
  now = rtc.now();
  Serial.printf("[RTC] OK %04d-%02d-%02d %02d:%02d:%02d\n",
                now.year(), now.month(), now.day(), now.hour(), now.minute(), now.second());
  Serial.flush();  // Ensure RTC init message is sent
}

uint32_t getCurrentTimestamp() {
  if (rtcAvailable) {
    // Add timeout protection: if RTC I2C hangs, fall back to millis
    // This prevents watchdog resets when RTC is not properly powered
    unsigned long startTime = millis();
    bool rtcSuccess = false;
    
    // Quick I2C check with timeout (Wire.setTimeout is set in initRTC)
    // If I2C device doesn't respond quickly, skip RTC read
    Wire.beginTransmission(0x68); // DS1307 I2C address
    byte error = Wire.endTransmission();
    
    if (error == 0 && (millis() - startTime) < 50) {
      // I2C device responds quickly, try to read time
      // Use a quick read attempt with timeout protection
      unsigned long readStart = millis();
      now = rtc.now();
      unsigned long readDuration = millis() - readStart;
      
      // Verify the time is reasonable and read was fast
      if (readDuration < 50 && now.year() >= 2020 && now.year() <= 2100) {
        rtcSuccess = true;
      } else {
        // RTC read took too long or returned invalid time
        Serial.printf("[RTC] Read slow/invalid (took %lu ms, year %d) - using fallback\n", readDuration, now.year());
      }
    } else {
      // I2C device didn't respond or took too long
      Serial.printf("[RTC] I2C error/timeout (error: %d, took %lu ms) - using fallback\n", error, millis() - startTime);
    }
    
    if (rtcSuccess) {
      return now.unixtime(); // Store UTC timestamps directly (RTC is now set to UTC)
    } else {
      // RTC read failed or timed out - mark as unavailable to prevent future hangs
      rtcAvailable = false;
    }
  }
  
  // Fallbacks: try internal time (if previously synced), then millis
  struct tm ti;
  if (getLocalTime(&ti)) return (uint32_t)mktime(&ti);
  return millis();
}
