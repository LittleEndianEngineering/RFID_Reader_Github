# Run on the target platform: python -m PyInstaller --clean --noconfirm RFIDDashboard.spec
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all, copy_metadata

HERE = Path(SPECPATH)
datas = [(str(HERE / 'app.py'), 'customer'), (str(HERE / 'EB_logo.png'), 'customer')]
binaries = []
hiddenimports = ['customer_protocol', 'plotly.express', 'serial.tools.list_ports', 'pytz', 'streamlit.testing.v1']
for package in ['streamlit', 'plotly']:
    package_datas, package_binaries, package_imports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_imports
for distribution in ['streamlit', 'pandas', 'plotly', 'pyserial', 'pytz']:
    datas += copy_metadata(distribution)

a = Analysis([str(HERE / 'launcher.py')], pathex=[str(HERE)], binaries=binaries,
             datas=datas, hiddenimports=hiddenimports, hookspath=[], hooksconfig={},
             runtime_hooks=[], excludes=['IPython', 'jupyter', 'matplotlib', 'scipy'],
             noarchive=False)
pyz = PYZ(a.pure)
if sys.platform == 'darwin':
    # A normal app bundle opens in Finder without one-file extraction on every launch.
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='RFIDDashboard',
              debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
              console=False, disable_windowed_traceback=False, argv_emulation=False)
    collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='RFIDDashboard')
    app = BUNDLE(collection, name='RFIDDashboard.app',
                 bundle_identifier='com.establishmentlabs.rfiddashboard',
                 info_plist={'CFBundleDisplayName': 'RFID Dashboard',
                             'CFBundleShortVersionString': '6.2.0',
                             'CFBundleVersion': '6.2.0',
                             'LSMinimumSystemVersion': '15.0',
                             'NSHighResolutionCapable': True,
                             'LSUIElement': True})
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='RFIDDashboard',
              debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
              console=False, disable_windowed_traceback=False)
