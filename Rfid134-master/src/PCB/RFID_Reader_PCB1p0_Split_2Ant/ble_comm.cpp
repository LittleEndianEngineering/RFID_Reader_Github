#include "ble_comm.h"

#include <SPIFFS.h>
#include <vector>
#include <time.h>

#include "BLEDevice.h"
#include "BLEServer.h"
#include "BLEUtils.h"
#include "BLE2902.h"
#include "esp_bt.h"   // for btStop()

#include "globals.h"
#include "config.h"
#include "flash_store.h"
#include "pins.h"
#include "rfid_reader.h"
#include "led_status.h"

static const char* bleAntennaFromFlags(uint8_t flags) {
  if (flags & FLAG_ANT2) return "ANT2";
  return "ANT1";
}

static String formatReadingLine(int readingNumber, const RfidReading& reading) {
  time_t timestamp = reading.timestamp;
  struct tm* ti = gmtime(&timestamp);
  char buffer[160];

  if (reading.temp_raw == 0xFFFF) {
    snprintf(buffer, sizeof(buffer),
             "#%d: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, N/A, %s",
             readingNumber,
             ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
             ti->tm_hour, ti->tm_min, ti->tm_sec,
             reading.country, reading.id, bleAntennaFromFlags(reading.flags));
  } else {
    float temp = reading.temp_raw / 100.0f;
    snprintf(buffer, sizeof(buffer),
             "#%d: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, %.2f°C, %s",
             readingNumber,
             ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
             ti->tm_hour, ti->tm_min, ti->tm_sec,
             reading.country, reading.id, temp, bleAntennaFromFlags(reading.flags));
  }

  return String(buffer);
}

static void sendBLEGetResponse(const String& markerName, const String& value) {
  sendBLEResponse("<" + markerName + "_BEGIN>");
  sendBLEResponse(value);
  sendBLEResponse("<" + markerName + "_END>");
}

static void markBLEManualReadActivity() {
  // Treat BLE-initiated manual reads like button/serial manual reads. Marking
  // before and after the read window prevents both queued and stale periodic
  // checks, plus any stale button edge, from immediately launching a full
  // ANT1+ANT2 cycle.
  unsigned long now = millis();
  lastCommandTime = now;
  lastPeriodicRead = now;
  timerWakePending = false;
  buttonWakePending = false;
  suppressButtonReadUntilMs = now + 2000UL;
  buttonPressed = false;
  longPressDetected = false;
  longPressFeedbackStarted = false;
  lastButtonState = digitalRead(BUTTON_PIN);
}

static bool processBLEGetCommand(const String& command) {
  if (command == "get rfidOnTimeMs") {
    sendBLEGetResponse("GET_RFIDONTIME", String(rfidOnTimeMs));
  } else if (command == "get periodicIntervalMs") {
    sendBLEGetResponse("GET_PERIODICINTERVAL", String(periodicIntervalMs));
  } else if (command == "get liveViewAutoReadIntervalMs") {
    sendBLEGetResponse("GET_LIVEVIEWAUTOREADINTERVALMS", String(liveViewAutoReadIntervalMs));
  } else if (command == "get longPressMs") {
    sendBLEGetResponse("GET_LONGPRESSMS", String(longPressMs));
  } else if (command == "get socLowIdleEnabled" || command == "get soclowidle") {
    sendBLEGetResponse(command == "get soclowidle" ? "GET_SOCLOWIDLE" : "GET_SOCLOWIDLEENABLED",
                       socLowIdleEnabled ? "1" : "0");
  } else if (command == "get lowSocUsbRecoveryWindowMs") {
    sendBLEGetResponse("GET_LOWSOCUSBRECOVERYWINDOWMS", String(lowSocUsbRecoveryWindowMs));
  } else if (command == "get socLowThresholdPercent") {
    sendBLEGetResponse("GET_SOCLOWTHRESHOLDPERCENT", String(SOC_LOW_THRESHOLD_PERCENT, 2));
  } else if (command == "get batteryMinVoltage") {
    sendBLEGetResponse("GET_BATTERYMINVOLTAGE", String(BATTERY_MIN_VOLTAGE, 2));
  } else if (command == "get batteryMaxVoltage") {
    sendBLEGetResponse("GET_BATTERYMAXVOLTAGE", String(BATTERY_MAX_VOLTAGE, 2));
  } else if (command == "get verbose") {
    sendBLEGetResponse("GET_VERBOSE", verbose ? "1" : "0");
  } else if (command == "get dashboardModeActive") {
    sendBLEGetResponse("GET_DASHBOARDMODEACTIVE", dashboardModeActive ? "1" : "0");
  } else if (command == "get ledHeartbeatIntervalMs") {
    sendBLEGetResponse("GET_LEDHEARTBEATINTERVALMS", String(ledHeartbeatIntervalMs));
  } else if (command == "get ledHeartbeatOnMs") {
    sendBLEGetResponse("GET_LEDHEARTBEATONMS", String(ledHeartbeatOnMs));
  } else {
    return false;
  }
  return true;
}

static bool processBLESetCommand(const String& command) {
  if (command.startsWith("set rfidOnTimeMs ")) {
    String value = command.substring(17);
    rfidOnTimeMs = value.toInt();
    saveConfigVar("rfidOnTimeMs", value);
  } else if (command.startsWith("set periodicIntervalMs ")) {
    String value = command.substring(23);
    periodicIntervalMs = value.toInt();
    saveConfigVar("periodicIntervalMs", value);
  } else if (command.startsWith("set liveViewAutoReadIntervalMs ")) {
    String value = command.substring(31);
    unsigned long parsed = value.toInt();
    if (parsed < 8000UL || parsed > 300000UL) {
      sendBLEResponse("ERROR: liveViewAutoReadIntervalMs must be 8000-300000");
      return true;
    }
    liveViewAutoReadIntervalMs = parsed;
    saveConfigVar("liveViewAutoReadIntervalMs", String(liveViewAutoReadIntervalMs));
  } else if (command.startsWith("set longPressMs ")) {
    String value = command.substring(16);
    longPressMs = value.toInt();
    saveConfigVar("longPressMs", value);
  } else if (command.startsWith("set socLowIdleEnabled ") || command.startsWith("set soclowidle ")) {
    String value = command.startsWith("set soclowidle ") ? command.substring(15) : command.substring(22);
    socLowIdleEnabled = (value.toInt() != 0);
    saveConfigVar("socLowIdleEnabled", socLowIdleEnabled ? "true" : "false");
    evaluateIdleState();
    setLEDStatus(idleModeActive ? "idle" : (dashboardModeActive ? "dashboard_active" : "sleeping"));
  } else if (command.startsWith("set lowSocUsbRecoveryWindowMs ")) {
    String value = command.substring(30);
    unsigned long parsed = value.toInt();
    if (parsed > 300000UL) {
      sendBLEResponse("ERROR: lowSocUsbRecoveryWindowMs must be 0-300000");
      return true;
    }
    lowSocUsbRecoveryWindowMs = parsed;
    saveConfigVar("lowSocUsbRecoveryWindowMs", String(lowSocUsbRecoveryWindowMs));
  } else if (command.startsWith("set socLowThresholdPercent ")) {
    String value = command.substring(27);
    float parsed = value.toFloat();
    if (parsed < 0.0f || parsed > 100.0f) {
      sendBLEResponse("ERROR: socLowThresholdPercent must be 0-100");
      return true;
    }
    SOC_LOW_THRESHOLD_PERCENT = parsed;
    saveConfigVar("socLowThresholdPercent", String(SOC_LOW_THRESHOLD_PERCENT, 2));
    evaluateIdleState();
    setLEDStatus(idleModeActive ? "idle" : (dashboardModeActive ? "dashboard_active" : "sleeping"));
  } else if (command.startsWith("set batteryMinVoltage ")) {
    String value = command.substring(22);
    float parsed = value.toFloat();
    if (parsed < 2.5f || parsed > 4.2f) {
      sendBLEResponse("ERROR: batteryMinVoltage must be 2.5-4.2");
      return true;
    }
    BATTERY_MIN_VOLTAGE = parsed;
    saveConfigVar("batteryMinVoltage", String(BATTERY_MIN_VOLTAGE, 2));
    evaluateIdleState();
    setLEDStatus(idleModeActive ? "idle" : (dashboardModeActive ? "dashboard_active" : "sleeping"));
  } else if (command.startsWith("set batteryMaxVoltage ")) {
    String value = command.substring(22);
    float parsed = value.toFloat();
    if (parsed < 3.5f || parsed > 4.5f) {
      sendBLEResponse("ERROR: batteryMaxVoltage must be 3.5-4.5");
      return true;
    }
    BATTERY_MAX_VOLTAGE = parsed;
    saveConfigVar("batteryMaxVoltage", String(BATTERY_MAX_VOLTAGE, 2));
    evaluateIdleState();
    setLEDStatus(idleModeActive ? "idle" : (dashboardModeActive ? "dashboard_active" : "sleeping"));
  } else if (command.startsWith("set verbose ")) {
    String value = command.substring(12);
    verbose = (value.toInt() != 0);
    saveConfigVar("verbose", verbose ? "true" : "false");
  } else if (command.startsWith("set dashboardModeActive ")) {
    String value = command.substring(24);
    dashboardModeActive = (value.toInt() != 0);
    saveConfigVar("dashboardModeActive", dashboardModeActive ? "true" : "false");
    if (dashboardModeActive) {
      startBLEAdvertising();
    } else {
      setLEDStatus(idleModeActive ? "idle" : "sleeping");
      sendBLEResponse("OK");
      stopBLEAdvertising();
      return true;
    }
    setLEDStatus(idleModeActive ? "idle" : (dashboardModeActive ? "dashboard_active" : "sleeping"));
  } else if (command.startsWith("set ledHeartbeatIntervalMs ")) {
    String value = command.substring(27);
    unsigned long parsed = value.toInt();
    if (parsed < 1000UL) {
      sendBLEResponse("ERROR: ledHeartbeatIntervalMs must be >= 1000");
      return true;
    }
    ledHeartbeatIntervalMs = parsed;
    saveConfigVar("ledHeartbeatIntervalMs", String(ledHeartbeatIntervalMs));
  } else if (command.startsWith("set ledHeartbeatOnMs ")) {
    String value = command.substring(21);
    unsigned long parsed = value.toInt();
    if (parsed < 100UL || parsed >= ledHeartbeatIntervalMs) {
      sendBLEResponse("ERROR: ledHeartbeatOnMs must be >= 100 and below ledHeartbeatIntervalMs");
      return true;
    }
    ledHeartbeatOnMs = parsed;
    saveConfigVar("ledHeartbeatOnMs", String(ledHeartbeatOnMs));
  } else {
    return false;
  }

  sendBLEResponse("OK");
  return true;
}

// =============================================================================
// BLE CALLBACK CLASSES
// =============================================================================

class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
      deviceConnected = true;
      Serial.println("[BLE] Device connected");
      
      // Request larger MTU to prevent data truncation
      // Default MTU is 23 bytes (20 bytes payload), which is too small for our readings (~50-60 bytes)
      // The Arduino BLE library's setMTU() will handle the MTU exchange with the client
      // iOS typically negotiates to ~185 bytes automatically, Android can go up to 512 bytes
      // We request 512 bytes (maximum) and let the client negotiate the actual value
      BLEDevice::setMTU(512);
      VERBOSE_PRINTLN("[BLE] MTU negotiation requested (512 bytes) - client will negotiate actual value");
    };

    void onDisconnect(BLEServer* pServer) {
      deviceConnected = false;
      VERBOSE_PRINTLN("[BLE] Device disconnected");
      
      // Restart advertising if Dashboard Mode is still active
      // This allows reconnection without restarting the ESP32
      if (dashboardModeActive) {
        delay(500); // Small delay to ensure clean disconnection
        bleAdvertising = false; // Reset flag so startBLEAdvertising() will restart it
        startBLEAdvertising(); // Use the proper function to restart advertising
      }
    }
};

class MyCharacteristicCallbacks: public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
      String rxValue = pCharacteristic->getValue().c_str();
      
      if (rxValue.length() > 0) {
        VERBOSE_PRINTLN("[BLE] Received command: " + rxValue);
        
        // Process the command (same as serial commands)
        String command = rxValue;
        command.trim();
        
        // Mark host as active for sleep gating
        lastCommandTime = millis();
        
        // Process BLE command
        processBLECommand(command);
      }
    }
};

// =============================================================================
// BLE MANAGEMENT FUNCTIONS
// =============================================================================

void initBLE() {
  if (bleInitialized) return;
  
  VERBOSE_PRINTLN("[BLE] Initializing BLE...");
  
  BLEDevice::init("RFID Reader");
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  BLEService *pService = pServer->createService(RFID_SERVICE_UUID);

  // Command characteristic (mobile app -> ESP32)
  pCommandCharacteristic = pService->createCharacteristic(
                                         COMMAND_CHAR_UUID,
                                         BLECharacteristic::PROPERTY_WRITE
                                       );
  pCommandCharacteristic->setCallbacks(new MyCharacteristicCallbacks());

  // Response characteristic (ESP32 -> mobile app)
  pResponseCharacteristic = pService->createCharacteristic(
                                         RESPONSE_CHAR_UUID,
                                         BLECharacteristic::PROPERTY_READ |
                                         BLECharacteristic::PROPERTY_NOTIFY
                                       );
  pResponseCharacteristic->addDescriptor(new BLE2902());

  // Status characteristic (ESP32 -> mobile app)
  pStatusCharacteristic = pService->createCharacteristic(
                                         STATUS_CHAR_UUID,
                                         BLECharacteristic::PROPERTY_READ |
                                         BLECharacteristic::PROPERTY_NOTIFY
                                       );
  pStatusCharacteristic->addDescriptor(new BLE2902());

  pService->start();
  bleInitialized = true;
  VERBOSE_PRINTLN("[BLE] BLE service initialized");
}

void startBLEAdvertising() {
  if (!bleInitialized) {
    initBLE();
  }
  
  if (!bleAdvertising) {
    BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(RFID_SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    pAdvertising->setMinPreferred(0x06);
    pAdvertising->setMaxPreferred(0x12);
    BLEDevice::startAdvertising();
    bleAdvertising = true;
    VERBOSE_PRINTLN("[BLE] BLE advertising started");
  }
}

void stopBLEAdvertising() {
  if (bleAdvertising) {
    BLEDevice::stopAdvertising();
    bleAdvertising = false;
    VERBOSE_PRINTLN("[BLE] BLE advertising stopped");
  }
  
  // ESP32-S3: Completely deinitialize BLE when not in Dashboard Mode
  // This prevents BLE from interfering with USB-CDC Serial during sleep/wake cycles
  if (bleInitialized) {
    // Stop Bluetooth controller to free resources and prevent USB-CDC interference
    btStop();
    bleInitialized = false;
    pServer = nullptr;
    pCommandCharacteristic = nullptr;
    pResponseCharacteristic = nullptr;
    pStatusCharacteristic = nullptr;
    deviceConnected = false;
    VERBOSE_PRINTLN("[BLE] BLE deinitialized to prevent USB-CDC interference");
  }
}

void sendBLEResponse(const String& response) {
  if (deviceConnected && pResponseCharacteristic) {
    // V2 responses are newline-delimited UTF-8. Split bytes to the negotiated
    // payload size; the app buffers bytes until a complete line is available.
    String framed = response;
    if (!framed.endsWith("\n")) framed += "\n";
    uint16_t mtu = pServer ? pServer->getPeerMTU(pServer->getConnId()) : 23;
    size_t payloadLimit = mtu > 3 ? mtu - 3 : 20;
    if (payloadLimit > 180) payloadLimit = 180;
    for (size_t offset = 0; offset < framed.length() && deviceConnected; offset += payloadLimit) {
      size_t length = framed.length() - offset;
      if (length > payloadLimit) length = payloadLimit;
      pResponseCharacteristic->setValue(
        reinterpret_cast<const uint8_t*>(framed.c_str()) + offset, length);
      pResponseCharacteristic->notify();
      // Retain the existing pacing for mobile notification queues.
      delay(300);
      yield();
    }
  }
}

void sendBLEStatus(const String& status) {
  if (deviceConnected && pStatusCharacteristic) {
    pStatusCharacteristic->setValue(status.c_str());
    pStatusCharacteristic->notify();
    VERBOSE_PRINTLN("[BLE] Sent status: " + status);
  }
}

void processBLECommand(const String& command) {
  // Process the same commands as serial interface
  if (command == "protocol") {
    sendBLEResponse("RFID_PROTOCOL_V2");
  }
  else if (command == "status") {
    String response = "Dashboard Mode: " + String(dashboardModeActive ? "ACTIVE" : "INACTIVE") +
                     "\nIdle mode: " + String(idleModeActive ? "ACTIVE" : "INACTIVE") +
                     "\nIdle reason: " + String(idleReasonToString(latestIdleReason)) +
                     "\nLow SoC idle: " + String(socLowIdleEnabled ? "ENABLED" : "DISABLED") +
                     "\nLow SoC USB recovery: " + String(lowSocUsbRecoveryWindowActive() ? "ACTIVE" : "INACTIVE") +
                     "\nUSB recovery remaining: " + String(lowSocUsbRecoveryWindowRemainingMs() / 1000UL) + "s";
    String batteryStatus = "Reading count: " + String(readingCount) +
                           "\nLED status: " + currentLEDStatus;
    float batteryVoltage = 0.0f;
    float socPercent = 0.0f;
    uint16_t rawAdc = 0;
    uint32_t pinMilliVolts = 0;
    if (readBatterySoc(batteryVoltage, socPercent, rawAdc, pinMilliVolts)) {
      batteryStatus += "\nBattery voltage: " + String(batteryVoltage, 3);
      batteryStatus += "\nBattery SoC: " + String(socPercent, 1);
    } else {
      batteryStatus += "\nBattery voltage: N/A";
      batteryStatus += "\nBattery SoC: N/A";
    }
    sendBLEResponse(response);
    sendBLEResponse(batteryStatus);
  }
  else if (command == "debugsimple") {
    String response = "ESP32 Status: OK\nReading count: " + String(readingCount) + 
                     "\nDashboard mode: " + String(dashboardModeActive ? "ACTIVE" : "INACTIVE") +
                     "\nIdle mode: " + String(idleModeActive ? "ACTIVE" : "INACTIVE") +
                     "\nIdle reason: " + String(idleReasonToString(latestIdleReason)) +
                     "\nLow SoC idle: " + String(socLowIdleEnabled ? "ENABLED" : "DISABLED") +
                     "\nLow SoC USB recovery: " + String(lowSocUsbRecoveryWindowActive() ? "ACTIVE" : "INACTIVE") +
                     " (" + String(lowSocUsbRecoveryWindowRemainingMs() / 1000UL) + "s remaining)";
    String socLine;
    float batteryVoltage = 0.0f;
    float socPercent = 0.0f;
    uint16_t rawAdc = 0;
    uint32_t pinMilliVolts = 0;
    if (readBatterySoc(batteryVoltage, socPercent, rawAdc, pinMilliVolts)) {
      socLine = "[SOC] Latest: raw=" + String(rawAdc) +
                ", pin=" + String(pinMilliVolts) + "mV" +
                ", battery=" + String(batteryVoltage, 3) + "V" +
                ", soc=" + String(socPercent, 1) + "%";
    } else {
      socLine = "[SOC] Latest: N/A";
    }
    sendBLEResponse(response);
    sendBLEResponse(socLine);
  }
  else if (command == "print") {
    // Send first chunk via BLE (pagination support)
    // For backward compatibility, "print" sends chunk 0
    sendStoredReadingsByBLEChunk(0);
  }
  else if (command.startsWith("print_chunk ")) {
    // Process pagination command: "print_chunk N" where N is the chunk index
    String chunkStr = command.substring(12);
    chunkStr.trim();
    int chunkIndex = chunkStr.toInt();
    if (chunkIndex >= 0) {
      sendStoredReadingsByBLEChunk(chunkIndex);
    } else {
      sendBLEResponse("ERROR: Invalid chunk index");
    }
  }
  else if (command.startsWith("range ")) {
    // Process range command - send first chunk (chunk 0) for pagination support
    String rangeCmd = command.substring(6);
    int spaceIndex = rangeCmd.indexOf(' ');
    if (spaceIndex > 0) {
      uint32_t startTime = rangeCmd.substring(0, spaceIndex).toInt();
      uint32_t endTime = rangeCmd.substring(spaceIndex + 1).toInt();
      sendStoredReadingsByRangeBLEChunk(startTime, endTime, 0);
    } else {
      VERBOSE_PRINTLN("[BLE] ERROR: Invalid range command format");
      sendBLEResponse("ERROR: Invalid range command format");
    }
  }
  else if (command.startsWith("range_chunk ")) {
    // Process pagination command for range queries: "range_chunk START END CHUNK" where CHUNK is the chunk index
    String chunkCmd = command.substring(12);
    int firstSpace = chunkCmd.indexOf(' ');
    int secondSpace = chunkCmd.indexOf(' ', firstSpace + 1);
    if (firstSpace > 0 && secondSpace > 0) {
      uint32_t startTime = chunkCmd.substring(0, firstSpace).toInt();
      uint32_t endTime = chunkCmd.substring(firstSpace + 1, secondSpace).toInt();
      String chunkStr = chunkCmd.substring(secondSpace + 1);
      chunkStr.trim();
      int chunkIndex = chunkStr.toInt();
      if (chunkIndex >= 0) {
        sendStoredReadingsByRangeBLEChunk(startTime, endTime, chunkIndex);
      } else {
        sendBLEResponse("ERROR: Invalid chunk index");
      }
    } else {
      VERBOSE_PRINTLN("[BLE] ERROR: Invalid range_chunk command format");
      sendBLEResponse("ERROR: Invalid range_chunk command format");
    }
  }
  else if (command == "last") {
    // Send only the last reading via BLE
    sendLastReadingByBLE();
  }
  else if (command == "readnow") {
    // Trigger manual RFID read (same as button press)
    if (!rfidReadsAllowed()) {
      sendBLEResponse("[IDLE] Manual read blocked: " + String(idleReasonToString(latestIdleReason)));
    } else {
      sendBLEResponse("[MANUAL] Starting RFID read window (" + String(rfidOnTimeMs) + "ms)");
      markBLEManualReadActivity();
      powerOnAndReadTagWindow(rfidOnTimeMs);
      markBLEManualReadActivity();
      sendBLEResponse("[MANUAL] RFID read complete count=" + String(readingCount));
    }
  }
  else if (command == "readant 1" || command == "readant 2") {
    uint8_t antennaId = command.endsWith("2") ? 2 : 1;
    if (!rfidReadsAllowed()) {
      sendBLEResponse("[IDLE] Manual read blocked: " + String(idleReasonToString(latestIdleReason)));
    } else {
      sendBLEResponse("[MANUAL] Starting ANT" + String(antennaId) + " RFID read window (" + String(rfidOnTimeMs) + "ms)");
      markBLEManualReadActivity();
      powerOnAndReadSingleAntennaWindow(rfidOnTimeMs, antennaId);
      markBLEManualReadActivity();
      sendBLEResponse("[MANUAL] ANT" + String(antennaId) + " RFID read complete count=" + String(readingCount));
    }
  }
  else if (command == "dashboardmode on") {
    dashboardModeActive = true;
    saveConfigVar("dashboardModeActive", "true");
    setLEDStatus(idleModeActive ? "idle" : "dashboard_active");
    startBLEAdvertising();
    sendBLEResponse("[DASHBOARD] Dashboard Mode: ON - ESP32 will stay awake");
    sendBLEResponse("OK");
  }
  else if (command == "dashboardmode off") {
    dashboardModeActive = false;
    saveConfigVar("dashboardModeActive", "false");
    setLEDStatus(idleModeActive ? "idle" : "sleeping");
    sendBLEResponse("[DASHBOARD] Dashboard Mode: OFF - ESP32 will use light sleep");
    sendBLEResponse("OK");
    stopBLEAdvertising();
  }
  else if (command.startsWith("get ")) {
    if (!processBLEGetCommand(command)) {
      sendBLEResponse("ERROR: Unknown get command");
    }
  }
  else if (command.startsWith("set ")) {
    if (!processBLESetCommand(command)) {
      sendBLEResponse("ERROR: Unknown set command");
    }
  }
  else if (command == "clear") {
    SPIFFS.remove(FLASH_FILENAME);
    readingCount = 0;
    sendBLEResponse("Cleared");
  }
  else {
    sendBLEResponse("ERROR: Unknown command: " + command);
  }
}

void sendStoredReadingsByBLE() {
  // Recalculate readingCount from file size to ensure accuracy
  // This ensures we get the latest count even if readingCount was out of sync
  File countFile = SPIFFS.open(FLASH_FILENAME, "r");
  int actualCount = 0;
  if (countFile) {
    actualCount = countFile.size() / READING_SIZE;
    countFile.close();
    readingCount = actualCount; // Update global count
  }
  
  if (readingCount == 0) {
    sendBLEResponse("---BEGIN_READINGS---");
    sendBLEResponse("Printing 0 stored readings:");
    sendBLEResponse("---END_READINGS---");
    return;
  }
  
  sendBLEResponse("---BEGIN_READINGS---");
  sendBLEResponse("Printing " + String(readingCount) + " stored readings:");
  
  File file = SPIFFS.open(FLASH_FILENAME, "r");
  if (!file) { 
    sendBLEResponse("---END_READINGS---"); 
    return; 
  }
  
  // Send readings in small batches (2 readings per notification) to balance reliability and speed
  // iOS has a very limited notification queue (~10-15 notifications)
  // Batching reduces the number of notifications while keeping each batch well under MTU limits
  // Each reading is ~50-60 bytes, so 2 readings = ~100-120 bytes (safe for iOS MTU ~185 bytes)
  const int BATCH_SIZE = 2;
  String batchBuffer = "";
  int batchCount = 0;
  int i = 0;
  
  while (file.available() >= READING_SIZE) {
    // Check if device is still connected before sending (prevents sending to disconnected device)
    if (!deviceConnected) {
      VERBOSE_PRINTLN("[BLE] Device disconnected during send, aborting");
      break;
    }
    
    // ESP32-S3: Reset watchdog during long operations
    yield();  // Use yield() for compatibility
    
    RfidReading reading;
    file.read((uint8_t*)&reading, READING_SIZE);
    if (reading.timestamp > 1000000000) {
      String readingStr = formatReadingLine(i + 1, reading);
      
      // Add reading to batch buffer
      if (batchBuffer.length() > 0) {
        batchBuffer += "\n"; // Separate readings with newline
      }
      batchBuffer += readingStr;
      batchCount++;
      
      // Send batch when it reaches BATCH_SIZE
      if (batchCount >= BATCH_SIZE) {
        // Log every 10 batches to reduce serial spam
        if ((i + 1) % 20 == 0 || i == 0) {
          VERBOSE_PRINTF("[BLE] Sending batch of %d readings (size: %d bytes, total sent: %d/%d)\n", batchCount, batchBuffer.length(), i + 1, readingCount);
        }
        sendBLEResponse(batchBuffer);
        batchBuffer = ""; // Clear buffer
        batchCount = 0;
        // Additional yield after sending batch
        yield();
      }
    }
    i++; 
    yield();
  }
  
  // Send any remaining readings in the buffer
  if (batchBuffer.length() > 0) {
    VERBOSE_PRINTF("[BLE] Sending final batch of %d readings (size: %d bytes)\n", batchCount, batchBuffer.length());
    sendBLEResponse(batchBuffer);
  }
  file.close();
  
  sendBLEResponse("---END_READINGS---");
}

void sendStoredReadingsByBLEChunk(int chunkIndex) {
  // Pagination support: Send readings in chunks to avoid iOS notification queue overflow
  // Chunk size: 15 readings per chunk (fits safely in iOS notification queue)
  const int CHUNK_SIZE = 15;
  
  // Recalculate readingCount from file size to ensure accuracy
  File countFile = SPIFFS.open(FLASH_FILENAME, "r");
  int actualCount = 0;
  if (countFile) {
    actualCount = countFile.size() / READING_SIZE;
    countFile.close();
    readingCount = actualCount; // Update global count
  }
  
  if (readingCount == 0) {
    sendBLEResponse("---BEGIN_READINGS---");
    sendBLEResponse("Printing 0 stored readings:");
    sendBLEResponse("---END_READINGS---");
    return;
  }
  
  // Calculate chunk information
  int totalChunks = (readingCount + CHUNK_SIZE - 1) / CHUNK_SIZE; // Ceiling division
  int startIndex = chunkIndex * CHUNK_SIZE;
  int endIndex = min(startIndex + CHUNK_SIZE, readingCount);
  bool hasMore = (chunkIndex + 1) < totalChunks;
  
  // Validate chunk index
  if (chunkIndex < 0 || startIndex >= readingCount) {
    sendBLEResponse("ERROR: Invalid chunk index " + String(chunkIndex));
    return;
  }
  
  // Send chunk metadata
  if (chunkIndex == 0) {
    // First chunk: send BEGIN marker and total count
    sendBLEResponse("---BEGIN_READINGS---");
    sendBLEResponse("Printing " + String(readingCount) + " stored readings (chunk " + String(chunkIndex + 1) + "/" + String(totalChunks) + "):");
  } else {
    // Subsequent chunks: send chunk info only
    sendBLEResponse("Chunk " + String(chunkIndex + 1) + "/" + String(totalChunks) + " (readings " + String(startIndex + 1) + "-" + String(endIndex) + "):");
  }
  
  File file = SPIFFS.open(FLASH_FILENAME, "r");
  if (!file) { 
    sendBLEResponse("ERROR: Failed to open FLASH file");
    sendBLEResponse("---END_READINGS---");
    return; 
  }
  
  // Skip to the start of the requested chunk
  file.seek(startIndex * READING_SIZE);
  
  // Send readings in small batches (2 readings per notification) to balance reliability and speed
  const int BATCH_SIZE = 2;
  String batchBuffer = "";
  int batchCount = 0;
  int readingsInChunk = 0;
  
  for (int i = startIndex; i < endIndex && file.available() >= READING_SIZE; i++) {
    // Check if device is still connected before sending
    if (!deviceConnected) {
      VERBOSE_PRINTLN("[BLE] Device disconnected during send, aborting");
      break;
    }
    
    // ESP32-S3: Reset watchdog during long operations
    yield();
    
    RfidReading reading;
    file.read((uint8_t*)&reading, READING_SIZE);
    if (reading.timestamp > 1000000000) {
      String readingStr = formatReadingLine(i + 1, reading);
      
      // Add reading to batch buffer
      if (batchBuffer.length() > 0) {
        batchBuffer += "\n";
      }
      batchBuffer += readingStr;
      batchCount++;
      readingsInChunk++;
      
      // Send batch when it reaches BATCH_SIZE
      if (batchCount >= BATCH_SIZE) {
        sendBLEResponse(batchBuffer);
        batchBuffer = "";
        batchCount = 0;
        yield();
      }
    }
    yield();
  }
  
  // Send any remaining readings in the buffer
  if (batchBuffer.length() > 0) {
    sendBLEResponse(batchBuffer);
  }
  
  file.close();
  
  // Send chunk completion marker
  if (hasMore) {
    sendBLEResponse("---CHUNK_COMPLETE---");
  } else {
    sendBLEResponse("---END_READINGS---");
  }
}

// Range response entry point; starts BLE pagination at the first chunk.
void sendStoredReadingsByRangeBLE(uint32_t startTime, uint32_t endTime) {
  sendStoredReadingsByRangeBLEChunk(startTime, endTime, 0);
}

void sendStoredReadingsByRangeBLEChunk(uint32_t startTime, uint32_t endTime, int chunkIndex) {
  // Pagination support: Send range readings in chunks to avoid iOS notification queue overflow
  // Chunk size: 15 readings per chunk (fits safely in iOS notification queue)
  const int CHUNK_SIZE = 15;
  
  sendBLEResponse("=== Range Request Start ===");
  
  File file = SPIFFS.open(FLASH_FILENAME, "r");
  if (!file) { 
    sendBLEResponse("ERROR: Failed to open FLASH file");
    sendBLEResponse("---BEGIN_READINGS---");
    sendBLEResponse("---END_READINGS---");
    return; 
  }
  
  // First pass: collect all valid readings in range
  std::vector<RfidReading> validReadings;
  int scanned = 0; int matched = 0;
  while (file.available() >= READING_SIZE) {
    RfidReading reading;
    file.read((uint8_t*)&reading, READING_SIZE);
    // Filter: must be valid timestamp (after year 2001) AND within the specified time range
    // Note: reading.timestamp is stored as Unix epoch (UTC)
    if (reading.timestamp > 1000000000 &&
        reading.timestamp >= startTime && reading.timestamp <= endTime) {
      validReadings.push_back(reading);
      matched++;
    }
    scanned++;
    yield();
  }
  file.close();
  
  
  // Calculate chunk information
  int totalChunks = (validReadings.size() + CHUNK_SIZE - 1) / CHUNK_SIZE; // Ceiling division
  int startIndex = chunkIndex * CHUNK_SIZE;
  int endIndex = min(startIndex + CHUNK_SIZE, (int)validReadings.size());
  bool hasMore = (chunkIndex + 1) < totalChunks;

  if (validReadings.empty() && chunkIndex == 0) {
    sendBLEResponse("Found 0 readings in range.");
    sendBLEResponse("---BEGIN_READINGS---");
    sendBLEResponse("---END_READINGS---");
    sendBLEResponse("=== Range Request End ===");
    return;
  }
  
  // Validate chunk index
  if (chunkIndex < 0 || startIndex >= (int)validReadings.size()) {
    sendBLEResponse("ERROR: Invalid chunk index " + String(chunkIndex));
    sendBLEResponse("---END_READINGS---");
    return;
  }
  
  // Send count and chunk metadata
  if (chunkIndex == 0) {
    // First chunk: send count and BEGIN marker
    sendBLEResponse("Found " + String(validReadings.size()) + " readings in range.");
    sendBLEResponse("---BEGIN_READINGS---");
    sendBLEResponse("Range readings (chunk " + String(chunkIndex + 1) + "/" + String(totalChunks) + "):");
  } else {
    // Subsequent chunks: send chunk info only
    sendBLEResponse("Chunk " + String(chunkIndex + 1) + "/" + String(totalChunks) + " (readings " + String(startIndex + 1) + "-" + String(endIndex) + "):");
  }
  
  // Send readings in small batches (2 readings per notification) to balance reliability and speed
  const int BATCH_SIZE = 2;
  String batchBuffer = "";
  int batchCount = 0;
  
  for (int i = startIndex; i < endIndex; ++i) {
    // Check if device is still connected before sending
    if (!deviceConnected) {
      VERBOSE_PRINTLN("[BLE] Device disconnected during range send, aborting");
      break;
    }
    
    // Calculate global reading number within the filtered list
    // i is already the index in validReadings (which contains only filtered readings)
    // So reading number is simply i + 1 (1-indexed for display)
    int globalReadingNum = i + 1;
    String readingStr = formatReadingLine(globalReadingNum, validReadings[i]);
    
    // Add reading to batch buffer
    if (batchBuffer.length() > 0) {
      batchBuffer += "\n";
    }
    batchBuffer += readingStr;
    batchCount++;
    
    // Send batch when it reaches BATCH_SIZE
    if (batchCount >= BATCH_SIZE) {
      sendBLEResponse(batchBuffer);
      batchBuffer = "";
      batchCount = 0;
      yield();
    }
  }
  
  // Send any remaining readings in the buffer
  if (batchBuffer.length() > 0) {
    sendBLEResponse(batchBuffer);
  }
  
  // Send chunk completion marker
  if (hasMore) {
    sendBLEResponse("---CHUNK_COMPLETE---");
  } else {
    sendBLEResponse("---END_READINGS---");
    sendBLEResponse("=== Range Request End ===");
  }
}

void sendLastReadingByBLE() {
  if (readingCount == 0) { 
    sendBLEResponse("No readings stored.");
    return; 
  }
  
  sendBLEResponse("---BEGIN_READINGS---");
  sendBLEResponse("Last reading:");
  
  File file = SPIFFS.open(FLASH_FILENAME, "r");
  if (!file) { 
    sendBLEResponse("ERROR: Failed to open FLASH file");
    sendBLEResponse("---END_READINGS---");
    return; 
  }
  
  // Skip to the last reading
  int totalReadings = file.size() / READING_SIZE;
  if (totalReadings > 0) {
    // Seek to the last reading
    file.seek((totalReadings - 1) * READING_SIZE, SeekSet);
    
    RfidReading reading;
    if (file.read((uint8_t*)&reading, READING_SIZE) == READING_SIZE) {
      if (reading.timestamp > 1000000000) {
        String readingStr = formatReadingLine(totalReadings, reading);
        sendBLEResponse(readingStr);
      }
    }
  }
  file.close();
  sendBLEResponse("---END_READINGS---");
}
