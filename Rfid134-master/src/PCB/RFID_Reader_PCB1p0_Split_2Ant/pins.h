#pragma once

// =============================================================================
// HARDWARE PIN CONFIGURATION
// =============================================================================

#define BUTTON_PIN 37        // Push button (INPUT_PULLUP): pressed = LOW
#define RFID_PWR_PIN 42      // RFID power control (active LOW)
#define RFID_TX_PIN 41       // RFID serial
#define ANT_SEL_PIN 36      // Selection between ANT1 & ANT2

// I2C Pins for RTC (DS1307) - ESP32-S3 Safe Pins
#define I2C_SDA_PIN 35        // I2C Data pin
#define I2C_SCL_PIN 45        // I2C Clock pin

// RGB LED Status Indicator (ESP32-S3 Safe Pins)
#define LED_RED_PIN 5        // Red anode pin
#define LED_GREEN_PIN 6      // Green anode pin
#define LED_BLUE_PIN 4       // Blue anode pin
