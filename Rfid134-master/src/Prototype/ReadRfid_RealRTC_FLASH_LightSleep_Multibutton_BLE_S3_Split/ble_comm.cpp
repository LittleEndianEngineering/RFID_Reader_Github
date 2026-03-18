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
#include "flash_store.h"
#include "rfid_reader.h"

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
      Serial.println("[BLE] MTU negotiation requested (512 bytes) - client will negotiate actual value");
    };

    void onDisconnect(BLEServer* pServer) {
      deviceConnected = false;
      Serial.println("[BLE] Device disconnected");
      
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
        Serial.println("[BLE] Received command: " + rxValue);
        
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
  
  Serial.println("[BLE] Initializing BLE...");
  
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
  Serial.println("[BLE] BLE service initialized");
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
    Serial.println("[BLE] BLE advertising started");
  }
}

void stopBLEAdvertising() {
  if (bleAdvertising) {
    BLEDevice::stopAdvertising();
    bleAdvertising = false;
    Serial.println("[BLE] BLE advertising stopped");
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
    Serial.println("[BLE] BLE deinitialized to prevent USB-CDC interference");
  }
}

void sendBLEResponse(const String& response) {
  if (deviceConnected && pResponseCharacteristic) {
    // Check message length to prevent truncation
    // BLE notifications/indications are limited to MTU - 3 bytes
    // iOS typically negotiates to ~185 bytes, so payload limit is ~182 bytes
    // Android can negotiate up to 512 bytes, so payload limit is ~509 bytes
    // Our readings are ~50-60 bytes, so they should fit, but we check anyway
    int msgLength = response.length();
    const int SAFE_MTU_LIMIT = 180;  // Conservative limit (iOS default ~185 - 3 = 182)
    if (msgLength > SAFE_MTU_LIMIT) {
      Serial.printf("[BLE] WARNING: Message length (%d bytes) exceeds safe MTU limit (%d bytes), truncation possible\n", msgLength, SAFE_MTU_LIMIT);
    }
    
    // Set the characteristic value first, then notify
    // This ensures the data is ready before notification is sent
    pResponseCharacteristic->setValue(response.c_str());
    
    // Send notification (ESP32 -> iOS/Android)
    // The PROPERTY_NOTIFY flag ensures this works correctly
    pResponseCharacteristic->notify();
    // Only log every 10th message to reduce serial spam (since we're sending one reading per notification)
    static int logCounter = 0;
    if (++logCounter % 10 == 0 || response.indexOf("BEGIN") >= 0 || response.indexOf("END") >= 0 || response.indexOf("Printing") >= 0) {
      Serial.println("[BLE] Sent response: " + response);
    }
    // Delay to prevent BLE notification queue overflow on iOS
    // iOS has a very limited notification queue (~10-15 notifications)
    // With batches of 2 readings, we have fewer notifications but each is still safe
    // 300ms delay gives iOS time to process each batch before the next one is sent
    // This prevents queue overflow while being faster than single-reading approach
    delay(300); // 300ms delay between BLE notifications (batched approach reduces total notifications)
    // Allow BLE stack to process the notification
    yield();
  }
}

void sendBLEStatus(const String& status) {
  if (deviceConnected && pStatusCharacteristic) {
    pStatusCharacteristic->setValue(status.c_str());
    pStatusCharacteristic->notify();
    Serial.println("[BLE] Sent status: " + status);
  }
}

void processBLECommand(const String& command) {
  // Process the same commands as serial interface
  if (command == "status") {
    String response = "Dashboard Mode: " + String(dashboardModeActive ? "ACTIVE" : "INACTIVE");
    sendBLEResponse(response);
  }
  else if (command == "debugsimple") {
    String response = "ESP32 Status: OK\nReading count: " + String(readingCount) + 
                     "\nDashboard mode: " + String(dashboardModeActive ? "ACTIVE" : "INACTIVE");
    sendBLEResponse(response);
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
      Serial.println("[BLE] ERROR: Invalid range command format");
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
      Serial.println("[BLE] ERROR: Invalid range_chunk command format");
      sendBLEResponse("ERROR: Invalid range_chunk command format");
    }
  }
  else if (command == "last") {
    // Send only the last reading via BLE
    sendLastReadingByBLE();
  }
  else if (command == "readnow") {
    // Trigger manual RFID read (same as button press)
    sendBLEResponse("[MANUAL] Starting RFID read...");
    powerOnAndReadTagWindow(rfidOnTimeMs);
  }
  else {
    sendBLEResponse("Unknown command: " + command);
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
    sendBLEResponse("No readings stored.");
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
      Serial.println("[BLE] Device disconnected during send, aborting");
      break;
    }
    
    // ESP32-S3: Reset watchdog during long operations
    yield();  // Use yield() for compatibility
    
    RfidReading reading;
    file.read((uint8_t*)&reading, READING_SIZE);
    if (reading.timestamp > 1000000000) {
      time_t timestamp = reading.timestamp;
      struct tm* ti = gmtime(&timestamp);
      String readingStr;
      
      // Check if temperature is available (0xFFFF = marker for N/A)
      if (reading.temp_raw == 0xFFFF) {
        readingStr = "#" + String(i + 1) + ": " + 
                     String(ti->tm_year + 1900) + "-" + 
                     String(ti->tm_mon + 1) + "-" + 
                     String(ti->tm_mday) + " " + 
                     String(ti->tm_hour) + ":" + 
                     String(ti->tm_min) + ":" + 
                     String(ti->tm_sec) + ", " + 
                     String(reading.country) + ", " + 
                     String(reading.id) + ", N/A";
      } else {
        float temp = reading.temp_raw / 100.0f;
        readingStr = "#" + String(i + 1) + ": " + 
                         String(ti->tm_year + 1900) + "-" + 
                         String(ti->tm_mon + 1) + "-" + 
                         String(ti->tm_mday) + " " + 
                         String(ti->tm_hour) + ":" + 
                         String(ti->tm_min) + ":" + 
                         String(ti->tm_sec) + ", " + 
                         String(reading.country) + ", " + 
                         String(reading.id) + ", " + 
                         String(temp, 2) + "°C";
      }
      
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
          Serial.printf("[BLE] Sending batch of %d readings (size: %d bytes, total sent: %d/%d)\n", batchCount, batchBuffer.length(), i + 1, readingCount);
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
    Serial.printf("[BLE] Sending final batch of %d readings (size: %d bytes)\n", batchCount, batchBuffer.length());
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
    sendBLEResponse("No readings stored.");
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
      Serial.println("[BLE] Device disconnected during send, aborting");
      break;
    }
    
    // ESP32-S3: Reset watchdog during long operations
    yield();
    
    RfidReading reading;
    file.read((uint8_t*)&reading, READING_SIZE);
    if (reading.timestamp > 1000000000) {
      time_t timestamp = reading.timestamp;
      struct tm* ti = gmtime(&timestamp);
      String readingStr;
      
      // Check if temperature is available (0xFFFF = marker for N/A)
      if (reading.temp_raw == 0xFFFF) {
        readingStr = "#" + String(i + 1) + ": " + 
                     String(ti->tm_year + 1900) + "-" + 
                     String(ti->tm_mon + 1) + "-" + 
                     String(ti->tm_mday) + " " + 
                     String(ti->tm_hour) + ":" + 
                     String(ti->tm_min) + ":" + 
                     String(ti->tm_sec) + ", " + 
                     String(reading.country) + ", " + 
                     String(reading.id) + ", N/A";
      } else {
        float temp = reading.temp_raw / 100.0f;
        readingStr = "#" + String(i + 1) + ": " + 
                     String(ti->tm_year + 1900) + "-" + 
                     String(ti->tm_mon + 1) + "-" + 
                     String(ti->tm_mday) + " " + 
                     String(ti->tm_hour) + ":" + 
                     String(ti->tm_min) + ":" + 
                     String(ti->tm_sec) + ", " + 
                     String(reading.country) + ", " + 
                     String(reading.id) + ", " + 
                     String(temp, 2) + "°C";
      }
      
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

// Legacy function - now calls chunked version with chunk 0
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
      Serial.println("[BLE] Device disconnected during range send, aborting");
      break;
    }
    
    time_t timestamp = validReadings[i].timestamp;
    struct tm* ti = gmtime(&timestamp);
    String readingStr;
    
    // Calculate global reading number within the filtered list
    // i is already the index in validReadings (which contains only filtered readings)
    // So reading number is simply i + 1 (1-indexed for display)
    int globalReadingNum = i + 1;
    
    // Check if temperature is available (0xFFFF = marker for N/A)
    if (validReadings[i].temp_raw == 0xFFFF) {
      readingStr = "#" + String(globalReadingNum) + ": " + 
                       String(ti->tm_year + 1900) + "-" + 
                       String(ti->tm_mon + 1) + "-" + 
                       String(ti->tm_mday) + " " + 
                       String(ti->tm_hour) + ":" + 
                       String(ti->tm_min) + ":" + 
                       String(ti->tm_sec) + ", " + 
                       String(validReadings[i].country) + ", " + 
                   String(validReadings[i].id) + ", N/A";
    } else {
      float temp = validReadings[i].temp_raw / 100.0f;
      readingStr = "#" + String(globalReadingNum) + ": " + 
                   String(ti->tm_year + 1900) + "-" + 
                   String(ti->tm_mon + 1) + "-" + 
                   String(ti->tm_mday) + " " + 
                   String(ti->tm_hour) + ":" + 
                   String(ti->tm_min) + ":" + 
                   String(ti->tm_sec) + ", " + 
                   String(validReadings[i].country) + ", " + 
                   String(validReadings[i].id) + ", " + 
                       String(temp, 2) + "°C";
    }
    
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
        time_t timestamp = reading.timestamp;
        struct tm* ti = gmtime(&timestamp);
        String readingStr;
        
        // Check if temperature is available (0xFFFF = marker for N/A)
        if (reading.temp_raw == 0xFFFF) {
          readingStr = "#" + String(totalReadings) + ": " + 
                       String(ti->tm_year + 1900) + "-" + 
                       String(ti->tm_mon + 1) + "-" + 
                       String(ti->tm_mday) + " " + 
                       String(ti->tm_hour) + ":" + 
                       String(ti->tm_min) + ":" + 
                       String(ti->tm_sec) + ", " + 
                       String(reading.country) + ", " + 
                       String(reading.id) + ", N/A";
        } else {
          float temp = reading.temp_raw / 100.0f;
          readingStr = "#" + String(totalReadings) + ": " + 
                       String(ti->tm_year + 1900) + "-" + 
                       String(ti->tm_mon + 1) + "-" + 
                       String(ti->tm_mday) + " " + 
                       String(ti->tm_hour) + ":" + 
                       String(ti->tm_min) + ":" + 
                       String(ti->tm_sec) + ", " + 
                       String(reading.country) + ", " + 
                       String(reading.id) + ", " + 
                       String(temp, 2) + "°C";
        }
        sendBLEResponse(readingStr);
      }
    }
  }
  file.close();
  sendBLEResponse("---END_READINGS---");
}
