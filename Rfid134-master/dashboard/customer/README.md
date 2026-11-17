# Final deliverable for RFID Reader 2026

Customer dashboard **6.2.1** targets the firmware already delivered on **PCB v2 and PCB v3**:

- Firmware header version: **1.5**, July 2026.
- Firmware branch: **`main_2Ant`**.
- Firmware commit: **`dbf098dbd869d88fe63274aad421fdba6d7ed18a`**.
- Firmware source: `src/PCB/RFID_Reader_PCB1p0_Split_2Ant/` relative to the project root.

The exact commit identifies the delivery; a firmware version string alone is insufficient.
The firmware on the customer-release branch must stay identical to this baseline.
Experimental firmware and the future mobile app are developed separately.

## Layout

```text
customer/
  src/          Editable dashboard, protocol helpers and logo
  packaging/    Launcher, PyInstaller spec, pinned requirements, build/release tools
  tests/        Protocol and launcher regression tests
  releases/
    rfid-reader-2026/
      source/           Exact dashboard .py/helper/logo snapshot used in these builds
      windows-x64/      Customer executable
      macos-arm64/      Apple Silicon app archive
      macos-x64/        Intel app archive
      linux-x64/        Linux executable archive
      verification/     Native manifests and test evidence
      release_manifest.json
      SHA256SUMS.txt
      README.md
```

The canonical editable dashboard is
**`src/rfid_dashboard_configure_lightsleep_multibutton_S3_live_2Ant.py`**.
There is no separate `app.py` implementation. The `source/` copy in each versioned
release is an immutable reference that must match that release's executable builds.
Generated `build/`, `dist/`, virtual environments and Python caches are ignored.

## Customer delivery

Use the packages and instructions in `releases/rfid-reader-2026/`. Python is bundled;
the customer receives only the application/package for their platform. Reference source
and verification records are provided alongside it for traceability.

This dashboard retains dual-antenna Read Now, Live View, history/range retrieval, charts,
CSV export, status and configuration. It keeps recovery-aware read timeouts, delayed-ACK
handling and mode synchronization. It preserves partial reads and blocks further commands
until pending completion is drained; empty history and flash-write errors are handled.
Individual-antenna commands remain hidden because delivered firmware lacks `readant`.

The release is prepared for handoff. Physical USB acceptance on both PCB revisions and
customer-like Windows Explorer/Linux desktop launch checks remain pending. Mac native
builds also exercise Finder/LaunchServices, following the 2026-11-17 local launch issue.

## Development and native builds

Use Python **3.11** on the target platform. From this directory:

```sh
python -m pip install -r packaging/requirements-build.txt
python -m unittest discover -s tests -v
python packaging/build.py --target windows-x64
# Or: macos-arm64, macos-x64, linux-x64 on their matching native platforms.
```

For quick development without rebuilding an executable:

```sh
python -m streamlit run src/rfid_dashboard_configure_lightsleep_multibutton_S3_live_2Ant.py
# Or test the native launcher against the editable source:
python packaging/launcher.py
```

Windows developers can double-click `packaging/build_windows.bat`, which creates the
local build environment and runs the same build/test pipeline. Linux headless builds
need Tcl/Tk/X11, Xvfb and `xvfb-run --auto-servernum` before the Python build command.
The Git-root `.github/workflows/build-customer-dashboard.yml` builds all four native
targets. It triggers on source/packaging/test changes, not on release-binary commits.

Build products are written to ignored `dist/<target>/` directories. Each contains the
package, exact source reference, manifest, and frozen UI/native Tk/server/assets/shutdown
reports. Mac tests launch through LaunchServices. All platform builds must use the same
source commit before assembling a release:

```sh
python packaging/assemble_release.py --artifacts-root /path/to/downloaded/platform-folders
```

The assembler checks firmware/version identities, identical source, package/binary hashes,
required test results, and a common build commit. It refuses to overwrite an existing
release directory. For subsequent deliveries choose a new `--output releases/<release-id>`;
update dashboard version/build metadata and keep earlier delivered snapshots immutable.

## Version control

Source, release manifests, checksums and test evidence are normal Git files. Executables
and platform archives under `releases/` use **Git LFS**, because the Linux binary package
exceeds GitHub's 100 MiB normal-file limit. Developers need Git LFS installed:

```sh
git lfs install
git lfs pull
```

Never force-add generated `dist/`, extracted app bundles, duplicate binaries or caches.
Review `git status` and stage only the customer release and its workflow. The surrounding
working tree also contains experimental firmware/mobile work that belongs to its own track.
A suitable release commit title is:

`Final deliverable for RFID Reader 2026 — dashboard 6.2.1 for firmware 1.5 (dbf098d)`

## Validation and runtime notes

Software tests do not replace reader testing. Before customer delivery check COM connection
and reconnect, two/single/no tags, recovery, Live View stop/start, empty/full/range history,
configuration roundtrip and reboot persistence on both PCB revisions. Clear only expendable
stored data. USB adapter drivers and Linux serial permissions are host requirements.
Windows builds are unsigned; Mac bundles are ad-hoc signed without Apple notarization.

The app serves only `127.0.0.1`. Logs are under
`%LOCALAPPDATA%\EstablishmentLabs\RFIDDashboard` on Windows,
`~/Library/Application Support/EstablishmentLabs/RFIDDashboard` on Mac, or
`$XDG_DATA_HOME/EstablishmentLabs/RFIDDashboard` on Linux (default `~/.local/share`).

References: [PyInstaller platform rules](https://pyinstaller.org/en/stable/usage.html),
[GitHub large-file limits](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github).
