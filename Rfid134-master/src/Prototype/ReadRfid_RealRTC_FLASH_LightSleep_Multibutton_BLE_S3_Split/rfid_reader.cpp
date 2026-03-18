#include "rfid_reader.h"

#include "globals.h"
#include "pins.h"
#include "flash_store.h"
#include "rtc_time.h"
#include "ble_comm.h"
#include "led_status.h"

// Helper function to check if temperature data is available
bool isTemperatureAvailable(const Rfid134Reading& tag) {
  // Temperature availability detection (hybrid approach):
  // 
  // 1. If isData == true: Extended data block exists → Always calculate temperature
  //    (even if reserved1 is 0, it could be a real 23.3°C reading)
  //
  // 2. If isData == false BUT reserved1 > 0: Some tags have temperature data
  //    even without the isData flag set → Calculate temperature
  //
  // 3. If isData == false AND reserved1 == 0: Definitely no temperature data → Show N/A
  //
  // This handles both standard FDX-B tags and non-standard tags that might
  // have temperature data without the isData flag properly set.
  
  if (tag.isData) {
    // Extended data block exists → Temperature sensor is available
    return true;
  }
  
  // No extended data block, but check if reserved1 has any data
  if (tag.reserved1 > 0) {
    // Some tags have temperature data even without isData flag
    // (e.g., tag 999 has reserved1 = 7, which gives ~24.08°C)
    return true;
  }
  
  // No extended data block AND reserved1 is zero → No temperature data
  return false;
}

// --- Helper to try reading and storing a tag ---
void tryReadAndStoreTag() {
  if (lastTagValid) {
    // Validate if temperature data is available
    bool temperatureAvailable = isTemperatureAvailable(lastTag);
    
    if (!temperatureAvailable) {
      Serial.println("[TEMP] Temperature not available (sensor not enabled)");
    }
    
    uint8_t firstByte = lastTag.reserved1 & 0xFF;
    float temperature;
    uint16_t temp_raw;
    
    if (temperatureAvailable) {
      temperature = 23.3 + (0.112 * firstByte);
      temp_raw = (uint16_t)(temperature * 100);
    } else {
      // Store special marker value (0xFFFF = 655.35°C when divided by 100)
      // This indicates "temperature not available"
      temperature = 0.0;
      temp_raw = 0xFFFF;
    }
    
    RfidReading storedReading;
    storedReading.timestamp = getCurrentTimestamp();
    storedReading.country = lastTag.country;
    storedReading.id = lastTag.id;
    storedReading.temp_raw = temp_raw;
    storedReading.flags = (lastTag.isData ? 1 : 0) | (lastTag.isAnimal ? 2 : 0);
    storedReading.reserved = 0;
    storeReading(storedReading);
    Serial.printf("#%d\n", readingCount);
    if (temperatureAvailable) {
      Serial.printf("TAG: %03u %012llu %.2f°C\n", lastTag.country, lastTag.id, temperature);
    } else {
      Serial.printf("TAG: %03u %012llu TEMP: N/A\n", lastTag.country, lastTag.id);
    }
    if (rtcAvailable && storedReading.timestamp > 1000000000) {
      time_t timestamp = storedReading.timestamp;
      struct tm* timeinfo = gmtime(&timestamp);
      Serial.printf("Time: %04d-%02d-%02d %02d:%02d:%02d\n",
                    timeinfo->tm_year + 1900, timeinfo->tm_mon + 1, timeinfo->tm_mday,
                    timeinfo->tm_hour, timeinfo->tm_min, timeinfo->tm_sec);
    } else {
      Serial.printf("Time: %lu ms\n", storedReading.timestamp);
    }
    Serial.println();
  }
}

// RFID notify
void RfidNotify::OnError(Rfid134_Error errorCode) {
  rfidErrorCount++;
  rfidConsecutiveErrors++;
  
  Serial.printf("[RFID] Error %d - ", errorCode);
  String errorMsg = "";
  if (errorCode == 130) {
    errorMsg = "Communication timeout or protocol error";
    Serial.println(errorMsg);
  } else if (errorCode == 131) {
    errorMsg = "Checksum error";
    Serial.println(errorMsg);
  } else if (errorCode == 132) {
    errorMsg = "Invalid response";
    Serial.println(errorMsg);
  } else {
    errorMsg = "Unknown RFID error";
    Serial.println(errorMsg);
  }
  
  // Send error via BLE if in dashboard mode
  if (dashboardModeActive && deviceConnected) {
    String bleError = "[RFID] ERROR: " + errorMsg + " (Count: " + String(rfidConsecutiveErrors) + ")";
    sendBLEResponse(bleError);
  }
  
  Serial.printf("[RFID] Error count: %u (consecutive: %u)\n", rfidErrorCount, rfidConsecutiveErrors);
}

void RfidNotify::OnPacketRead(const Rfid134Reading& reading) {
  // Reset error count on successful read
  rfidConsecutiveErrors = 0;
  
  // Store tag data for later processing in powerOnAndReadTagWindow()
  // DO NOT store reading here - it will be stored in powerOnAndReadTagWindow()
  // to prevent duplicate storage
  lastTag = reading;
  lastTagValid = true;
  
  // Don't print tag info here - it will be printed in tryReadAndStoreTag()
  // to avoid duplicate prints
  
  // Trigger green LED flash for successful tag detection
  setLEDStatus("reading_success");
  
  // Send BLE status update if connected (for immediate feedback)
  if (deviceConnected) {
    bool tempAvailable = isTemperatureAvailable(reading);
    String statusUpdate;
    if (tempAvailable) {
      uint8_t firstByte = reading.reserved1 & 0xFF;
      float temperature = 23.3 + (0.112 * firstByte);
      statusUpdate = "New reading: " + String(reading.country) + " " + 
                         String(reading.id) + " " + String(temperature, 2) + "°C";
    } else {
      statusUpdate = "New reading: " + String(reading.country) + " " + 
                    String(reading.id) + " TEMP: N/A";
    }
    sendBLEStatus(statusUpdate);
  }
}

Rfid134<HardwareSerial, RfidNotify> rfid(Serial1);

// Power cycle RFID module for recovery
void powerCycleRFIDModule() {
  Serial.println("[RFID] Power cycling module for recovery...");
  if (dashboardModeActive) sendBLEResponse("[RFID] Power cycling module for recovery...");
  
  // Power OFF
  digitalWrite(RFID_PWR_PIN, LOW); // Power OFF (active HIGH)
  delay(200); // Wait for power to drain
  
  // Power ON
  digitalWrite(RFID_PWR_PIN, HIGH); // Power ON (active HIGH)
  delay(500); // Wait for module to initialize
  
  // Reinitialize RFID communication
  Serial1.end();
  delay(100);
  Serial1.begin(9600, SERIAL_8N2, RFID_TX_PIN);
  rfid.begin();
  delay(200);
  
  rfidConsecutiveErrors = 0; // Reset error count after power cycle
  Serial.println("[RFID] Power cycle complete, module reinitialized");
  if (dashboardModeActive) sendBLEResponse("[RFID] Power cycle complete");
}

void powerOnAndReadTagWindow(unsigned long windowMs) {
  // Check if RFID module needs recovery
  if (rfidConsecutiveErrors >= MAX_RFID_ERRORS) {
    Serial.printf("[RFID] Too many errors (%u), power cycling module...\n", rfidConsecutiveErrors);
    if (dashboardModeActive) {
      sendBLEResponse("[RFID] Module error detected, attempting recovery...");
    }
    powerCycleRFIDModule();
  }
  
  Serial.printf("[RFID] Powering ON for %lu ms\n", windowMs);
  if (dashboardModeActive) sendBLEResponse("[RFID] Powering ON for " + String(windowMs) + " ms");
  digitalWrite(RFID_PWR_PIN, HIGH); // Power ON (active HIGH)
  delay(500); // Increased delay to give RFID module more time to initialize
  Serial.println("[RFID] RFID module powered on, starting read window...");
  if (dashboardModeActive) sendBLEResponse("[RFID] RFID module powered on, starting read window...");
  unsigned long start = millis();
  lastTagValid = false;
  bool tagStored = false;
  bool rfidHangDetected = false;

  unsigned long lastYieldTime = start; // Track last yield time for this read window
  unsigned long lastLoopTime = start; // Track rfid.loop() execution time
  unsigned long lastSuccessfulLoop = start; // Track last successful loop completion
  
  // Safety: Limit total read window time to prevent infinite hangs
  unsigned long maxReadTime = (windowMs > RFID_SAFETY_TIMEOUT_MS) ? RFID_SAFETY_TIMEOUT_MS : windowMs;
  
  while (millis() - start < maxReadTime && !tagStored && !rfidHangDetected) {
    // CRITICAL: Feed watchdog BEFORE calling rfid.loop() to prevent reset
    yield(); // Always yield before potentially blocking operation
    
    // Timeout protection: if rfid.loop() takes too long, it might be hung
    unsigned long loopStart = millis();
    rfid.loop();
    unsigned long loopDuration = millis() - loopStart;
    unsigned long now = millis();
    
    // Detect if RFID module is hung (loop takes too long)
    if (loopDuration > RFID_LOOP_TIMEOUT_MS) {
      Serial.printf("[RFID] WARNING: rfid.loop() took %lu ms (possible hang)\n", loopDuration);
      rfidConsecutiveErrors++;
      if (rfidConsecutiveErrors >= MAX_RFID_ERRORS) {
        Serial.println("[RFID] Module appears hung, aborting read window immediately");
        if (dashboardModeActive) {
          sendBLEResponse("[RFID] Module hang detected, aborting read");
        }
        rfidHangDetected = true;
        break; // Exit loop immediately
      }
    } else {
      // Loop completed successfully - reset timeout tracking
      lastSuccessfulLoop = now;
    }
    
    // Additional safety: If no successful loop for too long, abort
    if (now - lastSuccessfulLoop > RFID_SAFETY_TIMEOUT_MS) {
      Serial.println("[RFID] Safety timeout: No successful loop for too long, aborting");
      if (dashboardModeActive) {
        sendBLEResponse("[RFID] Safety timeout: Module not responding");
      }
      rfidHangDetected = true;
      rfidConsecutiveErrors = MAX_RFID_ERRORS; // Trigger recovery on next attempt
      break;
    }
    
    if (lastTagValid) {
      tagStored = true;
      Serial.println("[RFID] Tag detected and stored");
      if (dashboardModeActive) sendBLEResponse("[RFID] Tag detected and stored");
      
      // Store the reading and send it via BLE
      tryReadAndStoreTag();
      
      // Send the reading data via BLE if in dashboard mode
      if (dashboardModeActive) {
        bool tempAvailable = isTemperatureAvailable(lastTag);
        time_t timestamp = getCurrentTimestamp();
        struct tm* ti = gmtime(&timestamp);
        
        char readingStr[128];
        if (tempAvailable) {
          uint8_t firstByte = lastTag.reserved1 & 0xFF;
          float temperature = 23.3 + (0.112 * firstByte);
          snprintf(readingStr, sizeof(readingStr), 
                   "#%d: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, %.2f°C",
                   readingCount, ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
                   ti->tm_hour, ti->tm_min, ti->tm_sec,
                   lastTag.country, lastTag.id, temperature);
        } else {
          snprintf(readingStr, sizeof(readingStr), 
                   "#%d: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, N/A",
                   readingCount, ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
                   ti->tm_hour, ti->tm_min, ti->tm_sec,
                   lastTag.country, lastTag.id);
        }
        sendBLEResponse(readingStr);
      }
      
      // Clear lastTagValid to prevent duplicate storage
      lastTagValid = false;
    }
    
    // ESP32-S3: Feed watchdog more frequently during long RFID read window
    // This prevents watchdog resets during 5-second read operations
    // Yield at least every 50ms to keep watchdog happy (more frequent for safety)
    if (now - lastYieldTime > 50) {
      yield(); // Feed watchdog and allow other tasks to run
      lastYieldTime = now;
    }
  }
  
  // CRITICAL: Always power off module, even if aborted
  digitalWrite(RFID_PWR_PIN, LOW); // Power OFF (active HIGH)
  Serial.println("[RFID] Power OFF");
  if (dashboardModeActive) sendBLEResponse("[RFID] Power OFF");
  
  // Handle results - ALWAYS send a response to prevent app timeout
  if (rfidHangDetected) {
    Serial.println("[RFID] Read aborted due to module hang");
    if (dashboardModeActive) {
      sendBLEResponse("[RFID] Read aborted: Module hardware issue detected");
      // Send explicit "no tag" equivalent so app doesn't timeout
      sendBLEResponse("[RFID] No tag detected during window");
    }
    // Power cycle will happen on next read attempt
  } else if (!tagStored) {
    Serial.println("[RFID] No tag detected during window");
    if (dashboardModeActive) sendBLEResponse("[RFID] No tag detected during window");
  }
  
  // Final yield to ensure all messages are sent before function returns
  yield();
  Serial.flush();
  
  // Don't immediately reset LED status - let updateLEDStatus() handle the timing
  // The green flash will automatically return to the appropriate status after the flash duration
}
