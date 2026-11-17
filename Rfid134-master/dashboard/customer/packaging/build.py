"""Build RFID Reader 2026 dashboard 6.2.1 for delivered firmware 1.5/dbf098d."""
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

PACKAGING = Path(__file__).resolve().parent
ROOT = PACKAGING.parent
SOURCE = ROOT / 'src'
sys.path.insert(0, str(SOURCE))
from customer_protocol import VERSION, FIRMWARE_BASELINE, FIRMWARE_VERSION, FIRMWARE_BRANCH, DASHBOARD_FILENAME

TARGETS = {'windows-x64': ('win32', 'AMD64'), 'macos-arm64': ('darwin', 'arm64'),
           'macos-x64': ('darwin', 'x86_64'), 'linux-x64': ('linux', 'x86_64')}


def build(target):
    expected_system, expected_machine = TARGETS[target]
    assert sys.platform == expected_system and platform.machine() == expected_machine
    assert sys.version_info[:2] == (3, 11), 'Use Python 3.11 on the target platform'
    os.chdir(ROOT)
    output = ROOT / 'dist' / target
    output.mkdir(parents=True, exist_ok=True)
    native_dist = ROOT / 'build' / target / 'dist'
    subprocess.run([sys.executable, '-m', 'pip', 'check'], check=True)
    subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(ROOT / 'tests'), '-v'], check=True)
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm',
                    '--distpath', str(native_dist), '--workpath', str(ROOT / 'build' / target / 'work'),
                    str(PACKAGING / 'RFIDDashboard.spec')], check=True)
    if sys.platform == 'darwin':
        application = native_dist / 'RFIDDashboard.app'
        executable = application / 'Contents' / 'MacOS' / 'RFIDDashboard'
    else:
        executable = native_dist / ('RFIDDashboard.exe' if sys.platform == 'win32' else 'RFIDDashboard')
    subprocess.run([sys.executable, str(PACKAGING / 'smoke_executable.py'), str(executable),
                    '--output-dir', str(output)], check=True)
    if sys.platform == 'darwin':
        subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(application)], check=True)
        artifact = output / f'RFIDDashboard-{target}.zip'
        subprocess.run(['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                        str(application), str(artifact)], check=True)
    elif sys.platform == 'win32':
        artifact = output / 'RFIDDashboard.exe'
        shutil.copy2(executable, artifact)
    else:
        artifact = output / f'RFIDDashboard-{target}.tar.gz'
        with tarfile.open(artifact, 'w:gz') as archive:
            archive.add(executable, arcname='RFIDDashboard')
    for name in (DASHBOARD_FILENAME, 'customer_protocol.py', 'EB_logo.png'):
        shutil.copy2(SOURCE / name, output / name)
    shutil.copy2(PACKAGING / 'requirements.txt', output / 'requirements.txt')
    manifest = {
        'release_name': 'Final deliverable for RFID Reader 2026',
        'dashboard_version': VERSION, 'firmware_version': FIRMWARE_VERSION,
        'firmware_branch': FIRMWARE_BRANCH, 'firmware_baseline': FIRMWARE_BASELINE,
        'customer_hardware': ['PCB v2', 'PCB v3'],
        'source_commit': os.environ.get('GITHUB_SHA'), 'target': target,
        'system': platform.platform(), 'machine': platform.machine(),
        'python': platform.python_version(), 'libc': platform.libc_ver(),
        'artifact': artifact.name,
        'artifact_sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
        'dashboard_filename': DASHBOARD_FILENAME,
        'dashboard_source_sha256': hashlib.sha256((SOURCE / DASHBOARD_FILENAME).read_bytes()).hexdigest(),
        'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
        'packages': {d.metadata['Name']: d.version for d in importlib.metadata.distributions()},
    }
    (output / 'build_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (output / 'ARTIFACT_SHA256SUMS.txt').write_text(f"{manifest['artifact_sha256']}  {artifact.name}\n", encoding='ascii')
    print(f"Verified {target} dashboard {VERSION} for firmware {FIRMWARE_VERSION} ({FIRMWARE_BASELINE}): {artifact}", flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', choices=TARGETS, required=True)
    build(parser.parse_args().target)
