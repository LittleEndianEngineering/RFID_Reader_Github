#include "flash_store.h"

#include <SPIFFS.h>
#include <time.h>

#include "globals.h"

void initFlash() {
  if (!SPIFFS.begin(true)) { Serial.println("[FS] SPIFFS Mount Failed"); return; }
  File file = SPIFFS.open(FLASH_FILENAME, "r");
  if (!file) readingCount = 0;
  else { readingCount = file.size() / READING_SIZE; file.close(); }
  Serial.printf("[FS] FLASH has %d readings\n", readingCount);
}

void storeReading(const RfidReading& reading) {
  if (!SPIFFS.begin(true)) { Serial.println("[FS] SPIFFS Mount Failed"); return; }
  File file = SPIFFS.open(FLASH_FILENAME, "a");
  if (!file) { Serial.println("[FS] Failed to open file for writing"); return; }
  file.write((uint8_t*)&reading, READING_SIZE);
  file.close();
  readingCount++;

  // Extra blank line before the stored-reading line
  Serial.println();
  Serial.printf("[FS] Stored reading #%d\n", readingCount);
}

void printStoredReadings() {
  if (readingCount == 0) { Serial.println("No readings stored."); return; }
  Serial.println("---BEGIN_READINGS---");
  Serial.printf("Printing %d stored readings:\n", readingCount);
  File file = SPIFFS.open(FLASH_FILENAME, "r");
  if (!file) { Serial.println("---END_READINGS---"); return; }
  int i = 0;
  while (file.available() >= READING_SIZE) {
    RfidReading reading;
    file.read((uint8_t*)&reading, READING_SIZE);
    if (reading.timestamp > 1000000000) {
      time_t timestamp = reading.timestamp;
      struct tm* ti = gmtime(&timestamp);
      
      // Check if temperature is available (0xFFFF = marker for N/A)
      if (reading.temp_raw == 0xFFFF) {
        Serial.printf("#%d: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, N/A\n",
                      i + 1, ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
                      ti->tm_hour, ti->tm_min, ti->tm_sec,
                      reading.country, reading.id);
      } else {
        float temp = reading.temp_raw / 100.0f;
        Serial.printf("#%d: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, %.2f°C\n",
                      i + 1, ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
                      ti->tm_hour, ti->tm_min, ti->tm_sec,
                      reading.country, reading.id, temp);
      }
    }
    i++; yield();
  }
  file.close();
  Serial.println("---END_READINGS---");
}

void printLastReading() {
  if (readingCount == 0) { Serial.println("No readings stored."); return; }
  Serial.println("---BEGIN_READINGS---");
  Serial.println("Last reading:");
  File file = SPIFFS.open(FLASH_FILENAME, "r");
  if (!file) { Serial.println("---END_READINGS---"); return; }
  
  // Skip to the last reading
  int totalReadings = file.size() / READING_SIZE;
  if (totalReadings > 0) {
    // Seek to the last reading
    file.seek((totalReadings - 1) * READING_SIZE, SeekSet);
    
    RfidReading reading;
    if (file.read((uint8_t*)&reading, READING_SIZE) == READING_SIZE) {
      if (reading.timestamp > 1000000000) {
        time_t timestamp = reading.timestamp;
        struct tm* ti = gmtime(&timestamp);
        
        // Check if temperature is available (0xFFFF = marker for N/A)
        if (reading.temp_raw == 0xFFFF) {
          Serial.printf("#%d: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, N/A\n",
                        totalReadings, ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
                        ti->tm_hour, ti->tm_min, ti->tm_sec,
                        reading.country, reading.id);
        } else {
          float temp = reading.temp_raw / 100.0f;
          Serial.printf("#%d: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, %.2f°C\n",
                        totalReadings, ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
                        ti->tm_hour, ti->tm_min, ti->tm_sec,
                        reading.country, reading.id, temp);
        }
      }
    }
  }
  file.close();
  Serial.println("---END_READINGS---");
}

// NEW: concise summary for boot and on-demand
void printReadingsSummary() {
  Serial.println("[FS] --- Readings Summary ---");
  Serial.printf("[FS] Count: %d / %d\n", readingCount, MAX_READINGS);

  unsigned long usedBytes = (unsigned long)readingCount * READING_SIZE;
  unsigned long totalBytes = (unsigned long)MAX_READINGS * READING_SIZE;
  float pct = (totalBytes > 0) ? (100.0f * usedBytes / totalBytes) : 0.0f;
  Serial.printf("[FS] Bytes used: %lu of %lu (%.1f%%)\n", usedBytes, totalBytes, pct);

  if (readingCount > 0) {
    File f = SPIFFS.open(FLASH_FILENAME, "r");
    if (f) {
      RfidReading first, last;

      // First record
      f.seek(0, SeekSet);
      if (f.read((uint8_t*)&first, READING_SIZE) == READING_SIZE) {
        if (first.timestamp > 1000000000UL) {
          time_t ts = first.timestamp;
          struct tm* ti = gmtime(&ts);
          Serial.printf("[FS] Oldest: %04d-%02d-%02d %02d:%02d:%02d (country=%u id=%llu)\n",
                        ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
                        ti->tm_hour, ti->tm_min, ti->tm_sec,
                        first.country, first.id);
        }
      }

      // Last record
      f.seek((readingCount - 1) * READING_SIZE, SeekSet);
      if (f.read((uint8_t*)&last, READING_SIZE) == READING_SIZE) {
        if (last.timestamp > 1000000000UL) {
          time_t ts = last.timestamp;
          struct tm* ti = gmtime(&ts);
          Serial.printf("[FS] Newest: %04d-%02d-%02d %02d:%02d:%02d (country=%u id=%llu)\n",
                        ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
                        ti->tm_hour, ti->tm_min, ti->tm_sec,
                        last.country, last.id);
        }
      }

      f.close();
    }
  } else {
    Serial.println("[FS] No readings yet.");
  }
  Serial.println("[FS] ------------------------");
}

void sendStoredReadingsByRange(uint32_t startTime, uint32_t endTime) {
  Serial.println("[RANGE] === Range Request Start ===");
  File file = SPIFFS.open(FLASH_FILENAME, "r");
  if (!file) { 
    Serial.println("[RANGE] ERROR: Failed to open FLASH file"); 
    Serial.println("<DASHBOARD_DATA>\n---BEGIN_READINGS---\n---END_READINGS---\n</DASHBOARD_DATA>"); 
    return; 
  }
  
  // STREAMING APPROACH: Two-pass to avoid stack overflow
  // Pass 1: Count matches and find first/last (store only 2 readings max)
  int count = 0;
  RfidReading firstReading, lastReading;
  bool firstFound = false;
  
  while (file.available() >= READING_SIZE) {
    RfidReading reading;
    file.read((uint8_t*)&reading, READING_SIZE);
    if (reading.timestamp > 1000000000 &&
        reading.timestamp >= startTime && reading.timestamp <= endTime) {
      if (!firstFound) {
        firstReading = reading;
        firstFound = true;
      }
      lastReading = reading;  // Always update last as we scan
      count++;
    }
    yield();  // Prevent watchdog timeout
  }
  file.close();
  
  // Print summary (same format as before)
  Serial.printf("Found %d readings in range.\n", count);
  if (count > 0) {
    time_t ts_first = firstReading.timestamp;
    struct tm* ti_first = gmtime(&ts_first);
    if (firstReading.temp_raw == 0xFFFF) {
      Serial.printf("First: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, N/A\n",
        ti_first->tm_year + 1900, ti_first->tm_mon + 1, ti_first->tm_mday,
        ti_first->tm_hour, ti_first->tm_min, ti_first->tm_sec,
        firstReading.country, firstReading.id);
    } else {
      float temp_first = firstReading.temp_raw / 100.0f;
      Serial.printf("First: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, %.2fC\n",
        ti_first->tm_year + 1900, ti_first->tm_mon + 1, ti_first->tm_mday,
        ti_first->tm_hour, ti_first->tm_min, ti_first->tm_sec,
        firstReading.country, firstReading.id, temp_first);
    }
    time_t ts_last = lastReading.timestamp;
    struct tm* ti_last = gmtime(&ts_last);
    if (lastReading.temp_raw == 0xFFFF) {
      Serial.printf("Last: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, N/A\n",
        ti_last->tm_year + 1900, ti_last->tm_mon + 1, ti_last->tm_mday,
        ti_last->tm_hour, ti_last->tm_min, ti_last->tm_sec,
        lastReading.country, lastReading.id);
    } else {
      float temp_last = lastReading.temp_raw / 100.0f;
      Serial.printf("Last: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, %.2fC\n",
        ti_last->tm_year + 1900, ti_last->tm_mon + 1, ti_last->tm_mday,
        ti_last->tm_hour, ti_last->tm_min, ti_last->tm_sec,
        lastReading.country, lastReading.id, temp_last);
    }
  } else {
    Serial.println("None");
  }

  // Pass 2: Stream all matching readings directly (no vector storage)
  Serial.println("<DASHBOARD_DATA>");
  Serial.println("---BEGIN_READINGS---");
  
  file = SPIFFS.open(FLASH_FILENAME, "r");
  if (!file) {
    Serial.println("---END_READINGS---");
    Serial.println("</DASHBOARD_DATA>");
    Serial.println("[RANGE] === Range Request End ===");
    return;
  }
  
  int readingNum = 0;
  while (file.available() >= READING_SIZE) {
    RfidReading reading;
    file.read((uint8_t*)&reading, READING_SIZE);
    if (reading.timestamp > 1000000000 &&
        reading.timestamp >= startTime && reading.timestamp <= endTime) {
      readingNum++;
      time_t timestamp = reading.timestamp;
      struct tm* ti = gmtime(&timestamp);
      if (reading.temp_raw == 0xFFFF) {
        Serial.printf("#%d: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, N/A\n",
          readingNum, ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
          ti->tm_hour, ti->tm_min, ti->tm_sec,
          reading.country, reading.id);
      } else {
        float temp = reading.temp_raw / 100.0f;
        Serial.printf("#%d: %04d-%02d-%02d %02d:%02d:%02d, %u, %llu, %.2f°C\n",
          readingNum, ti->tm_year + 1900, ti->tm_mon + 1, ti->tm_mday,
          ti->tm_hour, ti->tm_min, ti->tm_sec,
          reading.country, reading.id, temp);
      }
      // Yield periodically to prevent watchdog timeout and allow serial transmission
      if (readingNum % 50 == 0) {
        yield();
        Serial.flush();  // Ensure data is sent before continuing
      }
    }
    yield();  // Yield on every iteration to prevent blocking
  }
  file.close();
  
  Serial.println("---END_READINGS---");
  Serial.println("</DASHBOARD_DATA>");
  Serial.println("[RANGE] === Range Request End ===");
  Serial.flush();  // Ensure final data is sent
}
