#pragma once

#include <Arduino.h>

#include "types.h"

constexpr int MAX_READINGS = 20160;
constexpr int READING_SIZE = 20;

void initFlash();
void storeReading(const RfidReading& reading);
void printStoredReadings();
void printLastReading();
void printReadingsSummary();
void sendStoredReadingsByRange(uint32_t startTime, uint32_t endTime);
