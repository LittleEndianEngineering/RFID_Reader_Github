param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$CustomerRoot = Split-Path $PSScriptRoot -Parent
Set-Location $CustomerRoot

function Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Program $Arguments" }
}

# Final RFID Reader 2026 dashboard; firmware 1.5/main_2Ant/dbf098d is unchanged.
Checked $Python @("-c", "import sys,struct; assert sys.platform == 'win32' and struct.calcsize('P') == 8; assert sys.version_info[:2] == (3,11), 'Use 64-bit Python 3.11'")
Checked $Python @("-m", "venv", ".build-venv")
$BuildPython = Join-Path $CustomerRoot ".build-venv\Scripts\python.exe"
Checked $BuildPython @("-m", "pip", "install", "-r", "packaging\requirements-build.txt")
Checked $BuildPython @("packaging\build.py", "--target", "windows-x64")
Write-Host "Verified executable: $CustomerRoot\dist\windows-x64\RFIDDashboard.exe"
