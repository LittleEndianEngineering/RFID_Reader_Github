#include "led_status.h"

#include "globals.h"
#include "pins.h"

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
    // CRITICAL: Always check dashboardModeActive to ensure correct LED state
    if (dashboardModeActive) {
      setLEDStatus("dashboard_active");  // Red LED - Dashboard Mode active
    } else {
      setLEDStatus("sleeping");  // Blue LED - Normal sleep mode
    }
  }
  
  // Additional safety check: If Dashboard Mode is active but LED is not red, fix it
  // This prevents LED from being blue when Dashboard Mode is active
  if (dashboardModeActive && currentLEDStatus != "dashboard_active" && 
      currentLEDStatus != "reading_success" && currentLEDStatus != "booting") {
    // Only fix if not in a temporary state (reading_success flash or booting)
    setLEDStatus("dashboard_active");
  }
}
