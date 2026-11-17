param([string]$Python = "python")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Program $Arguments" }
}

if (-not [System.Environment]::Is64BitOperatingSystem) { throw "A 64-bit Windows build environment is required." }
Checked $Python @("-c", "import sys,struct; assert sys.platform == 'win32' and struct.calcsize('P') == 8; assert sys.version_info[:2] == (3,11), 'Use 64-bit Python 3.11'")
Checked $Python @("-m", "venv", ".build-venv")
$BuildPython = Join-Path $PSScriptRoot ".build-venv\Scripts\python.exe"
Checked $BuildPython @("-m", "pip", "install", "-r", "requirements-build.txt")
Checked $BuildPython @("-m", "pip", "check")
Checked $BuildPython @("-m", "unittest", "discover", "-s", "tests", "-v")
Checked $BuildPython @("-m", "PyInstaller", "--clean", "--noconfirm", "RFIDDashboard.spec")
Checked $BuildPython @("smoke_executable.py", "dist\RFIDDashboard.exe")
Checked $BuildPython @("-c", "import importlib.metadata,json,pathlib,platform; from customer_protocol import VERSION,FIRMWARE_BASELINE; p=pathlib.Path('dist/build_manifest.json'); p.write_text(json.dumps({'dashboard_version':VERSION,'firmware_baseline':FIRMWARE_BASELINE,'python':platform.python_version(),'machine':platform.machine(),'packages':{d.metadata['Name']:d.version for d in importlib.metadata.distributions()}},indent=2),encoding='utf-8')")
Write-Host "Customer executable ready: $PSScriptRoot\dist\RFIDDashboard.exe"
