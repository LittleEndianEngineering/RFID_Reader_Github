#pragma once

#include <Arduino.h>
#include <RTClib.h>
#include <Rfid134.h>
#include <time.h>

#include "BLEDevice.h"
#include "BLEServer.h"

#include "types.h"

// =============================================================================
// GLOBAL STATE
// =============================================================================

// WiFi Configuration (can be updated via serial commands)
extern String ssid_str;
extern String password_str;
extern const char* ssid;
extern const char* password;

// RTC Configuration - External DS1307 Module
extern RTC_DS1307 rtc;
extern bool rtcAvailable;
extern DateTime now;
extern struct tm timeinfo; // For NTP sync when RTC is stopped

// Flash Storage Configuration
extern const char* FLASH_FILENAME;
extern int readingCount;
extern unsigned long startTime;

// Reading configuration
extern const unsigned long debounceDelay; // ms
extern unsigned long rfidOnTimeMs;        // configurable
extern unsigned long lastPeriodicRead;
extern unsigned long periodicIntervalMs; // configurable
extern bool radiosOffBetweenReads;
extern bool dashboardModeActive;

// BLE State
extern BLEServer* pServer;
extern BLECharacteristic* pCommandCharacteristic;
extern BLECharacteristic* pResponseCharacteristic;
extern BLECharacteristic* pStatusCharacteristic;
extern bool deviceConnected;
extern bool bleInitialized;
extern bool bleAdvertising;

// Button state tracking for long press detection
extern unsigned long buttonPressStart;
extern bool buttonPressed;
extern bool longPressDetected;
extern unsigned long longPressMs;
extern const unsigned long LONG_PRESS_FEEDBACK_MS;
extern bool longPressFeedbackStarted;

// Store last tag read (for button logic)
extern Rfid134Reading lastTag;
extern bool lastTagValid;

// RFID Module Failover Tracking
extern unsigned int rfidErrorCount;
extern unsigned int rfidConsecutiveErrors;
extern const unsigned int MAX_RFID_ERRORS;
extern const unsigned long RFID_LOOP_TIMEOUT_MS;
extern const unsigned long RFID_SAFETY_TIMEOUT_MS;

// Host activity heartbeat (prevents sleep while dashboard is active)
extern unsigned long lastCommandTime;
extern const unsigned long HOST_ACTIVE_TIMEOUT_MS;

// UART wake-up processing
extern volatile bool uartWakePending;
extern unsigned long uartWakeTime;
extern const unsigned long UART_WAKE_PROCESSING_MS;

// Config Persistence
extern String configFile;

// LED Status tracking
extern String currentLEDStatus;
extern unsigned long ledStatusStartTime;
extern unsigned long ledFlashDuration;

// Light-sleep diagnostics & wake fixes
extern uint32_t wake_count_timer;
extern uint32_t wake_count_button;
extern volatile bool buttonWakePending;
extern volatile bool timerWakePending;
extern uint32_t wake_button_consumed;
extern uint32_t wake_timer_consumed;
extern bool lastButtonState;
