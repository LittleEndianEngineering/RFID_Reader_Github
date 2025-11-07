# Implant RFID Reader - ESP32-S3 System

**PROPRIETARY SOFTWARE**  
Copyright (c) 2025 Establishment Labs  
Developed by Little Endian Engineering

---

## Overview

Complete RFID reader system for medical implant temperature monitoring, featuring:
- **ESP32-S3 Firmware**: RFID reading with RTC, flash storage, light sleep power saving, and BLE connectivity
- **Python Dashboard**: Streamlit web interface for device configuration and data analysis
- **Flutter Mobile App**: Cross-platform mobile application for BLE connectivity and data visualization

---

## System Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Flutter App    │────▶│   ESP32-S3       │◀────│ Python Dashboard│
│  (BLE Client)   │ BLE │  (BLE Server)    │ USB │  (Serial/USB)   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                              │
                              ▼
                        ┌─────────────┐
                        │ RFID Module │
                        │  (WL-134)   │
                        └─────────────┘
```

---

## Features

### ESP32-S3 Firmware
- ✅ **RFID Reading**: WL-134 module with temperature sensor data extraction
- ✅ **RTC Integration**: DS1307 external RTC module for accurate timekeeping
- ✅ **Flash Storage**: SPIFFS-based storage for up to 20,160 readings
- ✅ **Light Sleep Mode**: Power-efficient sleep with timer, GPIO, and UART wake-up
- ✅ **Multi-Button Control**: Single button for manual reads and Dashboard Mode toggle
- ✅ **RGB LED Status**: Visual feedback (booting, sleeping, reading success, dashboard active)
- ✅ **BLE Support**: Bluetooth Low Energy for mobile app connectivity (Dashboard Mode only)
- ✅ **WiFi & NTP**: Automatic time synchronization via WiFi
- ✅ **ESP32-S3 Mac Compatible**: USB-CDC stability improvements for macOS

### Python Dashboard
- ✅ **Streamlit Web Interface**: Real-time device monitoring and control
- ✅ **Data Visualization**: Temperature charts and reading history
- ✅ **Date/Time Filtering**: Timezone-aware data retrieval
- ✅ **CSV Export**: Data export functionality
- ✅ **Configuration Management**: WiFi, button timings, and device settings
- ✅ **Latest Reading Highlight**: Quick access to most recent reading

### Flutter Mobile App
- ✅ **BLE Connectivity**: Connect to ESP32-S3 via Bluetooth Low Energy
- ✅ **Real-Time Reading**: Manual RFID reading with live results
- ✅ **Data Filtering**: Date/time range filtering with timezone support
- ✅ **Temperature Visualization**: Interactive charts with fl_chart
- ✅ **CSV Export**: Export filtered readings to CSV
- ✅ **Image Export**: Save temperature charts to device gallery
- ✅ **Cross-Platform**: iOS, Android, and macOS support
- ✅ **Responsive Design**: Optimized for phones and tablets

---

## Hardware Requirements

### ESP32-S3 Development Board
- ESP32-S3 microcontroller
- USB-C port for programming and power

### RFID Module
- WL-134 RFID reader module
- Connected via UART (GPIO 48)

### RTC Module
- DS1307 Real-Time Clock
- Connected via I2C (GPIO 8 = SDA, GPIO 9 = SCL)

### Additional Components
- Push button (GPIO 37) for manual reads and Dashboard Mode
- RGB LED (GPIO 2 = Red, GPIO 5 = Green, GPIO 6 = Blue) for status indication
- RFID power control (GPIO 36)

---

## Software Requirements

### ESP32 Firmware
- Arduino IDE 2.x or PlatformIO
- ESP32 Arduino Core 3.3.1+
- Required libraries:
  - `Rfid134.h` (included in repository)
  - `RTClib.h` (Adafruit RTClib)
  - `SPIFFS.h` (ESP32 core)
  - `BLEDevice.h` (ESP32 BLE)

### Python Dashboard
- Python 3.8+
- Required packages (see `dashboard/src/requirements.txt`):
  - `streamlit>=1.28.0`
  - `pandas>=1.5.0`
  - `pyserial>=3.5`
  - `plotly>=5.15.0`
  - `pytz>=2023.3`

### Flutter Mobile App
- Flutter SDK 3.8.1+
- Dart 3.8.1+
- Required packages (see `mobile_app/rfid_reader_app/pubspec.yaml`):
  - `flutter_blue_plus: ^1.12.9` (BLE support)
  - `fl_chart: ^0.68.0` (charts)
  - `timezone: ^0.9.2` (timezone conversion)
  - `path_provider`, `share_plus`, `gallery_saver`

---

## Installation & Setup

### 1. ESP32-S3 Firmware

1. **Install Arduino IDE** and ESP32 board support:
   - Add ESP32 board URL: `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
   - Install "esp32" by Espressif Systems

2. **Install Required Libraries**:
   - Install `RTClib` by Adafruit from Library Manager
   - Copy `src/Rfid134.h` to your Arduino libraries folder

3. **Upload Firmware**:
   - Open `src/ReadRfid_RealRTC_FLASH_LightSleep_Multibutton_BLE_S3/ReadRfid_RealRTC_FLASH_LightSleep_Multibutton_BLE_S3.ino`
   - Select board: **ESP32S3 Dev Module**
   - Select port: Your ESP32-S3 USB port
   - Upload

4. **Configure WiFi** (optional, for NTP sync):
   - Edit `ssid_str` and `password_str` in the firmware code
   - Or use serial commands: `wifi SSID PASSWORD`

### 2. Python Dashboard

1. **Install Python Dependencies**:
   ```bash
   cd dashboard/src
   pip install -r requirements.txt
   ```

2. **Run Dashboard**:
   ```bash
   streamlit run rfid_dashboard_configure_lightsleep_multibutton.py
   ```

3. **Access Dashboard**:
   - Open browser to `http://localhost:8501`
   - Connect ESP32-S3 via USB
   - Select the correct serial port

### 3. Flutter Mobile App

1. **Install Flutter SDK**:
   - Follow [Flutter installation guide](https://flutter.dev/docs/get-started/install)

2. **Get Dependencies**:
   ```bash
   cd mobile_app/rfid_reader_app
   flutter pub get
   ```

3. **Run App**:
   ```bash
   # iOS
   flutter run -d ios
   
   # Android
   flutter run -d android
   
   # macOS
   flutter run -d macos
   ```

4. **Build for Production**:
   ```bash
   # iOS
   flutter build ios --release
   
   # Android
   flutter build apk --release
   ```

---

## Usage

### ESP32-S3 Operation Modes

#### Normal Mode (Default)
- Periodic RFID reads every 60 seconds (configurable)
- Light sleep between reads for power efficiency
- BLE disabled
- RGB LED indicates sleep status

#### Dashboard Mode
- Activated by long-pressing the button (default: 3 seconds)
- ESP32 stays awake, no periodic reads
- BLE advertising enabled for mobile app
- Responsive to serial/USB commands from dashboard
- RGB LED indicates dashboard active status

#### Manual Read
- Short press button: Trigger immediate RFID read
- Works in both Normal and Dashboard Mode

### Mobile App Workflow

1. **Connect to ESP32**:
   - Enable Dashboard Mode on ESP32 (long press button)
   - Open mobile app
   - Tap Bluetooth button to scan
   - Select "RFID Reader" device
   - Wait for connection

2. **Read RFID Tags**:
   - Go to "Filter & Graph" tab
   - Tap "Read Now" button
   - Place RFID tag near reader
   - View live reading result

3. **Retrieve Stored Data**:
   - Set date/time range and timezone
   - Tap "Retrieve Data"
   - View filtered readings in table
   - Analyze temperature trends in chart

4. **Export Data**:
   - Tap "Export CSV" to export readings table
   - Tap "Save Image" to save temperature chart to gallery

### Dashboard Workflow

1. **Connect Device**:
   - Connect ESP32-S3 via USB
   - Select serial port in dashboard
   - Device status will show "Connected"

2. **Configure Settings**:
   - Update WiFi credentials
   - Adjust button press timings
   - Configure periodic read intervals

3. **View Data**:
   - See latest reading in "Latest Reading" section
   - Filter by date/time range
   - Export data as CSV
   - View temperature trends

---

## BLE Communication

### Service & Characteristics

- **Service UUID**: `4fafc201-1fb5-459e-8fcc-c5c9c331914b`
- **Command Characteristic**: `beb5483e-36e1-4688-b7f5-ea07361b26a8` (write)
- **Response Characteristic**: `beb5483e-36e1-4688-b7f5-ea07361b26a9` (notify)
- **Status Characteristic**: `beb5483e-36e1-4688-b7f5-ea07361b26aa` (notify)

### Available Commands

- `readnow` - Trigger manual RFID read
- `last` - Get last stored reading
- `print` - Get all stored readings
- `range <start_epoch> <end_epoch>` - Get readings in time range (UTC Unix timestamps)
- `status` - Get device status
- `debugsimple` - Enable verbose debug output

### Response Format

Individual readings:
```
#1: 2025-10-22 04:29:52, 999, 141004263679, 25.87°C
```

Range responses:
```
---BEGIN_READINGS---
#1: 2025-10-22 04:29:52, 999, 141004263679, 25.87°C
#2: 2025-10-22 04:30:46, 999, 141004263679, 31.70°C
...
---END_READINGS---
```

---

## File Structure

```
Rfid134-master/
├── src/
│   ├── ReadRfid_RealRTC_FLASH_LightSleep_Multibutton_BLE_S3/
│   │   └── ReadRfid_RealRTC_FLASH_LightSleep_Multibutton_BLE_S3.ino  # Main firmware
│   └── Rfid134.h                                                      # RFID library
├── dashboard/
│   └── src/
│       ├── rfid_dashboard_configure_lightsleep_multibutton.py         # Streamlit dashboard
│       ├── requirements.txt                                          # Python dependencies
│       └── README_MultiButton_Dashboard.md                           # Dashboard docs
└── mobile_app/
    └── rfid_reader_app/
        ├── lib/
        │   └── main.dart                                              # Flutter app code
        ├── pubspec.yaml                                               # Flutter dependencies
        ├── assets/images/                                             # App assets
        └── ios/macos/android/                                         # Platform configs
```

---

## Troubleshooting

### ESP32-S3 USB Connection Issues (macOS)
- Ensure USB-C cable supports data transfer
- Try different USB port
- Restart Arduino IDE if connection drops
- Check USB-CDC stability improvements in firmware

### WiFi Connection Fails
- Verify SSID and password are correct
- Check 2.4 GHz network (ESP32 doesn't support 5 GHz)
- Try reducing WiFi TX power: `esp_wifi_set_max_tx_power(40)`
- Ensure router allows ESP32 connections

### BLE Not Discoverable
- Ensure Dashboard Mode is active (long press button)
- Check RGB LED shows dashboard active status
- Restart ESP32 if BLE doesn't start
- Verify mobile app has Bluetooth permissions

### Mobile App Can't Connect
- Verify ESP32 is in Dashboard Mode
- Check BLE UUIDs match between firmware and app
- Ensure Bluetooth is enabled on mobile device
- Try disconnecting and reconnecting

---

## License

**PROPRIETARY SOFTWARE**  
Copyright (c) 2025 Establishment Labs  
All rights reserved.

This software is proprietary and confidential. Unauthorized copying, modification, distribution, or use of this software, via any medium, is strictly prohibited.

---

## Support

For technical support or inquiries:
- **Email**: lyu@establishmentlabs.com
- **Developer**: info@littleendianengineering.com

---

## Version History

- **v1.4** (September 2025): ESP32-S3 Mac compatibility, BLE reconnection fix, responsive mobile app UI
- **v1.3**: Multi-button support, RGB LED status indicators
- **v1.2**: Light sleep optimization, Dashboard Mode
- **v1.1**: RTC integration, flash storage
- **v1.0**: Initial release with basic RFID reading

---

## Acknowledgments

- **Rfid134 Library**: Based on Makuna's Rfid134 library for WL-134 module support
- **ESP32 Community**: For excellent documentation and support
- **Flutter Team**: For cross-platform mobile development framework
