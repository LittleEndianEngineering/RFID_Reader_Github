# Multi-Button RFID Reader Dashboard

This document describes the current Streamlit dashboard for the ESP32-S3 2Ant RFID reader firmware.

## Overview

The production dashboard is:

```bash
streamlit run rfid_dashboard_configure_lightsleep_multibutton_S3_live_2Ant.py
```

It supports:

- **Multi-Button Functionality**: Single button controls both RFID readings and dashboard mode
- **Configurable Long Press Timer**: Adjustable duration for dashboard mode activation
- **Live View**: Dashboard-controlled `readnow` cycles with live graph updates
- **Dual-Antenna Results**: ANT1 and ANT2 parsing, display, and latest result cards
- **Real-time Configuration**: Set timing, idle, battery, service, debug, and LED settings
- **Low-SoC Service Recovery**: Configure battery-triggered idle behavior and USB recovery window

## Features

### Multi-Button Control
- **Short Press**: Triggers manual RFID reading
- **Long Press**: Toggles Dashboard Mode ON/OFF
- **Configurable Timing**: Long press duration can be set from 1-30 seconds
- **Real-time Feedback**: Serial messages guide user during long press

### Dashboard Mode
- **Active**: ESP32 stays awake for USB dashboard service access and BLE advertising
- **Inactive**: Light sleep between reads, autonomous periodic RFID scanning
- **Visual Indicators**: Clear status display in dashboard

### Live View
- **Read Now**: Sends one immediate `readnow` command to the firmware
- **Auto-Read Interval**: Saved to firmware as `liveViewAutoReadIntervalMs`
- **Safe Timing**: Dashboard enforces a minimum interval for dual-antenna read windows
- **Graph Updates**: New points are parsed directly from `[RFID_RESULT]` lines

### Configuration Management
- **WiFi Settings**: SSID and password configuration
- **RFID Timing**: ON time, periodic interval, and Live View interval settings
- **Button Timing**: Long press duration configuration
- **Power and Idle**: Low-SoC threshold, battery min/max voltage, and USB recovery window
- **Diagnostics**: Verbose firmware logging and Dashboard Mode service latch
- **LED Heartbeat**: Heartbeat interval and on-duration configuration
- **Real-time Updates**: Changes applied immediately to ESP32

## Usage

### Starting the Dashboard
```bash
streamlit run rfid_dashboard_configure_lightsleep_multibutton_S3_live_2Ant.py
```

### Configuration Tab
1. **WiFi SSID**: Enter your WiFi network name
2. **WiFi Password**: Enter your WiFi password
3. **RFID ON Time**: Duration for each read window. Minimum is 3 seconds for stable dual-antenna reads
4. **Periodic Interval**: Time between automatic reads (10-3600 seconds)
5. **Long Press Timer**: Duration to hold button for dashboard mode (1-30 seconds)
6. **Live View Auto-Read Interval**: Dashboard-commanded read interval saved to device flash
7. **Stored-Reading Fetch Timeout**: Timeout for manual stored-reading range retrieval
8. **Power and Idle Mode**: Low-SoC idle, USB recovery, and voltage calibration settings
9. **Diagnostics and Runtime**: Verbose logging and Dashboard Mode service access
10. **LED Heartbeat**: Configure status heartbeat timing

### Setting Variables
1. Click "Set Variables on ESP32" to apply all settings
2. Click "Read Variables from ESP32" to load current settings
3. Confirm values in the debug expanders if needed

### Data Display
- **Read Now**: Triggers one firmware read window and highlights the latest ANT1/ANT2 results
- **Live View**: Runs repeated dashboard-commanded reads and appends new points to the graph
- **Retrieve Data**: Reads stored data for the selected date/time range
- **Download CSV**: Exports the currently displayed table
- **Clear Display**: Clears only the dashboard graph/table
- **Clear Storage**: Clears readings on the device after password confirmation

## Button Behavior

### Short Press (< configured long press time)
- Triggers immediate RFID reading
- Works when idle mode is inactive and RFID reads are allowed

### Long Press (≥ configured long press time)
- Toggles Dashboard Mode service access ON/OFF
- Real-time feedback during press:
  - 1 second: "Long press in progress..."
  - At threshold: "*** LONG PRESS DETECTED ***"
- Works from any state (awake or sleeping)

### Low-SoC Idle
- Low-SoC idle can block RFID reads when battery percentage is below the configured threshold
- The USB recovery window keeps the device available briefly so Dashboard Mode can be enabled
- Dashboard Mode keeps service access available even if the low-SoC idle condition remains active

## Technical Details

### ESP32 Firmware Requirements
- Firmware: `src/PCB/RFID_Reader_PCB1p0_Split_2Ant/RFID_Reader_PCB1p0_Split_2Ant.ino`
- Serial baud: 115200
- Required current firmware support:
  - `readnow`
  - `[RFID_RESULT] ... ts=...`
  - `get/set liveViewAutoReadIntervalMs`
  - Low-SoC and USB recovery configuration commands

### Dashboard Features
- Real-time serial communication
- Timezone-aware timestamp conversion
- Interactive data visualization
- CSV export functionality
- Password-protected storage clearing
- macOS CP210x serial open fallback handling

## Configuration Variables

| Variable | Range | Default | Description |
|----------|-------|---------|-------------|
| `longPressMs` | 1000-30000 | 5000 | Long press duration in milliseconds |
| `rfidOnTimeMs` | 3000-60000 | 5000 | RFID scanning duration |
| `periodicIntervalMs` | 10000-3600000 | 60000 | Periodic reading interval |
| `liveViewAutoReadIntervalMs` | 8000-300000 | 8000 | Dashboard Live View auto-read interval |
| `lowSocUsbRecoveryWindowMs` | 0-300000 | 15000 | USB recovery window after low-SoC idle |
| `socLowThresholdPercent` | 0-100 | 10 | Low-SoC idle threshold |
| `batteryMinVoltage` | 2.5-4.2 | 3.52 | Voltage treated as 0% for current linear SoC calculation |
| `batteryMaxVoltage` | 3.5-4.5 | 4.15 | Voltage treated as 100% for current linear SoC calculation |
| `ledHeartbeatIntervalMs` | >=1000 | 20000 | Off-time between heartbeat blinks |
| `ledHeartbeatOnMs` | 100 to below interval | 1000 | On-time for each heartbeat blink |
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

### Live View Not Updating
1. Confirm the firmware response includes `[RFID_RESULT] stored=true`
2. Confirm the tag is present for the active antenna
3. Check that `RFID ON Time` and `Live View Auto-Read Interval` satisfy the dashboard safe minimum
4. Use the General Debug Log expander to inspect `live_readnow_start`, `live_readnow_merge`, and `live_range_skipped`

## Version History

- **v1.6 (2Ant Live View)**: Added `readnow` Live View, timestamped `[RFID_RESULT]` parsing, latest ANT1/ANT2 cards, Live View interval persistence, and timeout controls
- **v1.5 (Low-SoC Service)**: Added low-SoC idle controls, USB recovery window, Dashboard Mode service latch, battery calibration, and LED heartbeat settings
- **v1.1 (Multi-Button)**: Added configurable long press timer and multi-button functionality
- **v1.0**: Initial release with basic dashboard functionality

## Support

For technical support or questions:
- **Establishment Labs**: jdelgadoq@establishmentlabs.com
- **Little Endian Engineering**: info@littleendianengineering.com

---

**CONFIDENTIAL - PROPRIETARY SOFTWARE**
© 2025 Establishment Labs. All rights reserved.

