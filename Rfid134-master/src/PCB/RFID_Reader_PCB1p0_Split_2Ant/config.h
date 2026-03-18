#pragma once

#include <Arduino.h>

bool configExists();
void saveConfigVar(const String& key, const String& value);
String loadConfigVar(const String& key);
void loadConfig();
