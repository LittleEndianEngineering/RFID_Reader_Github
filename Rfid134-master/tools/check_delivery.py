"""Read-only identity checks for a recorded customer delivery; standard library only."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile


class DeliveryError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise DeliveryError(message)


def stream_digest(stream):
    result = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        result.update(block)
    return result.hexdigest()


def digest(path):
    with Path(path).open('rb') as stream:
        return stream_digest(stream)


def git(project, *args):
    result = subprocess.run(['git', *args], cwd=project, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False)
    require(result.returncode == 0, 'Git object unavailable: ' + ' '.join(args)
            + '. Fetch the recorded commits before checking this delivery.')
    return result.stdout


def tree(project, commit, path):
    return git(project, 'rev-parse', '--verify', commit + ':' + path).decode().strip()


def safe_file(root, name):
    root = Path(root).resolve()
    path = (root / name).resolve()
    require(path != root and root in path.parents, 'Path escapes its root: ' + name)
    return path


def compare_worktree(project, commit, git_path):
    git_root = Path(git(project, 'rev-parse', '--show-toplevel').decode().strip())
    names = git(git_root, 'ls-tree', '--full-tree', '-rz', '--name-only', commit, '--', git_path)
    expected = {name.decode() for name in names.split(b'\0') if name}
    folder = safe_file(git_root, git_path)
    # Python caches and Finder metadata are generated, not build inputs.
    files = {path.relative_to(git_root).as_posix(): path for path in folder.rglob('*')
             if path.is_file() and '__pycache__' not in path.parts
             and path.name != '.DS_Store' and path.suffix not in ('.pyc', '.pyo')}
    require(set(files) == expected, 'Working-tree file set differs: ' + git_path)
    changed = [name for name in sorted(expected)
               if hashlib.sha256(git(project, 'show', commit + ':' + name)).hexdigest()
               != digest(files[name])]
    require(not changed, 'Working-tree experimental/modified files: ' + ', '.join(changed))


def check_delivery(record, project, candidate=None, package=None, working_tree=False):
    require(record['schema_version'] == 1, 'Unsupported delivery record schema')
    firmware = record['firmware']
    dashboard = record['dashboard']
    candidate = candidate or dashboard['release_commit']
    # Resolve to a commit first; a tree/tag name alone is not a build identity.
    candidate = git(project, 'rev-parse', '--verify', candidate + '^{commit}').decode().strip()
    baseline = firmware['commit']
    require(tree(project, baseline, firmware['git_path']) == firmware['git_tree'],
            'Recorded firmware tree does not match its baseline commit')
    for commit in (candidate, dashboard['build_commit']):
        require(tree(project, commit, firmware['git_path']) == firmware['git_tree'],
                'Firmware differs from the customer-delivered baseline: ' + commit)
    for item in dashboard['build_trees']:
        for commit in (candidate, dashboard['build_commit']):
            require(tree(project, commit, item['git_path']) == item['git_tree'],
                    'Dashboard/build source differs from this frozen delivery: ' + item['git_path'])
    source = git(project, 'show', candidate + ':' + dashboard['source_git_path'])
    require(hashlib.sha256(source).hexdigest() == dashboard['source_sha256'],
            'Committed dashboard source hash mismatch')
    helper = git(project, 'show', candidate + ':' + dashboard['metadata_git_path'])
    values = {}
    for node in ast.parse(helper).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    values[target.id] = node.value.value
    for key, value in [('VERSION', dashboard['version']), ('FIRMWARE_VERSION', firmware['version']),
                       ('FIRMWARE_BRANCH', firmware['branch']), ('FIRMWARE_BASELINE', baseline)]:
        require(values.get(key) == value, 'Dashboard firmware/version metadata mismatch: ' + key)
    messages = ['Committed firmware and dashboard/build identities match ' + record['delivery_id']]

    # Downloaded canonical artifacts are outside the dirty experimental source paths.
    snapshot = safe_file(project, dashboard['artifact_snapshot'])
    source_file = safe_file(snapshot, dashboard['snapshot_source'])
    require(source_file.is_file() and digest(source_file) == dashboard['source_sha256'],
            'Release source snapshot missing or changed: ' + str(source_file))
    for target, artifact in dashboard['artifacts'].items():
        path = safe_file(snapshot, artifact['file'])
        require(path.is_file() and path.stat().st_size == artifact['size_bytes']
                and digest(path) == artifact['sha256'],
                'Release artifact missing or changed: ' + target + '. Download Git LFS objects if needed.')
    messages.append('Canonical release source and platform package hashes match')

    if working_tree:
        compare_worktree(project, baseline, firmware['git_path'])
        for item in dashboard['build_trees']:
            compare_worktree(project, dashboard['build_commit'], item['git_path'])
        messages.append('Working-tree firmware/customer build inputs match the pinned commits')

    if package is not None:
        package = Path(package)
        if not package.is_absolute():
            package = Path(project) / package
        wanted = record['customer_package']
        require(package.is_file() and package.stat().st_size == wanted['size_bytes']
                and digest(package) == wanted['sha256'], 'Customer ZIP is missing or does not match this delivery')
        expected = {entry['file']: entry for entry in wanted['entries']}
        with zipfile.ZipFile(package) as archive:
            require(len(archive.infolist()) == len(expected)
                    and set(archive.namelist()) == set(expected), 'Unexpected or duplicate customer ZIP entries')
            for name, entry in expected.items():
                require(archive.getinfo(name).file_size == entry['size_bytes'], 'ZIP entry size mismatch: ' + name)
                with archive.open(name) as stream:
                    require(stream_digest(stream) == entry['sha256'], 'ZIP entry hash mismatch: ' + name)
        messages.append('Exact customer ZIP and every contained file match')
    messages.append('Acceptance state: ' + record['status'] + '; identity checks do not establish hardware compatibility')
    return messages


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', type=Path, default=project / 'release_records/delivery-v6.json')
    parser.add_argument('--candidate', help='Committed candidate ref; defaults to the recorded release commit')
    parser.add_argument('--package', type=Path, help='Also verify the simple customer ZIP')
    parser.add_argument('--working-tree', action='store_true', help='Reject dirty/experimental firmware or customer build inputs')
    args = parser.parse_args()
    try:
        record = json.loads(args.record.read_text(encoding='utf-8'))
        messages = check_delivery(record, project, args.candidate, args.package, args.working_tree)
    except (DeliveryError, OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        return 1
    for message in messages:
        print('OK: ' + message)
    return 0


if __name__ == '__main__':
    sys.exit(main())
