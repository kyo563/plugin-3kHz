param([string]$ReleaseDirectory = 'dist\onecomme-release-0.1.4-redesign-final')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$candidate = Join-Path $repoRoot $ReleaseDirectory
if (-not (Test-Path -LiteralPath (Join-Path $candidate 'Taikiretsu-Seiri-App-OneComme-0.1.4-windows-x64.zip'))) { throw 'Missing candidate ZIP' }
if (-not (Test-Path -LiteralPath (Join-Path $candidate 'SHA256SUMS.txt'))) { throw 'Missing candidate checksums' }
$backup = Join-Path $repoRoot ('dist\release-backup-redesign-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backup | Out-Null
$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE = 'never'
$credentials = "protocol=https`nhost=github.com`n" | git -c credential.interactive=never credential fill
$password = ($credentials | Where-Object { $_ -like 'password=*' }) -replace '^password=',''
if (-not $password) { throw 'GitHub authentication unavailable' }
$headers = @{Authorization="Bearer $password";Accept='application/vnd.github+json';'X-GitHub-Api-Version'='2022-11-28'}
$api = 'https://api.github.com/repos/kyo563/plugin-3kHz'
$release = Invoke-RestMethod -Headers $headers -Uri "$api/releases/tags/onecomme-v0.1.4"
if ($release.id -ne 400028895 -or $release.draft -or $release.prerelease) { throw 'Unexpected release' }
$release | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $backup 'release.json') -Encoding utf8
$names = @('Taikiretsu-Seiri-App-OneComme-0.1.4-windows-x64.zip','SHA256SUMS.txt')
$uploadBase = $release.upload_url -replace '\{.*$',''
$staged = @()
foreach ($name in $names) {
    $old = @($release.assets | Where-Object name -eq $name)
    if ($old.Count -ne 1) { throw 'Missing or ambiguous asset' }
    Invoke-WebRequest -Uri $old[0].browser_download_url -OutFile (Join-Path $backup $name)
    $local = Join-Path $candidate $name
    $tempName = $name + '.redesign-staged'
    $new = Invoke-RestMethod -Method Post -Headers $headers -Uri ($uploadBase + '?name=' + [Uri]::EscapeDataString($tempName)) -ContentType 'application/octet-stream' -InFile $local
    $download = Join-Path $backup ($name + '.verified')
    Invoke-WebRequest -Uri ($new.browser_download_url + '?asset=' + $new.id) -OutFile $download
    if ((Get-FileHash $local).Hash -ne (Get-FileHash $download).Hash) { throw 'Uploaded checksum mismatch' }
    $staged += [pscustomobject]@{name=$name; old=$old[0]; new=$new}
}
foreach ($item in $staged) {
    $null = Invoke-RestMethod -Method Patch -Headers $headers -Uri "$api/releases/assets/$($item.old.id)" -ContentType 'application/json' -Body (@{name=$item.name+'.previous-redesign'} | ConvertTo-Json)
    $null = Invoke-RestMethod -Method Patch -Headers $headers -Uri "$api/releases/assets/$($item.new.id)" -ContentType 'application/json' -Body (@{name=$item.name} | ConvertTo-Json)
}
$body = Get-Content -LiteralPath (Join-Path $repoRoot 'docs\RELEASE_ONECOMME_0.1.4.md') -Raw -Encoding utf8
$json = @{body=$body;draft=$false;prerelease=$false;make_latest='true'} | ConvertTo-Json
$null = Invoke-RestMethod -Method Patch -Headers $headers -Uri "$api/releases/$($release.id)" -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($json))
foreach ($item in $staged) {
    $new = Invoke-RestMethod -Headers $headers -Uri "$api/releases/assets/$($item.new.id)"
    $download = Join-Path $backup ($item.name + '.final')
    Invoke-WebRequest -Uri ($new.browser_download_url + '?asset=' + $new.id) -OutFile $download
    if ((Get-FileHash (Join-Path $candidate $item.name)).Hash -ne (Get-FileHash $download).Hash) { throw 'Final download checksum mismatch; previous assets retained' }
}
# Exact backed-up asset IDs only; the verified new downloads remain available.
foreach ($item in $staged) {
    $null = Invoke-RestMethod -Method Delete -Headers $headers -Uri "$api/releases/assets/$($item.old.id)"
}
[pscustomobject]@{published=$true;backup=$backup;assets=@($staged | ForEach-Object { @{name=$_.name;id=$_.new.id} })} | ConvertTo-Json -Depth 5
