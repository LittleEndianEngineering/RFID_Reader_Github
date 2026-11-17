# Final deliverable for RFID Reader 2026

Dashboard **6.2.1**, for the firmware already delivered on PCB v2/v3:
**firmware 1.5, `main_2Ant`, commit `dbf098dbd869d88fe63274aad421fdba6d7ed18a`**.

| Platform | Package | Run |
|---|---|---|
| Windows x64 | `windows-x64/RFIDDashboard.exe` | Double-click the executable. |
| macOS 15+ Apple Silicon | `macos-arm64/RFIDDashboard-macos-arm64.zip` | Extract, copy the app to Applications, then open it. |
| macOS 15+ Intel | `macos-x64/RFIDDashboard-macos-x64.zip` | Extract, copy the app to Applications, then open it. |
| Desktop Linux x64 | `linux-x64/RFIDDashboard-linux-x64.tar.gz` | Extract and open `RFIDDashboard`; executable permission is preserved. |

Python and application dependencies are bundled. A default browser and access to the
reader's USB serial port are required. Keep the small control window open while using
the dashboard. Use Close Dashboard to stop it and release the serial port.
Linux was built/tested on Ubuntu 22.04/glibc 2.35, with an X11/XWayland display.
The Windows executable is unsigned; downloaded files may encounter organizational
security checks. Mac app bundles are ad-hoc signed without Developer ID/notarization.
A USB driver or Linux serial-device group membership may be needed on the host.

The exact long-named dashboard source and its helper/logo are in `source/` for reference.
For development edit `../../src/`; this delivery snapshot is immutable.
`release_manifest.json` records firmware, source and package identities. `SHA256SUMS.txt`
covers every release file. `verification/` contains the native build/test evidence.

Native regression/UI/server/assets/shutdown tests and Mac Finder-style launch passed.
Windows Explorer launch, Linux file-manager launch, and physical USB acceptance with
both PCB revisions remain pending. This release label identifies the prepared
customer package and does not assert that those pending customer checks have passed.
