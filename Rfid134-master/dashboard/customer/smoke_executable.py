"""Build-time checks of the real frozen executable; no reader is required."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess
import time
import urllib.request


def check(executable):
    executable = executable.resolve()
    folder = executable.parent
    report = folder / 'self-test.json'
    subprocess.run([str(executable), '--self-test', '--report', str(report)], check=True, timeout=240)
    details = json.loads(report.read_text(encoding='utf-8'))
    assert details['passed'] and details['frozen'], details
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    with (folder / 'server-smoke.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([str(executable), '--serve', '--port', str(port)], stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 120
            while True:
                if process.poll() is not None:
                    raise RuntimeError('Frozen server exited before becoming healthy. See server-smoke.log.')
                try:
                    with urllib.request.urlopen(url + '/_stcore/health', timeout=1) as response:
                        if response.status == 200 and response.read().strip() == b'ok': break
                except OSError:
                    pass
                if time.monotonic() >= deadline: raise TimeoutError('Frozen server startup timed out')
                time.sleep(.5)
            with urllib.request.urlopen(url, timeout=5) as response:
                html = response.read().decode()
                assert response.status == 200
            assets = re.findall(r'(?:src|href)="(?:\./)?(static/[^\"]+\.(?:js|css))"', html)
            assert assets, 'Streamlit front-end assets were not referenced'
            for asset in assets:
                with urllib.request.urlopen(url + '/' + asset, timeout=10) as response:
                    assert response.status == 200 and len(response.read()) > 0, asset
            (folder / 'server-smoke.json').write_text(json.dumps({'passed': True, 'health': True, 'frontend_assets': assets}, indent=2), encoding='utf-8')
        finally:
            process.terminate()
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    (folder / 'SHA256SUMS.txt').write_text(f'{digest}  {executable.name}\n', encoding='ascii')
    print('Frozen app/UI, local server and bundled front-end assets passed. SHA-256:', digest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('executable', type=Path)
    check(parser.parse_args().executable)
