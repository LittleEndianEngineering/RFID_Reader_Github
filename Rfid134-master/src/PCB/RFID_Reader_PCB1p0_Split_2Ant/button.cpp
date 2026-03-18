#include "button.h"

#include <Arduino.h>

#include "globals.h"
#include "pins.h"
#include "config.h"
#include "led_status.h"
#include "ble_comm.h"
#include "rfid_reader.h"

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
          if (idleModeActive) {
            Serial.printf("[IDLE] Short press ignored - manual read blocked (%s)\n", idleReasonToString(latestIdleReason));
          } else {
            Serial.println("[BUTTON] Short press -> RFID read");
            powerOnAndReadTagWindow(rfidOnTimeMs);
            lastPeriodicRead = millis(); // Reset periodic timer
          }
        }
      } else {
        // Long press - toggle dashboard mode
        Serial.println("[BUTTON] Long press -> Dashboard mode toggle");
        dashboardModeActive = !dashboardModeActive;
        saveConfigVar("dashboardModeActive", dashboardModeActive ? "true" : "false");  // Persist to flash
        
        if (dashboardModeActive) {
          Serial.println("[DASHBOARD] *** DASHBOARD MODE ACTIVATED (Button, Persistent) ***");
          Serial.println("[DASHBOARD] ESP32 will stay awake - no periodic reads");
          Serial.println("[DASHBOARD] BLE advertising started for mobile app connectivity");
          if (idleModeActive) {
            Serial.printf("[DASHBOARD] Idle reason: %s\n", idleReasonToString(latestIdleReason));
          }
          setLEDStatus("dashboard_active");  // Red LED for dashboard mode
          startBLEAdvertising();  // Start BLE advertising for mobile apps
        } else {
          Serial.println("[DASHBOARD] *** DASHBOARD MODE DEACTIVATED (Button, Persistent) ***");
          Serial.println("[DASHBOARD] ESP32 will use light sleep - periodic reads enabled");
          Serial.println("[DASHBOARD] BLE advertising stopped");
          setLEDStatus(idleModeActive ? "idle" : "sleeping");
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
