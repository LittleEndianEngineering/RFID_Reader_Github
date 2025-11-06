# RFID Reader Mobile App

A Flutter mobile application for connecting to and managing ESP32-S3 RFID Reader devices via Bluetooth Low Energy (BLE).

## Features

- **BLE Connectivity**: Connect to ESP32-S3 RFID Reader devices
- **Data Visualization**: Temperature charts with filtering capabilities
- **Data Export**: CSV export and PNG image export
- **Cross-Platform**: Supports iOS, Android, macOS, and Web
- **Real-time Data**: Live temperature monitoring and data retrieval

## Requirements

- Flutter SDK 3.0+
- Dart 3.0+
- Xcode (for iOS/macOS development)
- Android Studio (for Android development)

## Dependencies

- `flutter_blue_plus: ^1.12.9` - BLE connectivity
- `fl_chart: ^0.68.0` - Chart visualization
- `path_provider: ^2.1.1` - File system access
- `share_plus: ^7.2.1` - File sharing

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   flutter pub get
   ```

3. Run the app:
   ```bash
   flutter run
   ```

## Platform-Specific Setup

### macOS
- Requires Xcode for native development
- BLE permissions are configured in `macos/Runner/Info.plist`

### iOS
- Requires Xcode and iOS deployment target 11.0+
- BLE permissions configured automatically

### Android
- Requires Android SDK and minimum API level 21
- BLE permissions are handled automatically

## Usage

1. **Connect**: Use the BLE scan button to find and connect to RFID Reader devices
2. **Dashboard**: Send commands to the ESP32 (status, debug, last reading, print all)
3. **Filter & Graph**: Set date/time ranges and visualize temperature data
4. **Export**: Save data as CSV or charts as PNG images

## BLE Service Configuration

The app connects to ESP32-S3 devices with the following BLE service:
- **Service UUID**: `4fafc201-1fb5-459e-8fcc-c5c9c331914b`
- **Command Characteristic**: `beb5483e-36e1-4688-b7f5-ea07361b26a8`
- **Response Characteristic**: `beb5483e-36e1-4688-b7f5-ea07361b26a9`
- **Status Characteristic**: `beb5483e-36e1-4688-b7f5-ea07361b26aa`

## Development

Built with Flutter 3.0+ and follows Material Design 3 principles.

## License

Proprietary - Establishment Labs