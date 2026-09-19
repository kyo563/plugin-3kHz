param([string]$Python = "python")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
& $Python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Python 3.12 x64 is required to create the environment." }
& .\.venv\Scripts\python.exe -m pip install -r requirements-windows.lock.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
