# Implant RFID Reader - ESP32-S3 System

**PROPRIETARY SOFTWARE**  
Copyright (c) 2025 Establishment Labs  
Developed by Little Endian Engineering

---

## Overview

Complete RFID reader system for medical implant temperature monitoring, featuring:
- **ESP32-S3 2Ant Firmware**: Dual-antenna RFID reading with RTC, flash storage, light sleep power saving, BLE connectivity, low-SoC idle protection, and USB service recovery
- **Python Dashboard**: Streamlit web interface for live reads, device configuration, data retrieval, battery/idle visibility, and data analysis
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
- ✅ **Dual-Antenna RFID Reading**: WL-134 module with ANT1/ANT2 selection and temperature sensor data extraction
- ✅ **RTC Integration**: DS1307 external RTC module for accurate timekeeping
- ✅ **Flash Storage**: SPIFFS-based storage for up to 20,160 readings
- ✅ **Light Sleep Mode**: Power-efficient sleep with timer, GPIO, and UART wake-up
- ✅ **Multi-Button Control**: Single button for manual reads and Dashboard Mode toggle
- ✅ **RGB LED Status**: Visual feedback for boot, sleep, dashboard, idle, and read states
- ✅ **BLE Support**: Bluetooth Low Energy for mobile app connectivity (Dashboard Mode only)
- ✅ **Low-SoC Idle Protection**: Configurable battery threshold, voltage calibration, and USB recovery window
- ✅ **Live View Support**: Serial `readnow` command with timestamped `[RFID_RESULT]` output for dashboard plotting
- ✅ **ESP32-S3 Mac Compatible**: USB-CDC stability improvements for macOS

### Python Dashboard
- ✅ **Streamlit Web Interface**: Real-time device monitoring and control
- ✅ **Live View**: Manual and automatic `readnow` cycles with latest ANT1/ANT2 result cards
- ✅ **Data Visualization**: Temperature charts and reading history
- ✅ **Date/Time Filtering**: Timezone-aware data retrieval
- ✅ **CSV Export**: Data export functionality
- ✅ **Configuration Management**: WiFi, read timing, Live View timing, low-SoC, Dashboard Mode, verbose logging, and LED heartbeat settings
- ✅ **Latest Reading Highlight**: Quick access to most recent ANT1/ANT2 readings

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
- Connected via UART (GPIO 41)
- Antenna select control on GPIO 36

### RTC Module
- DS1307 Real-Time Clock
- Connected via I2C (GPIO 35 = SDA, GPIO 45 = SCL)

### Additional Components
- Push button (GPIO 37) for manual reads and Dashboard Mode
- RGB LED (GPIO 5 = Red, GPIO 6 = Green, GPIO 4 = Blue) for status indication
- RFID power control (GPIO 42)
- Battery SoC ADC input (GPIO 7)

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
   - Use the included RFID library header at `src/PCB/Rfid134.h`

3. **Upload Firmware**:
   - Open `src/PCB/RFID_Reader_PCB1p0_Split_2Ant/RFID_Reader_PCB1p0_Split_2Ant.ino`
   - Select board: **ESP32S3 Dev Module**
   - Select port: Your ESP32-S3 USB port
   - Upload

4. **Configure WiFi** (optional, for NTP sync):
   - Edit `ssid_str` and `password_str` in the firmware code
   - Or use dashboard configuration fields / serial `set ssid ...` and `set password ...` commands

### 2. Python Dashboard

1. **Install Python Dependencies**:
   ```bash
   cd dashboard/src
   pip install -r requirements.txt
   ```

2. **Run Dashboard**:
   ```bash
   streamlit run rfid_dashboard_configure_lightsleep_multibutton_S3_live_2Ant.py
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
- Activated by long-pressing the button (default: 5 seconds) or by explicit dashboard configuration command
- ESP32 stays awake for USB dashboard service access
- Periodic RFID reads are paused while Dashboard Mode is active
- BLE advertising enabled for mobile app
- Responsive to serial/USB commands from dashboard
- RGB LED indicates dashboard active status

#### Low-SoC Idle Mode
- Optional battery-based idle entry using configurable SoC threshold and voltage calibration
- RFID reads are blocked while idle mode is active
- A configurable USB recovery window keeps the device awake briefly after low-SoC idle so Dashboard Mode can be enabled
- Once Dashboard Mode is active, USB dashboard access remains available even if low-SoC idle remains active

#### Manual Read
- Short press button: Trigger immediate RFID read
- Works when idle mode is inactive and RFID reads are allowed

#### Live View
- Dashboard-controlled read loop using the serial `readnow` command
- Configurable auto-read interval saved as `liveViewAutoReadIntervalMs`
- Dashboard enforces a safe minimum interval for dual-antenna read windows
- New readings are plotted directly from timestamped `[RFID_RESULT]` lines

### Mobile App Workflow

1. **Connect to ESP32**:
   - Enable Dashboard Mode on ESP32 using the long press button or dashboard service configuration
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
   - Adjust RFID, Live View, and button timings
   - Configure low-SoC idle, USB recovery, Dashboard Mode, verbose logging, and LED heartbeat settings

3. **View Data**:
   - Use **Read Now** or **Live View** for immediate ANT1/ANT2 reads
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
- `dashboardmode on|off` - Enable or disable Dashboard Mode service access
- `get liveViewAutoReadIntervalMs` / `set liveViewAutoReadIntervalMs <ms>` - Read or configure Live View interval

### Response Format

Individual readings:
```
#1: 2025-10-22 04:29:52, 999, 141004263679, 25.87°C
```

Live Read Now results:
```
[RFID_RESULT] stored=true ant=ANT1 reading=42 ts=1761107392 tag=999 141004263679 temp=25.87°C
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
│   └── PCB/
│       ├── Rfid134.h                                                  # RFID library
│       └── RFID_Reader_PCB1p0_Split_2Ant/
│           ├── RFID_Reader_PCB1p0_Split_2Ant.ino                      # Main firmware
│           ├── config.cpp/.h                                          # Persistent configuration
│           ├── serial_cmd.cpp/.h                                      # USB serial command handling
│           ├── rfid_reader.cpp/.h                                     # Dual-antenna RFID reads
│           ├── sleep_wake.cpp/.h                                      # Light sleep and idle behavior
│           └── pins.h                                                 # Hardware pin map
├── dashboard/
│   └── src/
│       ├── rfid_dashboard_configure_lightsleep_multibutton_S3_live_2Ant.py
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
- Ensure Dashboard Mode is active using the long press button or dashboard service configuration
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

- **v1.6** (July 2026): Live View auto-read interval persistence, serial `readnow`, timestamped `[RFID_RESULT]` output, latest ANT1/ANT2 cards, and dashboard timeout controls
- **v1.5** (July 2026): Low-SoC idle controls, USB recovery window, Dashboard Mode service latch, idle event logging
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
