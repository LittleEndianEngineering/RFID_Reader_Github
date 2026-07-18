#include "rfid_reader.h"

#include <string.h>

#include "globals.h"
#include "pins.h"
#include "flash_store.h"
#include "rtc_time.h"
#include "ble_comm.h"
#include "led_status.h"

static uint8_t selectedAntennaId = 0;
static int lastRfidErrorCode = 0;
static unsigned long lastRfidErrorAtMs = 0;
static bool nextWindowIsRecovery = false;
struct AntennaReadResult {
  bool stored;
  bool packetSeen;
  bool rfidHangDetected;
  bool sawError130;
};

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
void tryReadAndStoreTag(uint8_t antennaId) {
  if (lastTagValid) {
    VERBOSE_PRINTF("[READDBG] STORE_ATTEMPT t=%lu ant=%u tag=%03u %012llu\n",
                   millis(), antennaId, lastTag.country, lastTag.id);
    // Validate if temperature data is available
    bool temperatureAvailable = isTemperatureAvailable(lastTag);
    
    if (!temperatureAvailable) {
      VERBOSE_PRINTLN("[TEMP] Temperature not available (sensor not enabled)");
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
    if (storedReading.timestamp < 1000000000UL) {
      Serial.println("[RTC] Timestamp unavailable - reading not stored (idle mode enforced)");
      return;
    }
    storedReading.country = lastTag.country;
    storedReading.id = lastTag.id;
    storedReading.temp_raw = temp_raw;
    storedReading.flags = (lastTag.isData ? FLAG_IS_DATA : 0) |
                          (lastTag.isAnimal ? FLAG_IS_ANIMAL : 0) |
                          ((antennaId == 2) ? FLAG_ANT2 : FLAG_ANT1);
    storedReading.reserved = 0;
    storeReading(storedReading);
    VERBOSE_PRINTF("[READDBG] STORE_OK t=%lu ant=%u count=%u ts=%lu\n",
                   millis(), antennaId, readingCount, (unsigned long)storedReading.timestamp);
    if (temperatureAvailable) {
      Serial.printf("[RFID_RESULT] stored=true ant=ANT%u reading=%d ts=%lu tag=%03u %012llu temp=%.2f°C\n",
                    antennaId, readingCount, (unsigned long)storedReading.timestamp, lastTag.country, lastTag.id, temperature);
    } else {
      Serial.printf("[RFID_RESULT] stored=true ant=ANT%u reading=%d ts=%lu tag=%03u %012llu temp=N/A\n",
                    antennaId, readingCount, (unsigned long)storedReading.timestamp, lastTag.country, lastTag.id);
    }
    VERBOSE_PRINTF("#%d\n", readingCount);
    if (temperatureAvailable) {
      VERBOSE_PRINTF("TAG: %03u %012llu %.2f°C\n", lastTag.country, lastTag.id, temperature);
    } else {
      VERBOSE_PRINTF("TAG: %03u %012llu TEMP: N/A\n", lastTag.country, lastTag.id);
    }
    if (storedReading.timestamp > 1000000000UL) {
      time_t timestamp = storedReading.timestamp;
      struct tm* timeinfo = gmtime(&timestamp);
      VERBOSE_PRINTF("Time: %04d-%02d-%02d %02d:%02d:%02d\n",
                     timeinfo->tm_year + 1900, timeinfo->tm_mon + 1, timeinfo->tm_mday,
                     timeinfo->tm_hour, timeinfo->tm_min, timeinfo->tm_sec);
    }
    if (verbose) Serial.println();

    // Per-antenna success feedback: brief green flash, then return to steady state.
    setLEDStatus("reading_success");
    delay(1000);
    if (idleModeActive) {
      setLEDStatus("idle");
    } else if (dashboardModeActive) {
      setLEDStatus("dashboard_active");
    } else {
      setLEDStatus("sleeping");
    }
  }
}

// RFID notify
void RfidNotify::OnError(Rfid134_Error errorCode) {
  lastRfidErrorCode = (int)errorCode;
  lastRfidErrorAtMs = millis();
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
  VERBOSE_PRINTF("[READDBG] PACKET_RX t=%lu tag=%03u %012llu isData=%d ant_pending=%d\n",
                 millis(), reading.country, reading.id, reading.isData ? 1 : 0, selectedAntennaId);
  
  // Don't print tag info here - it will be printed in tryReadAndStoreTag()
  // to avoid duplicate prints
  
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
static const unsigned long ANTENNA_SWITCH_DELAY_MS = 1000;

static void selectAntenna1() {
  // ANT1 is selected when ANT_SEL is HiZ.
  pinMode(ANT_SEL_PIN, INPUT);
}

static void selectAntenna2() {
  // ANT2 is selected when ANT_SEL is actively driven LOW.
  pinMode(ANT_SEL_PIN, OUTPUT);
  digitalWrite(ANT_SEL_PIN, LOW);
}

static AntennaReadResult runSingleAntennaReadWindow(unsigned long windowMs, const char* antennaLabel, uint8_t antennaId) {
  selectedAntennaId = antennaId;
  bool isRecoveryWindow = nextWindowIsRecovery;
  nextWindowIsRecovery = false;
  lastRfidErrorCode = 0;
  lastRfidErrorAtMs = 0;
  lastTagValid = false;
  unsigned int drainedBytes = 0;
  while (Serial1.available()) {
    Serial1.read();
    drainedBytes++;
  }
  Serial.printf("[READDBG] WINDOW_START t=%lu ant=%u label=%s window_ms=%lu recovery=%d\n",
                millis(), antennaId, antennaLabel, windowMs, isRecoveryWindow ? 1 : 0);
  if (drainedBytes > 0) {
    VERBOSE_PRINTF("[READDBG] RX_DRAIN t=%lu ant=%u bytes=%u\n", millis(), antennaId, drainedBytes);
  }
  VERBOSE_PRINTF("[RFID][%s] Powering ON for %lu ms\n", antennaLabel, windowMs);
  if (dashboardModeActive) sendBLEResponse(String("[RFID][") + antennaLabel + "] Powering ON for " + String(windowMs) + " ms");
  digitalWrite(RFID_PWR_PIN, HIGH); // Power ON (active HIGH)
  delay(500); // Give RFID module time to initialize
  VERBOSE_PRINTF("[RFID][%s] RFID module powered on, starting read window...\n", antennaLabel);
  if (dashboardModeActive) sendBLEResponse(String("[RFID][") + antennaLabel + "] RFID module powered on, starting read window...");
  // Anchor for error eligibility/retries in this antenna cycle, including
  // stabilization/recovery-kick phase before timed polling starts.
  unsigned long windowOpenTs = millis();

  // Give each antenna a short parser/radio settle sequence before the timed
  // window starts. Any packet captured here is preserved and stored below.
  VERBOSE_PRINTF("[READDBG] ANT%u_STABILIZE_START t=%lu\n", antennaId, millis());
  for (int i = 0; i < 6; i++) {
    rfid.loop();
    delay(20);
  }
  VERBOSE_PRINTF("[READDBG] ANT%u_STABILIZE_END t=%lu\n", antennaId, millis());

  // Recovery windows can become "silent" after module reinit; do a short
  // explicit warm-up sequence to re-prime parser/UART state before timed loop.
  if (isRecoveryWindow) {
    VERBOSE_PRINTF("[READDBG] RECOVERY_KICK_START t=%lu ant=%u\n", millis(), antennaId);
    for (int i = 0; i < 8; i++) {
      rfid.loop();
      delay(25);
      if (lastTagValid) {
        break;
      }
    }
    VERBOSE_PRINTF("[READDBG] RECOVERY_KICK_END t=%lu ant=%u tag_ready=%d\n", millis(), antennaId, lastTagValid ? 1 : 0);
  }

  unsigned long start = millis();
  bool tagStored = false;
  bool rfidHangDetected = false;
  bool packetSeen = false;
  const char* exitReason = "unknown";
  unsigned int error130RetryCount = 0;
  unsigned long lastHandledErrorMs = 0;
  bool error130BurstDone = false;
  bool sawError130 = false;

  unsigned long lastYieldTime = start;
  unsigned long lastSuccessfulLoop = start;
  // Keep the configured read window duration as-is.
  // Stall safety timeout remains active independently to catch hung loops.
  unsigned long maxReadTime = windowMs;
  unsigned long stallSafetyTimeoutMs = (RFID_SAFETY_TIMEOUT_MS > windowMs) ? RFID_SAFETY_TIMEOUT_MS : (windowMs + 250);

  // If stabilization/recovery kick already captured a valid packet, accept/store
  // immediately before entering timed polling loop.
  if (lastTagValid) {
    packetSeen = true;
    tagStored = true;
    VERBOSE_PRINTF("[READDBG] TAG_ACCEPT t=%lu ant=%u elapsed=%lu\n", millis(), antennaId, millis() - start);
    VERBOSE_PRINTF("[RFID][%s] Tag detected and stored\n", antennaLabel);
    if (dashboardModeActive) sendBLEResponse(String("[RFID][") + antennaLabel + "] Tag detected and stored");
    tryReadAndStoreTag(antennaId);
    lastTagValid = false;
    exitReason = "tag_stored";
  }

  while (millis() - start < maxReadTime && !tagStored && !rfidHangDetected) {
    yield();

    unsigned long loopStart = millis();
    rfid.loop();
    unsigned long loopDuration = millis() - loopStart;
    unsigned long now = millis();

    if (loopDuration > RFID_LOOP_TIMEOUT_MS) {
      Serial.printf("[RFID][%s] WARNING: rfid.loop() took %lu ms (possible hang)\n", antennaLabel, loopDuration);
      rfidConsecutiveErrors++;
      if (rfidConsecutiveErrors >= MAX_RFID_ERRORS) {
        Serial.printf("[RFID][%s] Module appears hung, aborting read window immediately\n", antennaLabel);
        if (dashboardModeActive) {
          sendBLEResponse(String("[RFID][") + antennaLabel + "] Module hang detected, aborting read");
        }
        rfidHangDetected = true;
        exitReason = "loop_hang_abort";
        break;
      }
    } else {
      lastSuccessfulLoop = now;
    }

    // Deterministic retry assist for Error 130:
    // once first 130 is observed in this antenna window, run a bounded 4-attempt
    // quick retry burst (within the same window budget).
    if (!tagStored &&
        lastRfidErrorCode == 130 &&
        lastRfidErrorAtMs != 0 &&
        lastRfidErrorAtMs >= windowOpenTs &&
        lastRfidErrorAtMs != lastHandledErrorMs &&
        !error130BurstDone) {
      sawError130 = true;
      lastHandledErrorMs = lastRfidErrorAtMs;
      while (error130RetryCount < 3 && !tagStored && (millis() - start) < maxReadTime) {
        error130RetryCount++;
        VERBOSE_PRINTF("[READDBG] E130_RETRY t=%lu ant=%u retry=%u/3\n", millis(), antennaId, error130RetryCount);
        unsigned int retryDrainBytes = 0;
        while (Serial1.available()) {
          Serial1.read();
          retryDrainBytes++;
        }
        if (retryDrainBytes > 0) {
          VERBOSE_PRINTF("[READDBG] E130_RETRY_DRAIN t=%lu ant=%u bytes=%u\n", millis(), antennaId, retryDrainBytes);
        }
        lastTagValid = false;
        rfid.begin();
        delay(250);
        rfid.loop();
        if (lastTagValid) {
          packetSeen = true;
          tagStored = true;
          VERBOSE_PRINTF("[READDBG] TAG_ACCEPT t=%lu ant=%u elapsed=%lu\n", millis(), antennaId, millis() - start);
          VERBOSE_PRINTF("[RFID][%s] Tag detected and stored\n", antennaLabel);
          if (dashboardModeActive) sendBLEResponse(String("[RFID][") + antennaLabel + "] Tag detected and stored");
          tryReadAndStoreTag(antennaId);
          lastTagValid = false;
          exitReason = "tag_stored";
          break;
        }
      }
      error130BurstDone = true;
      if (!tagStored) {
        VERBOSE_PRINTF("[READDBG] E130_RETRY_LIMIT t=%lu ant=%u retries=%u\n", millis(), antennaId, error130RetryCount);
        exitReason = "error130_retry_limit";
        break;
      }
    }

    if (now - lastSuccessfulLoop > stallSafetyTimeoutMs) {
      Serial.printf("[RFID][%s] Safety timeout: No successful loop for too long, aborting\n", antennaLabel);
      if (dashboardModeActive) {
        sendBLEResponse(String("[RFID][") + antennaLabel + "] Safety timeout: Module not responding");
      }
      rfidHangDetected = true;
      rfidConsecutiveErrors = MAX_RFID_ERRORS;
      exitReason = "stall_safety_timeout";
      break;
    }

    if (lastTagValid) {
      packetSeen = true;
      tagStored = true;
      VERBOSE_PRINTF("[READDBG] TAG_ACCEPT t=%lu ant=%u elapsed=%lu\n", millis(), antennaId, millis() - start);
      VERBOSE_PRINTF("[RFID][%s] Tag detected and stored\n", antennaLabel);
      if (dashboardModeActive) sendBLEResponse(String("[RFID][") + antennaLabel + "] Tag detected and stored");

      // Keep storage flow unchanged: each detected tag is stored with its own timestamp/index.
      tryReadAndStoreTag(antennaId);

      if (dashboardModeActive) {
        bool tempAvailable = isTemperatureAvailable(lastTag);
        uint32_t readingTimestamp = getCurrentTimestamp();
        bool hasValidTimestamp = (readingTimestamp > 1000000000UL);
        struct tm* ti = nullptr;
        if (hasValidTimestamp) {
          time_t timestamp = readingTimestamp;
          ti = gmtime(&timestamp);
        }

        char readingStr[128];
        if (tempAvailable) {
          uint8_t firstByte = lastTag.reserved1 & 0xFF;
          float temperature = 23.3 + (0.112 * firstByte);
          if (hasValidTimestamp && ti != nullptr) {
            snprintf(readingStr, sizeof(readingStr),
                     "#%d: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, %.2f°C",
                     readingCount, ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
                     ti->tm_hour, ti->tm_min, ti->tm_sec,
                     lastTag.country, lastTag.id, temperature);
          } else {
            snprintf(readingStr, sizeof(readingStr),
                     "#%d: NO_RTC_TIME, %u, %llu, %.2f°C",
                     readingCount, lastTag.country, lastTag.id, temperature);
          }
        } else {
          if (hasValidTimestamp && ti != nullptr) {
            snprintf(readingStr, sizeof(readingStr),
                     "#%d: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, N/A",
                     readingCount, ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
                     ti->tm_hour, ti->tm_min, ti->tm_sec,
                     lastTag.country, lastTag.id);
          } else {
            snprintf(readingStr, sizeof(readingStr),
                     "#%d: NO_RTC_TIME, %u, %llu, N/A",
                     readingCount, lastTag.country, lastTag.id);
          }
        }
        sendBLEResponse(readingStr);
      }

      lastTagValid = false;
      exitReason = "tag_stored";
    }

    if (now - lastYieldTime > 50) {
      yield();
      lastYieldTime = now;
    }
  }

  if (!tagStored && !rfidHangDetected && strcmp(exitReason, "unknown") == 0) {
    exitReason = "window_timeout_no_tag";
  }

  digitalWrite(RFID_PWR_PIN, LOW); // Power OFF (active HIGH)
  Serial.printf("[READDBG] WINDOW_END t=%lu ant=%u stored=%d hang=%d packet_seen=%d elapsed=%lu reason=%s e130_retries=%u loop_err_total=%u loop_err_consec=%u\n",
                millis(), antennaId, tagStored ? 1 : 0, rfidHangDetected ? 1 : 0, packetSeen ? 1 : 0, millis() - start, exitReason,
                error130RetryCount, rfidErrorCount, rfidConsecutiveErrors);
  VERBOSE_PRINTF("[RFID][%s] Power OFF\n", antennaLabel);
  if (dashboardModeActive) sendBLEResponse(String("[RFID][") + antennaLabel + "] Power OFF");

  if (rfidHangDetected) {
    Serial.printf("[RFID][%s] Read aborted due to module hang\n", antennaLabel);
    if (dashboardModeActive) {
      sendBLEResponse(String("[RFID][") + antennaLabel + "] Read aborted: Module hardware issue detected");
      sendBLEResponse(String("[RFID][") + antennaLabel + "] No tag detected during window");
    }
  } else if (!tagStored) {
    VERBOSE_PRINTF("[RFID][%s] No tag detected during window\n", antennaLabel);
    if (dashboardModeActive) sendBLEResponse(String("[RFID][") + antennaLabel + "] No tag detected during window");
  }

  yield();
  Serial.flush();
  return {tagStored, packetSeen, rfidHangDetected, sawError130};
}

// Power cycle RFID module for recovery
void powerCycleRFIDModule() {
  VERBOSE_PRINTLN("[RFID] Power cycling module for recovery...");
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
  VERBOSE_PRINTLN("[RFID] Power cycle complete, module reinitialized");
  if (dashboardModeActive) sendBLEResponse("[RFID] Power cycle complete");
}

void powerOnAndReadTagWindow(unsigned long windowMs) {
  VERBOSE_PRINTF("[READDBG] READ_EFFORT_START t=%lu window_ms=%lu dashboard=%d idle=%d\n",
                 millis(), windowMs, dashboardModeActive ? 1 : 0, idleModeActive ? 1 : 0);
  // Check if RFID module needs recovery
  if (rfidConsecutiveErrors >= MAX_RFID_ERRORS) {
    VERBOSE_PRINTF("[RFID] Too many errors (%u), power cycling module...\n", rfidConsecutiveErrors);
    if (dashboardModeActive) {
      sendBLEResponse("[RFID] Module error detected, attempting recovery...");
    }
    powerCycleRFIDModule();
  }

  bool readSucceeded = false;

  // ANT1: HiZ select (default path)
  selectAntenna1();
  AntennaReadResult ant1 = runSingleAntennaReadWindow(windowMs, "ANT1", 1);
  if (ant1.stored) {
    readSucceeded = true;
  }

  if (!ant1.packetSeen && ant1.sawError130) {
    VERBOSE_PRINTLN("[READDBG] ANT1 had Error130 with no packet - power cycling and retrying ANT1 once");
    powerCycleRFIDModule();
    nextWindowIsRecovery = true;
    selectAntenna1();
    AntennaReadResult ant1Recovery = runSingleAntennaReadWindow(windowMs, "ANT1", 1);
    if (ant1Recovery.stored) {
      readSucceeded = true;
    }
  }

  // Hardware-required cool-down between ANT1 and ANT2 read windows.
  delay(ANTENNA_SWITCH_DELAY_MS);

  // ANT2: drive selection low and run the same read algorithm.
  selectAntenna2();
  AntennaReadResult ant2 = runSingleAntennaReadWindow(windowMs, "ANT2", 2);
  if (ant2.stored) {
    readSucceeded = true;
  }

  if (!ant2.packetSeen && ant2.sawError130) {
    VERBOSE_PRINTLN("[READDBG] ANT2 had Error130 with no packet - power cycling and retrying ANT2 once");
    powerCycleRFIDModule();
    nextWindowIsRecovery = true;
    selectAntenna2();
    AntennaReadResult ant2Recovery = runSingleAntennaReadWindow(windowMs, "ANT2", 2);
    if (ant2Recovery.stored) {
      readSucceeded = true;
    }
  }

  // Return antenna select to ANT1 default HiZ state.
  selectAntenna1();

  // Measure battery state once per complete read effort (both antennas).
  printBatterySoc("Read effort complete");
  VERBOSE_PRINTF("[READDBG] READ_EFFORT_END t=%lu count=%u led=%s\n",
                 millis(), readingCount, currentLEDStatus.c_str());
  VERBOSE_PRINTF("[READDBG] READ_EFFORT_RESULT t=%lu result=%s\n",
                 millis(), readSucceeded ? "success" : "failed");

  // Don't immediately reset LED status - let updateLEDStatus() handle timing.
}
