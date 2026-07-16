#pragma once

#include <Arduino.h>

#include "types.h"

constexpr int MAX_READINGS = 20160;
constexpr int READING_SIZE = 20;
constexpr int MAX_IDLE_EVENTS = 512;
constexpr int IDLE_EVENT_SIZE = sizeof(IdleEvent);

void initFlash();
void storeReading(const RfidReading& reading);
void printStoredReadings();
void printLastReading();
void printReadingsSummary();
void sendStoredReadingsByRange(uint32_t startTime, uint32_t endTime);
void storeIdleEvent(uint8_t reason);
void printIdleEvents();
void clearIdleEvents();
