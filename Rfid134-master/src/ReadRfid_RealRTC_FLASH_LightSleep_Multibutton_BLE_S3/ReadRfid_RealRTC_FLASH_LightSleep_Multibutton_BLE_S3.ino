/*
 * Implant RFID Reader - ESP32 Firmware (Light Sleep + Multi-Button + BLE Version)
 * ================================================================================
 *
 * PROPRIETARY SOFTWARE
 * Copyright (c) 2025 Establishment Labs
 * Developed by Little Endian Engineering
 *
 * Version: 1.4 (Light Sleep + Multi-Button + RGB LED + BLE) - ESP32-S3 Mac Compatible
 * Date: September 2025
 *
 * DESCRIPTION:
 * ESP32-based RFID reader with DS1307 RTC, SPIFFS storage, light-sleep power saving, and BLE support.
 * Features multi-button functionality, RGB LED status indicators, and BLE connectivity for mobile apps:
 * - Short press: Manual RFID reading
 * - Long press (configurable): Toggle Dashboard Mode ON/OFF
 * - Dashboard Mode: ESP32 stays awake, no periodic reads, responsive to dashboard, BLE enabled
 * - Normal Mode: Light sleep between reads, periodic RFID scanning, BLE disabled
 * - RGB LED Status: Visual feedback for booting, sleeping, reading success, dashboard active
 * - BLE Support: Mobile app connectivity (Dashboard Mode only)
 * - ESP32-S3 Mac Compatibility: USB keepalive and serial stability improvements
 *
 * NOTES:
 * - Periodic wake: RTC timer via esp_sleep_enable_timer_wakeup()
 * - Button wake: GPIO wake via gpio_wakeup_enable() + esp_sleep_enable_gpio_wakeup()
 * - UART wake: esp_sleep_enable_uart_wakeup(UART_NUM_0) so dashboard can wake the device
 * - On wake, code resumes where it left off (unlike Deep Sleep).
 * - Multi-button: Single GPIO button handles both RFID reads and dashboard mode control
 * - RGB LED: Status indicators for visual feedback (GPIO 18=Red, 19=Green, 4=Blue)
 * - BLE: Only enabled during Dashboard Mode for mobile app connectivity
 * - ESP32-S3: Mac-friendly USB CDC with keepalive system
 */

// Reading structure (20 bytes total) - MUST be defined before any includes
typedef struct RfidReading {
  uint32_t timestamp;    // Unix UTC
  uint16_t country;
  uint64_t id;
  uint16_t temp_raw;     // temp * 100
  uint8_t  flags;
  uint8_t  reserved;
} RfidReading;

#include <Rfid134.h>
#include <SPIFFS.h>
#include <time.h>
#include <WiFi.h>
#include <Wire.h>
#include <RTClib.h>
#include <FS.h>
#include <vector>
#include <esp_wifi.h>

// BLE Support
#include "BLEDevice.h"
#include "BLEServer.h"
#include "BLEUtils.h"
#include "BLE2902.h"

// Sleep & GPIO
#include "esp_sleep.h"
#include "driver/gpio.h"
#include "esp_bt.h"   // for btStop()
#include "esp_task_wdt.h"  // for watchdog functions

// UART drain and wake-up
#include "driver/uart.h"
extern "C" {
  #include "freertos/FreeRTOS.h"
  #include "freertos/task.h"
  #include "soc/soc.h"
}

/* ======== ESP32-S3 MAC COMPATIBILITY ======== */
// DEV mode removed - using single PROD mode with essential verbose output
/* ============================================== */

// =============================================================================
// CONFIGURATION SECTION
// =============================================================================

// WiFi Configuration (can be updated via serial commands)
String ssid_str = "QuesadaRivas";
String password_str = "50A5DC34CD20";
const char* ssid = ssid_str.c_str();
const char* password = password_str.c_str();

// RTC Configuration - External DS1307 Module
RTC_DS1307 rtc;
bool rtcAvailable = false;
DateTime now;
struct tm timeinfo; // For NTP sync when RTC is stopped

// Flash Storage Configuration
#define MAX_READINGS 20160
#define READING_SIZE 20
const char* FLASH_FILENAME = "/readings.dat";

// Reading structure is now defined at the top of the file

int readingCount = 0;
unsigned long startTime = 0;

// =============================================================================
// HARDWARE PIN CONFIGURATION
// =============================================================================

#define BUTTON_PIN 37        // Push button (INPUT_PULLUP): pressed = LOW
#define RFID_PWR_PIN 36      // RFID power control (active LOW)
#define RFID_TX_PIN 48       // RFID serial

// I2C Pins for RTC (DS1307) - ESP32-S3 Safe Pins
#define I2C_SDA_PIN 8        // I2C Data pin (GPIO 8 - safe on ESP32-S3)
#define I2C_SCL_PIN 9        // I2C Clock pin (GPIO 9 - safe on ESP32-S3)

// RGB LED Status Indicator (ESP32-S3 Safe Pins)
#define LED_RED_PIN 2        // Red anode pin (GPIO 2 - safe on ESP32-S3)
#define LED_GREEN_PIN 5      // Green anode pin (GPIO 5 - safe on ESP32-S3)  
#define LED_BLUE_PIN 6       // Blue anode pin (GPIO 6 - safe on ESP32-S3)

// =============================================================================
// READING CONFIGURATION
// =============================================================================

const unsigned long debounceDelay = 200; // ms
unsigned long rfidOnTimeMs = 5 * 1000;   // configurable
unsigned long lastPeriodicRead = 0;
unsigned long periodicIntervalMs = 1 * 60 * 1000UL; // configurable

// Optional: aggressively disable radios while sleeping
bool radiosOffBetweenReads = true;

// Dashboard Mode - ESP32 stays awake when dashboard is connected
bool dashboardModeActive = false;

// =============================================================================
// BLE CONFIGURATION (Dashboard Mode Only)
// =============================================================================

// BLE Service and Characteristic UUIDs
#define RFID_SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define COMMAND_CHAR_UUID        "beb5483e-36e1-4688-b7f5-ea07361b26a8"
#define RESPONSE_CHAR_UUID       "beb5483e-36e1-4688-b7f5-ea07361b26a9"
#define STATUS_CHAR_UUID         "beb5483e-36e1-4688-b7f5-ea07361b26aa"

// BLE Objects
BLEServer* pServer = nullptr;
BLECharacteristic* pCommandCharacteristic = nullptr;
BLECharacteristic* pResponseCharacteristic = nullptr;
BLECharacteristic* pStatusCharacteristic = nullptr;

// BLE State
bool deviceConnected = false;
bool bleInitialized = false;
bool bleAdvertising = false;

// =============================================================================
// MULTI-BUTTON CONFIGURATION (Long Press for Dashboard Mode)
// =============================================================================

// Button state tracking for long press detection
unsigned long buttonPressStart = 0;        // When button was first pressed
bool buttonPressed = false;                // Current button state
bool longPressDetected = false;            // Flag to prevent multiple long press events
unsigned long longPressMs = 5000;          // Configurable long press duration (default 5 seconds)
const unsigned long LONG_PRESS_FEEDBACK_MS = 1000; // Start feedback at 1 second

// Visual feedback for long press (using built-in LED or serial messages)
bool longPressFeedbackStarted = false;

// Store last tag read (for button logic)
Rfid134Reading lastTag;
bool lastTagValid = false;

// --- Host activity heartbeat (prevents sleep while dashboard is active) ---
unsigned long lastCommandTime = 0;               // updated whenever a serial command is received
const unsigned long HOST_ACTIVE_TIMEOUT_MS = 15000; // stay awake for 15s after last command

// --- UART wake-up processing ---
volatile bool uartWakePending = false;           // flag set when UART wake-up occurs
unsigned long uartWakeTime = 0;                  // timestamp of UART wake-up
const unsigned long UART_WAKE_PROCESSING_MS = 5000; // time to stay awake after UART wake-up (increased)

// --- Config Persistence ---
String configFile = "/config.txt";

// =============================================================================
// RGB LED STATUS CONTROL
// =============================================================================

// LED Status tracking
String currentLEDStatus = "off";
unsigned long ledStatusStartTime = 0;
unsigned long ledFlashDuration = 0;

// LED control functions
void setLEDColor(int red, int green, int blue) {
  digitalWrite(LED_RED_PIN, red);
  digitalWrite(LED_GREEN_PIN, green);
  digitalWrite(LED_BLUE_PIN, blue);
}

void setLEDStatus(String status) {
  currentLEDStatus = status;
  ledStatusStartTime = millis();
  
  if (status == "booting") {
    setLEDColor(1, 1, 1);      // White - booting phase
    ledFlashDuration = 0;      // Continuous
  }
  else if (status == "sleeping") {
    setLEDColor(0, 0, 1);      // Blue - light sleep
    ledFlashDuration = 0;      // Continuous
  }
  else if (status == "reading_success") {
    setLEDColor(0, 1, 0);      // Green - successful reading
    ledFlashDuration = 1000;   // Flash for 1 second
  }
  else if (status == "dashboard_active") {
    setLEDColor(1, 0, 0);      // Red - dashboard mode active
    ledFlashDuration = 0;      // Continuous
  }
  else {
    setLEDColor(0, 0, 0);      // Off
    ledFlashDuration = 0;
  }
}

// Update LED status based on current system state
void updateLEDStatus() {
  // Handle timed status changes (like reading success flash)
  if (ledFlashDuration > 0 && (millis() - ledStatusStartTime) > ledFlashDuration) {
    // Return to appropriate status based on current system state
    if (dashboardModeActive) {
      setLEDStatus("dashboard_active");
    } else {
      setLEDStatus("sleeping");
    }
  }
}

// =============================================================================
// BLE CALLBACK CLASSES
// =============================================================================

class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
      deviceConnected = true;
      Serial.println("[BLE] Device connected");
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
    pResponseCharacteristic->setValue(response.c_str());
    pResponseCharacteristic->notify();
    Serial.println("[BLE] Sent response: " + response);
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
    // Send all readings via BLE
    sendStoredReadingsByBLE();
  }
  else if (command.startsWith("range ")) {
    // Process range command
    String rangeCmd = command.substring(6);
    int spaceIndex = rangeCmd.indexOf(' ');
    if (spaceIndex > 0) {
      uint32_t startTime = rangeCmd.substring(0, spaceIndex).toInt();
      uint32_t endTime = rangeCmd.substring(spaceIndex + 1).toInt();
      sendStoredReadingsByRangeBLE(startTime, endTime);
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
  
  int i = 0;
  while (file.available() >= READING_SIZE) {
    // ESP32-S3: Reset watchdog during long operations
    yield();  // Use yield() for compatibility
    
    RfidReading reading;
    file.read((uint8_t*)&reading, READING_SIZE);
    if (reading.timestamp > 1000000000) {
      float temp = reading.temp_raw / 100.0f;
      time_t timestamp = reading.timestamp;
      struct tm* ti = gmtime(&timestamp);
      String readingStr = "#" + String(i + 1) + ": " + 
                         String(ti->tm_year + 1900) + "-" + 
                         String(ti->tm_mon + 1) + "-" + 
                         String(ti->tm_mday) + " " + 
                         String(ti->tm_hour) + ":" + 
                         String(ti->tm_min) + ":" + 
                         String(ti->tm_sec) + ", " + 
                         String(reading.country) + ", " + 
                         String(reading.id) + ", " + 
                         String(temp, 2) + "°C";
      sendBLEResponse(readingStr);
    }
    i++; 
    yield();
  }
  file.close();
  sendBLEResponse("---END_READINGS---");
}

void sendStoredReadingsByRangeBLE(uint32_t startTime, uint32_t endTime) {
  int count = 0;
  sendBLEResponse("=== Range Request Start ===");
  
  File file = SPIFFS.open(FLASH_FILENAME, "r");
  if (!file) { 
    sendBLEResponse("ERROR: Failed to open FLASH file");
    sendBLEResponse("---BEGIN_READINGS---");
    sendBLEResponse("---END_READINGS---");
    return; 
  }
  
  std::vector<RfidReading> validReadings;
  int scanned = 0; int matched = 0;
  while (file.available() >= READING_SIZE) {
    RfidReading reading;
    file.read((uint8_t*)&reading, READING_SIZE);
    if (reading.timestamp > 1000000000 &&
        reading.timestamp >= startTime && reading.timestamp <= endTime) {
      validReadings.push_back(reading);
      matched++;
    }
    count++; scanned++;
    yield();
  }
  file.close();
  
  sendBLEResponse("Found " + String(validReadings.size()) + " readings in range.");
  
  sendBLEResponse("---BEGIN_READINGS---");
  for (size_t i = 0; i < validReadings.size(); ++i) {
    float temp = validReadings[i].temp_raw / 100.0f;
    time_t timestamp = validReadings[i].timestamp;
    struct tm* ti = gmtime(&timestamp);
    String readingStr = "#" + String(i + 1) + ": " + 
                       String(ti->tm_year + 1900) + "-" + 
                       String(ti->tm_mon + 1) + "-" + 
                       String(ti->tm_mday) + " " + 
                       String(ti->tm_hour) + ":" + 
                       String(ti->tm_min) + ":" + 
                       String(ti->tm_sec) + ", " + 
                       String(validReadings[i].country) + ", " + 
                       String(validReadings[i].id) + ", " + 
                       String(temp, 2) + "°C";
    sendBLEResponse(readingStr);
  }
  sendBLEResponse("---END_READINGS---");
  sendBLEResponse("=== Range Request End ===");
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
        float temp = reading.temp_raw / 100.0f;
        time_t timestamp = reading.timestamp;
        struct tm* ti = gmtime(&timestamp);
        String readingStr = "#" + String(totalReadings) + ": " + 
                           String(ti->tm_year + 1900) + "-" + 
                           String(ti->tm_mon + 1) + "-" + 
                           String(ti->tm_mday) + " " + 
                           String(ti->tm_hour) + ":" + 
                           String(ti->tm_min) + ":" + 
                           String(ti->tm_sec) + ", " + 
                           String(reading.country) + ", " + 
                           String(reading.id) + ", " + 
                           String(temp, 2) + "°C";
        sendBLEResponse(readingStr);
      }
    }
  }
  file.close();
  sendBLEResponse("---END_READINGS---");
}

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
}

// WiFi Functions
void connectWiFi() {
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
    now = rtc.now();
    return now.unixtime(); // Store UTC timestamps directly (RTC is now set to UTC)
  } else {
    // Fallbacks: try internal time (if previously synced), then millis
    struct tm ti;
    if (getLocalTime(&ti)) return (uint32_t)mktime(&ti);
    return millis();
  }
}

// Flash Functions
void initFlash() {
  if (!SPIFFS.begin(true)) { Serial.println("[FS] SPIFFS Mount Failed"); return; }
  File file = SPIFFS.open(FLASH_FILENAME, "r");
  if (!file) readingCount = 0;
  else { readingCount = file.size() / READING_SIZE; file.close(); }
  Serial.printf("[FS] FLASH has %d readings\n", readingCount);
}

void storeReading(const RfidReading& reading) {
  if (!SPIFFS.begin(true)) { Serial.println("[FS] SPIFFS Mount Failed"); return; }
  File file = SPIFFS.open(FLASH_FILENAME, "a");
  if (!file) { Serial.println("[FS] Failed to open file for writing"); return; }
  file.write((uint8_t*)&reading, READING_SIZE);
  file.close();
  readingCount++;

  // Extra blank line before the stored-reading line
  Serial.println();
  Serial.printf("[FS] Stored reading #%d\n", readingCount);
}

void printStoredReadings() {
  if (readingCount == 0) { Serial.println("No readings stored."); return; }
  Serial.println("---BEGIN_READINGS---");
  Serial.printf("Printing %d stored readings:\n", readingCount);
  File file = SPIFFS.open(FLASH_FILENAME, "r");
  if (!file) { Serial.println("---END_READINGS---"); return; }
  int i = 0;
  while (file.available() >= READING_SIZE) {
    RfidReading reading;
    file.read((uint8_t*)&reading, READING_SIZE);
    if (reading.timestamp > 1000000000) {
      float temp = reading.temp_raw / 100.0f;
      time_t timestamp = reading.timestamp;
      struct tm* ti = gmtime(&timestamp);
      Serial.printf("#%d: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, %.2f°C\n",
                    i + 1, ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
                    ti->tm_hour, ti->tm_min, ti->tm_sec,
                    reading.country, reading.id, temp);
    }
    i++; yield();
  }
  file.close();
  Serial.println("---END_READINGS---");
}

void printLastReading() {
  if (readingCount == 0) { Serial.println("No readings stored."); return; }
  Serial.println("---BEGIN_READINGS---");
  Serial.println("Last reading:");
  File file = SPIFFS.open(FLASH_FILENAME, "r");
  if (!file) { Serial.println("---END_READINGS---"); return; }
  
  // Skip to the last reading
  int totalReadings = file.size() / READING_SIZE;
  if (totalReadings > 0) {
    // Seek to the last reading
    file.seek((totalReadings - 1) * READING_SIZE, SeekSet);
    
    RfidReading reading;
    if (file.read((uint8_t*)&reading, READING_SIZE) == READING_SIZE) {
      if (reading.timestamp > 1000000000) {
        float temp = reading.temp_raw / 100.0f;
        time_t timestamp = reading.timestamp;
        struct tm* ti = gmtime(&timestamp);
        Serial.printf("#%d: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, %.2f°C\n",
                      totalReadings, ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
                      ti->tm_hour, ti->tm_min, ti->tm_sec,
                      reading.country, reading.id, temp);
      }
    }
  }
  file.close();
  Serial.println("---END_READINGS---");
}

// NEW: concise summary for boot and on-demand
void printReadingsSummary() {
  Serial.println("[FS] --- Readings Summary ---");
  Serial.printf("[FS] Count: %d / %d\n", readingCount, MAX_READINGS);

  unsigned long usedBytes = (unsigned long)readingCount * READING_SIZE;
  unsigned long totalBytes = (unsigned long)MAX_READINGS * READING_SIZE;
  float pct = (totalBytes > 0) ? (100.0f * usedBytes / totalBytes) : 0.0f;
  Serial.printf("[FS] Bytes used: %lu of %lu (%.1f%%)\n", usedBytes, totalBytes, pct);

  if (readingCount > 0) {
    File f = SPIFFS.open(FLASH_FILENAME, "r");
    if (f) {
      RfidReading first, last;

      // First record
      f.seek(0, SeekSet);
      if (f.read((uint8_t*)&first, READING_SIZE) == READING_SIZE) {
        if (first.timestamp > 1000000000UL) {
          time_t ts = first.timestamp;
          struct tm* ti = gmtime(&ts);
          Serial.printf("[FS] Oldest: %04d-%02d-%02d %02d:%02d:%02d (country=%u id=%llu)\n",
                        ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
                        ti->tm_hour, ti->tm_min, ti->tm_sec,
                        first.country, first.id);
        }
      }

      // Last record
      f.seek((readingCount - 1) * READING_SIZE, SeekSet);
      if (f.read((uint8_t*)&last, READING_SIZE) == READING_SIZE) {
        if (last.timestamp > 1000000000UL) {
          time_t ts = last.timestamp;
          struct tm* ti = gmtime(&ts);
          Serial.printf("[FS] Newest: %04d-%02d-%02d %02d:%02d:%02d (country=%u id=%llu)\n",
                        ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
                        ti->tm_hour, ti->tm_min, ti->tm_sec,
                        last.country, last.id);
        }
      }

      f.close();
    }
  } else {
    Serial.println("[FS] No readings yet.");
  }
  Serial.println("[FS] ------------------------");
}

void sendStoredReadingsByRange(uint32_t startTime, uint32_t endTime) {
  int count = 0;
  Serial.println("[RANGE] === Range Request Start ===");
  if (startTime > 0) {
    time_t ts = startTime; struct tm* ti = gmtime(&ts);
    Serial.printf("[RANGE] Start: %04d-%02d-%02d %02d:%02d:%02d (%lu)\n",
                  ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
                  ti->tm_hour, ti->tm_min, ti->tm_sec, (unsigned long)startTime);
  } else {
    Serial.printf("[RANGE] Start: %lu (non-epoch)\n", (unsigned long)startTime);
  }
  if (endTime > 0) {
    time_t ts2 = endTime; struct tm* ti2 = gmtime(&ts2);
    Serial.printf("[RANGE] End  : %04d-%02d-%02d %02d:%02d:%02d (%lu)\n",
                  ti2->tm_year + 1900, ti2->tm_mon + 1, ti2->tm_mday,
                  ti2->tm_hour, ti2->tm_min, ti2->tm_sec, (unsigned long)endTime);
  } else {
    Serial.printf("[RANGE] End  : %lu (non-epoch)\n", (unsigned long)endTime);
  }

  File file = SPIFFS.open(FLASH_FILENAME, "r");
  if (!file) { Serial.println("[RANGE] ERROR: Failed to open FLASH file"); Serial.println("<DASHBOARD_DATA>\n---BEGIN_READINGS---\n---END_READINGS---\n</DASHBOARD_DATA>"); return; }
  Serial.printf("[RANGE] File opened. Size=%u bytes, readingCount=%d, recordSize=%d\n",
                (unsigned)file.size(), readingCount, READING_SIZE);
  std::vector<RfidReading> validReadings;
  int scanned = 0; int matched = 0;
  while (file.available() >= READING_SIZE) {
    RfidReading reading;
    file.read((uint8_t*)&reading, READING_SIZE);
    if (reading.timestamp > 1000000000 &&
        reading.timestamp >= startTime && reading.timestamp <= endTime) {
      validReadings.push_back(reading);
      matched++;
    }
    count++; scanned++;
    if ((scanned % 500) == 0) {
      Serial.printf("[RANGE] Scanned=%d, Matched=%d\n", scanned, matched);
    }
    yield();
  }
  file.close();
  count = validReadings.size();
  Serial.printf("Found %d readings in range.\n", count);
  if (count > 0) {
    float temp_first = validReadings.front().temp_raw / 100.0f;
    time_t ts_first = validReadings.front().timestamp;
    struct tm* ti_first = gmtime(&ts_first);
    Serial.printf("First: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, %.2fC\n",
      ti_first->tm_year + 1900, ti_first->tm_mon + 1, ti_first->tm_mday,
      ti_first->tm_hour, ti_first->tm_min, ti_first->tm_sec,
      validReadings.front().country, validReadings.front().id, temp_first);
    float temp_last = validReadings.back().temp_raw / 100.0f;
    time_t ts_last = validReadings.back().timestamp;
    struct tm* ti_last = gmtime(&ts_last);
    Serial.printf("Last: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, %.2fC\n",
      ti_last->tm_year + 1900, ti_last->tm_mon + 1, ti_last->tm_mday,
      ti_last->tm_hour, ti_last->tm_min, ti_last->tm_sec,
      validReadings.back().country, validReadings.back().id, temp_last);
  } else {
    Serial.println("None");
  }

  Serial.println("<DASHBOARD_DATA>");
  Serial.println("---BEGIN_READINGS---");
  for (size_t i = 0; i < validReadings.size(); ++i) {
    float temp = validReadings[i].temp_raw / 100.0f;
    time_t timestamp = validReadings[i].timestamp;
    struct tm* ti = gmtime(&timestamp);
    Serial.printf("#%d: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, %.2f°C\n",
      (int)(i + 1), ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
      ti->tm_hour, ti->tm_min, ti->tm_sec,
      validReadings[i].country, validReadings[i].id, temp);
  }
  Serial.println("---END_READINGS---");
  Serial.println("</DASHBOARD_DATA>");
  Serial.println("[RANGE] === Range Request End ===");
}

// --- Helper to try reading and storing a tag (unchanged) ---
void tryReadAndStoreTag() {
  if (lastTagValid) {
    uint8_t firstByte = lastTag.reserved1 & 0xFF;
    float temperature = 23.3 + (0.112 * firstByte);
    RfidReading storedReading;
    storedReading.timestamp = getCurrentTimestamp();
    storedReading.country = lastTag.country;
    storedReading.id = lastTag.id;
    storedReading.temp_raw = (uint16_t)(temperature * 100);
    storedReading.flags = (lastTag.isData ? 1 : 0) | (lastTag.isAnimal ? 2 : 0);
    storedReading.reserved = 0;
    storeReading(storedReading);
    Serial.printf("#%d\n", readingCount);
    Serial.printf("TAG: %03u %012llu %.2f°C\n", lastTag.country, lastTag.id, temperature);
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
class RfidNotify {
public:
  static void OnError(Rfid134_Error errorCode) {
    Serial.printf("[RFID] Error %d - ", errorCode);
    if (errorCode == 130) {
      Serial.println("Communication timeout or protocol error");
    } else if (errorCode == 131) {
      Serial.println("Checksum error");
    } else if (errorCode == 132) {
      Serial.println("Invalid response");
    } else {
      Serial.println("Unknown RFID error");
    }
  }
  static void OnPacketRead(const Rfid134Reading& reading) {
    lastTag = reading;
    lastTagValid = true;
    uint8_t firstByte = reading.reserved1 & 0xFF;
    float temperature = 23.3 + (0.112 * firstByte);
    RfidReading storedReading;
    storedReading.timestamp = getCurrentTimestamp();
    storedReading.country = reading.country;
    storedReading.id = reading.id;
    storedReading.temp_raw = (uint16_t)(temperature * 100);
    storedReading.flags = (reading.isData ? 1 : 0) | (reading.isAnimal ? 2 : 0);
    storedReading.reserved = 0;
    storeReading(storedReading);
    Serial.printf("#%d\n", readingCount);
    Serial.printf("TAG: %03u %012llu %.2f°C\n", reading.country, reading.id, temperature);
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
    
    // Trigger green LED flash for successful tag detection
    setLEDStatus("reading_success");
    
    // Send BLE status update if connected
    if (deviceConnected) {
      String statusUpdate = "New reading: " + String(reading.country) + " " + 
                           String(reading.id) + " " + String(temperature, 2) + "°C";
      sendBLEStatus(statusUpdate);
    }
  }
};

Rfid134<HardwareSerial, RfidNotify> rfid(Serial1);

// ---------------- LIGHT-SLEEP DIAGNOSTICS & WAKE FIXES ----------------
uint32_t wake_count_timer  = 0;
uint32_t wake_count_button = 0;

// Treat wakes as pending actions handled at the top of loop()
volatile bool buttonWakePending = false;
volatile bool timerWakePending  = false;

uint32_t wake_button_consumed = 0;
uint32_t wake_timer_consumed  = 0;

// Make lastButtonState global so we can normalize it after wake handling
bool lastButtonState = HIGH;

// Drain Serial TX completely so prints don't get truncated before sleep
inline void serialDrain(uint32_t timeout_ms = 80) {
  // ESP32-S3: USB-CDC path - Serial.flush() is enough; avoid uart_wait_tx_done() on S3 USB
  Serial.flush();
  delay(10); // Small delay to ensure USB-CDC transmission completes
}

void printWakeupCause() {
  esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
  switch (cause) {
    case ESP_SLEEP_WAKEUP_TIMER:
      wake_count_timer++;
      timerWakePending = true; // <-- ensure we perform the periodic read now
      Serial.printf("[LIGHTSLEEP] Woke up! cause=Timer  total(timer)=%u\n", wake_count_timer);
      break;
    case ESP_SLEEP_WAKEUP_GPIO:
      wake_count_button++;
      buttonWakePending = true; // <-- mark to guarantee a read on next loop
      Serial.printf("[LIGHTSLEEP] Woke up! cause=Button total(button)=%u\n", wake_count_button);
      break;
    case ESP_SLEEP_WAKEUP_UART:
      uartWakePending = true; // <-- mark to process UART command
      uartWakeTime = millis();
      Serial.printf("[LIGHTSLEEP] Woke up! cause=UART\n");
      break;
    default:
      Serial.printf("[LIGHTSLEEP] Woke up! cause=%d (other)\n", (int)cause);
      break;
  }
}

// Configure wake sources for the next sleep window
void configureWakeSources(uint64_t sleep_us, bool enableButtonWake, bool enableUartWake) {
  // Clear previous wake sources
  esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_ALL);

  // Timer wake for the remaining interval (if >0)
  if (sleep_us > 0) {
    esp_sleep_enable_timer_wakeup(sleep_us); // time in microseconds
  }

  // Button wake on LOW (works with any GPIO via GPIO wake in Light Sleep)
  if (enableButtonWake) {
    gpio_wakeup_enable((gpio_num_t)BUTTON_PIN, GPIO_INTR_LOW_LEVEL); // wake on LOW
    esp_sleep_enable_gpio_wakeup();
  }

  // UART wake so dashboard can nudge the chip awake
  if (enableUartWake) {
    // Set UART wake-up threshold (number of edges on RX pin to trigger wake-up)
    // Must be between 1 and 127
    esp_err_t threshold_result = uart_set_wakeup_threshold(UART_NUM_0, 1);
    if (threshold_result != ESP_OK) {
      Serial.printf("[LIGHTSLEEP] UART threshold FAILED: %d\n", threshold_result);
      // Don't enable UART wake-up if threshold setting failed
      return;
    }
    
    esp_err_t uart_result = esp_sleep_enable_uart_wakeup(UART_NUM_0);
    if (uart_result == ESP_OK) {
      Serial.println("[LIGHTSLEEP] UART wake-up enabled for dashboard commands");
    } else {
      Serial.printf("[LIGHTSLEEP] UART wake-up FAILED: %d\n", uart_result);
    }
  } else {
    Serial.println("[LIGHTSLEEP] UART wake-up disabled");
  }
}

// Enter light sleep until either the timer expires or button/UART wakes
void lightSleepUntilNextEvent(uint64_t sleep_us) {
  // If dashboard mode is active, do not sleep - stay awake
  if (dashboardModeActive) {
    return;
  }

// USB check removed - ESP32-S3 USB stability improvements are sufficient
  
  // If serial data is available, do not sleep
  if (Serial.available()) {
    return;
  }
  
  // If UART wake-up is pending, do not sleep - stay awake to process command
  if (uartWakePending && (millis() - uartWakeTime) < UART_WAKE_PROCESSING_MS) {
    return;
  }
  
  // If remaining == 0, don't go to sleep; handle pending flags first
  if (sleep_us == 0) {
    Serial.println("[LIGHTSLEEP] Skip sleep (remaining=0 ms)");
    return;
  }

  // Optional: turn radios off to save a bit more
  if (radiosOffBetweenReads) {
    WiFi.mode(WIFI_OFF);
    btStop(); // okay even if BT wasn't started
  }

  configureWakeSources(sleep_us, /*button*/true, /*uart*/false); // Disable UART wake-up temporarily

  // ESP32-S3: Prevent USB power domain from being powered down during light sleep
  // This helps prevent macOS from suspending USB-CDC connection
  esp_sleep_pd_config(ESP_PD_DOMAIN_VDDSDIO, ESP_PD_OPTION_ON);
  esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_PERIPH, ESP_PD_OPTION_ON);
  // Note: USB domain is part of VDDSDIO, keeping it ON should help

  // Print BEFORE going to sleep (essential for dashboard)
  Serial.printf("[LIGHTSLEEP] Entering light sleep for ~%llu ms\n",
                (unsigned long long)(sleep_us / 1000ULL));
  Serial.println("[LIGHTSLEEP] About to enter sleep...");
  Serial.flush(); // Ensure message is sent before drain
  serialDrain(100); // reliably flush console before clocks stop
  
  // ESP32-S3 specific: Additional delay for USB-CDC stability
  delay(50);

  // Enter Light Sleep (RAM & state retained; resumes here after wake)
  esp_light_sleep_start();  // sleeps

  // ESP32-S3 USB-CDC: After wake-up, USB may need more time to reconnect
  // USB-CDC can suspend during light sleep and needs time to re-enumerate
  delay(100);  // Increased delay for USB-CDC to reconnect
  
  // ESP32-S3: Try to "wake up" Serial by ensuring it's ready
  // Give USB-CDC extra time to reconnect before printing
  for (int i = 0; i < 5; i++) {
    delay(20);
    if (Serial) break;  // Check if Serial is ready
  }
  
  // AFTER wake, print the cause and set flags if needed (essential for dashboard)
  Serial.println("[LIGHTSLEEP] Woke up from sleep!");
  Serial.flush(); // Ensure message is sent
  
  // Small delay to ensure USB-CDC processed the first message
  delay(10);
  
  // Debug: Print wake-up cause immediately
  esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
  const char* causeName = "";
  if (cause == ESP_SLEEP_WAKEUP_TIMER) causeName = "Timer";
  else if (cause == ESP_SLEEP_WAKEUP_GPIO) causeName = "GPIO";
  else if (cause == ESP_SLEEP_WAKEUP_UART) causeName = "UART";
  else causeName = "Other";
  
  Serial.printf("[LIGHTSLEEP] Wake-up cause: %d (%s)\n", (int)cause, causeName);
  Serial.flush(); // Ensure message is sent
  
  delay(10);  // Small delay between messages
  
  printWakeupCause();
  Serial.flush(); // Ensure all wake-up messages are sent
  
  // CRITICAL: After waking from light sleep, immediately check for serial data
  // This ensures we don't miss commands that arrived during sleep
  if (Serial.available()) {
    // Mark host as active to prevent immediate re-sleep
    lastCommandTime = millis();
    // NOTE: Dashboard Mode is controlled ONLY by the multi-button (long press)
    // Serial commands do NOT affect Dashboard Mode
  }
}

// =============================================================================
// MULTI-BUTTON HANDLING FUNCTIONS
// =============================================================================

// Handle multi-button functionality: short press = RFID read, long press = toggle dashboard mode
void handleMultiButton() {
  bool currentButtonState = digitalRead(BUTTON_PIN);
  unsigned long currentTime = millis();
  
  // Button press detection (HIGH to LOW transition)
  if (lastButtonState == HIGH && currentButtonState == LOW) {
    // Button just pressed
    buttonPressed = true;
    buttonPressStart = currentTime;
    longPressDetected = false;
    longPressFeedbackStarted = false;
  }
  
  // Button release detection (LOW to HIGH transition)
  else if (lastButtonState == LOW && currentButtonState == HIGH) {
    // Button just released
    if (buttonPressed) {
      unsigned long pressDuration = currentTime - buttonPressStart;
      
      if (pressDuration < longPressMs) {
        // Short press - trigger RFID read
        // Use different debounce thresholds for different states
        unsigned long minPressTime = dashboardModeActive ? 50 : 100; // 50ms when awake, 100ms when sleeping
        
        if (pressDuration > minPressTime) {
          Serial.println("[BUTTON] Short press -> RFID read");
          powerOnAndReadTagWindow(rfidOnTimeMs);
          lastPeriodicRead = millis(); // Reset periodic timer
        }
      } else {
        // Long press - toggle dashboard mode
        Serial.println("[BUTTON] Long press -> Dashboard mode toggle");
        dashboardModeActive = !dashboardModeActive;
        
        if (dashboardModeActive) {
          Serial.println("[DASHBOARD] *** DASHBOARD MODE ACTIVATED (Button) ***");
          Serial.println("[DASHBOARD] ESP32 will stay awake - no periodic reads");
          Serial.println("[DASHBOARD] BLE advertising started for mobile app connectivity");
          setLEDStatus("dashboard_active");  // Red LED for dashboard mode
          startBLEAdvertising();  // Start BLE advertising for mobile apps
        } else {
          Serial.println("[DASHBOARD] *** DASHBOARD MODE DEACTIVATED (Button) ***");
          Serial.println("[DASHBOARD] ESP32 will use light sleep - periodic reads enabled");
          Serial.println("[DASHBOARD] BLE advertising stopped");
          setLEDStatus("sleeping");  // Blue LED for normal sleep mode
          stopBLEAdvertising();  // Stop BLE advertising
        }
      }
      
      // Reset all button state flags
      buttonPressed = false;
      longPressDetected = false;
      longPressFeedbackStarted = false;
    }
  }
  
  // Handle long press feedback while button is held
  if (buttonPressed && currentButtonState == LOW) {
    unsigned long pressDuration = currentTime - buttonPressStart;
    
    // Start feedback at 1 second
    if (pressDuration >= LONG_PRESS_FEEDBACK_MS && !longPressFeedbackStarted) {
      longPressFeedbackStarted = true;
      // Removed verbose feedback message to reduce print clutter
    }
    
    // Detect long press completion
    if (pressDuration >= longPressMs && !longPressDetected) {
      longPressDetected = true;
      Serial.println("[BUTTON] *** LONG PRESS DETECTED ***");
      Serial.println("[BUTTON] Release button to toggle dashboard mode");
    }
  }
  
  lastButtonState = currentButtonState;
}

// ------------------------------------------------------------

void setup() {
  // ESP32-S3: Working boot pattern (from successful LED test)
  delay(300);                       // Allow time for USB to settle
  Serial.begin(115200);             // USB-CDC
  
// Give macOS time to enumerate CDC and IDE time to reopen port
  unsigned long t0 = millis();
  while (!Serial && millis() - t0 < 2000) {}  // Wait a bit for connection

  Serial.println("Start");
  Serial.println("[BOOT] ESP32-S3 RFID Reader starting...");
  delay(500);  // Give time to see this message
  
  Serial.println("[BOOT] Initializing SPIFFS...");
  SPIFFS.begin(true);
  Serial.println("[BOOT] SPIFFS initialized");

  // Initialize RGB LED pins (ESP32-S3: Using safe GPIO pins)
  Serial.println("[BOOT] Setting up LEDs...");
  pinMode(LED_RED_PIN, OUTPUT);
  pinMode(LED_GREEN_PIN, OUTPUT);
  pinMode(LED_BLUE_PIN, OUTPUT);
  setLEDStatus("booting");  // Set booting status (white)
  Serial.println("[BOOT] LEDs configured");
  
  // ESP32-S3: Flash LED to show we're alive (like working test)
  for(int i = 0; i < 3; i++) {
    setLEDColor(1, 1, 1);  // White
    delay(200);
    setLEDColor(0, 0, 0);  // Off
    delay(200);
  }
  // Restore booting status after LED test
  setLEDStatus("booting");  // Keep white during boot process
  Serial.println("[BOOT] LED test completed");

  Serial.println("[BOOT] Loading configuration...");
  if (configExists()) loadConfig();
  Serial.println("[BOOT] Configuration loaded");

  Serial.println("[BOOT] Initializing RTC...");
  initRTC();
  Serial.println("[BOOT] RTC initialized");
  
  Serial.println("[BOOT] Initializing Flash...");
  initFlash();
  Serial.println("[BOOT] Flash initialized");

  Serial.println("[BOOT] Setting up RFID...");
  startTime = millis();
  Serial1.begin(9600, SERIAL_8N2, RFID_TX_PIN);
  rfid.begin();
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(RFID_PWR_PIN, INPUT); // Hi-Z at startup
  Serial.println("[BOOT] RFID initialized");

  Serial.println("[BOOT] Checking stored readings...");
  // concise summary instead of dumping all readings
  if (readingCount > 0) {
    printReadingsSummary();
  } else {
    Serial.println("[FS] No readings stored yet.");
  }

  // Initialize periodic scheduler to "now"
  lastPeriodicRead = millis();
  Serial.println("[BOOT] Periodic scheduler initialized");

  // UART wake-up threshold will be set in configureWakeSources() when needed

  Serial.println("[BOOT] Initializing button state...");
  // Initialize button state
  lastButtonState = digitalRead(BUTTON_PIN);
  buttonPressed = false;
  longPressDetected = false;
  longPressFeedbackStarted = false;
  Serial.println("[BOOT] Button state initialized");

  Serial.println("[BOOT] Ready (Light Sleep mode)");
  Serial.println("[BOOT] Periodic reads will be skipped when Dashboard Mode is ON");
  Serial.println("[BOOT] BLE advertising enabled only during Dashboard Mode");
  Serial.printf("[BOOT] Multi-Button: Short press=RFID read, Long press (%lums)=Toggle Dashboard Mode\n", longPressMs);
  
  // ESP32-S3: Setup complete
  Serial.println("[BOOT] Setup complete");
  Serial.println("[BOOT] ESP32-S3 RFID Reader ready - USB connection stable");
  
  // Set LED to sleeping status AFTER all boot messages are complete
  setLEDStatus("sleeping");
  
  Serial.println(); // Blank line after boot completion
  Serial.flush();  // Ensure all messages are sent
}

void powerOnAndReadTagWindow(unsigned long windowMs) {
  Serial.printf("[RFID] Powering ON for %lu ms\n", windowMs);
  if (dashboardModeActive) sendBLEResponse("[RFID] Powering ON for " + String(windowMs) + " ms");
  pinMode(RFID_PWR_PIN, OUTPUT);
  digitalWrite(RFID_PWR_PIN, LOW); // Power ON (active LOW)
  delay(500); // Increased delay to give RFID module more time to initialize
  Serial.println("[RFID] RFID module powered on, starting read window...");
  if (dashboardModeActive) sendBLEResponse("[RFID] RFID module powered on, starting read window...");
  unsigned long start = millis();
  lastTagValid = false;
  bool tagStored = false;

  while (millis() - start < windowMs && !tagStored) {
    rfid.loop();
    if (lastTagValid) {
      tagStored = true;
      Serial.println("[RFID] Tag detected and stored");
      if (dashboardModeActive) sendBLEResponse("[RFID] Tag detected and stored");
      
      // Store the reading and send it via BLE
      tryReadAndStoreTag();
      
      // Send the reading data via BLE if in dashboard mode
      if (dashboardModeActive) {
        uint8_t firstByte = lastTag.reserved1 & 0xFF;
        float temperature = 23.3 + (0.112 * firstByte);
        time_t timestamp = getCurrentTimestamp();
        struct tm* ti = gmtime(&timestamp);
        
        char readingStr[128];
        snprintf(readingStr, sizeof(readingStr), 
                 "#%d: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, %.2f°C",
                 readingCount, ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
                 ti->tm_hour, ti->tm_min, ti->tm_sec,
                 lastTag.country, lastTag.id, temperature);
        sendBLEResponse(readingStr);
      }
      
      // Clear lastTagValid to prevent duplicate storage
      lastTagValid = false;
    }
    yield();
  }
  if (!tagStored) {
    Serial.println("[RFID] No tag detected during window");
    if (dashboardModeActive) sendBLEResponse("[RFID] No tag detected during window");
  }

  pinMode(RFID_PWR_PIN, INPUT); // Hi-Z (power OFF)
  Serial.println("[RFID] Power OFF");
  if (dashboardModeActive) sendBLEResponse("[RFID] Power OFF");
  
  // Don't immediately reset LED status - let updateLEDStatus() handle the timing
  // The green flash will automatically return to the appropriate status after the flash duration
}

void loop() {
  // ESP32-S3: Simple yield for task management (following working test pattern)
  yield();
  
  // Heartbeat removed - not needed in production
  
  // ----- Handle UART wake-up first (highest priority) -----
  if (uartWakePending) {
    uartWakePending = false;
    Serial.println("[UART] Wake-up detected - staying awake for command processing");
    Serial.println("[UART] *** UART WAKE-UP WORKING ***");
    
    // UART wake-up occurred - process command but don't change Dashboard Mode
    // Dashboard Mode is controlled ONLY by the multi-button (long press)
    
    // Mark host as active to prevent immediate re-sleep
    lastCommandTime = millis();
    Serial.printf("[UART] lastCommandTime set to: %lu\n", lastCommandTime);
    
    // Wait longer for command to arrive (dashboard needs more time to send)
    Serial.println("[UART] Waiting for command...");
    delay(1000); // Increased delay to give dashboard more time
    
    // Process any pending serial commands immediately (like button does with RFID)
    if (Serial.available()) {
      String command = Serial.readStringUntil('\n');
      command.trim();
      
      // Skip empty commands
      if (command.length() > 0) {
        // Process the command immediately (same logic as in main serial section)
        Serial.println("CMD_RECEIVED");
        Serial.flush();
        
        // Handle dashboard mode commands immediately
        if (command == "dashboardmode on") {
          dashboardModeActive = true;
          Serial.println("[DASHBOARD] Dashboard Mode: ON - ESP32 will stay awake");
          Serial.println("[DASHBOARD] *** DASHBOARD MODE ACTIVATED (Serial Command) ***");
          Serial.println("[DASHBOARD] BLE advertising started for mobile app connectivity");
          setLEDStatus("dashboard_active");  // Red LED for dashboard mode
          startBLEAdvertising();  // Start BLE advertising for mobile apps
          Serial.flush();
          return; // Exit immediately after processing
        }
        
        if (command == "dashboardmode off") {
          dashboardModeActive = false;
          Serial.println("[DASHBOARD] Dashboard Mode: OFF - ESP32 will use light sleep");
          Serial.println("[DASHBOARD] *** DASHBOARD MODE DEACTIVATED (Serial Command) ***");
          Serial.println("[DASHBOARD] BLE advertising stopped");
          setLEDStatus("sleeping");  // Blue LED for normal sleep mode
          stopBLEAdvertising();  // Stop BLE advertising
          Serial.flush();
          return; // Exit immediately after processing
        }
        
        // Handle status command immediately
        if (command == "status") {
          Serial.printf("[DASHBOARD] Dashboard Mode: %s\n", dashboardModeActive ? "ACTIVE" : "INACTIVE");
          Serial.flush();
          return; // Exit immediately after processing
        }
        
        // Handle other quick commands
        if (command == "debugsimple") {
          Serial.println("[DEBUG] ESP32 Status: OK");
          Serial.printf("[DEBUG] Reading count: %d\n", readingCount);
          Serial.printf("[DEBUG] Dashboard mode: %s\n", dashboardModeActive ? "ACTIVE" : "INACTIVE");
          Serial.flush();
          return; // Exit immediately after processing
        }
        
        // For other commands, let them fall through to main serial processing
        // but ensure we stay awake
        Serial.flush();
      }
    } else {
      // No immediate command available, but stay awake for a bit to allow command to arrive
      Serial.println("[UART] No immediate command - staying awake for command arrival");
      // The lastCommandTime is already set, so we'll stay awake
    }
    
    // CRITICAL: After UART wake-up, skip all other processing and return to main loop
    // This prevents timer wake-up from interfering with UART command processing
    return;
  }

  // ----- Handle GPIO wake as a virtual press (covers short/early releases) -----
  if (buttonWakePending) {
    buttonWakePending = false;

    // GPIO wake-up means button was pressed while sleeping
    // We need to wait for the button to be released and measure the duration
    unsigned long pressStartTime = millis();
    
    // Wait for button release and measure duration
    while (digitalRead(BUTTON_PIN) == LOW) {
      delay(10);
      // Check for long press feedback while waiting
      unsigned long currentTime = millis();
      unsigned long pressDuration = currentTime - pressStartTime;
      
      // Start feedback at 1 second
      if (pressDuration >= LONG_PRESS_FEEDBACK_MS && !longPressFeedbackStarted) {
        longPressFeedbackStarted = true;
        // Removed verbose feedback message to reduce print clutter
      }
      
      // Detect long press completion
      if (pressDuration >= longPressMs && !longPressDetected) {
        longPressDetected = true;
        Serial.println("[BUTTON] *** LONG PRESS DETECTED ***");
        Serial.println("[BUTTON] Release button to toggle dashboard mode");
      }
    }
    
    // Button was released - measure total duration
    unsigned long totalDuration = millis() - pressStartTime;
    
    if (totalDuration < longPressMs) {
      // Short press - trigger RFID read
      // Use adaptive debounce: 50ms when awake, 100ms when sleeping (reduced from 200ms)
      unsigned long minPressTime = dashboardModeActive ? 50 : 100;
      
      if (totalDuration > minPressTime) {
        Serial.println("[BUTTON] GPIO wake -> Short press -> RFID read");
        powerOnAndReadTagWindow(rfidOnTimeMs);
        lastPeriodicRead = millis();
      }
    } else {
      // Long press - toggle dashboard mode
      Serial.println("[BUTTON] GPIO wake -> Long press -> Dashboard mode toggle");
      dashboardModeActive = !dashboardModeActive;
      
      if (dashboardModeActive) {
        Serial.println("[DASHBOARD] *** DASHBOARD MODE ACTIVATED (Button) ***");
        Serial.println("[DASHBOARD] ESP32 will stay awake - no periodic reads");
        Serial.println("[DASHBOARD] BLE advertising started for mobile app connectivity");
        setLEDStatus("dashboard_active");  // Red LED for dashboard mode
        startBLEAdvertising();  // Start BLE advertising for mobile apps
      } else {
        Serial.println("[DASHBOARD] *** DASHBOARD MODE DEACTIVATED (Button) ***");
        Serial.println("[DASHBOARD] ESP32 will use light sleep - periodic reads enabled");
        Serial.println("[DASHBOARD] BLE advertising stopped");
        setLEDStatus("sleeping");  // Blue LED for normal sleep mode
        stopBLEAdvertising();  // Stop BLE advertising
      }
    }
    
    // Reset all button state flags
    buttonPressed = false;
    longPressDetected = false;
    longPressFeedbackStarted = false;
    
    // Normalize edge detector base state
    lastButtonState = digitalRead(BUTTON_PIN);

    wake_button_consumed++;
  }

  // ----- Handle TIMER wake immediately (guarantee periodic read after timer) -----
  if (timerWakePending) {
    timerWakePending = false;

    // Check if UART wake-up is also pending - if so, prioritize UART
    if (uartWakePending) {
      Serial.println("[PERIODIC] Timer wake deferred - UART wake-up has priority");
      return; // Let UART wake-up handle the processing
    }

    // Skip periodic reads when Dashboard Mode is active to maintain responsiveness
    if (dashboardModeActive) {
      Serial.println("[PERIODIC] Skipped (Dashboard Mode active)");
      lastPeriodicRead = millis(); // Reset timer to prevent immediate retry
      return; // Don't go to sleep, stay awake for dashboard
    }

    Serial.println("[PERIODIC] Timer wake -> trigger RFID read");
    lastPeriodicRead = millis();           // anchor schedule to now
    powerOnAndReadTagWindow(rfidOnTimeMs);
    wake_timer_consumed++;
    Serial.printf("[PERIODIC] RFID read completed, LED status: %s\n", currentLEDStatus.c_str());
    Serial.println(); // Blank line for spacing

    // Give LED status time to update before going to sleep
    if (currentLEDStatus == "reading_success") {
      // Wait for LED flash to complete by calling updateLEDStatus() repeatedly
      unsigned long startWait = millis();
      while (currentLEDStatus == "reading_success" && (millis() - startWait) < 2000) {
        updateLEDStatus();
        delay(10);
      }
    }

    if (!Serial.available() && !dashboardModeActive) {
      uint64_t sleep_us = (uint64_t)periodicIntervalMs * 1000ULL; // full interval until next slot
      lightSleepUntilNextEvent(sleep_us);
      return; // <-- handle next wake cleanly
    }
  }

  // --- Determine if periodic read is due (fallback when awake for a while) ---
  unsigned long nowMs = millis();
  bool periodicDue = (nowMs - lastPeriodicRead) >= periodicIntervalMs;
  
  // Debug: Show dashboard mode status periodically (reduced frequency)
  static unsigned long lastDebugTime = 0;
  if (nowMs - lastDebugTime > 60000) { // Every 60 seconds (reduced from 10s)
    lastDebugTime = nowMs;
    // Removed frequent debug message to reduce print clutter
  }
  
  // --- Watchdog: If we've been in light sleep too long without activity, force a wake ---
  static unsigned long lastActivityCheck = 0;
  if (nowMs - lastActivityCheck > 300000) { // Check every 5 minutes (reduced frequency)
    lastActivityCheck = nowMs;
    // If no serial activity for a long time, ensure we're responsive
    if (nowMs - lastCommandTime > 600000) { // No commands for 10 minutes (increased from 2 minutes)
      // Force a brief activity to keep the system responsive
      // Watchdog message removed - not needed in production
    }
  }

  // --- Multi-button handling (short press = RFID read, long press = dashboard mode toggle) ---
  handleMultiButton();
  
  // --- Update LED status (handle timed status changes) ---
  updateLEDStatus();

  // --- Periodic automatic reading (fallback path) ---
  if (periodicDue) {
    // Skip periodic reads when Dashboard Mode is active to maintain responsiveness
    if (dashboardModeActive) {
      Serial.println("[PERIODIC] Timer slot -> skipped (Dashboard Mode active)");
      lastPeriodicRead = nowMs; // Reset timer to prevent immediate retry
    } else {
      Serial.println("[PERIODIC] Timer slot -> trigger RFID read");
      lastPeriodicRead = nowMs;
      powerOnAndReadTagWindow(rfidOnTimeMs);
      Serial.printf("[PERIODIC] Fallback RFID read completed, LED status: %s\n", currentLEDStatus.c_str());
      Serial.println(); // Blank line for spacing
    }
  }

  // Serial data checking removed - UART wake-up should handle this properly

  // --- Enter Light Sleep until next event (timer or button/uart) ---
  // Compute remaining time to next periodic slot
  nowMs = millis();
  unsigned long elapsed = nowMs - lastPeriodicRead;
  unsigned long remainingMs = (elapsed < periodicIntervalMs) ? (periodicIntervalMs - elapsed) : 0UL;

  // If we don't have pending serial input and nothing is immediately due, sleep
  // CRITICAL: Never sleep when dashboard mode is active
  if (!Serial.available() && !dashboardModeActive && !uartWakePending) {
    // If button is being held LOW, skip sleeping to avoid bouncing
    if (digitalRead(BUTTON_PIN) == HIGH && remainingMs > 0) { // <-- don't sleep for 0 ms
      // Ensure LED status is properly set before going to sleep
      if (currentLEDStatus == "reading_success" && ledFlashDuration > 0) {
        // If we're in a flash state, don't go to sleep yet - wait for it to complete
        return;
      }
      lightSleepUntilNextEvent((uint64_t)remainingMs * 1000ULL);
      return; // <-- next iteration will handle the wake cause immediately
    }
  } else if (dashboardModeActive) {
    // Dashboard mode is active - stay awake and don't sleep
    // Only print this message occasionally to avoid spam
    static unsigned long lastDashboardMessage = 0;
    if (millis() - lastDashboardMessage > 120000) { // Every 2 minutes
      lastDashboardMessage = millis();
      Serial.println("[DASHBOARD] Staying awake - Dashboard Mode active");
    }
  }

  // --- Dashboard mode management ---
  // Dashboard mode is controlled purely by the dashboard toggle
  // No auto-deactivation - only explicit "dashboardmode off" command can deactivate it
  // This ensures it stays active as long as the dashboard toggle is ON
  
  // --- UART wake-up timeout management ---
  // Clear UART wake-up flag after processing timeout
  if (uartWakePending && (millis() - uartWakeTime) > UART_WAKE_PROCESSING_MS) {
    uartWakePending = false;
    Serial.println("[UART] Wake-up processing timeout - clearing flag");
  }

  // --- Serial config commands ---
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    
    // Skip empty commands
    if (command.length() == 0) {
      return;
    }
    
    // mark host as active for sleep gating
    lastCommandTime = millis();
    
    // Serial activity detected - will be processed immediately
    
    // NOTE: Dashboard Mode is controlled ONLY by the multi-button (long press)
    // Serial commands do NOT affect Dashboard Mode
    
    // Immediately respond to any command to prevent sleep during processing
    Serial.println("CMD_RECEIVED");
    Serial.flush(); // Ensure the response is sent immediately
    
    // Check for status command to show dashboard mode status
    if (command == "status") {
      Serial.printf("[DASHBOARD] Dashboard Mode: %s\n", dashboardModeActive ? "ACTIVE" : "INACTIVE");
      return; // Don't process further
    }
    
    // Check for dashboard mode commands
    if (command == "dashboardmode on") {
      dashboardModeActive = true;
      Serial.println("[DASHBOARD] Dashboard Mode: ON - ESP32 will stay awake");
      Serial.println("[DASHBOARD] *** DASHBOARD MODE ACTIVATED ***");
      Serial.println("[DASHBOARD] BLE advertising started for mobile app connectivity");
      setLEDStatus("dashboard_active");  // Red LED for dashboard mode
      startBLEAdvertising();  // Start BLE advertising for mobile apps
      Serial.flush();
      return; // Don't process further
    }
    
    if (command == "dashboardmode off") {
      dashboardModeActive = false;
      Serial.println("[DASHBOARD] Dashboard Mode: OFF - ESP32 will use light sleep");
      Serial.println("[DASHBOARD] *** DASHBOARD MODE DEACTIVATED ***");
      Serial.println("[DASHBOARD] BLE advertising stopped");
      setLEDStatus("sleeping");  // Blue LED for normal sleep mode
      stopBLEAdvertising();  // Stop BLE advertising
      Serial.flush();
      return; // Don't process further
    }
    
    // Alternative dashboard commands for serial debugging
    if (command == "dashboard on") {
      dashboardModeActive = true;
      Serial.println("[DASHBOARD] Dashboard Mode: ON - ESP32 will stay awake");
      Serial.println("[DASHBOARD] *** DASHBOARD MODE ACTIVATED (Serial Debug) ***");
      Serial.println("[DASHBOARD] BLE advertising started for mobile app connectivity");
      setLEDStatus("dashboard_active");  // Red LED for dashboard mode
      startBLEAdvertising();  // Start BLE advertising for mobile apps
      Serial.flush();
      return; // Don't process further
    }
    
    if (command == "dashboard off") {
      dashboardModeActive = false;
      Serial.println("[DASHBOARD] Dashboard Mode: OFF - ESP32 will use light sleep");
      Serial.println("[DASHBOARD] *** DASHBOARD MODE DEACTIVATED (Serial Debug) ***");
      Serial.println("[DASHBOARD] BLE advertising stopped");
      setLEDStatus("sleeping");  // Blue LED for normal sleep mode
      stopBLEAdvertising();  // Stop BLE advertising
      Serial.flush();
      return; // Don't process further
    }
    
    
    // Simple debug command that responds quickly
    if (command == "debugsimple") {
      Serial.println("[DEBUG] ESP32 Status: OK");
      Serial.printf("[DEBUG] Reading count: %d\n", readingCount);
      Serial.printf("[DEBUG] Dashboard mode: %s\n", dashboardModeActive ? "ACTIVE" : "INACTIVE");
      return; // Don't process further
    }
    
    // Debug command with immediate response
    if (command == "debug") {
      Serial.println("[DEBUG] --- Device Debug Info ---");
      Serial.printf("[DEBUG] Reading count: %d\n", readingCount);
      Serial.printf("[DEBUG] MAX_READINGS: %d\n", MAX_READINGS);
      Serial.printf("[DEBUG] READING_SIZE: %d\n", READING_SIZE);
      Serial.printf("[DEBUG] Available slots: %d\n", MAX_READINGS - readingCount);
      Serial.printf("[DEBUG] Dashboard mode: %s\n", dashboardModeActive ? "ACTIVE" : "INACTIVE");
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
      return; // Don't process further
    }
    
    // Get command handlers for dashboard
    if (command == "get ssid") {
      Serial.println("<GET_SSID_BEGIN>");
      Serial.println(ssid_str);
      Serial.println("<GET_SSID_END>");
      return; // Don't process further
    }
    if (command == "get password") {
      Serial.println("<GET_PASSWORD_BEGIN>");
      Serial.println(password_str);
      Serial.println("<GET_PASSWORD_END>");
      return; // Don't process further
    }
    if (command == "get rfidOnTimeMs") {
      Serial.println("<GET_RFIDONTIME_BEGIN>");
      Serial.println(rfidOnTimeMs);
      Serial.println("<GET_RFIDONTIME_END>");
      return; // Don't process further
    }
    if (command == "get periodicIntervalMs") {
      Serial.println("<GET_PERIODICINTERVAL_BEGIN>");
      Serial.println(periodicIntervalMs);
      Serial.println("<GET_PERIODICINTERVAL_END>");
      return; // Don't process further
    }
    if (command == "get longPressMs") {
      Serial.println("<GET_LONGPRESSMS_BEGIN>");
      Serial.println(longPressMs);
      Serial.println("<GET_LONGPRESSMS_END>");
      return; // Don't process further
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
    } else if (command == "resetconfig") {
      if (SPIFFS.exists(configFile)) { SPIFFS.remove(configFile); Serial.println("Config reset. Reboot to use hardcoded values."); }
      else { Serial.println("No config to reset."); }
    } else if (command == "summary") {
      printReadingsSummary();
    } else if (command == "print") {
      printStoredReadings();
    } else if (command == "last") {
      printLastReading();
    } else if (command == "clear") {
      SPIFFS.remove(FLASH_FILENAME); readingCount = 0; Serial.println("Cleared");
    } else if (command.startsWith("range ")) {
      command = command.substring(6);
      int spaceIndex = command.indexOf(' ');
      if (spaceIndex > 0) {
        uint32_t startTime = command.substring(0, spaceIndex).toInt();
        uint32_t endTime = command.substring(spaceIndex + 1).toInt();
        sendStoredReadingsByRange(startTime, endTime);
      }
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
    } else if (command == "dashboardmode") {
    } else if (command == "sleepstats") {
      Serial.printf("[STATS] wakes: timer=%u, button=%u (gpio-wake-consumed=%u, timer-consumed=%u)\n",
                    wake_count_timer, wake_count_button, wake_button_consumed, wake_timer_consumed);
    } else if (command == "resetrtc") {
      Serial.println("[RTC] Resetting RTC to UTC...");
      Serial.println("[RTC] This will take a moment...");
      
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
    } else if (command == "testuart") {
      Serial.println("[UART] Testing UART wake-up...");
      Serial.println("[UART] ESP32 will go to sleep for 10 seconds");
      Serial.println("[UART] Send any command to wake it up");
      Serial.flush();
      delay(1000);
      lightSleepUntilNextEvent(10000000); // Sleep for 10 seconds
      Serial.println("[UART] Woke up from sleep!");
    } else if (command == "testsleep") {
      Serial.println("[SLEEP] Testing sleep functionality...");
      Serial.println("[SLEEP] Going to sleep for 5 seconds");
      Serial.flush();
      delay(1000);
      lightSleepUntilNextEvent(5000000); // Sleep for 5 seconds
      Serial.println("[SLEEP] Woke up from sleep!");
    } else if (command == "testuartlong") {
      Serial.println("[UART] Testing UART wake-up with 30-second sleep...");
      Serial.println("[UART] ESP32 will go to sleep for 30 seconds");
      Serial.println("[UART] Send any command to wake it up via UART");
      Serial.flush();
      delay(1000);
      lightSleepUntilNextEvent(30000000); // Sleep for 30 seconds
      Serial.println("[UART] Woke up from sleep!");
    } else if (command == "buttonmode") {
      Serial.println("[BUTTON] Multi-Button Mode Status:");
      Serial.printf("[BUTTON] Dashboard Mode: %s\n", dashboardModeActive ? "ACTIVE" : "INACTIVE");
      Serial.println("[BUTTON] Short press: RFID read");
      Serial.printf("[BUTTON] Long press (%lums): Toggle Dashboard Mode\n", longPressMs);
      Serial.printf("[BUTTON] Current button state: %s\n", digitalRead(BUTTON_PIN) == LOW ? "PRESSED" : "RELEASED");
    } else if (command == "testbutton") {
      Serial.println("[BUTTON] Testing multi-button functionality...");
      Serial.printf("[BUTTON] Press and hold the button for %lu seconds to toggle dashboard mode\n", longPressMs / 1000);
      Serial.println("[BUTTON] Short press for RFID read");
      Serial.println("[BUTTON] Current dashboard mode will be toggled on long press");
    } else if (command == "status") {
      Serial.println("[STATUS] Current ESP32 Status:");
      Serial.printf("[STATUS] Dashboard Mode: %s\n", dashboardModeActive ? "ACTIVE" : "INACTIVE");
      Serial.printf("[STATUS] lastCommandTime: %lu\n", lastCommandTime);
      Serial.printf("[STATUS] Serial.available(): %s\n", Serial.available() ? "true" : "false");
      Serial.printf("[STATUS] Current time: %lu ms\n", millis());
      Serial.printf("[STATUS] Long press timer: %lu ms\n", longPressMs);
    }
    
    // Ensure all responses are sent before potentially going to sleep
    Serial.flush();
    delay(10); // Small delay to ensure response is fully transmitted
  }
}
