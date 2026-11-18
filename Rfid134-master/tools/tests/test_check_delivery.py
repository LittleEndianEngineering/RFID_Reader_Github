"""Exercise wrong-firmware, dirty-source and artifact-mixup release failures."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_delivery import check_delivery, DeliveryError, digest


class DeliveryChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.run_git('init', '-q')
        self.write('firmware/main.cpp', '// delivered firmware\n')
        self.write('customer/src/dashboard.py', '# dashboard 6.2.1\n')
        self.write('customer/packaging/build.py', '# packaging\n')
        self.write('customer/src/customer_protocol.py', 'VERSION="6.2.1"\nFIRMWARE_VERSION="1.5"\nFIRMWARE_BRANCH="main_2Ant"\nFIRMWARE_BASELINE="PLACEHOLDER"\n')
        self.baseline = self.commit('baseline')
        self.write('customer/src/customer_protocol.py',
                   (self.project / 'customer/src/customer_protocol.py').read_text().replace('PLACEHOLDER', self.baseline))
        self.release = self.commit('customer dashboard')
        self.write('snapshot/source/dashboard.py', '# dashboard 6.2.1\n')
        self.write('snapshot/windows-x64/RFIDDashboard.exe', 'native application fixture\n')
        package = self.project / 'customer.zip'
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr('RFIDDashboard.exe', b'native application fixture\n')
            archive.writestr('dashboard.py', b'# dashboard 6.2.1\n')
        with zipfile.ZipFile(package) as archive:
            entries = [{'file': name, 'size_bytes': archive.getinfo(name).file_size,
                        'sha256': hashlib.sha256(archive.read(name)).hexdigest()} for name in archive.namelist()]
        artifact = self.project / 'snapshot/windows-x64/RFIDDashboard.exe'
        self.record = {
            'schema_version': 1, 'delivery_id': 'v6', 'status': 'prepared_for_customer_testing',
            'firmware': {'version': '1.5', 'branch': 'main_2Ant', 'commit': self.baseline,
                         'git_path': 'firmware', 'git_tree': self.object_id(self.baseline, 'firmware')},
            'dashboard': {'version': '6.2.1', 'build_commit': self.release, 'release_commit': self.release,
                          'source_git_path': 'customer/src/dashboard.py',
                          'source_sha256': digest(self.project / 'customer/src/dashboard.py'),
                          'metadata_git_path': 'customer/src/customer_protocol.py',
                          'build_trees': [{'git_path': path, 'git_tree': self.object_id(self.release, path)}
                                          for path in ('customer/src', 'customer/packaging')],
                          'artifact_snapshot': 'snapshot', 'snapshot_source': 'source/dashboard.py',
                          'artifacts': {'windows-x64': {'file': 'windows-x64/RFIDDashboard.exe',
                                       'size_bytes': artifact.stat().st_size, 'sha256': digest(artifact)}}},
            'customer_package': {'size_bytes': package.stat().st_size, 'sha256': digest(package), 'entries': entries}}

    def run_git(self, *args):
        return subprocess.check_output(['git', '-c', 'user.name=Release Test', '-c',
                                        'user.email=release-test@example.invalid', '-c',
                                        'core.hooksPath=/dev/null', *args], cwd=self.project).decode().strip()

    def write(self, name, content):
        file = self.project / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    def commit(self, message):
        self.run_git('add', 'firmware', 'customer')
        self.run_git('commit', '-q', '-m', message)
        return self.run_git('rev-parse', 'HEAD')

    def object_id(self, commit, path):
        return self.run_git('rev-parse', commit + ':' + path)

    def test_frozen_delivery_with_package_passes(self):
        messages = check_delivery(self.record, self.project, package='customer.zip', working_tree=True)
        self.assertTrue(any('Exact customer ZIP' in message for message in messages))

    def test_changed_committed_firmware_is_rejected(self):
        self.write('firmware/main.cpp', '// experimental firmware\n')
        changed = self.commit('mobile firmware')
        with self.assertRaisesRegex(DeliveryError, 'Firmware differs'):
            check_delivery(self.record, self.project, candidate=changed)

    def test_dirty_firmware_does_not_impersonate_release(self):
        self.write('firmware/main.cpp', '// uncommitted mobile firmware\n')
        check_delivery(self.record, self.project)
        with self.assertRaisesRegex(DeliveryError, 'Working-tree experimental'):
            check_delivery(self.record, self.project, working_tree=True)

    def test_changed_dashboard_is_not_unchanged_v6(self):
        self.write('customer/src/dashboard.py', '# dashboard hotfix\n')
        changed = self.commit('dashboard change')
        with self.assertRaisesRegex(DeliveryError, 'Dashboard/build source differs'):
            check_delivery(self.record, self.project, candidate=changed)

    def test_artifact_tampering_is_rejected(self):
        self.write('snapshot/windows-x64/RFIDDashboard.exe', 'wrong build\n')
        with self.assertRaisesRegex(DeliveryError, 'Release artifact missing or changed'):
            check_delivery(self.record, self.project)

    def test_replaced_zip_is_rejected(self):
        self.write('customer.zip', 'replacement file')
        with self.assertRaisesRegex(DeliveryError, 'Customer ZIP is missing or does not match'):
            check_delivery(self.record, self.project, package='customer.zip')

    def test_wrong_version_metadata_is_rejected(self):
        record = copy.deepcopy(self.record)
        record['dashboard']['version'] = '6.2.2'
        with self.assertRaisesRegex(DeliveryError, 'metadata mismatch: VERSION'):
            check_delivery(record, self.project)

    def test_extra_source_input_is_rejected(self):
        self.write('firmware/mobile_extension.cpp', '// uncommitted extra input\n')
        with self.assertRaisesRegex(DeliveryError, 'Working-tree file set differs'):
            check_delivery(self.record, self.project, working_tree=True)


if __name__ == '__main__':
    unittest.main()
