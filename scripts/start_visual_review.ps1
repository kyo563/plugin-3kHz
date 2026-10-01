$ErrorActionPreference = 'Stop'
$reviewRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $reviewRoot '.venv\Scripts\python.exe'
if (-not (Get-NetTCPConnection -LocalPort 18879 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $python -ArgumentList @('-u', 'scripts/preview_onecomme.py') -WorkingDirectory $reviewRoot -WindowStyle Hidden
    Start-Sleep -Seconds 3
}
$status = Invoke-RestMethod -Uri 'http://127.0.0.1:18879/preview-status'
if ($status.preview -ne 'joinqueue-isolated-visual-review') { throw 'Port 18879 is used by another application.' }
Start-Process 'http://127.0.0.1:18879/control#key=joinqueue-isolated-visual-review-only-20261001'
