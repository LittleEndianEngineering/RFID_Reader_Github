#pragma once

#include <Arduino.h>

// BLE Service and Characteristic UUIDs
#define RFID_SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define COMMAND_CHAR_UUID        "beb5483e-36e1-4688-b7f5-ea07361b26a8"
#define RESPONSE_CHAR_UUID       "beb5483e-36e1-4688-b7f5-ea07361b26a9"
#define STATUS_CHAR_UUID         "beb5483e-36e1-4688-b7f5-ea07361b26aa"

void initBLE();
void startBLEAdvertising();
void stopBLEAdvertising();
void sendBLEResponse(const String& response);
void sendBLEStatus(const String& status);
void processBLECommand(const String& command);

void sendStoredReadingsByBLE();
void sendStoredReadingsByBLEChunk(int chunkIndex);
void sendStoredReadingsByRangeBLE(uint32_t startTime, uint32_t endTime);
void sendStoredReadingsByRangeBLEChunk(uint32_t startTime, uint32_t endTime, int chunkIndex);
void sendLastReadingByBLE();
