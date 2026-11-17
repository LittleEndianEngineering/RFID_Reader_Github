# Customer desktop dashboard 6.2.0

This dashboard targets the delivered PCB v2/v3 firmware at `dbf098dbd869d88fe63274aad421fdba6d7ed18a` (`main_2Ant`). It is derived from the preferred local dashboard appearance and configuration protections. Experimental firmware and mobile code are separate.

## What the customer receives

**RFIDDashboard.exe** is the only application file required. On 64-bit Windows, double-click it; the dashboard opens in the default browser. Keep the small control window open while using the reader. Use **Close Dashboard** to exit and release the serial port. No Python installation, pip commands, terminal, or Streamlit setup is required on the customer's computer.

Plug in the delivered reader, choose its COM port, and connect in the dashboard. A driver for the reader's USB adapter must already be installed or provided by Windows. The application does not install device drivers or change reader firmware. Internet access is unnecessary for running the dashboard. Windows/PCB acceptance testing remains a release check; software smoke tests do not verify physical antenna or power behavior.

The dashboard is served only on `127.0.0.1`. The launcher chooses an available port and opens the browser automatically. Its log is under `%LOCALAPPDATA%\EstablishmentLabs\RFIDDashboard\dashboard.log`.

## Changes for this customer build

- Dual-antenna Read Now, Live View, history, graph, CSV, status and configuration are retained.
- Unsupported individual-antenna controls, their capability probe and the experimental-firmware flash prompt are omitted.
- Recovery-aware timeout and configuration acknowledgment/retry/mode protections are retained.
- Partial reads retain their data, pause Live View and prevent another serial command until the pending completion is drained or a new connection is used.
- An empty `No readings stored.` response is recognized normally.
- A reported configuration flash-write failure is treated as a failure even if firmware also prints `OK`.
- The logo is bundled and resolved relative to the app, independent of the working directory.

## Build on Windows (developer only)

Use **64-bit CPython 3.11**. Double-click `build_windows.bat`, or run `build_windows.ps1` in PowerShell. Build-time dependencies are downloaded into `.build-venv`. The customer does not run this build script.

The script runs regression tests, builds the single-file/windowed PyInstaller executable, renders the actual frozen Streamlit application, initializes its bundled native Tk window, starts its local server, checks health and bundled front-end assets, and records a SHA-256 and dependency manifest.

Build outputs are under `dist/`:

- `RFIDDashboard.exe`: customer application.
- `SHA256SUMS.txt`: exact executable hash.
- `build_manifest.json`: dashboard, baseline and dependency identities.
- `self-test.json`, `server-smoke.json`: verification results.

The repository-root workflow `.github/workflows/build-customer-dashboard-windows.yml` performs the same build on a Windows x64 runner. It runs on the dedicated `customer/windows-dashboard-*` build branches or manual dispatch. A Windows executable must be produced on Windows; a macOS PyInstaller output is not a Windows executable.

Source/dependency verification references: [PyInstaller platform rules](https://pyinstaller.org/en/stable/), [Streamlit CLI](https://docs.streamlit.io/develop/api-reference/cli/run).

## Before delivery

Validate the executable on the customer's Windows environment with the actual shipped firmware on both PCB revisions: COM connection/reconnect, two/single/no tags, recovery, Live View stop/start, empty/full/range history, configuration roundtrip and selected reboot persistence. Test clearing only on expendable data. Include any required USB driver separately. This build does not carry a publisher signing certificate; signing requires the organization's existing code-signing process.


## macOS and Linux packages

The same dashboard source is packaged for macOS 15+ on Apple Silicon (`macos-arm64`) and Intel (`macos-x64`), and desktop Linux x64 (`linux-x64`). Linux builds use Ubuntu 22.04/glibc 2.35; compatible newer glibc-based distributions may work but are not all independently tested. Linux requires an X11/XWayland desktop, default browser, and user access to the USB serial device (commonly the `dialout` group on Ubuntu).

On macOS, unzip `RFIDDashboard-macos-<architecture>.zip`, move `RFIDDashboard.app` to Applications, and open it. The app bundle includes Python, dependencies, and the launcher. It is ad-hoc signed for integrity, without an Apple Developer ID or notarization; macOS may require approving the trusted download under Privacy & Security. It runs from the extracted app bundle without loose Python files.

On Linux, extract `RFIDDashboard-linux-x64.tar.gz` and open the executable `RFIDDashboard`. The archive preserves its executable permission. Some file managers require explicitly allowing execution. Python is bundled; the application does not install USB drivers or change system device permissions.

Both platforms open the dashboard in the default browser and provide the same small control window as Windows. Use Close Dashboard to exit. macOS logs are in `~/Library/Application Support/EstablishmentLabs/RFIDDashboard`; Linux uses `$XDG_DATA_HOME/EstablishmentLabs/RFIDDashboard` (default `~/.local/share/EstablishmentLabs/RFIDDashboard`). Browser launch on Linux restores system library paths so bundled libraries do not interfere with the desktop browser.

The Git-root workflow `.github/workflows/build-customer-dashboard-unix.yml` builds all three targets on native runners with Python 3.11. Developer build commands are `python -m pip install -r requirements-build.txt` then `python build_native.py --target <target>`. On headless Linux, run the build under `xvfb-run --auto-servernum` and provide Tcl/Tk and X11 libraries. Dependencies are installed only on the build machine.

Each artifact includes the package archive, the corresponding dashboard `.py` reference with its helper/logo, README, package hash, source/dependency manifest, and frozen UI/native Tk/server/assets/shutdown test reports. Reports are outside the macOS app bundle to preserve its signature. Build outputs are `dist/macos-arm64/`, `dist/macos-x64/`, and `dist/linux-x64/`; existing Windows delivery files at `dist/` stay separate.

Packaging references: [PyInstaller macOS app bundles and Linux compatibility](https://pyinstaller.org/en/stable/usage.html), [external browser library environment](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html), [GitHub native runner architectures](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
