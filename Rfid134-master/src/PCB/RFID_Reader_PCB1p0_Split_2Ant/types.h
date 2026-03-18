#pragma once

#include <Arduino.h>

// Reading structure (20 bytes total) - MUST be defined before any includes
typedef struct RfidReading {
  uint32_t timestamp;    // Unix UTC
  uint16_t country;
  uint64_t id;
  uint16_t temp_raw;     // temp * 100
  uint8_t  flags;
  uint8_t  reserved;
} RfidReading;
