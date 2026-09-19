param([string]$Compiler = "ISCC.exe", [string]$Version = "0.1.0-preview.1")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if ($Version -notmatch '^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$') { throw "Invalid version." }
if (!(Test-Path -LiteralPath 'dist/参加型整列プラグイン/参加型整列プラグイン.exe')) { throw "Run build-windows.ps1 first." }
$numericVersion=$Version.Split('-')[0]
& $Compiler "/DAppVersion=$Version" "/DFileVersion=$numericVersion" 'installer/WaitingListApp.iss'
if ($LASTEXITCODE -ne 0) { throw "Installer build failed." }
