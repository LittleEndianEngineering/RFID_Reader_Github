# RFID Reader Mobile App Code Review Findings

Date reviewed: 2026-07-25  
Scope: Read-only review of the current Flutter mobile app before comparing against the newer device firmware.

## Functionality Summary

The current app is a Flutter BLE dashboard for an ESP32-S3 RFID reader. Most behavior lives in `rfid_reader_app/lib/main.dart`.

Main user workflows:

- Scan for BLE devices whose advertised name contains `RFID Reader`.
- Connect to a fixed ESP32 BLE service and discover command, response, and status characteristics.
- Send plain-text commands to the firmware: `status`, `debugsimple`, `readnow`, `last`, `print`, `range`, `print_chunk`, and `range_chunk`.
- Listen for text notifications from the response/status characteristics.
- Parse live/manual RFID reads and historical readings.
- Retrieve all readings or date/time-filtered readings, including chunked pagination.
- Display readings in a table and plot temperature over time with `fl_chart`.
- Export parsed readings to CSV through the share sheet.
- Save the temperature chart image to the photo gallery.

## Firmware Contract Assumptions

The app currently assumes the firmware exposes:

- Service UUID: `4fafc201-1fb5-459e-8fcc-c5c9c331914b`
- Command characteristic UUID: `beb5483e-36e1-4688-b7f5-ea07361b26a8`
- Response characteristic UUID: `beb5483e-36e1-4688-b7f5-ea07361b26a9`
- Status characteristic UUID: `beb5483e-36e1-4688-b7f5-ea07361b26aa`
- Device name containing `RFID Reader`
- UTF-8 text responses sent as complete logical messages per BLE notification
- Readings formatted like `#1: 2025-10-22 04:29:52, 506, 1234567890, 37.20°C`
- Temperature field formatted as either a positive decimal ending in `°C` or exactly `N/A`
- Firmware stores timestamps in UTC, and range commands accept UTC Unix epoch seconds
- Historical retrieval markers such as `---BEGIN_READINGS---`, `---CHUNK_COMPLETE---`, and `---END_READINGS---`
- Count headers such as `Found X readings in range` and `Printing X stored readings`
- Manual read status strings such as `Tag detected and stored` and `No tag detected during window`

Any newer firmware change to UUIDs, command names, chunk protocol, response delimiters, timestamp format, temperature format, or tag/country field shape will require app-side updates.

## Findings

### High: Android BLE permissions are missing

File: `rfid_reader_app/android/app/src/main/AndroidManifest.xml`

The Android manifest has no BLE or location permissions. Scanning and connecting are likely broken on Android 12+ and may also fail on older Android versions depending on Bluetooth/location behavior.

Relevant code:

- `rfid_reader_app/lib/main.dart`: `_startScan()` calls `FlutterBluePlus.startScan(...)`.
- `rfid_reader_app/README.md` says Android BLE permissions are handled automatically, but the manifest does not declare them.

Likely required permissions for modern Android include `BLUETOOTH_SCAN`, `BLUETOOTH_CONNECT`, and possibly legacy `BLUETOOTH`, `BLUETOOTH_ADMIN`, and `ACCESS_FINE_LOCATION` with SDK guards.

### High: BLE stream subscriptions are not cleaned up

File: `rfid_reader_app/lib/main.dart`

The app creates listeners without storing/canceling `StreamSubscription`s:

- `FlutterBluePlus.adapterState.listen(...)`
- `FlutterBluePlus.scanResults.listen(...)`
- `characteristic.lastValueStream.listen(_handleESP32Response)`
- `characteristic.lastValueStream.listen(_handleESP32Status)`

Repeated scans/reconnects can stack duplicate handlers. A disposed widget can also still receive callbacks that call `setState`, causing runtime exceptions.

### High: Disconnect during dispose can call setState after disposal

File: `rfid_reader_app/lib/main.dart`

`dispose()` calls `_disconnect()`, but `_disconnect()` is async and calls `setState()` after `await connectedDevice!.disconnect()`. Because `dispose()` cannot await this safely, the widget may be unmounted by the time the disconnect completes.

This can cause `setState() called after dispose()` during normal navigation, app close, or hot reload flows.

### Medium: App marks connected before validating required characteristics

File: `rfid_reader_app/lib/main.dart`

`_connectToDevice()` sets `isConnected = true` immediately after `device.connect()`, before confirming that the expected service and characteristics exist. If the newer firmware changes UUIDs, characteristic properties, or the advertised service, the UI can show "Connected" while commands silently do nothing because `commandCharacteristic` remains null.

The connect path should distinguish:

- BLE link connected
- Expected RFID service discovered
- Required command/response/status characteristics available
- Notifications successfully enabled

### Medium: Response parsing is tightly coupled to fragile text formats

File: `rfid_reader_app/lib/main.dart`

Parsing depends on literal text markers and regexes. The current parser assumes notifications arrive as complete UTF-8 messages and does not maintain a receive buffer for split packets. BLE notifications may split, merge, or partially deliver logical messages depending on MTU and platform.

Fragile assumptions include:

- Response starts with `#` for reading lines.
- Temperature is positive decimal only; negative temperatures or signed values are not matched.
- Country and tag are numeric only.
- Timestamp must look like `YYYY-MM-DD HH:MM:SS`.
- `°C` must be present for temperature readings.
- Chunk headers and markers contain exact words/case.

For the next firmware iteration, consider moving to a framed protocol such as newline-delimited records, JSON lines, length-prefixed messages, or explicit typed packets.

### Medium: Empty result queries can leave loading active

File: `rfid_reader_app/lib/main.dart`

For `Found 0 readings in range` or `Printing 0 stored readings`, `_totalExpectedReadings` becomes `0`, `_isLoadingReadings` becomes true, and the timeout check does not abort because `currentCount < _totalExpectedReadings` is false. If firmware does not send `---END_READINGS---`, the app can remain in a loading state.

This is important when validating firmware behavior for empty history or empty date ranges.

### Medium: Stop/abort only clears app state, not firmware transfer

File: `rfid_reader_app/lib/main.dart`

`_abortDataRetrieval()` clears local state but explicitly does not send a cancel command to the ESP32. If the firmware continues sending notifications, the app can still process late data depending on state flags and response type. For large histories, this may create confusing UI recovery after a stop.

The newer firmware could benefit from a `cancel`/`abort` command, transfer ID, or request sequence number.

### Medium: Default widget test is stale and should fail

File: `rfid_reader_app/test/widget_test.dart`

The test pumps `const MyApp()`, but the app defines `RFIDReaderApp`. This default counter test is still from a template and does not match the app.

Expected issue:

- `MyApp` is undefined.
- The counter expectations and `Icons.add` interaction do not apply to this app.

### Low: CSV generation does not escape fields

File: `rfid_reader_app/lib/main.dart`

CSV rows are generated by interpolating values with commas. If any future tag, country, timestamp, or firmware field contains a comma, quote, newline, or localized text, exported CSV will become malformed.

This is not a blocker for the current numeric field format but is worth fixing if firmware output becomes richer.

### Low: Debug logging is very verbose

File: `rfid_reader_app/lib/main.dart`

The app prints full BLE responses and detailed parse/debug logs. This is helpful during firmware bring-up but can expose tag IDs/timestamps in logs and degrade performance during large history transfers.

Consider gating verbose logs behind a debug flag or build mode before release/testing with real data.

### Low: Release Android config is still template/default

File: `rfid_reader_app/android/app/build.gradle.kts`

The Android application ID remains `com.example.rfid_reader_app`, and release builds use the debug signing config. This is fine for development, but not for production distribution.

## Recommended Next Review Focus Against New Firmware

When switching to the current firmware branch, compare these items first:

- BLE service UUID and all characteristic UUIDs.
- Characteristic properties: write vs write without response, notify/indicate.
- Device advertised name and advertisement payload.
- MTU/chunk size expectations.
- Command vocabulary and argument formats.
- Whether responses are newline-delimited, marker-delimited, JSON, binary, or still free-form text.
- Whether historical reads support cancellation or transfer/session IDs.
- Timestamp source and timezone: UTC, local RTC, epoch seconds, milliseconds, or ISO 8601.
- Reading fields: tag ID type, country format, temperature signedness, precision, missing-value representation.
- Empty result behavior: ensure an explicit completion response is always emitted.
- Error response vocabulary and whether errors are machine-readable.

## Suggested App-Side Direction

Before large firmware/app integration work, it would be useful to separate:

- BLE connection management
- Firmware protocol commands/responses
- Reading model/parsing
- UI state/rendering

The current single-file implementation makes firmware protocol changes harder than necessary because UI state, BLE transport, parsing, pagination, export, and charting all share one stateful widget.
