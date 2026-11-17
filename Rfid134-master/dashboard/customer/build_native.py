"""Build and verify the macOS/Linux release using native Python 3.11."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile

from customer_protocol import VERSION, FIRMWARE_BASELINE

HERE = Path(__file__).resolve().parent
TARGETS = {
    'macos-arm64': ('darwin', 'arm64'),
    'macos-x64': ('darwin', 'x86_64'),
    'linux-x64': ('linux', 'x86_64'),
}


def build(label):
    expected_system, expected_machine = TARGETS[label]
    assert sys.platform == expected_system and platform.machine() == expected_machine
    assert sys.version_info[:2] == (3, 11), 'Use Python 3.11 on the target platform'
    os.chdir(HERE)
    output = HERE / 'dist' / label
    output.mkdir(parents=True, exist_ok=True)
    native_dist = HERE / 'build' / 'native-dist'
    subprocess.run([sys.executable, '-m', 'pip', 'check'], check=True)
    subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], check=True)
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm',
                    '--distpath', str(native_dist), '--workpath', str(HERE / 'build' / 'native-work'),
                    str(HERE / 'RFIDDashboard.spec')], check=True)
    if sys.platform == 'darwin':
        application = native_dist / 'RFIDDashboard.app'
        executable = application / 'Contents' / 'MacOS' / 'RFIDDashboard'
    else:
        application = executable = native_dist / 'RFIDDashboard'
    subprocess.run([sys.executable, str(HERE / 'smoke_executable.py'), str(executable),
                    '--output-dir', str(output)], check=True)
    if sys.platform == 'darwin':
        subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(application)], check=True)
        archive = output / f'RFIDDashboard-{label}.zip'
        subprocess.run(['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                        str(application), str(archive)], check=True)
    else:
        archive = output / f'RFIDDashboard-{label}.tar.gz'
        with tarfile.open(archive, 'w:gz') as target:
            target.add(executable, arcname='RFIDDashboard')
    reference_name = 'rfid_dashboard_configure_lightsleep_multibutton_S3_live_2Ant.py'
    shutil.copy2(HERE / 'app.py', output / reference_name)
    for name in ('customer_protocol.py', 'EB_logo.png'):
        shutil.copy2(HERE / name, output / name)
    manifest = {
        'dashboard_version': VERSION,
        'firmware_baseline': FIRMWARE_BASELINE,
        'source_commit': os.environ.get('GITHUB_SHA'),
        'target': label,
        'system': platform.platform(),
        'machine': platform.machine(),
        'python': platform.python_version(),
        'libc': platform.libc_ver(),
        'archive': archive.name,
        'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'dashboard_source_sha256': hashlib.sha256((HERE / 'app.py').read_bytes()).hexdigest(),
        'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
        'packages': {d.metadata['Name']: d.version for d in importlib.metadata.distributions()},
    }
    (output / 'build_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (output / 'ARCHIVE_SHA256SUMS.txt').write_text(f"{manifest['archive_sha256']}  {archive.name}\n", encoding='ascii')
    if sys.platform == 'darwin':
        instructions = f'''RFID Dashboard {VERSION} - {label}
Requires macOS 15 or later, {'Apple Silicon' if label.endswith('arm64') else 'Intel'}.
Unzip {archive.name}, move RFIDDashboard.app to Applications and open it.
The dashboard opens in your browser. Keep its small control window open;
Close Dashboard stops the server and releases the reader port.
Python and dependencies are bundled. No terminal or Python installation is required.
This build is ad-hoc signed for bundle integrity, without Apple Developer ID/notarization.
macOS may require approval in System Settings > Privacy & Security for a trusted download.
Runtime log: ~/Library/Application Support/EstablishmentLabs/RFIDDashboard/dashboard.log
'''
    else:
        instructions = f'''RFID Dashboard {VERSION} - Linux x64
Built and tested on Ubuntu 22.04 (glibc 2.35). Requires a compatible desktop Linux
installation with glibc 2.35 or later, X11/XWayland display and a default browser.
Extract {archive.name}, then open RFIDDashboard. If your file manager asks,
allow executing the file as a program. You can also run ./RFIDDashboard.
Python and dashboard dependencies are bundled. Keep the small control window open;
Close Dashboard stops the server and releases the reader port.
The signed-in user must have access to the USB serial device; on Ubuntu this is
usually membership in the dialout group. The app does not change system permissions.
Runtime log: $XDG_DATA_HOME/EstablishmentLabs/RFIDDashboard/dashboard.log
(defaults to ~/.local/share/EstablishmentLabs/RFIDDashboard/dashboard.log).
'''
    instructions += f'''
Firmware target: main_2Ant / {FIRMWARE_BASELINE}, PCB v2/v3.
Firmware is unchanged; individual antenna commands remain hidden.
The .py and helper/logo files are reference copies, not required to run the package.
Actual USB reader/PCB acceptance testing is still required before customer delivery.
'''
    (output / 'README.txt').write_text(instructions, encoding='utf-8')
    print(f'Verified {label} package: {archive}\nSHA-256: {manifest["archive_sha256"]}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', choices=TARGETS, required=True)
    build(parser.parse_args().target)
