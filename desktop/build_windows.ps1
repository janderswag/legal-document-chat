# One-command Windows build of docuchat-setup.exe (D-61 scaffold).
# Run on a WINDOWS machine, from the repo root, inside the project venv. See
# desktop/WINDOWS_TEST.md for the full prerequisites + verification runbook.
#
#     powershell -ExecutionPolicy Bypass -File desktop\build_windows.ps1

$ErrorActionPreference = "Stop"

Write-Host "==> Building docuchat-setup with PyInstaller..." -ForegroundColor Cyan
pyinstaller --noconfirm --clean desktop\build_windows.spec

$exe = "dist\docuchat-setup\docuchat-setup.exe"
if (Test-Path $exe) {
    Write-Host "==> Build OK: $exe" -ForegroundColor Green
    Write-Host "    Run it, then verify Ollama detection + the first-run wizard (WINDOWS_TEST.md)."
} else {
    Write-Host "==> Build finished but $exe was not found — check the PyInstaller output above." -ForegroundColor Yellow
    exit 1
}
