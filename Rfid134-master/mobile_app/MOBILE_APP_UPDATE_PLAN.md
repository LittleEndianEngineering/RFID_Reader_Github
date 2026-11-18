# RFID Mobile App Update Plan

Date: 2026-07-26

## Goal

Bring the Flutter mobile app safely up to the current ESP32-S3 dual-antenna firmware and Streamlit dashboard behavior, without destabilizing the existing BLE workflows.

## Current Assessment

The existing mobile app still reflects the older BLE contract: connect to the fixed RFID BLE service, send text commands, parse stored readings without antenna metadata, show table/chart/export, and provide basic read-now/last/print/range flows.

The current firmware and dashboard are ahead of that:

- Stored serial readings include an antenna suffix (`ANT1`/`ANT2`).
- Live `readnow` emits `[RFID_RESULT] stored=true ant=ANTx ...` lines over serial.
- Dashboard supports Live View auto-read, dual-antenna latest-read cards, status/idle/recovery visibility, battery/SoC details, configuration get/set, dashboard-mode latch, LED heartbeat settings, clear storage, and richer timeout handling.
- BLE firmware currently exposes only the older subset: `status`, `debugsimple`, `print`, `print_chunk`, `range`, `range_chunk`, `last`, and `readnow`.

## Step 1: Stabilize Existing Flutter BLE Foundation

Scope:

- Add Android BLE permissions declarations.
- Add a minimal runtime permission path for Android where possible without broad new architecture changes.
- Own and cancel BLE stream subscriptions.
- Guard async callbacks and timers against `setState` after dispose.
- Stop scans and disconnect safely.
- Mark the app fully connected only after required service, command, response, and status characteristics are discovered and notifications are enabled.
- Make parsing and loading state safer for empty or terminal responses.
- Replace the stale template widget test with an app smoke test.
- Keep behavior compatible with the current firmware BLE command subset.

Verification:

- `flutter analyze`
- `flutter test`

## Step 2: Define Shared Firmware Protocol Contract

Scope:

- Decide whether the short-term protocol remains text/line based or moves to typed newline-delimited records.
- Document message types, completion markers, error markers, empty-result responses, antenna fields, status fields, and configuration responses.
- Preserve backward compatibility for legacy mobile parsing where reasonable.

Recommended minimum BLE/serial reading record:

```text
#<n>: <UTC timestamp>, <country>, <tag>, <temp or N/A>, <ANT1|ANT2>
```

Recommended live result record:

```text
[RFID_RESULT] stored=true ant=<ANT1|ANT2> reading=<n> ts=<epoch> tag=<country> <tag> temp=<value|N/A>
```

## Step 3: Add BLE Firmware Parity

Scope:

- Add BLE support for current dashboard commands where mobile needs them:
  - `get <var>`
  - `set <var> <value>`
  - `dashboardmode on`
  - `dashboardmode off`
  - `clear`
  - optionally `idlelog` / `clearidlelog`
- Add antenna suffixes to BLE stored-reading, range, and last-reading responses.
- Add explicit empty-result responses for `print` and `range`.
- Consider a `cancel` command or request/session id for long data transfers.

## Step 4: Update Mobile Protocol Model And Parser

Scope:

- Introduce typed models for readings, device status, config variables, transfer state, and command responses.
- Parse both legacy 4-field readings and current 5-field antenna readings.
- Parse `[RFID_RESULT]` records for Read Now and Live View.
- Support signed temperatures and `N/A`.
- Buffer BLE notifications into line-oriented messages instead of assuming one complete logical response per notification.
- Dedupe by timestamp/country/tag/temperature/antenna, not reading number alone.

## Step 5: Match Dashboard Functionality In Mobile UI

Scope:

- Status cards: dashboard mode, idle mode, idle reason, recovery countdown, battery/SoC.
- Dual-antenna latest-read cards for `ANT1` and `ANT2`.
- Antenna-aware table, CSV export, and chart grouping.
- Configuration screen for RFID on time, periodic interval, Live View interval, long press, low-SoC settings, battery calibration, verbose logging, dashboard mode, and LED heartbeat timing.
- Clear display vs clear device storage, with confirmation for destructive storage clear.
- Live View auto-read using `readnow` and `[RFID_RESULT]` records.
- Quick actions should keep `Read Now` as the dual-antenna read and add `Read ANT1` / `Read ANT2` buttons that send `readant 1` and `readant 2`.

## Step 6: End-To-End Verification

Test scenarios:

- Android scan/connect/disconnect/reconnect.
- iOS/macOS BLE connect and notification behavior.
- Empty storage.
- Empty range.
- Large paginated history.
- Dual-antenna Read Now.
- Low-SoC blocked read.
- Config get/set roundtrip.
- Clear storage confirmation.
- Timeout/abort recovery.
- CSV export and chart save.

## Sequencing Note

Do not build the full current-dashboard mobile UI until BLE firmware exposes the required status/config/antenna data. Otherwise the app will display controls the device cannot answer over BLE.
