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

typedef struct IdleEvent {
  uint32_t timestamp;    // Unix UTC, 0 if RTC/time is unavailable
  uint8_t reason;        // IdleReason value
  uint8_t reserved[3];
} IdleEvent;

// RfidReading::flags bit layout.
static const uint8_t FLAG_IS_DATA  = 0x01;
static const uint8_t FLAG_IS_ANIMAL = 0x02;
static const uint8_t FLAG_ANT1 = 0x04;
static const uint8_t FLAG_ANT2 = 0x08;
