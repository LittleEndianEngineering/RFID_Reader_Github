"""Assemble an immutable RFID Reader 2026 delivery from verified native CI artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src'
sys.path.insert(0, str(SOURCE))
from customer_protocol import VERSION, FIRMWARE_BASELINE, FIRMWARE_VERSION, FIRMWARE_BRANCH, DASHBOARD_FILENAME

TARGETS = ('windows-x64', 'macos-arm64', 'macos-x64', 'linux-x64')


def digest(path):
    with Path(path).open('rb') as stream:
        return stream_digest(stream)


def stream_digest(stream):
    result = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        result.update(chunk)
    return result.hexdigest()


def validate_artifact(folder, target):
    manifest = json.loads((folder / 'build_manifest.json').read_text(encoding='utf-8'))
    assert manifest['target'] == target
    assert manifest['dashboard_version'] == VERSION
    assert manifest['firmware_version'] == FIRMWARE_VERSION
    assert manifest['firmware_branch'] == FIRMWARE_BRANCH
    assert manifest['firmware_baseline'] == FIRMWARE_BASELINE
    assert manifest['dashboard_source_sha256'] == digest(SOURCE / DASHBOARD_FILENAME)
    assert manifest['source_commit'] and len(manifest['source_commit']) == 40
    for name in (DASHBOARD_FILENAME, 'customer_protocol.py', 'EB_logo.png'):
        assert (folder / name).read_bytes() == (SOURCE / name).read_bytes(), name
    test = json.loads((folder / 'self-test.json').read_text(encoding='utf-8'))
    server = json.loads((folder / 'server-smoke.json').read_text(encoding='utf-8'))
    assert test['passed'] and test['frozen'] and test['native_window']
    assert test['version'] == VERSION and test['firmware_baseline'] == FIRMWARE_BASELINE
    assert server['passed'] and server['health'] and server['frontend_assets'] and server['shutdown_released_port']
    if target.startswith('macos'):
        assert test['launch_method'] == 'Finder/LaunchServices'
    artifact = folder / manifest['artifact']
    assert artifact.parent == folder and artifact.is_file()
    assert digest(artifact) == manifest['artifact_sha256']
    if target == 'windows-x64':
        assert artifact.name == 'RFIDDashboard.exe'
        assert digest(artifact) == manifest['executable_sha256']
    elif target.startswith('macos'):
        with zipfile.ZipFile(artifact) as archive:
            with archive.open('RFIDDashboard.app/Contents/MacOS/RFIDDashboard') as binary:
                assert stream_digest(binary) == manifest['executable_sha256']
    else:
        with tarfile.open(artifact) as archive:
            members = archive.getmembers()
            assert len(members) == 1 and members[0].name == 'RFIDDashboard' and members[0].isfile()
            assert members[0].mode & 0o111
            with archive.extractfile(members[0]) as binary:
                assert stream_digest(binary) == manifest['executable_sha256']
    return manifest


def assemble(artifacts_root, output):
    artifacts_root = Path(artifacts_root).resolve()
    output = Path(output).resolve()
    assert not output.exists(), 'Release snapshots are immutable. Choose a new release directory.'
    manifests = {target: validate_artifact(artifacts_root / target, target) for target in TARGETS}
    commits = {manifest['source_commit'] for manifest in manifests.values()}
    assert len(commits) == 1, 'All platform binaries must come from the same source commit.'
    output.mkdir(parents=True)
    source_output = output / 'source'
    source_output.mkdir()
    for name in (DASHBOARD_FILENAME, 'customer_protocol.py', 'EB_logo.png'):
        shutil.copy2(SOURCE / name, source_output / name)
    shutil.copy2(ROOT / 'packaging/requirements.txt', source_output / 'requirements.txt')
    platforms = {}
    for target, manifest in manifests.items():
        source_folder = artifacts_root / target
        platform_folder = output / target
        platform_folder.mkdir()
        artifact = platform_folder / manifest['artifact']
        shutil.copy2(source_folder / artifact.name, artifact)
        verification = output / 'verification' / target
        verification.mkdir(parents=True)
        for name in ('build_manifest.json', 'self-test.json', 'server-smoke.json', 'ci_artifact.json'):
            if (source_folder / name).is_file():
                shutil.copy2(source_folder / name, verification / name)
        platforms[target] = {'file': artifact.relative_to(output).as_posix(),
                             'sha256': manifest['artifact_sha256'], 'size_bytes': artifact.stat().st_size}
    release = {
        'release_name': 'Final deliverable for RFID Reader 2026',
        'dashboard_version': VERSION,
        'firmware': {'version': FIRMWARE_VERSION, 'branch': FIRMWARE_BRANCH, 'commit': FIRMWARE_BASELINE,
                     'repository': 'https://github.com/LittleEndianEngineering/RFID_Reader_Github',
                     'hardware': ['PCB v2', 'PCB v3']},
        'source_commit': commits.pop(),
        'dashboard_source': 'source/' + DASHBOARD_FILENAME,
        'dashboard_source_sha256': digest(SOURCE / DASHBOARD_FILENAME),
        'platforms': platforms,
        'validation': {'automated_native_tests': 'passed', 'macos_finder_launch': 'passed',
                       'windows_explorer_launch': 'pending', 'linux_file_manager_launch': 'pending',
                       'physical_pcb_v2_v3_usb_acceptance': 'pending'},
    }
    (output / 'release_manifest.json').write_text(json.dumps(release, indent=2) + '\n', encoding='utf-8')
    readme = f'''# Final deliverable for RFID Reader 2026

Dashboard **{VERSION}**, for the firmware already delivered on PCB v2/v3:
**firmware {FIRMWARE_VERSION}, `{FIRMWARE_BRANCH}`, commit `{FIRMWARE_BASELINE}`**.

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
'''
    (output / 'README.md').write_text(readme, encoding='utf-8')
    lines = [f'{digest(path)}  {path.relative_to(output).as_posix()}'
             for path in sorted(output.rglob('*')) if path.is_file() and path.name != 'SHA256SUMS.txt']
    (output / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(release, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifacts-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'releases/rfid-reader-2026')
    options = parser.parse_args()
    assemble(options.artifacts_root, options.output)
