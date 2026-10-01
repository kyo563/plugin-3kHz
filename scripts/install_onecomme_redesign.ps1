param(
    [string]$ReleaseDirectory = 'dist\onecomme-release-0.1.4-redesign-final',
    [string]$ExpectedHash = '39746adefd113b80372625e89ef5cadad4cd7da329e7ae167aaa3fa773ba5653'
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$candidate = Join-Path (Join-Path $repoRoot $ReleaseDirectory) 'sankagata-seiretsu'
$archive = Join-Path (Split-Path -Parent $candidate) 'Taikiretsu-Seiri-App-OneComme-0.1.4-windows-x64.zip'
$plugins = Join-Path $env:APPDATA 'onecomme\plugins'
$target = Join-Path $plugins 'sankagata-seiretsu'
$data = Join-Path $env:LOCALAPPDATA 'WaitingListAppOneComme'
$backupRoot = Join-Path $env:LOCALAPPDATA 'WaitingListAppOneComme-backups'
$backup = Join-Path $backupRoot ('redesign-20261001-' + (Get-Date -Format 'HHmmss'))
if ((Get-Process | Where-Object { $_.ProcessName -match 'onecomme|QueueWorker' }) -or (Get-NetTCPConnection -LocalPort 18765 -State Listen -ErrorAction SilentlyContinue)) { throw 'Close OneComme and its worker first.' }
if ($ExpectedHash -notmatch '^[a-f0-9]{64}$' -or (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower() -ne $ExpectedHash) { throw 'Candidate hash mismatch' }
if (-not (Test-Path -LiteralPath $target -PathType Container)) { throw 'Existing installation not found' }
# Resolve exact source/destination before moving this one plugin directory.
$target = (Resolve-Path -LiteralPath $target).Path
$expected = [IO.Path]::GetFullPath((Join-Path $plugins 'sankagata-seiretsu'))
if ($target -ne $expected -or -not [IO.Path]::GetFullPath($backup).StartsWith([IO.Path]::GetFullPath($backupRoot) + '\')) { throw 'Unexpected target boundary' }
if (Get-Item -LiteralPath $target | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) { throw 'Unexpected target reparse point' }
if (Get-ChildItem -LiteralPath $target -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) { throw 'Unexpected installed reparse point' }
function Manifest($path) {
    $result = @{}
    if (Test-Path -LiteralPath $path) {
        foreach ($file in Get-ChildItem -LiteralPath $path -File -Recurse -Force) {
            $result[$file.FullName.Substring($path.Length)] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
        }
    }
    return $result
}
$before = Manifest $data
New-Item -ItemType Directory -Path $backup | Out-Null
# Extract the verified archive outside OneDrive instead of copying cloud placeholders.
$staging = Join-Path $backup 'staging'
Expand-Archive -LiteralPath $archive -DestinationPath $staging
$candidate = Join-Path $staging 'sankagata-seiretsu'
if (-not (Test-Path -LiteralPath (Join-Path $candidate 'plugin.js'))) { throw 'Invalid archive layout' }
if (Get-ChildItem -LiteralPath $candidate -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) { throw 'Unexpected staged reparse point' }
if (Test-Path -LiteralPath $data) { Copy-Item -LiteralPath $data -Destination (Join-Path $backup 'saved-data') -Recurse }
Move-Item -LiteralPath $target -Destination (Join-Path $backup 'plugin')
try {
    Copy-Item -LiteralPath $candidate -Destination $target -Recurse
    $expectedFiles = Manifest $candidate
    $actualFiles = Manifest $target
    if ($expectedFiles.Count -ne $actualFiles.Count) { throw 'Installed file count mismatch' }
    foreach ($name in $expectedFiles.Keys) { if ($expectedFiles[$name] -ne $actualFiles[$name]) { throw 'Installed hash mismatch' } }
    $after = Manifest $data
    if ($before.Count -ne $after.Count) { throw 'Saved data changed' }
    foreach ($name in $before.Keys) { if ($before[$name] -ne $after[$name]) { throw 'Saved data changed' } }
    [pscustomobject]@{installed=$true; files=$actualFiles.Count; dataUnchanged=$true; backup=$backup} | ConvertTo-Json -Compress
} catch {
    if (Test-Path -LiteralPath $target) { Move-Item -LiteralPath $target -Destination (Join-Path $backup 'failed-candidate') }
    Move-Item -LiteralPath (Join-Path $backup 'plugin') -Destination $target
    throw
}
