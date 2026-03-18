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
 */

#include <SPIFFS.h>
#include <esp_system.h>

#include "types.h"
#include "pins.h"
#include "globals.h"
#include "config.h"
#include "led_status.h"
#include "rtc_time.h"
#include "flash_store.h"
#include "ble_comm.h"
#include "rfid_reader.h"
#include "sleep_wake.h"
#include "button.h"
#include "serial_cmd.h"

void setup() {
  // ESP32-S3: Working boot pattern (from successful LED test)
  delay(300);                       // Allow time for USB to settle
  Serial.begin(115200);             // USB-CDC
  
  // Give macOS time to enumerate CDC and IDE time to reopen port
  unsigned long t0 = millis();
  while (!Serial && millis() - t0 < 2000) {}  // Wait a bit for connection

  // Print reset reason immediately to diagnose connection resets
  esp_reset_reason_t reset_reason = esp_reset_reason();
  const char* reset_reason_str = "";
  switch (reset_reason) {
    case ESP_RST_POWERON: reset_reason_str = "POWERON"; break;
    case ESP_RST_EXT: reset_reason_str = "EXT (external pin)"; break;
    case ESP_RST_SW: reset_reason_str = "SW (software)"; break;
    case ESP_RST_PANIC: reset_reason_str = "PANIC (exception)"; break;
    case ESP_RST_INT_WDT: reset_reason_str = "INT_WDT (interrupt watchdog)"; break;
    case ESP_RST_TASK_WDT: reset_reason_str = "TASK_WDT (task watchdog)"; break;
    case ESP_RST_WDT: reset_reason_str = "WDT (watchdog)"; break;
    case ESP_RST_DEEPSLEEP: reset_reason_str = "DEEPSLEEP"; break;
    case ESP_RST_BROWNOUT: reset_reason_str = "BROWNOUT"; break;
    case ESP_RST_SDIO: reset_reason_str = "SDIO"; break;
    case ESP_RST_USB: reset_reason_str = "USB (USB-CDC reset)"; break;
    default: reset_reason_str = "UNKNOWN"; break;
  }
  Serial.printf("[BOOT] Reset reason: %d (%s)\n", (int)reset_reason, reset_reason_str);
  Serial.flush();

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
  
  // Restore Dashboard Mode if it was active before reset
  // This prevents connection drop after reset on macOS
  if (dashboardModeActive) {
    Serial.println("[BOOT] Restoring Dashboard Mode (was active before reset)");
    Serial.println("[DASHBOARD] *** DASHBOARD MODE RESTORED (Persistent) ***");
    Serial.println("[DASHBOARD] ESP32 will stay awake - no periodic reads");
    Serial.println("[DASHBOARD] BLE advertising started for mobile app connectivity");
    Serial.println("[DASHBOARD] LED set to RED - Dashboard Mode active");
    setLEDStatus("dashboard_active");  // Red LED for dashboard mode
    startBLEAdvertising();  // Start BLE advertising for mobile apps
    Serial.printf("[DASHBOARD] Verification: dashboardModeActive=%s, LED status=%s\n", 
                  dashboardModeActive ? "true" : "false", currentLEDStatus.c_str());
  } else {
    Serial.println("[BOOT] Dashboard Mode was NOT active before reset (normal sleep mode)");
  }

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
  pinMode(RFID_PWR_PIN, OUTPUT); // Initialize RFID Module
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
  
  // Set LED status AFTER all boot messages are complete
  // CRITICAL: Don't override Dashboard Mode LED if it was restored from flash
  if (!dashboardModeActive) {
    setLEDStatus("sleeping");  // Blue LED for normal sleep mode
  }
  // If Dashboard Mode is active, LED is already set to red in the restoration block above
  
  Serial.println(); // Blank line after boot completion
  Serial.flush();  // Ensure all messages are sent
}

void loop() {
  // ESP32-S3: Simple yield for task management (following working test pattern)
  yield();
  
  // Heartbeat removed - not needed in production
  
  // ============================================================================
  // PRIORITY: Serial command processing when Dashboard Mode is active
  // ============================================================================
  // When Dashboard Mode is active, prioritize Serial commands to ensure
  // dashboard can communicate with ESP32 without delays from other loop operations
  if (dashboardModeActive && Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    
    // Skip empty commands
    if (command.length() > 0) {
      // Mark host as active for sleep gating
      lastCommandTime = millis();
      
      // Immediately respond to any command to prevent sleep during processing
      Serial.println("CMD_RECEIVED");
      Serial.flush();
      
      // Process command using the same handler as the main Serial section
      // This ensures consistent behavior whether Dashboard Mode is active or not
      processSerialCommand(command);
      
      // After processing command, return to loop start to check for more commands
      // This ensures Serial commands are processed with highest priority in Dashboard Mode
      return;
    }
  }
  
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
        
        // Process command using centralized function for consistency
        // This handles all commands including dashboard mode, status, debug, get/set, etc.
        processSerialCommand(command);
        
        // Exit immediately after processing to return to loop start
        return;
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
    // Check current button state first - if already released, it was a quick press
    bool buttonCurrentlyPressed = (digitalRead(BUTTON_PIN) == LOW);
    unsigned long pressStartTime = millis();
    
    if (buttonCurrentlyPressed) {
      // Button is still pressed - wait for release and measure duration
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
    } else {
      // Button already released - it was a quick press that woke us up
      // Give it a minimum duration to ensure it's treated as a valid press
      // This handles the case where button was pressed and released before we could measure
      Serial.println("[BUTTON] GPIO wake -> Quick press detected (already released)");
      delay(50); // Small delay to ensure button state is stable
    }
    
    // Measure total duration (or use minimum for quick presses)
    unsigned long totalDuration = millis() - pressStartTime;
    
    // For quick presses that were already released, ensure minimum duration
    if (!buttonCurrentlyPressed && totalDuration < 50) {
      totalDuration = 50; // Treat as valid short press
    }
    
    if (totalDuration < longPressMs) {
      // Short press - trigger RFID read
      // Use adaptive debounce: 50ms when awake, 50ms minimum for wake-up presses
      unsigned long minPressTime = 50; // Reduced threshold for wake-up presses
      
      if (totalDuration >= minPressTime) {
        Serial.println("[BUTTON] GPIO wake -> Short press -> RFID read");
        powerOnAndReadTagWindow(rfidOnTimeMs);
        lastPeriodicRead = millis();
      } else {
        Serial.printf("[BUTTON] GPIO wake -> Press too short (%lu ms < %lu ms), ignoring\n", totalDuration, minPressTime);
      }
    } else {
      // Long press - toggle dashboard mode
      Serial.println("[BUTTON] GPIO wake -> Long press -> Dashboard mode toggle");
      dashboardModeActive = !dashboardModeActive;
      saveConfigVar("dashboardModeActive", dashboardModeActive ? "true" : "false");  // Persist to flash
      
      if (dashboardModeActive) {
        Serial.println("[DASHBOARD] *** DASHBOARD MODE ACTIVATED (Button, Persistent) ***");
        Serial.println("[DASHBOARD] ESP32 will stay awake - no periodic reads");
        Serial.println("[DASHBOARD] BLE advertising started for mobile app connectivity");
        setLEDStatus("dashboard_active");  // Red LED for dashboard mode
        startBLEAdvertising();  // Start BLE advertising for mobile apps
      } else {
        Serial.println("[DASHBOARD] *** DASHBOARD MODE DEACTIVATED (Button, Persistent) ***");
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

  // --- Serial config commands (for non-Dashboard Mode or fallback) ---
  // Note: When Dashboard Mode is active, Serial commands are processed at the
  // beginning of loop() for immediate response. This section handles commands
  // when Dashboard Mode is not active or as a fallback.
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    
    // Skip empty commands
    if (command.length() == 0) {
      return;
    }
    
    // mark host as active for sleep gating
    lastCommandTime = millis();
    
    // Immediately respond to any command to prevent sleep during processing
    Serial.println("CMD_RECEIVED");
    Serial.flush(); // Ensure the response is sent immediately
    
    // Process command using centralized function
    processSerialCommand(command);
    
    // Small delay to ensure response is fully transmitted
    delay(10);
  }
}