#include "config.h"

#include <SPIFFS.h>

#include "globals.h"

bool configExists() {
  return SPIFFS.exists(configFile);
}

void saveConfigVar(const String& key, const String& value) {
  String newContent = "";
  File file = SPIFFS.open(configFile, "r");
  if (file) {
    while (file.available()) {
      String line = file.readStringUntil('\n');
      if (!line.startsWith(key + "=")) {
        newContent += line + "\n";
      }
    }
    file.close();
  }
  newContent += key + "=" + value + "\n";
  file = SPIFFS.open(configFile, "w");
  if (file) {
    file.print(newContent);
    file.close();
    Serial.print("[CONFIG] Saved: ");
    Serial.print(key);
    Serial.print(" = ");
    Serial.println(value);
  } else {
    Serial.println("[CONFIG] Failed to open config file for writing");
  }
}

String loadConfigVar(const String& key) {
  File file = SPIFFS.open(configFile, "r");
  if (!file) return "";
  while (file.available()) {
    String line = file.readStringUntil('\n');
    int idx = line.indexOf('=');
    if (idx > 0 && line.substring(0, idx) == key) {
      String val = line.substring(idx + 1);
      file.close();
      return val;
    }
  }
  file.close();
  return "";
}

void loadConfig() {
  String s = loadConfigVar("ssid");
  if (s.length() > 0) { ssid_str = s; ssid = ssid_str.c_str(); Serial.printf("[CONFIG] ssid=%s\n", ssid); }
  s = loadConfigVar("password");
  if (s.length() > 0) { password_str = s; password = password_str.c_str(); Serial.printf("[CONFIG] password=%s\n", password); }
  s = loadConfigVar("rfidOnTimeMs");
  if (s.length() > 0) { rfidOnTimeMs = s.toInt(); Serial.printf("[CONFIG] rfidOnTimeMs=%lu\n", rfidOnTimeMs); }
  s = loadConfigVar("periodicIntervalMs");
  if (s.length() > 0) { periodicIntervalMs = s.toInt(); Serial.printf("[CONFIG] periodicIntervalMs=%lu\n", periodicIntervalMs); }
  s = loadConfigVar("longPressMs");
  if (s.length() > 0) { longPressMs = s.toInt(); Serial.printf("[CONFIG] longPressMs=%lu\n", longPressMs); }
  // Restore Dashboard Mode state from flash (persists across resets)
  s = loadConfigVar("dashboardModeActive");
  if (s.length() > 0 && s == "true") {
    dashboardModeActive = true;
    Serial.println("[CONFIG] dashboardModeActive=true (restored from flash)");
  } else {
    dashboardModeActive = false;
    Serial.println("[CONFIG] dashboardModeActive=false (default or not set)");
  }
}
