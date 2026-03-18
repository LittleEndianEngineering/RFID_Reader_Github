#pragma once

#include <Arduino.h>
#include <Rfid134.h>

bool isTemperatureAvailable(const Rfid134Reading& tag);
void tryReadAndStoreTag();
void powerCycleRFIDModule();
void powerOnAndReadTagWindow(unsigned long windowMs);

class RfidNotify {
public:
  static void OnError(Rfid134_Error errorCode);
  static void OnPacketRead(const Rfid134Reading& reading);
};

extern Rfid134<HardwareSerial, RfidNotify> rfid;
