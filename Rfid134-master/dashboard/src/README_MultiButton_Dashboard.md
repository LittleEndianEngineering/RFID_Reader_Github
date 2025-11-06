# Multi-Button RFID Reader Dashboard

This document describes the multi-button dashboard application for the ESP32 RFID reader with configurable button timings.

## Overview

The Multi-Button Dashboard (`rfid_dashboard_configure_lightsleep_multibutton.py`) is an enhanced version of the standard RFID reader dashboard that supports:

- **Multi-Button Functionality**: Single button controls both RFID readings and dashboard mode
- **Configurable Long Press Timer**: Adjustable duration for dashboard mode activation
- **Real-time Configuration**: Set button timings via the dashboard interface
- **Enhanced User Experience**: Clear visual feedback and status information

## Features

### Multi-Button Control
- **Short Press**: Triggers manual RFID reading
- **Long Press**: Toggles Dashboard Mode ON/OFF
- **Configurable Timing**: Long press duration can be set from 1-30 seconds
- **Real-time Feedback**: Serial messages guide user during long press

### Dashboard Mode
- **Active**: ESP32 stays awake, no periodic reads, responsive to dashboard
- **Inactive**: Light sleep between reads, periodic RFID scanning
- **Visual Indicators**: Clear status display in dashboard

### Configuration Management
- **WiFi Settings**: SSID and password configuration
- **RFID Timing**: ON time and periodic interval settings
- **Button Timing**: Long press duration configuration
- **Real-time Updates**: Changes applied immediately to ESP32

## Usage

### Starting the Dashboard
```bash
streamlit run rfid_dashboard_configure_lightsleep_multibutton.py
```

### Configuration Tab
1. **WiFi SSID**: Enter your WiFi network name
2. **WiFi Password**: Enter your WiFi password
3. **RFID ON Time**: Duration for RFID scanning (1-60 seconds)
4. **Periodic Interval**: Time between automatic reads (10-3600 seconds)
5. **Long Press Timer**: Duration to hold button for dashboard mode (1-30 seconds)

### Setting Variables
1. Click "Set Variables on ESP32" to apply all settings
2. Click "Read Variables from ESP32" to load current settings
3. Upload .ino file to parse current firmware values

### Multi-Button Testing
- **Button Mode**: Check current multi-button status and settings
- **Test Button**: Get instructions for testing button functionality

## Button Behavior

### Short Press (< configured long press time)
- Triggers immediate RFID reading
- Works in both Dashboard Mode ON and OFF
- Adaptive debounce: 50ms when awake, 100ms when sleeping

### Long Press (≥ configured long press time)
- Toggles Dashboard Mode ON/OFF
- Real-time feedback during press:
  - 1 second: "Long press in progress..."
  - At threshold: "*** LONG PRESS DETECTED ***"
- Works from any state (awake or sleeping)

## Technical Details

### ESP32 Firmware Requirements
- Multi-Button firmware: `ReadRfid_RealRTC_FLASH_Button_LightSleep_Optimized_Multibutton.ino`
- Configurable variables: `longPressMs` (milliseconds)
- Serial commands: `get longPressMs`, `set longPressMs`

### Dashboard Features
- Real-time serial communication
- Timezone-aware timestamp conversion
- Interactive data visualization
- CSV export functionality
- Password-protected storage clearing

## Configuration Variables

| Variable | Range | Default | Description |
|----------|-------|---------|-------------|
| `longPressMs` | 1000-30000 | 5000 | Long press duration in milliseconds |
| `rfidOnTimeMs` | 1000-60000 | 5000 | RFID scanning duration |
| `periodicIntervalMs` | 10000-3600000 | 60000 | Periodic reading interval |
| `ssid` | String | - | WiFi network name |
| `password` | String | - | WiFi password |

## Troubleshooting

### Button Not Responding
1. Check button mode status: Use "Button Mode" quick command
2. Verify button timing: Check current `longPressMs` setting
3. Test button functionality: Use "Test Button" quick command

### Dashboard Mode Issues
1. Verify Dashboard Mode toggle is working
2. Check ESP32 serial output for mode change messages
3. Ensure long press duration is appropriate for your use case

### Configuration Not Saving
1. Verify ESP32 connection is stable
2. Check serial communication in debug logs
3. Ensure all variables are within valid ranges

## Version History

- **v1.1 (Multi-Button)**: Added configurable long press timer and multi-button functionality
- **v1.0**: Initial release with basic dashboard functionality

## Support

For technical support or questions:
- **Establishment Labs**: jdelgadoq@establishmentlabs.com
- **Little Endian Engineering**: info@littleendianengineering.com

---

**CONFIDENTIAL - PROPRIETARY SOFTWARE**
© 2025 Establishment Labs. All rights reserved.


