#include "globals.h"

// WiFi Configuration (can be updated via serial commands)
//String ssid_str = "opauly";
//String password_str = "tienevirus23";
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
const char* FLASH_FILENAME = "/readings.dat";
int readingCount = 0;
unsigned long startTime = 0;

// Reading configuration
const unsigned long debounceDelay = 200; // ms
unsigned long rfidOnTimeMs = 5 * 1000;   // configurable
unsigned long lastPeriodicRead = 0;
unsigned long periodicIntervalMs = 1 * 60 * 1000UL; // configurable
bool radiosOffBetweenReads = true;
bool dashboardModeActive = false;
const unsigned long IDLE_SOC_POLL_INTERVAL_MS = 5000;

// Idle mode state
bool idleModeActive = false;
IdleReason latestIdleReason = IDLE_NONE;
bool rtcIdleLatch = false;
bool socLowTestOverride = false; // Placeholder hook until real SoC logic is integrated

// BLE State
BLEServer* pServer = nullptr;
BLECharacteristic* pCommandCharacteristic = nullptr;
BLECharacteristic* pResponseCharacteristic = nullptr;
BLECharacteristic* pStatusCharacteristic = nullptr;
bool deviceConnected = false;
bool bleInitialized = false;
bool bleAdvertising = false;

// Button state tracking for long press detection
unsigned long buttonPressStart = 0;
bool buttonPressed = false;
bool longPressDetected = false;
unsigned long longPressMs = 5000; // Configurable long press duration (default 5 seconds)
const unsigned long LONG_PRESS_FEEDBACK_MS = 1000; // Start feedback at 1 second
bool longPressFeedbackStarted = false;

// Store last tag read (for button logic)
Rfid134Reading lastTag;
bool lastTagValid = false;

// RFID Module Failover Tracking
unsigned int rfidErrorCount = 0;
unsigned int rfidConsecutiveErrors = 0;
const unsigned int MAX_RFID_ERRORS = 2; // Max errors before power cycle (reduced for faster recovery)
const unsigned long RFID_LOOP_TIMEOUT_MS = 100; // Max time for rfid.loop() to take (reduced for faster detection)
const unsigned long RFID_SAFETY_TIMEOUT_MS = 3000; // Max total time for RFID read window before abort

// Host activity heartbeat (prevents sleep while dashboard is active)
unsigned long lastCommandTime = 0;               // updated whenever a serial command is received
const unsigned long HOST_ACTIVE_TIMEOUT_MS = 15000; // stay awake for 15s after last command

// UART wake-up processing
volatile bool uartWakePending = false;           // flag set when UART wake-up occurs
unsigned long uartWakeTime = 0;                  // timestamp of UART wake-up
const unsigned long UART_WAKE_PROCESSING_MS = 5000; // time to stay awake after UART wake-up (increased)

// Config Persistence
String configFile = "/config.txt";

// LED Status tracking
String currentLEDStatus = "off";
unsigned long ledStatusStartTime = 0;
unsigned long ledFlashDuration = 0;

// Light-sleep diagnostics & wake fixes
uint32_t wake_count_timer = 0;
uint32_t wake_count_button = 0;
volatile bool buttonWakePending = false;
volatile bool timerWakePending = false;
uint32_t wake_button_consumed = 0;
uint32_t wake_timer_consumed = 0;
bool lastButtonState = HIGH;

bool isSocBelowThreshold() {
  return socLowTestOverride;
}

void evaluateIdleState() {
  bool rtcCondition = rtcIdleLatch;
  bool socCondition = isSocBelowThreshold();

  idleModeActive = rtcCondition || socCondition;

  if (socCondition) {
    latestIdleReason = IDLE_SOC_LOW;
  } else if (rtcCondition) {
    latestIdleReason = IDLE_RTC_INIT_FAILED;
  } else {
    latestIdleReason = IDLE_NONE;
  }
}

const char* idleReasonToString(IdleReason reason) {
  switch (reason) {
    case IDLE_RTC_INIT_FAILED: return "IDLE_RTC_INIT_FAILED";
    case IDLE_SOC_LOW: return "IDLE_SOC_LOW";
    case IDLE_NONE:
    default: return "IDLE_NONE";
  }
}
