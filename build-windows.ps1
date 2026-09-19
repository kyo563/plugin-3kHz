$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm waiting-list.spec
if ($LASTEXITCODE -ne 0) { throw "Windows build failed." }
Write-Output "Created dist/参加型整列プラグイン/参加型整列プラグイン.exe (distribute the entire folder)."
