#pragma once

#include <Arduino.h>

void serialDrain(uint32_t timeout_ms = 80);
void printWakeupCause();
void configureWakeSources(uint64_t sleep_us, bool enableButtonWake, bool enableUartWake);
void lightSleepUntilNextEvent(uint64_t sleep_us);
