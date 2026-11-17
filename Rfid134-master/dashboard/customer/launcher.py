"""Double-click launcher for the self-contained Windows customer dashboard."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from urllib.parse import urlparse
import webbrowser

APP_NAME = 'RFIDDashboard'
VERSION = '6.2.0'
BASELINE = 'dbf098dbd869d88fe63274aad421fdba6d7ed18a'


def resource_directory():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'customer'
    return Path(__file__).resolve().parent


def runtime_directory():
    base = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share'))
    path = base / 'EstablishmentLabs' / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def available_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def local_url(value):
    try:
        parsed = urlparse(value)
        if parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port and parsed.path in ('', '/'):
            return value
    except (TypeError, ValueError):
        pass
    return None


def healthy(url):
    if not local_url(url):
        return False
    try:
        with urllib.request.urlopen(url.rstrip('/') + '/_stcore/health', timeout=0.3) as response:
            return response.status == 200 and response.read(64).strip() == b'ok'
    except (OSError, urllib.error.URLError):
        return False


class InstanceLock:
    def __init__(self, path):
        self.path = Path(path)
        self.file = None

    def acquire(self):
        self.file = self.path.open('a+b')
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b'0')
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            self.file = None
            return False
        return True

    def close(self):
        if self.file is not None:
            self.file.close()
            self.file = None


def child_command(port):
    args = ['--serve', '--port', str(port)]
    if getattr(sys, 'frozen', False):
        return [sys.executable, *args]
    return [sys.executable, str(Path(__file__).resolve()), *args]


def serve(port):
    from streamlit.web import bootstrap
    # No network access is needed at runtime. Serve the UI only on this computer.
    options = {
        'server.address': '127.0.0.1',
        'server.port': port,
        'server.headless': True,
        'server.fileWatcherType': 'none',
        'server.runOnSave': False,
        'browser.gatherUsageStats': False,
        'global.developmentMode': False,
    }
    # bootstrap.run does not apply CLI options itself; load them before creating Server.
    bootstrap.load_config_options(options)
    bootstrap.run(str(resource_directory() / 'app.py'), False, [], options)


def self_test(report):
    result = {'version': VERSION, 'firmware_baseline': BASELINE, 'frozen': bool(getattr(sys, 'frozen', False))}
    try:
        import pandas
        import plotly.express
        import serial.tools.list_ports
        import pytz
        from streamlit.testing.v1 import AppTest
        app = resource_directory() / 'app.py'
        assert app.is_file() and (app.parent / 'EB_logo.png').is_file()
        # This renders the actual customer UI without opening any serial port.
        test = AppTest.from_file(str(app), default_timeout=60).run()
        assert not test.exception, '\n'.join(str(item.value) for item in test.exception)
        labels = [button.label for button in test.button]
        assert 'Read ANT1' not in labels and 'Read ANT2' not in labels
        assert 'Set Variables on ESP32' in labels
        result['packages'] = {name: importlib.metadata.version(name) for name in ('streamlit', 'pandas', 'plotly', 'pyserial', 'pytz')}
        if sys.platform == 'win32':
            import tkinter
            root = tkinter.Tk()
            root.withdraw()
            root.update_idletasks()
            root.destroy()
            result['native_window'] = True
        result['passed'] = True
    except Exception:
        result['passed'] = False
        result['error'] = traceback.format_exc()
    output = json.dumps(result, indent=2)
    if report:
        Path(report).write_text(output, encoding='utf-8')
    elif sys.stdout:
        print(output)
    return 0 if result['passed'] else 1


def launch():
    import tkinter as tk
    from tkinter import messagebox

    folder = runtime_directory()
    state = folder / 'instance.json'
    lock = InstanceLock(folder / 'instance.lock')
    if not lock.acquire():
        for _ in range(100):
            try:
                url = local_url(json.loads(state.read_text(encoding='utf-8')).get('url'))
            except (OSError, ValueError):
                url = None
            if url and healthy(url):
                webbrowser.open(url, new=0)
                return 0
            time.sleep(0.3)
        messagebox.showinfo('RFID Dashboard', 'The dashboard is already starting. Please use its control window.')
        return 0

    process = None
    log = None
    root = None
    try:
        root = tk.Tk()
        root.title('RFID Dashboard')
        root.geometry('430x190')
        root.resizable(False, False)
        label = tk.StringVar(value='Starting the dashboard...')
        tk.Label(root, text='Implant RFID Reader', font=('Segoe UI', 16, 'bold')).pack(pady=(18, 8))
        tk.Label(root, textvariable=label, wraplength=400).pack(pady=4)
        port = available_port()
        url = f'http://127.0.0.1:{port}/'
        state.write_text(json.dumps({'url': url}), encoding='utf-8')
        log = (folder / 'dashboard.log').open('w', encoding='utf-8')
        options = {'cwd': str(folder), 'stdout': log, 'stderr': subprocess.STDOUT}
        if os.name == 'nt':
            options['creationflags'] = subprocess.CREATE_NO_WINDOW
        process = subprocess.Popen(child_command(port), **options)
        open_button = tk.Button(root, text='Open Dashboard', command=lambda: webbrowser.open(url, new=0), state='disabled')
        open_button.pack(pady=(8, 4))
        tk.Button(root, text='Close Dashboard', command=root.destroy).pack()
        root.protocol('WM_DELETE_WINDOW', root.destroy)
        deadline = time.monotonic() + 120
        opened = False

        def check():
            nonlocal opened
            if process.poll() is not None:
                label.set('The dashboard stopped. Close this window and try again.')
                if not opened:
                    messagebox.showerror('RFID Dashboard', f'The dashboard could not start. Details are in:\n{folder / "dashboard.log"}')
                return
            if not opened and healthy(url):
                opened = True
                open_button.configure(state='normal')
                label.set('The dashboard is running. Keep this window open while using the reader.')
                webbrowser.open(url, new=0)
            elif not opened and time.monotonic() > deadline:
                label.set('Startup took too long. Close this window and try again.')
                return
            root.after(500, check)

        root.after(200, check)
        root.mainloop()
        return 0
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if log:
            log.close()
        state.unlink(missing_ok=True)
        lock.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--port', type=int, default=8501)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--report')
    args = parser.parse_args()
    if args.self_test:
        return self_test(args.report)
    if args.serve:
        serve(args.port)
        return 0
    return launch()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        folder = runtime_directory()
        detail = traceback.format_exc()
        (folder / 'launcher-error.log').write_text(detail, encoding='utf-8')
        if sys.stderr:
            sys.stderr.write(detail)
        if '--serve' not in sys.argv and '--self-test' not in sys.argv:
            import tkinter.messagebox
            tkinter.messagebox.showerror('RFID Dashboard', f'Unable to open the dashboard. Details are in:\n{folder / "launcher-error.log"}')
        raise SystemExit(1)
