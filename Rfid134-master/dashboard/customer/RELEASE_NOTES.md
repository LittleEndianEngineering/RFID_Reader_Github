# Customer dashboard release notes

## 6.2.1 — Final deliverable for RFID Reader 2026

Target: delivered firmware **1.5 / `main_2Ant` /
`dbf098dbd869d88fe63274aad421fdba6d7ed18a`**, PCB v2/v3.

- Establish one editable dashboard using its original long filename under `src/`.
- Put launch/build/dependency tools under `packaging/` and keep regression tests under `tests/`.
- Pin the delivered firmware version, branch and full commit in source comments and manifests.
- Rebuild all four native packages from this source layout and version.
- Test macOS launch via Finder/LaunchServices, extending the previous direct-executable checks.
- Store one package per platform in an immutable release, with source snapshot, hashes and evidence.
- Track executable packages through Git LFS; ignore generated working products and caches.

The dashboard's serial/read/configuration behavior is unchanged from customer 6.2.0.
The firmware baseline is unchanged. Customer-machine launch/physical reader acceptance
remains explicit in the release manifest.

## 6.2.0 — Initial customer packaging

Derived from the preferred local dashboard for delivered firmware dbf098d. Removed
unsupported single-antenna controls; retained dual Read Now, Live View and configuration
protections. Added Windows x64, macOS ARM/Intel and Linux x64 packaging. A local macOS
Finder registration failure was resolved by installing a clean Apple Silicon copy in the
user Applications folder; its precise initial registration-state cause was not established.
