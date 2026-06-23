#include "led_status.h"

#include "globals.h"
#include "pins.h"

void setLEDColor(int red, int green, int blue) {
  VERBOSE_PRINTF("[LEDDBG] COLOR t=%lu R=%d G=%d B=%d\n", millis(), red, green, blue);
  digitalWrite(LED_RED_PIN, red);
  digitalWrite(LED_GREEN_PIN, green);
  digitalWrite(LED_BLUE_PIN, blue);
}

bool isLEDHeartbeatStatus(const String& status) {
  return status == "sleeping" || status == "dashboard_active" || status == "idle";
}

static void setLEDColorForStatus(const String& status) {
  if (status == "sleeping") {
    setLEDColor(0, 0, 1);      // Blue - light sleep
  } else if (status == "dashboard_active") {
    setLEDColor(1, 0, 0);      // Red - dashboard mode active
  } else if (status == "idle") {
    setLEDColor(1, 1, 0);      // Yellow - idle mode active
  } else {
    setLEDColor(0, 0, 0);      // Off
  }
}

static void startLEDHeartbeat() {
  ledHeartbeatOn = true;
  ledHeartbeatPhaseStartTime = millis();
  ledFlashDuration = 0;
  setLEDColorForStatus(currentLEDStatus);
}

bool getLEDHeartbeatNextEventMs(unsigned long& waitMs) {
  if (!isLEDHeartbeatStatus(currentLEDStatus)) {
    return false;
  }

  unsigned long targetMs = ledHeartbeatOn ? ledHeartbeatOnMs : ledHeartbeatIntervalMs;
  unsigned long elapsedMs = millis() - ledHeartbeatPhaseStartTime;
  waitMs = (elapsedMs >= targetMs) ? 0 : (targetMs - elapsedMs);
  return true;
}

void setLEDStatus(String status) {
  String previousStatus = currentLEDStatus;
  currentLEDStatus = status;
  ledStatusStartTime = millis();
  VERBOSE_PRINTF("[LEDDBG] STATUS t=%lu from=%s to=%s idle=%d dashboard=%d flash_ms=%lu\n",
                 ledStatusStartTime, previousStatus.c_str(), status.c_str(),
                 idleModeActive ? 1 : 0, dashboardModeActive ? 1 : 0, (unsigned long)ledFlashDuration);

  if (status == "booting") {
    ledHeartbeatOn = false;
    setLEDColor(1, 1, 1);      // White - booting phase
    ledFlashDuration = 0;      // Continuous
  }
  else if (isLEDHeartbeatStatus(status)) {
    startLEDHeartbeat();       // Immediate heartbeat blink on mode entry
  }
  else if (status == "reading_success") {
    ledHeartbeatOn = false;
    setLEDColor(0, 1, 0);      // Green - successful reading
    ledFlashDuration = 1000;   // Flash for 1 second
  }
  else {
    ledHeartbeatOn = false;
    setLEDColor(0, 0, 0);      // Off
    ledFlashDuration = 0;
  }
}

// Update LED status based on current system state
void updateLEDStatus() {
  unsigned long now = millis();

  // Handle timed status changes (like reading success flash)
  if (ledFlashDuration > 0 && (now - ledStatusStartTime) >= ledFlashDuration) {
    VERBOSE_PRINTF("[LEDDBG] FLASH_EXPIRE t=%lu status=%s elapsed=%lu\n",
                   now, currentLEDStatus.c_str(), now - ledStatusStartTime);
    // Return to appropriate status based on current system state
    // Priority: idle > dashboard > sleeping.
    if (idleModeActive) {
      setLEDStatus("idle");  // Yellow LED - Idle mode active
    } else if (dashboardModeActive) {
      setLEDStatus("dashboard_active");  // Red LED - Dashboard Mode active
    } else {
      setLEDStatus("sleeping");  // Blue LED - Normal sleep mode
    }
    return;
  }

  if (isLEDHeartbeatStatus(currentLEDStatus)) {
    unsigned long waitMs = 0;
    if (getLEDHeartbeatNextEventMs(waitMs) && waitMs == 0) {
      ledHeartbeatPhaseStartTime = now;
      ledHeartbeatOn = !ledHeartbeatOn;
      if (ledHeartbeatOn) {
        setLEDColorForStatus(currentLEDStatus);
      } else {
        setLEDColor(0, 0, 0);
      }
    }
  }

  // Additional safety check to ensure steady-state LED priority.
  if (idleModeActive && currentLEDStatus != "idle" &&
      currentLEDStatus != "reading_success" && currentLEDStatus != "booting") {
    setLEDStatus("idle");
  } else if (!idleModeActive && dashboardModeActive && currentLEDStatus != "dashboard_active" &&
             currentLEDStatus != "reading_success" && currentLEDStatus != "booting") {
    setLEDStatus("dashboard_active");
  }
}
