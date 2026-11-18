"""Protect firmware/source/package identity when assembling a customer release."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'packaging'))
import assemble_release as release


class ReleaseIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.executable = self.folder / 'RFIDDashboard.exe'
        self.executable.write_bytes(b'MZ release-integrity fixture')
        for name in (release.DASHBOARD_FILENAME, 'customer_protocol.py', 'EB_logo.png'):
            shutil.copy2(release.SOURCE / name, self.folder / name)
        self.manifest = dict(target='windows-x64', dashboard_version=release.VERSION,
                             firmware_version=release.FIRMWARE_VERSION, firmware_branch=release.FIRMWARE_BRANCH,
                             firmware_baseline=release.FIRMWARE_BASELINE,
                             dashboard_source_sha256=release.digest(release.SOURCE / release.DASHBOARD_FILENAME),
                             source_commit='a' * 40, artifact=self.executable.name,
                             artifact_sha256=release.digest(self.executable), executable_sha256=release.digest(self.executable))
        self.write_manifest()
        (self.folder / 'self-test.json').write_text(json.dumps(dict(passed=True, frozen=True, native_window=True,
                                                                  version=release.VERSION, firmware_baseline=release.FIRMWARE_BASELINE)))
        (self.folder / 'server-smoke.json').write_text(json.dumps(dict(passed=True, health=True,
                                                                     frontend_assets=['test.js'], shutdown_released_port=True)))

    def write_manifest(self):
        (self.folder / 'build_manifest.json').write_text(json.dumps(self.manifest))

    def test_package_tampering_is_rejected(self):
        release.validate_artifact(self.folder, 'windows-x64')
        self.executable.write_bytes(b'changed binary')
        with self.assertRaises(AssertionError):
            release.validate_artifact(self.folder, 'windows-x64')

    def test_wrong_delivered_firmware_commit_is_rejected(self):
        self.manifest['firmware_baseline'] = '0' * 40
        self.write_manifest()
        with self.assertRaises(AssertionError):
            release.validate_artifact(self.folder, 'windows-x64')

    def test_mismatched_reference_source_is_rejected(self):
        (self.folder / release.DASHBOARD_FILENAME).write_text('different dashboard')
        with self.assertRaises(AssertionError):
            release.validate_artifact(self.folder, 'windows-x64')

    def test_mixed_build_commits_are_rejected_before_creating_release(self):
        output = self.folder / 'release'
        manifests = [dict(source_commit=('a' if i == 0 else 'b') * 40) for i in range(4)]
        with mock.patch.object(release, 'validate_artifact', side_effect=manifests):
            with self.assertRaises(AssertionError):
                release.assemble(self.folder, output)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
