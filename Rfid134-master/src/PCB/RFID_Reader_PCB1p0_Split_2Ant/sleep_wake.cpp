#include "sleep_wake.h"

#include <WiFi.h>
#include "esp_sleep.h"
#include "driver/gpio.h"
#include "esp_bt.h"   // for btStop()
#include "driver/uart.h"

extern "C" {
  #include "freertos/FreeRTOS.h"
  #include "freertos/task.h"
  #include "soc/soc.h"
}

#include "globals.h"
#include "pins.h"
#include "led_status.h"

// Drain Serial TX completely so prints don't get truncated before sleep
void serialDrain(uint32_t timeout_ms) {
  (void)timeout_ms;
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
