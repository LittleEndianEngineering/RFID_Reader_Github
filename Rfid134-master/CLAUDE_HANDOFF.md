# Claude Code handoff: customer firmware/dashboard and future mobile development

## Versioning and follow-up delivery setup (2026-11-17)

Read `VERSIONING.md` first. `release_records/delivery-v6.json` pins the simplified
v6 ZIP (applications, original long-named reference `.py`, short README), exact
firmware/dashboard commits and artifact hashes. `release_records/development-2026-11-17.json`
identifies the separate uncommitted firmware/original-dashboard/mobile experiments;
it is not a source backup or compatibility approval. Firmware on customer boards
remains **1.5 / main_2Ant / dbf098dbd869d88fe63274aad421fdba6d7ed18a**.
Local firmware still has a 1.5 header despite different bytes; mobile declares
1.0.0+1 but has no customer release. Both local firmware/dashboard and mobile
compatibility must be tested before promotion. No component source or executable
was changed by the versioning setup.

`tools/check_delivery.py` verifies the committed firmware/customer build identities
and canonical artifact hashes. Add `--package 'dashboard/deliverables/deliverable v6/rfid_deliverable_v6.zip'`
to check the exact customer ZIP. `--working-tree` is expected to fail here because
the local firmware is experimental; the default check uses committed objects.
See `release_records/feedback-template.md` for issue/acceptance records. v6 is
prepared; customer sending/acceptance is not assumed. New customer feedback fixes
get a new component version as needed and a new immutable delivery ID (e.g. v6.1).
Tags are proposed in the record, not created/pushed by this setup. These versioning
files are prepared locally for review; no dirty experiments were committed, no
branch was switched and no remote was changed.

## Organized 2026 customer release (2026-11-17)

The user requested a clean customer development/release tree and a clearly identified “Final deliverable for RFID Reader 2026” commit, including executable packages and the original long dashboard filename.

**Current customer source:** `dashboard/customer/src/rfid_dashboard_configure_lightsleep_multibutton_S3_live_2Ant.py`. Dashboard version **6.2.1** is a packaging/source-layout revision; executable dashboard logic is AST-identical to 6.2.0 after excluding the updated module documentation. `app.py` is no longer a separate customer implementation. Helpers/logo live alongside the source; launcher, build tools, pinned requirements and release assembler are under `packaging/`; regression tests are under `tests/`.

**Firmware target is unchanged:** delivered header version **1.5**, branch **`main_2Ant`**, exact commit **`dbf098dbd869d88fe63274aad421fdba6d7ed18a`**, PCB v2/v3. Source comments, commit message and release manifests explicitly record all three identities. The release branch firmware tree matches that commit. Local experimental firmware/mobile work remains separate and untouched.

**Versioned customer delivery:** `dashboard/customer/releases/rfid-reader-2026/`. It has one package per platform (Windows x64, Mac ARM64/Intel, Linux x64), one immutable source snapshot using the long filename, release manifest, checksums, and per-platform build/test evidence. Packages are stored in Git LFS; source/JSON/checksums use normal Git. Linux's package exceeds GitHub's normal file-size limit. Developers should install Git LFS and run `git lfs pull` after cloning.

**Branch:** `customer/final-deliverable-rfid-reader-2026`; release-tree commit `0f6ea3f93c688f446b8462d2d49f5758fea09410`. Native binaries were built from source commit `4f1f01e22cb9411a7b76aa0c45fdf358053cc1a1`. These are intentionally different commits: the latter builds the binaries; the release-tree commit adds those exact artifacts and evidence. The actual original working copy stays on its pre-existing branch with unrelated dirty changes preserved; the customer release was committed from an isolated checkout.

**Build pipeline:** Git-root `.github/workflows/build-customer-dashboard.yml` consolidates all four native targets. Mac checks now execute the actual app via Finder/LaunchServices. Native UI/Tk, server/assets/shutdown and all 22 regression/release-integrity tests passed. Windows/Intel Mac/Linux were built in GitHub Actions run 44104997815. Apple Silicon was built and tested locally from the same source commit while its hosted runner remained queued; its build manifest explicitly records that origin. See the per-target manifests for provenance and validation evidence. Windows Explorer launch, Linux file-manager launch and physical customer USB acceptance on PCB v2/v3 remain pending; the “Final deliverable” label does not claim those checks passed. Windows is unsigned; Mac builds are ad-hoc signed without notarization.

**Previous folder backup:** `/private/tmp/rfid_customer_before_2026_cleanup`. It contains the entire pre-cleanup customer tree, including previous 6.2.0 executable packages, extracted apps, duplicate source copies and local launch evidence. Previous workflows were retained there as `previous-workflows/`. Do not confuse this local backup or ignored `build/`/`dist/` with the new versioned delivery. The installed working Mac app at `~/Applications/RFIDDashboard.app` remains the earlier 6.2.0 copy until deliberately updated.

The release commit was pushed successfully (all four LFS objects uploaded) and fetched into the original checkout as `origin/customer/final-deliverable-rfid-reader-2026`; its current working branch and unrelated dirty files were preserved. Git LFS is already installed at `/usr/local/bin/git-lfs` and its local repository hooks were initialized. Codex non-login shells may need `/usr/local/bin` added to PATH. The disposable isolated build checkout and duplicate CI downloads were removed after verifying the published commit and local release checksums; the previous customer-folder backup remains available at the path above.

The sections below document earlier snapshots; their `app.py`, flat packaging and `dist/` delivery paths are superseded by this organization.

## Local macOS Finder launch follow-up (2026-11-17)

The user reported Finder's generic “RFIDDashboard.app can’t be opened” dialog. Reproduced `open -n` failure `-10810`; system logs showed RunningBoard `NSPOSIXErrorDomain Code=22`, “Unable to load a valid LSApplicationProxy.” The Apple Silicon bundle had executable permissions, matched the Mac architecture/OS requirement, and passed deep/strict signature verification. Its direct executable self-test passed on this Mac.

A clean copy at an ASCII temporary path passed Finder-style `open -n -W ... --args --self-test` launch. Installed that same Apple Silicon build at **`/Users/oscarpauly/Applications/RFIDDashboard.app`**, preserving project copies, and verified Finder-style launch, actual normal launcher startup, native Tk/actual dashboard UI diagnostic, loopback server health (`ok`), and frontend HTML on macOS 15.7.1 arm64. The running application was left open for the user. Evidence: `dashboard/customer/dist/macos-arm64/local-launch-verification.json`.

Both NFC and NFD forms of the original project path subsequently passed diagnostic launch, so do not claim the original failure was conclusively caused by Unicode paths, missing notarization, architecture, or a dashboard bug. The exact initial macOS registration-state cause remains uncertain. The prior CI checks invoked the frozen executable directly and did not exercise Finder/LaunchServices; native executable checks alone are insufficient evidence of double-click launch. For future Mac release checks include Finder-style launch after extraction/installation. Use the installed user-Applications copy on this Mac.

## macOS and Linux executables (2026-11-16 update)

The customer dashboard now also has native macOS 15+ Apple Silicon and Intel app bundles, and a Linux x64 standalone binary built/tested on Ubuntu 22.04 (glibc 2.35). Packages, extracted executables, README instructions, dashboard `.py` reference/helper/logo, source/dependency manifest, SHA-256 files, and test reports are in:

- `dashboard/customer/dist/macos-arm64/`
- `dashboard/customer/dist/macos-x64/`
- `dashboard/customer/dist/linux-x64/`

Open the extracted macOS `RFIDDashboard.app`, or the extracted Linux `RFIDDashboard` binary. Python is bundled. macOS bundles have ad-hoc integrity signatures, without Developer ID/notarization. Linux requires a desktop display/default browser and USB serial permissions. See each README for operating requirements.

Dashboard source remains version 6.2.0, SHA-256 `53f75ea3de28fdf8a5d5310512ce663d18055dffbe5ed6de6f265728b729d2ae`, exactly the dashboard inside the earlier Windows delivery. Firmware remains `main_2Ant` / `dbf098dbd869d88fe63274aad421fdba6d7ed18a`. The previously saved Windows executable/reference and experimental firmware/mobile work were preserved.

Native packaging adds platform-standard runtime directories, safe system browser library paths on Linux, macOS `.app` bundling, and native Tk UI verification on all platforms. The native build workflow is `.github/workflows/build-customer-dashboard-unix.yml` at the Git root; use `build_native.py --target macos-arm64|macos-x64|linux-x64` on the matching native platform with build dependencies installed. All 18 regression tests plus frozen actual dashboard/native Tk, server health/assets and shutdown/port-release tests passed on each native runner. The downloaded archives and binary architecture/hashes were verified locally, and both extracted macOS bundle signatures were verified. Physical PCB v2/v3 acceptance testing remains pending.

Build identities:

- **macos-arm64**: commit `84a89d24f33eea7890d9f0d73f8288407dbf22fb`, run <https://github.com/LittleEndianEngineering/RFID_Reader_Github/actions/runs/44018649519>, artifact `14300610231`; package SHA-256 `83a7151838175766ca3c5ca3d695cba205c8f66c25fa368e0e41ca82956175e1`.
- **macos-x64**: commit `84a89d24f33eea7890d9f0d73f8288407dbf22fb`, run <https://github.com/LittleEndianEngineering/RFID_Reader_Github/actions/runs/44018649519>, artifact `14299947661`; package SHA-256 `a10e3dc83eb838fd53d26c6c04bfc6db6ea3c5867836a0208f05a663d64fbb65`.
- **linux-x64**: commit `84a89d24f33eea7890d9f0d73f8288407dbf22fb`, run <https://github.com/LittleEndianEngineering/RFID_Reader_Github/actions/runs/44018649519>, artifact `14299464639`; package SHA-256 `db7b981341c2cb66770a4802dd87c5e3653fa2ff74400b77b1f2db94f8c1c29b`.

This extends the earlier Windows-only package section below.

## Customer dashboard 6.2.0 package (2026-11-16 update)

The user chose to keep the delivered firmware unchanged and prepare a customer dashboard based on the improved local source. **Use `dashboard/customer/app.py` for this customer track.** The original `dashboard/src/rfid_dashboard_configure_lightsleep_multibutton_S3_live_2Ant.py` and experimental firmware/mobile files were preserved.

- Customer firmware remains `main_2Ant` / `dbf098dbd869d88fe63274aad421fdba6d7ed18a`, PCB v2/v3. The build branch firmware tree is identical to that baseline.
- Customer source/build branch: `customer/windows-dashboard-6.2.0`, commit `7679295b1f6b32684c90e877a70697a764dd56f9`. Only customer package/build files were uploaded with explicit user authorization; neither the main branch nor `main_2Ant` was changed.
- Windows build and verification: https://github.com/LittleEndianEngineering/RFID_Reader_Github/actions/runs/44016207596.
- Local single-file Windows x64 application: `dashboard/customer/dist/RFIDDashboard.exe` (double-click to launch browser and native control window; no customer Python setup). SHA-256: `c121d5b474deb225bb973fa9fbc251f4e46c1f38b4dadfcc1a14889a6524fb3d`.
- All 15 regression tests, frozen actual UI rendering, bundled native Tk initialization, local Streamlit server health, bundled JS/CSS checks, and server shutdown/port release passed on Windows. Reports/dependency manifest are alongside the executable.
- The customer dashboard removes unsupported individual-antenna controls/capability probing/experimental firmware prompt. It retains dual Read Now, Live View, configuration ACK/mode protections and recovery-aware timeout, preserves partial reads and prevents further commands on the pending connection until completion is drained, recognizes empty history, and rejects reported flash-write failures.
- Physical tests on shipped PCB v2/v3 and the customer's Windows machine remain pending. The executable has no publisher signature. USB adapter drivers remain a Windows/device requirement.
- Build via `dashboard/customer/build_windows.ps1` on Windows Python 3.11 x64, or the Git-root `.github/workflows/build-customer-dashboard-windows.yml`; see `dashboard/customer/README.md`.

The detailed comparison below is the earlier source snapshot. Its discussion of customer preparation as future work is superseded by this package update; hardware acceptance remains pending. Continue mobile work in its own session and coordinate any shared firmware change deliberately.

Updated: 2026-11-16, America/Costa_Rica.

## 1. User-confirmed scope and release baseline

The customer currently needs **the ESP32-S3 firmware and the Python USB dashboard only**. The mobile app is future work. Most recent local firmware changes were made to support that future mobile app; they are not automatically customer-release changes.

The user explicitly confirmed that firmware delivered on **PCB v2 and PCB v3** comes from GitHub branch **`main_2Ant`, commit `dbf098d`**. Preserve that firmware baseline while preparing a compatible customer dashboard. Improving the dashboard does **not** require flashing the experimental local firmware onto customer boards.

Two separate Claude Code sessions are intended:

1. **Customer session:** shipped firmware compatibility, dashboard improvements, release preparation and PCB v2/v3 validation.
2. **Mobile session:** Flutter BLE app and the local firmware changes it needs. Changes to shared firmware require deliberate coordination with the customer session.

This handoff records a source/contract comparison and simulated serial checks. It is not evidence that an updated dashboard or local firmware has passed physical customer-board acceptance tests.

## 2. Repository location and exact versions

Remote: <https://github.com/LittleEndianEngineering/RFID_Reader_Github>

Current project directory:

```text
/Users/oscarpauly/Projects/Little Endian/Establishment Labs/Diseño LE/Code/Rfid134-master
```

**The actual Git root is its parent `Code` directory.** Git object paths therefore start with `Rfid134-master/`. Earlier chat/workspace metadata points at a Desktop location that no longer contains this working copy. Locate the repository before editing; some file browsers display `ñ` with a different Unicode normalization.

### Verified Git references on 2026-11-16

| Reference | Exact commit | Meaning |
|---|---|---|
| GitHub `main_2Ant` | `dbf098dbd869d88fe63274aad421fdba6d7ed18a` | **Customer-delivered firmware baseline**, user confirmed. Commit: “Add 2Ant Live View readnow support and refresh docs,” 2026-07-18. |
| Local `HEAD`, branch `main_2Ant` | `c17d36c188ca3f82e28b5284dc7ca61641cfb6da` | One local-only commit ahead: “Stabilize mobile BLE foundation,” 2026-08-01. Its four changed files are mobile-only; committed firmware/dashboard equal `dbf098d`. |
| GitHub `main` | `b63351c7ad0f1d96aeac30e49b79050c932cbcbb` | Older default-branch merge, dated 2026-04-15. **Do not substitute this for the confirmed customer baseline.** It does not contain the specific `...S3_live_2Ant.py` dashboard under review. |
| Local working tree | `c17d36c` plus dirty/untracked files | Experimental firmware, improved dashboard, future mobile app. Not represented by one release commit or tag. |

Both GitHub branch tips were checked against the live remote through the GitHub connector and matched the locally available references. Recheck them in a later session; do not assume branch names remain immutable.

### Firmware and dashboard identities

| Item | Source path relative to project | Header version at Git baseline | Local header version |
|---|---|---|---|
| Firmware sketch | `src/PCB/RFID_Reader_PCB1p0_Split_2Ant/RFID_Reader_PCB1p0_Split_2Ant.ino` | **1.5**, “Light Sleep + Multi-Button + BLE + Low-SoC Service Access,” July 2026 | Still **1.5**, despite local changes |
| Dashboard | `dashboard/src/rfid_dashboard_configure_lightsleep_multibutton_S3_live_2Ant.py` | **6.1**, “ESP32-S3 + Dual Antenna + Low-SoC Service Access,” July 2026 | Still **6.1**, despite local changes |

Header version strings do not distinguish customer and experimental code. Identify builds by source commit and artifact hash; introduce a clear dashboard release identifier when producing a customer candidate.

Pinned Git objects at `dbf098d`:

- Firmware directory tree: `2fa972b3259c8a983cec0191f1271cab57d428b0`.
- Main sketch blob: `899029c92314b880d57760f9cc1db04c9ba0f1ad`.
- Dashboard blob: `9522028a7c793a6760920f24acee5569054faccb`.

Dashboard comparison snapshot:

| Snapshot | Lines | SHA-256 |
|---|---:|---|
| Git dashboard at `dbf098d` | 2,975 | `8591ba0c782b24b818ff519c2ebc44ea6af0d8ccd87b06500a7701ba02ce86ed` |
| Local dashboard on 2026-11-16 | 3,109 | `89bbb0a455a5f074d4728861c0f91b8e2c84409f44ef521494253be8a3fd3540` |

The local dashboard diff is **243 insertions / 109 deletions**, net +134 lines. Line count does not measure functional scope: many changes remove emoji from labels/messages.

## 3. How the components relate

```text
Customer track:
Python/Streamlit dashboard -- USB serial, 115200 baud --> shipped ESP32-S3 firmware
                                                          | RFID ANT1 / ANT2
                                                          | RTC and battery checks
                                                          | SPIFFS configuration/readings

Future mobile track:
Flutter Android/iOS app ---- BLE GATT/text notifications --> experimental local firmware
                                                           (shared hardware/storage code)
```

The dashboard uses USB serial, not BLE. BLE transport/framing changes are not a dependency of the customer's USB dashboard.

Important paths:

- `serial_cmd.cpp`: customer USB command contract.
- `rfid_reader.cpp/.h`: read windows, antenna selection, recovery, result output.
- `flash_store.cpp/.h`, `types.h`: stored records, antenna flags, history/range responses.
- `config.cpp`: SPIFFS configuration persistence.
- `globals.cpp/.h`, `sleep_wake.cpp`, `button.cpp`, `led_status.cpp`, `pins.h`: service/idle/sleep, button, battery and hardware behavior.
- `ble_comm.cpp/.h`: BLE command and notification transport, primarily the future mobile track.
- `mobile_app/rfid_reader_app/lib/main.dart`: Flutter app/UI and BLE integration.
- `mobile_app/rfid_reader_app/lib/ble_protocol.dart`: local typed parser, byte buffer and manual-read session model; currently **untracked**.
- `mobile_app/rfid_reader_app/test/ble_protocol_test.dart`: local protocol regressions; currently **untracked**.
- `mobile_app/MOBILE_APP_UPDATE_PLAN.md`, `MOBILE_BLE_PROTOCOL_CONTRACT.md`, `CODE_REVIEW_FINDINGS.md`: planning/history. Some describe earlier states; verify runtime code rather than assuming every planned feature exists.

The firmware directory name says `PCB1p0`, but the user reports deployment on PCB v2/v3. Do not infer different hardware mappings from that directory name. The baseline `pins.h` uses button 37, RFID power 42, RFID UART 41, antenna select 36, I2C 35/45, RGB 5/6/4, battery ADC 7. Confirm actual PCB/release settings on hardware before changing them. The power-pin comment says active LOW while reader code drives HIGH to power on; this comment inconsistency is not a reason to change shipped behavior without a schematic/device check.

## 4. Git dashboard versus shipped Git firmware: compatibility

**Conclusion:** the Git pair is compatible at the serial-command/record-format level for its principal workflows. It already contains much of what looks attractive in the local dashboard.

| Workflow | Shipped firmware support | Git dashboard |
|---|---|---|
| Connection, service mode, debug/status | `status`, `debugsimple`, `debug`, `time`, `dashboardmode on/off` | Supported |
| Manual dual-antenna read | `readnow`, per-antenna `[RFID_RESULT]`, final manual completion | Supported |
| Live View | Host repeatedly sends `readnow`; firmware stores `liveViewAutoReadIntervalMs` | Already supported |
| ANT1/ANT2 latest cards, table, graph, CSV, timezone conversion | Antenna metadata and UTC timestamps | Already supported |
| Stored history / date range | `print`, `range <start_epoch> <end_epoch>`, begin/end markers | Supported |
| Configuration | All **15 dashboard get variables** and **15 set commands** exist with matching markers | Supported |
| Battery/idle/recovery/LED controls | Present in serial status/config interface | Already supported |
| Individual antenna read | **No `readant 1/2`** | Not offered by Git dashboard |
| Protocol capability query | **No `protocol` / `RFID_PROTOCOL_V2`** | Not required by Git dashboard |

Relevant serial formats in shipped firmware:

```text
[RFID_RESULT] stored=true ant=ANT1 reading=<n> ts=<epoch_utc> tag=<country> <tag_id> temp=<value°C|N/A>
[MANUAL] RFID read complete count=<n>
[IDLE] Manual read blocked: <reason>
[MANUAL] RFID read skipped

---BEGIN_READINGS---
#<n>: <YYYY-MM-DD HH:MM:SS>, <country>, <tag_id>, <temperature°C|N/A>, <ANT1|ANT2>
---END_READINGS---
```

`range` also wraps its output in `<DASHBOARD_DATA> ... </DASHBOARD_DATA>`. Configuration reads use `<GET_<NAME>_BEGIN>` / value / `<GET_<NAME>_END>`; successful set commands emit an exact `OK` line. Unknown serial commands are silently ignored apart from optional verbose logging.

Shared limitations worth addressing in a dashboard release:

- Git dashboard default manual timeout is `2 × RFID_ON_seconds + 10`: **20 seconds at 5 seconds per antenna**. Shipped firmware can retry a full window once on each antenna after Error 130. Four windows plus startup/recovery overhead can exceed that timeout. This limitation exists in the delivered Git firmware/dashboard pairing; it is not caused solely by mobile changes.
- A quiet gap after an informational configuration message can make the Git dashboard finish reading before a delayed `OK`. The local acknowledgment-aware reader is better suited to this case.
- Git dashboard initializes its Dashboard Mode configuration checkbox to false. Status updates set `device_dashboard_mode` but do not synchronize that checkbox. Sending settings without first reading them can therefore unintentionally request Dashboard Mode OFF. The local synchronization logic addresses this mismatch.

## 5. Git dashboard versus local dashboard: what to inherit

**Recommendation:** prepare a dashboard-only customer candidate based on the preferred local appearance and reliability improvements, explicitly targeting firmware `dbf098d`. No customer firmware update is needed for those improvements.

| Local difference | Needs new firmware? | Customer recommendation |
|---|---|---|
| Simpler labels/messages; most emoji removed | No | Keep if this is the preferred appearance. |
| Extended manual-read timeout, currently `4 × on_time + 30` for both antennas: **50s at 5s/window** | No | Keep. It also benefits the shipped firmware's existing recovery behavior. A completed response still returns immediately. |
| Wait for `OK`/`ERROR`/`Invalid value` for set commands, retry once on missing confirmation, stop remaining commands on failure | No | Keep; verify success and rejection paths on shipped boards. |
| Synchronize Dashboard Mode checkbox from device status unless user edited it; reconcile before setting; send mode change last | No | Keep. Verify intentional OFF and persistence/readback behavior. |
| Generalized manual-read helper and latest-result labels/card count | No for normal `readnow` | Can keep; retain ANT1/ANT2 cards for the customer dual read. |
| `Read ANT1` / `Read ANT2` | **Yes: local-only `readant` handlers** | Hide/omit for this customer release, or leave unavailable with appropriate wording. Do not enable against `dbf098d`. |
| Cached serial `protocol` capability query | Shipped firmware does not answer it | Local fallback safely disables those buttons after at most a 3s reader timeout, but adds an unnecessary probe. Prefer omitting it in a fixed-baseline customer build. |
| Caption telling user to flash current firmware | Would direct customer to experimental code | Replace/remove. The customer's existing firmware is the supported target. |

The following functions were AST-identical between Git and local snapshots: `parse_readings`, `parse_live_readnow_results`, `merge_live_view_dataframe`, `get_live_view_refresh_interval`, `_wake_and_send_command`, `wait_for_device_ready`. Dual-antenna parsing, Live View, graph merging and the connection-readiness work are largely **already in Git**, not new local functionality to claim as a backport.

Additional release work identified, not implemented in this analysis:

1. **Incomplete read responses:** both dashboard versions currently prioritize any parsed reading over checking for final completion. If a timeout/disconnection occurs after ANT1, the UI can still show a completed reading result. Keep partial records, label the cycle incomplete, and handle Live View recovery before claiming a fully completed read.
2. **Empty `Print All`:** shipped `printStoredReadings()` returns `No readings stored.` without `---END_READINGS---` when empty. Both dashboard UIs can incorrectly warn that this response is incomplete. Recognize that exact empty response as terminal/valid in the dashboard.
3. **Python dependency contract:** `requirements.txt` permits Streamlit >=1.28, while the existing dashboard explicitly requires its `fragment` API for Live View and warns that this needs 1.37+. Specify/test a suitable environment and record the actual dependency versions used for the customer package. No dependency file was changed in this analysis.
4. **Durability caveat:** the shipped `saveConfigVar()` can log failure while the serial handler still emits `OK`. The local acknowledgment checks establish command acknowledgment, not guaranteed flash durability. Include settings readback and selected reboot-persistence tests; assess any firmware fix separately from the dashboard-only release.

These are source findings and simulated failure cases, not a claim that the customer has already observed each one.

## 6. Local experimental firmware and mobile state

Eight firmware files differ from `dbf098d`: the main sketch, `ble_comm.cpp`, `button.cpp`, `globals.cpp/.h`, `rfid_reader.cpp/.h`, `serial_cmd.cpp` (449 insertions / 173 deletions at this snapshot). Do not merge or distribute this set wholesale as part of a dashboard update.

The local additions include:

- Directed single-antenna reads over serial and BLE, plus the added `powerOnAndReadSingleAntennaWindow` entry point.
- `protocol` -> `RFID_PROTOCOL_V2` capability response over BLE and, later, serial.
- BLE newline framing, splitting to negotiated MTU minus 3 bytes capped at 180, and app-side buffering of bytes until a complete line. This fixes order/UTF-8/antenna-suffix fragmentation for the updated pair.
- Explicit BLE manual-read completion messages and app-side collection until command completion, preserving both antenna results.
- Antenna-aware BLE history/last/range records, structured live results and explicit empty-transfer endings.
- Expanded BLE configuration/status/clear support. Some corresponding mobile screens remain future work.
- BLE activity/timer/wake cleanup and short button-read suppression to reduce unwanted extra read cycles.
- A service-access change that also keeps a BLE-connected device awake. This is a behavioral/power-management difference from shipped firmware.
- Structured BLE results returned to connected clients regardless of Dashboard Mode latch.
- Local Wi-Fi-default changes in `globals.cpp`, unrelated to customer-dashboard compatibility. Do not copy credentials into handoffs, logs, patches for sharing, or release examples.

Earlier in this chat, 22 Flutter tests passed, the experimental firmware compiled for ESP32-S3, and a host-side test exercised its response splitting at MTUs 23/185/512. A later compile included the serial capability query. These were **software checks**, not physical PCB v2/v3 acceptance tests; firmware was not uploaded and the mobile app was not installed by this work.

Build profile used for that compile check: ESP32 Arduino core 3.3.8; `esp32:esp32:esp32s3:CDCOnBoot=cdc,PartitionScheme=huge_app`. This is a verification profile, **not proof of the customer's delivered flash/partition/PSRAM settings**. Consult actual delivery/build records before rebuilding customer firmware.

The current working tree is dirty across firmware, dashboard, mobile app, iOS setup/assets and other files. New parser/tests/protocol documents are untracked. Preserve them: a clean checkout or a new worktree will not automatically include uncommitted or untracked work. Neither a reset nor an all-files commit is appropriate for separating these tracks.

## 7. Verification performed for this handoff

On 2026-11-16, the pinned Git firmware was exported to a temporary snapshot. Both real dashboard source files were syntax-checked, selected functions were executed with fake serial/time objects, and their command/marker mappings were checked against the shipped `serial_cmd.cpp`.

| Check | Git dashboard + shipped firmware contract | Local dashboard + shipped firmware contract |
|---|---|---|
| All 15 get variable names/markers and their marker parsing | Pass | Pass |
| All 15 set command names exist in firmware | Pass (static command check) | Pass (static command check) |
| Dual ANT1/ANT2 live parsing, normal `readnow` completion | Pass | Pass |
| Stored ANT1/ANT2 records, legacy no-antenna default, range parsing | Pass | Pass |
| Idle-blocked read finishes promptly | Pass | Pass |
| Simulated 40-second read response completes before reader timeout | No | Yes |
| Simulated `OK` delayed to 2s after earlier config text is retained | No | Yes |
| Active device status synchronizes previously false form checkbox | No | Yes; also preserves an explicit user edit |
| Capability query against non-answering shipped firmware | Not needed | Unsupported/cached; no `readant` command is sent |

The 40s and 2s delays are **synthetic test inputs**, not measured board timings. The tests exercise the actual Python transport/parser/status functions, not a complete browser UI or actual SPIFFS writes. Wake/reset helpers were stubbed; these checks do not validate USB reconnect timing or real power behavior. No USB reader was present during this audit.

Temporary audit evidence in this environment (do not rely on `/private/tmp` surviving a restart):

```text
/private/tmp/rfid_customer_handoff_20261116/audit.py
/private/tmp/rfid_customer_handoff_20261116/results.json
/private/tmp/rfid_customer_handoff_20261116/git_baseline/
```

Only this handoff document is being added for the current analysis. Runtime code was not changed or reverted to make the compatibility conclusions true.

## 8. How to continue in two Claude Code sessions

### Session A: customer firmware/dashboard

Suggested opening prompt:

> Read CLAUDE_HANDOFF.md. Target the customer firmware on PCB v2/v3 at `dbf098dbd869d88fe63274aad421fdba6d7ed18a`. Prepare a dashboard-only customer candidate using the preferred local appearance, configuration acknowledgment/mode protections and recovery timeout. Preserve shipped firmware; omit unsupported directed reads and the experimental-firmware flash prompt. Resolve the dashboard release findings, run tests against the pinned firmware contract, and identify what still needs real-board validation.

Use an isolated branch/worktree rooted at the confirmed baseline, after preserving the dirty tree. Bring over reviewed dashboard changes selectively. The existing local-only `c17d36c` commit is mobile-only and is not needed for this customer dashboard candidate. Do not copy the entire dirty repository.

Customer acceptance checks, using the actual shipped firmware on **both** PCB revisions:

- USB connect, Dashboard Mode/service latch, disconnect/reconnect and reset behavior on supported customer OSes/adapters.
- Dual Read Now: two tags, ANT1 only, ANT2 only, neither antenna; normal completion and a recovery cycle.
- Live View start/stop, repeated cycles, retention of history, and partial/missing completion handling.
- Empty/full history, empty/populated date range, a larger history, UTC/local-time display, CSV and N/A temperature.
- Configuration get/set, invalid values, explicit `OK`, intentional Dashboard Mode OFF last, preserving ON when not edited, and selected reboot persistence.
- Low-SoC/RTC-blocked reads and service/recovery visibility.
- Verify that individual-antenna controls are absent/unavailable and no experimental firmware upgrade is requested.
- Test storage clear only with approved expendable test data; it deletes device readings.

Record the firmware commit, dashboard commit/build identifier, dependency versions and per-PCB acceptance results in the customer release package. The customer firmware need not change merely because local mobile development is newer.

### Session B: future mobile app

Suggested opening prompt:

> Read CLAUDE_HANDOFF.md and the mobile protocol documents, then inspect current code. Continue the future Flutter/BLE track while preserving the customer firmware/dashboard baseline. Preserve untracked `ble_protocol.dart` and its tests. Validate the updated app/experimental-firmware pair together; coordinate any shared firmware/storage/power-management change with the customer session before promoting it.

Preserve the existing uncommitted/untracked mobile and companion-firmware changes in a separate branch/worktree or a reviewed backup/patch set. A worktree created from `HEAD` alone will miss much of this work. Keep mobile firmware changes out of the customer-dashboard branch unless separately selected, justified and validated.

Known remaining mobile boundaries:

- Full dashboard-style configuration/status UI and Live View are not all implemented, even though BLE handlers/helper models exist.
- The updated protocol is most reliable with the paired updated firmware. Legacy framing/completion support is best-effort; missing antenna metadata cannot recreate historical ANT2 identity.
- Validate real Android/iOS notifications, MTUs, reconnects, errors, empty transfers, recovery, battery/service mode and power consumption.
- Keep tests/fixtures covering both antennas, recovery after a no-tag message, complete-command handling, split UTF-8 and antenna suffixes, message order, blocked/error responses and legacy timestamps.

## 9. Read-only commands for re-establishing context

Run from the project directory above. Prefer full SHAs for release comparisons.

```bash
git rev-parse --show-toplevel
git status --short --branch
git log -5 --oneline
git diff dbf098dbd869d88fe63274aad421fdba6d7ed18a -- dashboard/src/rfid_dashboard_configure_lightsleep_multibutton_S3_live_2Ant.py
git diff dbf098dbd869d88fe63274aad421fdba6d7ed18a -- src/PCB/RFID_Reader_PCB1p0_Split_2Ant
git show dbf098dbd869d88fe63274aad421fdba6d7ed18a:Rfid134-master/src/PCB/RFID_Reader_PCB1p0_Split_2Ant/serial_cmd.cpp
```

Dashboard start command from the project directory, using an appropriately prepared Python environment:

```bash
streamlit run dashboard/src/rfid_dashboard_configure_lightsleep_multibutton_S3_live_2Ant.py
```

For future branch separation, remember: a worktree created from this repository's Git root contains `Rfid134-master/` inside it. Do not assume the worktree root itself is the project directory.
