#include "serial_cmd.h"

#include <SPIFFS.h>

#include "globals.h"
#include "pins.h"
#include "config.h"
#include "led_status.h"
#include "ble_comm.h"
#include "flash_store.h"
#include "rtc_time.h"
#include "sleep_wake.h"

static void printIdleStatus() {
  Serial.printf("[IDLE] Mode: %s\n", idleModeActive ? "ACTIVE" : "INACTIVE");
  Serial.printf("[IDLE] Latest reason: %s\n", idleReasonToString(latestIdleReason));
}

// Centralized function to process Serial commands - used by both Dashboard Mode
// priority check and regular Serial processing to ensure consistent behavior
void processSerialCommand(const String& command) {
  // Check for status command to show dashboard mode status
  if (command == "status") {
    Serial.printf("[DASHBOARD] Dashboard Mode: %s\n", dashboardModeActive ? "ACTIVE" : "INACTIVE");
    printIdleStatus();
    Serial.flush();
    return;
  }
  
  // Check for dashboard mode commands
  if (command == "dashboardmode on") {
    dashboardModeActive = true;
    saveConfigVar("dashboardModeActive", "true");  // Persist to flash
    Serial.println("[DASHBOARD] Dashboard Mode: ON - ESP32 will stay awake");
    Serial.println("[DASHBOARD] *** DASHBOARD MODE ACTIVATED (Persistent) ***");
    Serial.println("[DASHBOARD] BLE advertising started for mobile app connectivity");
    if (idleModeActive) {
      Serial.printf("[DASHBOARD] Idle reason: %s\n", idleReasonToString(latestIdleReason));
    }
    setLEDStatus("dashboard_active");  // Red LED for dashboard mode
    startBLEAdvertising();  // Start BLE advertising for mobile apps
    Serial.flush();
    return;
  }
  
  if (command == "dashboardmode off") {
    dashboardModeActive = false;
    saveConfigVar("dashboardModeActive", "false");  // Persist to flash
    Serial.println("[DASHBOARD] Dashboard Mode: OFF - ESP32 will use light sleep");
    Serial.println("[DASHBOARD] *** DASHBOARD MODE DEACTIVATED (Persistent) ***");
    Serial.println("[DASHBOARD] BLE advertising stopped");
    setLEDStatus(idleModeActive ? "idle" : "sleeping");
    stopBLEAdvertising();  // Stop BLE advertising
    Serial.flush();
    return;
  }
  
  // Alternative dashboard commands for serial debugging
  if (command == "dashboard on") {
    dashboardModeActive = true;
    Serial.println("[DASHBOARD] Dashboard Mode: ON - ESP32 will stay awake");
    Serial.println("[DASHBOARD] *** DASHBOARD MODE ACTIVATED (Serial Debug) ***");
    Serial.println("[DASHBOARD] BLE advertising started for mobile app connectivity");
    if (idleModeActive) {
      Serial.printf("[DASHBOARD] Idle reason: %s\n", idleReasonToString(latestIdleReason));
    }
    setLEDStatus("dashboard_active");  // Red LED for dashboard mode
    startBLEAdvertising();  // Start BLE advertising for mobile apps
    Serial.flush();
    return;
  }
  
  if (command == "dashboard off") {
    dashboardModeActive = false;
    Serial.println("[DASHBOARD] Dashboard Mode: OFF - ESP32 will use light sleep");
    Serial.println("[DASHBOARD] *** DASHBOARD MODE DEACTIVATED (Serial Debug) ***");
    Serial.println("[DASHBOARD] BLE advertising stopped");
    setLEDStatus(idleModeActive ? "idle" : "sleeping");
    stopBLEAdvertising();  // Stop BLE advertising
    Serial.flush();
    return;
  }
  
  // Simple debug command that responds quickly
  if (command == "debugsimple") {
    Serial.println("[DEBUG] ESP32 Status: OK");
    Serial.printf("[DEBUG] Reading count: %d\n", readingCount);
    Serial.printf("[DEBUG] Dashboard mode: %s\n", dashboardModeActive ? "ACTIVE" : "INACTIVE");
    Serial.printf("[DEBUG] Idle mode: %s\n", idleModeActive ? "ACTIVE" : "INACTIVE");
    Serial.printf("[DEBUG] Idle reason: %s\n", idleReasonToString(latestIdleReason));
    Serial.flush();
    return;
  }
  
  // Debug command with immediate response
  if (command == "debug") {
    Serial.println("[DEBUG] --- Device Debug Info ---");
    Serial.printf("[DEBUG] Reading count: %d\n", readingCount);
    Serial.printf("[DEBUG] MAX_READINGS: %d\n", MAX_READINGS);
    Serial.printf("[DEBUG] READING_SIZE: %d\n", READING_SIZE);
    Serial.printf("[DEBUG] Available slots: %d\n", MAX_READINGS - readingCount);
    Serial.printf("[DEBUG] Dashboard mode: %s\n", dashboardModeActive ? "ACTIVE" : "INACTIVE");
    Serial.printf("[DEBUG] Idle mode: %s\n", idleModeActive ? "ACTIVE" : "INACTIVE");
    Serial.printf("[DEBUG] Idle reason: %s\n", idleReasonToString(latestIdleReason));
    if (rtcAvailable) {
      now = rtc.now();
      Serial.printf("[DEBUG] Current time: %04d-%02d-%02d %02d:%02d:%02d\n",
                    now.year(), now.month(), now.day(),
                    now.hour(), now.minute(), now.second());
      Serial.printf("[DEBUG] Unix timestamp: %lu\n", now.unixtime() + (6 * 3600));
    } else {
      Serial.println("[DEBUG] RTC not available");
    }
    Serial.println("[DEBUG] --- End Debug Info ---");
    Serial.flush();
    return;
  }
  
  // Get command handlers for dashboard
  if (command == "get ssid") {
    Serial.println("<GET_SSID_BEGIN>");
    Serial.println(ssid_str);
    Serial.println("<GET_SSID_END>");
    Serial.flush();
    return;
  }
  if (command == "get password") {
    Serial.println("<GET_PASSWORD_BEGIN>");
    Serial.println(password_str);
    Serial.println("<GET_PASSWORD_END>");
    Serial.flush();
    return;
  }
  if (command == "get rfidOnTimeMs") {
    Serial.println("<GET_RFIDONTIME_BEGIN>");
    Serial.println(rfidOnTimeMs);
    Serial.println("<GET_RFIDONTIME_END>");
    Serial.flush();
    return;
  }
  if (command == "get periodicIntervalMs") {
    Serial.println("<GET_PERIODICINTERVAL_BEGIN>");
    Serial.println(periodicIntervalMs);
    Serial.println("<GET_PERIODICINTERVAL_END>");
    Serial.flush();
    return;
  }
  if (command == "get longPressMs") {
    Serial.println("<GET_LONGPRESSMS_BEGIN>");
    Serial.println(longPressMs);
    Serial.println("<GET_LONGPRESSMS_END>");
    Serial.flush();
    return;
  }
  if (command == "get soclow") {
    Serial.println("<GET_SOCLOW_BEGIN>");
    Serial.println(socLowTestOverride ? "1" : "0");
    Serial.println("<GET_SOCLOW_END>");
    Serial.flush();
    return;
  }
  if (command.startsWith("set ssid ")) {
    String value = command.substring(9);
    ssid_str = value; ssid = ssid_str.c_str(); saveConfigVar("ssid", value); 
    Serial.println("OK");
    Serial.flush();
  } else if (command.startsWith("set password ")) {
    String value = command.substring(13);
    password_str = value; password = password_str.c_str(); saveConfigVar("password", value); 
    Serial.println("OK");
    Serial.flush();
  } else if (command.startsWith("set rfidOnTimeMs ")) {
    String value = command.substring(17);
    rfidOnTimeMs = value.toInt(); saveConfigVar("rfidOnTimeMs", value); 
    Serial.println("OK");
    Serial.flush();
  } else if (command.startsWith("set periodicIntervalMs ")) {
    String value = command.substring(23);
    periodicIntervalMs = value.toInt(); saveConfigVar("periodicIntervalMs", value); 
    Serial.println("OK");
    Serial.flush();
  } else if (command.startsWith("set longPressMs ")) {
    String value = command.substring(16);
    longPressMs = value.toInt(); saveConfigVar("longPressMs", value); 
    Serial.println("OK");
    Serial.flush();
  } else if (command.startsWith("set soclow ")) {
    String value = command.substring(11);
    socLowTestOverride = (value.toInt() != 0);
    evaluateIdleState();
    if (!dashboardModeActive) {
      setLEDStatus(idleModeActive ? "idle" : "sleeping");
    }
    Serial.println("OK");
    Serial.flush();
  } else if (command == "resetconfig") {
    if (SPIFFS.exists(configFile)) { SPIFFS.remove(configFile); Serial.println("Config reset. Reboot to use hardcoded values."); }
    else { Serial.println("No config to reset."); }
    Serial.flush();
  } else if (command == "summary") {
    printReadingsSummary();
    Serial.flush();
  } else if (command == "print") {
    printStoredReadings();
    Serial.flush();
  } else if (command == "last") {
    printLastReading();
    Serial.flush();
  } else if (command == "clear") {
    SPIFFS.remove(FLASH_FILENAME); readingCount = 0; Serial.println("Cleared");
    Serial.flush();
  } else if (command.startsWith("range ")) {
    String rangeCmd = command.substring(6);
    int spaceIndex = rangeCmd.indexOf(' ');
    if (spaceIndex > 0) {
      uint32_t startTime = rangeCmd.substring(0, spaceIndex).toInt();
      uint32_t endTime = rangeCmd.substring(spaceIndex + 1).toInt();
      sendStoredReadingsByRange(startTime, endTime);
    }
    Serial.flush();
  } else if (command == "printconfig") {
    File file = SPIFFS.open(configFile, "r");
    if (file) {
      Serial.println("[CONFIG] --- config.txt ---");
      while (file.available()) { Serial.write(file.read()); }
      file.close();
      Serial.println("[CONFIG] --- end ---");
    } else {
      Serial.println("[CONFIG] No config file.");
    }
    Serial.flush();
  } else if (command == "time") {
    if (rtcAvailable) {
      now = rtc.now();
      Serial.printf("Current time: %04d-%02d-%02d %02d:%02d:%02d\n",
                    now.year(), now.month(), now.day(),
                    now.hour(), now.minute(), now.second());
      Serial.printf("Unix timestamp: %lu\n", now.unixtime() + (6 * 3600));
    } else {
      Serial.println("RTC not available");
    }
    Serial.flush();
  } else if (command == "dashboardmode") {
    // Empty command - do nothing
  } else if (command == "sleepstats") {
    Serial.printf("[STATS] wakes: timer=%u, button=%u (gpio-wake-consumed=%u, timer-consumed=%u)\n",
                  wake_count_timer, wake_count_button, wake_button_consumed, wake_timer_consumed);
    Serial.flush();
  } else if (command == "resetrtc") {
    Serial.println("[RTC] Resetting RTC to UTC...");
    Serial.println("[RTC] This will take a moment...");
    Serial.flush();
    
    // Simple approach: just add 6 hours to current RTC time to convert from Costa Rica to UTC
    if (rtcAvailable) {
      now = rtc.now();
      DateTime utcTime = DateTime(now.unixtime() + (6 * 3600)); // Add 6 hours
      rtc.adjust(utcTime);
      Serial.println("[RTC] RTC converted from Costa Rica time to UTC");
      now = rtc.now();
      Serial.printf("[RTC] New time: %04d-%02d-%02d %02d:%02d:%02d (UTC)\n",
                    now.year(), now.month(), now.day(), now.hour(), now.minute(), now.second());
      Serial.println("[RTC] RTC is now set to UTC - new readings will be stored in UTC");
    } else {
      Serial.println("[RTC] RTC not available - cannot reset");
    }
    Serial.flush();
  } else if (command == "testuart") {
    Serial.println("[UART] Testing UART wake-up...");
    Serial.println("[UART] ESP32 will go to sleep for 10 seconds");
    Serial.println("[UART] Send any command to wake it up");
    Serial.flush();
    delay(1000);
    lightSleepUntilNextEvent(10000000); // Sleep for 10 seconds
    Serial.println("[UART] Woke up from sleep!");
    Serial.flush();
  } else if (command == "testsleep") {
    Serial.println("[SLEEP] Testing sleep functionality...");
    Serial.println("[SLEEP] Going to sleep for 5 seconds");
    Serial.flush();
    delay(1000);
    lightSleepUntilNextEvent(5000000); // Sleep for 5 seconds
    Serial.println("[SLEEP] Woke up from sleep!");
    Serial.flush();
  } else if (command == "testuartlong") {
    Serial.println("[UART] Testing UART wake-up with 30-second sleep...");
    Serial.println("[UART] ESP32 will go to sleep for 30 seconds");
    Serial.println("[UART] Send any command to wake it up via UART");
    Serial.flush();
    delay(1000);
    lightSleepUntilNextEvent(30000000); // Sleep for 30 seconds
    Serial.println("[UART] Woke up from sleep!");
    Serial.flush();
  } else if (command == "buttonmode") {
    Serial.println("[BUTTON] Multi-Button Mode Status:");
    Serial.printf("[BUTTON] Dashboard Mode: %s\n", dashboardModeActive ? "ACTIVE" : "INACTIVE");
    Serial.printf("[BUTTON] Idle Mode: %s\n", idleModeActive ? "ACTIVE" : "INACTIVE");
    Serial.printf("[BUTTON] Idle reason: %s\n", idleReasonToString(latestIdleReason));
    Serial.println("[BUTTON] Short press: RFID read");
    Serial.printf("[BUTTON] Long press (%lums): Toggle Dashboard Mode\n", longPressMs);
    Serial.printf("[BUTTON] Current button state: %s\n", digitalRead(BUTTON_PIN) == LOW ? "PRESSED" : "RELEASED");
    Serial.flush();
  } else if (command == "testbutton") {
    Serial.println("[BUTTON] Testing multi-button functionality...");
    Serial.printf("[BUTTON] Press and hold the button for %lu seconds to toggle dashboard mode\n", longPressMs / 1000);
    Serial.println("[BUTTON] Short press for RFID read");
    Serial.println("[BUTTON] Current dashboard mode will be toggled on long press");
    Serial.flush();
  } else {
    // Unknown command - do nothing (or could send error message)
    Serial.flush();
  }
}
