# Mobile BLE Protocol Contract

Date: 2026-08-02

## Purpose

Define the BLE command and response contract that the ESP32-S3 dual-antenna firmware and Flutter mobile app should share before implementing firmware BLE parity and mobile parser updates.

The original planning baseline is preserved below. The implementation update describes the paired firmware/mobile fixes now present in the working tree.

## Implementation Update — 2026-11-13

- After enabling response notifications, the mobile app sends `protocol`. Updated firmware replies `RFID_PROTOCOL_V2\n`. This identifies newline-framed responses, explicit manual-read completion, and `readant` support. Older firmware returns its existing unknown-command response; the app keeps legacy notification parsing and disables individual-antenna controls.
- Every updated firmware response ends in `\n`. Payloads are split to the negotiated MTU minus 3 bytes, capped at 180 bytes. The app buffers raw bytes through the newline so splitting UTF-8 or the antenna suffix cannot change a record. Legacy notifications retain their original line order.
- BLE `readnow` starts with `[MANUAL] Starting RFID read window (<ms>ms)` and ends with `[MANUAL] RFID read complete count=<n>`. A directed read uses `Starting ANT<1|2> RFID read window (<ms>ms)` and `[MANUAL] ANT<1|2> RFID read complete count=<n>`.
- Individual antenna success/no-tag messages are progress. Updated mobile code collects both antenna results until the command completion marker, including any recovery attempt. Duplicate structured/legacy notifications for the same antenna are kept once per manual command.
- Idle-blocked and unknown-command responses terminate the request with their actual reason. The timeout includes configured read windows plus recovery and BLE overhead; any results received before a timeout are preserved.
- With older firmware, the app uses antenna `Power OFF` messages as a best-effort completion fallback. Older firmware has no unambiguous end-of-command marker, so recovery cycles and fragmented unframed records remain inherently limited; use the updated pair for reliable completion/framing.
- Legacy history timestamps accept unpadded month/day/hour/minute/second values. Legacy history records without antenna metadata still default to ANT1.
- These fixes do not implement the planned mobile configuration/status screens or Live View UI. Dashboard individual-antenna buttons are available only after a serial `protocol` probe returns `RFID_PROTOCOL_V2`, and are disabled while Live View runs. The probe is cached per connection; reconnect after flashing firmware to refresh it. Actual antenna operation still requires device verification.

## Implementation Update — 2026-11-17 (mobile 1.0.0-dev.1)

- New **Device** tab: reader status cards (battery, stored readings, dashboard/idle mode, low-battery idle, USB recovery, LED) from `status`, and a settings list using `get <var>` / `set <var> <value>` for the 12 dashboard settings (all except `dashboardModeActive`).
- The app edits seconds/volts/percent and sends firmware units. Limits match the USB dashboard, because firmware does not range-check `rfidOnTimeMs`, `periodicIntervalMs` or `longPressMs`. Each `set` must reply `OK` and is confirmed by a fresh `get`.
- Status works with any firmware; settings are shown only after `RFID_PROTOCOL_V2`. Requests run one at a time and are refused while a read or history transfer is running.
- **Live View** (Filter & Graph tab): repeats `readnow` like the USB dashboard. It waits `liveViewAutoReadIntervalMs` after each read, kept between 8 and 300 s and at least `2 × rfidOnTimeMs + 2 s`. It pauses on a missing completion marker or a blocked (idle) read, and after two failed reads in a row. While it runs, manual reads, history and Device-tab commands are disabled. Readings are added to the table and chart.
- **Latest reading cards** for ANT1 and ANT2, updated by Read Now, Read ANTx and Live View.
- The app now notices when the reader drops the BLE link, stops the current task and keeps the readings it already received.
- Still not implemented: Dashboard Mode toggle, clear device storage. Verified by unit/widget tests only, not on a real phone and board.

## Original Planning Baseline

## Current Confirmed State

Android and iOS both build, run, connect over BLE, and receive `status` / `debugsimple` responses.

Reading retrieval is inconsistent because the mobile app still parses the older BLE reading format, while the current firmware/dashboard behavior has moved to dual-antenna records.

Current BLE service:

```text
Device name: RFID Reader
Service UUID: 4fafc201-1fb5-459e-8fcc-c5c9c331914b
Command characteristic: beb5483e-36e1-4688-b7f5-ea07361b26a8
Response characteristic: beb5483e-36e1-4688-b7f5-ea07361b26a9
Status characteristic: beb5483e-36e1-4688-b7f5-ea07361b26aa
```

Current BLE commands implemented in firmware:

```text
status
debugsimple
print
print_chunk <chunk_index>
range <start_epoch_utc> <end_epoch_utc>
range_chunk <start_epoch_utc> <end_epoch_utc> <chunk_index>
last
readnow
readant 1
readant 2
```

Current serial-only commands used by the dashboard but not yet fully exposed over BLE:

```text
dashboardmode on
dashboardmode off
get <var>
set <var> <value>
clear
idlelog
clearidlelog
summary
printconfig
time
sleepstats
resetconfig
```

## Current Format Mismatch

Serial stored readings include antenna metadata:

```text
#<n>: <YYYY-MM-DD HH:MM:SS>, <country>, <tag_id>, <temperature|N/A>, <ANT1|ANT2>
```

Current BLE stored, range, and last-reading responses still omit antenna metadata:

```text
#<n>: <YYYY-M-D H:M:S>, <country>, <tag_id>, <temperature|N/A>
```

Current live `readnow` serial output includes explicit antenna result records:

```text
[RFID_RESULT] stored=true ant=ANT<1|2> reading=<n> ts=<epoch_utc> tag=<country> <tag_id> temp=<value°C|N/A>
```

The dashboard already parses both legacy 4-field readings and newer 5-field antenna readings. The mobile app should gain the same backward-compatible parser behavior.

## Target Reading Record

Firmware BLE and serial should converge on this stored-reading line:

```text
#<n>: <YYYY-MM-DD HH:MM:SS>, <country>, <tag_id>, <temperature|N/A>, <ANT1|ANT2>
```

Rules:

- Timestamp is UTC.
- Timestamp should be zero-padded when practical: `YYYY-MM-DD HH:MM:SS`.
- `country` is a decimal integer.
- `tag_id` is decimal with no separators.
- `temperature` is either a signed/unsigned decimal value with `°C`, or `N/A`.
- `ANT1` and `ANT2` are the only antenna labels.
- Stored records without antenna metadata must be interpreted by the mobile app as `ANT1` for backward compatibility.

Examples:

```text
#1: 2026-08-01 21:13:05, 999, 141004265912, 24.86°C, ANT1
#2: 2026-08-01 21:13:09, 999, 141004265913, N/A, ANT2
```

## Target Live Read Result

`readnow` should emit one `[RFID_RESULT]` line per stored antenna result.

```text
[RFID_RESULT] stored=true ant=<ANT1|ANT2> reading=<n> ts=<epoch_utc> tag=<country> <tag_id> temp=<value°C|N/A>
```

Rules:

- `stored=true` means the reading was committed to flash.
- `ant` is required.
- `reading` is the global stored reading number.
- `ts` is required and is Unix UTC seconds.
- `tag` contains country and tag id separated by one space.
- `temp` is `N/A` or a Celsius value.
- A single `readnow` command may emit zero, one, or two `[RFID_RESULT]` lines.
- `readant 1` and `readant 2` emit zero or one `[RFID_RESULT]` line for the selected antenna only.

Example:

```text
[RFID_RESULT] stored=true ant=ANT1 reading=42 ts=1785633185 tag=999 141004265912 temp=24.86°C
[RFID_RESULT] stored=true ant=ANT2 reading=43 ts=1785633190 tag=999 141004265913 temp=N/A
```

## Target Transfer Markers

All commands that return stored readings must be line-oriented. The mobile app must not assume one BLE notification equals one logical line.

Full history:

```text
---BEGIN_READINGS---
Printing <count> stored readings (chunk <current>/<total>):
#...
---CHUNK_COMPLETE---
```

Subsequent history chunk:

```text
Chunk <current>/<total> (readings <start>-<end>):
#...
---CHUNK_COMPLETE---
```

Final history chunk:

```text
#...
---END_READINGS---
```

Range first chunk:

```text
Found <count> readings in range.
---BEGIN_READINGS---
Range readings (chunk <current>/<total>):
#...
---CHUNK_COMPLETE---
```

Range final chunk:

```text
#...
---END_READINGS---
=== Range Request End ===
```

Empty full-history result should be explicit and terminal:

```text
---BEGIN_READINGS---
Printing 0 stored readings:
---END_READINGS---
```

Empty range result should be explicit and terminal:

```text
Found 0 readings in range.
---BEGIN_READINGS---
---END_READINGS---
=== Range Request End ===
```

## Target Status Response

`status` must remain human-readable for dashboard/mobile compatibility, but should include all fields needed by the mobile app.

Minimum BLE status response:

```text
Dashboard Mode: ACTIVE|INACTIVE
Idle mode: ACTIVE|INACTIVE
Idle reason: <reason>
Low SoC idle: ENABLED|DISABLED
Low SoC USB recovery: ACTIVE|INACTIVE
USB recovery remaining: <seconds>s
```

Recommended additional status lines:

```text
Reading count: <count>
Battery voltage: <voltage|N/A>
Battery SoC: <percent|N/A>
LED status: <status>
```

Mobile parser rules:

- Accept both `[DASHBOARD] Dashboard Mode: ...` and `Dashboard Mode: ...`.
- Accept both `[IDLE] Mode: ...` and `Idle mode: ...`.
- Treat unknown extra lines as non-fatal.

## Target Config Commands

BLE should support the dashboard-critical subset of serial config commands:

```text
get rfidOnTimeMs
get periodicIntervalMs
get liveViewAutoReadIntervalMs
get longPressMs
get socLowIdleEnabled
get lowSocUsbRecoveryWindowMs
get socLowThresholdPercent
get batteryMinVoltage
get batteryMaxVoltage
get verbose
get dashboardModeActive
get ledHeartbeatIntervalMs
get ledHeartbeatOnMs
set rfidOnTimeMs <ms>
set periodicIntervalMs <ms>
set liveViewAutoReadIntervalMs <ms>
set longPressMs <ms>
set socLowIdleEnabled <0|1>
set lowSocUsbRecoveryWindowMs <ms>
set socLowThresholdPercent <percent>
set batteryMinVoltage <volts>
set batteryMaxVoltage <volts>
set verbose <0|1>
set dashboardModeActive <0|1>
set ledHeartbeatIntervalMs <ms>
set ledHeartbeatOnMs <ms>
dashboardmode on
dashboardmode off
```

For compatibility with the current dashboard, `get` responses should keep the existing marker convention:

```text
<GET_<NAME>_BEGIN>
<value>
<GET_<NAME>_END>
```

`set` responses should be:

```text
OK
```

or:

```text
ERROR: <message>
```

## Target Clear Commands

BLE should support storage clear only behind a confirmed destructive UI action in the mobile app.

Command:

```text
clear
```

Successful response:

```text
Cleared
```

The app must distinguish:

- Clear display: local UI/table/chart only.
- Clear device storage: sends `clear` and requires confirmation.

## Target Error Responses

All command errors should be line-oriented and start with `ERROR:` unless they are legacy idle/manual read status lines.

Examples:

```text
ERROR: Invalid command
ERROR: Invalid chunk index <n>
ERROR: Invalid range command format
ERROR: Failed to open FLASH file
[IDLE] Manual read blocked: <reason>
[RFID][ANT1] No tag detected during window
[RFID][ANT2] Module hang detected, aborting read
```

Mobile behavior:

- Show user-facing errors for `ERROR:` lines.
- Treat `[IDLE] Manual read blocked` as a blocked read, not a transport failure.
- Treat `No tag detected during window` as a valid read completion with no tag.
- Do not leave loading indicators active after terminal error or terminal empty markers.

## BLE Transport Rules

BLE response data must be treated as a stream of UTF-8 text, not as complete messages per notification.

Firmware rules:

- Send newline-delimited logical records whenever practical.
- Keep notification payloads below the safe MTU payload size.
- Keep the current 2-reading batch approach acceptable, but terminate each reading line with `\n`.
- Preserve `---CHUNK_COMPLETE---` and `---END_READINGS---` as standalone lines.

Mobile rules:

- Buffer notifications until newline boundaries are available.
- Parse multiple logical lines from one notification.
- Handle one logical line split across multiple notifications.
- Ignore empty lines.
- Keep unknown informational lines in the debug response log without breaking transfer state.

## Backward Compatibility

Mobile parser must support both:

```text
#<n>: <timestamp>, <country>, <tag_id>, <temperature|N/A>
#<n>: <timestamp>, <country>, <tag_id>, <temperature|N/A>, <ANT1|ANT2>
```

Legacy 4-field records default to:

```text
Antenna = ANT1
```

This preserves old stored records and older firmware BLE responses while enabling the dual-antenna firmware.

## Step 3 Firmware Checklist

- Add antenna suffixes to BLE `print`, `print_chunk`, `range`, `range_chunk`, and `last` reading lines.
- Add `[RFID_RESULT]` notifications over BLE for successful `readnow` stored results, matching serial output.
- Add explicit empty-result terminal blocks for `print` and `range`.
- Add BLE handlers for dashboard-mode, config get/set, clear, and optionally idle logs.
- Keep legacy command names intact.
- Keep current BLE UUIDs intact.
- Avoid changing flash record layout; antenna is already available from `RfidReading.flags`.

## Step 4 Mobile Checklist

- Add a line-buffered BLE response parser.
- Parse legacy and antenna-aware stored-reading lines.
- Parse `[RFID_RESULT]` lines for Read Now and Live View.
- Track antenna in reading model, table, chart grouping, CSV export, and latest-read cards.
- Dedupe using timestamp, country, tag, temperature, and antenna.
- End loading on explicit empty blocks, `ERROR:` lines, and `---END_READINGS---`.
- Keep status/debug behavior working while extending parser coverage.

## Deferred Decisions

- Whether to replace human-readable text lines with typed JSON/NDJSON later.
- Whether BLE long transfers should gain a request id/session id.
- Whether to add a `cancel` command for active transfers.
- Whether `ssid` and `password` config should be exposed over BLE; for now they are not recommended for mobile unless there is a clear product requirement.
