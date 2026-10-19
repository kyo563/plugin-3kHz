param(
    [string]$ReleaseDirectory = 'dist\onecomme-release-0.1.7-audit-20261020',
    [string]$ExpectedOldHash = '0c227c88ecce71691dce5cbb2ea26370d856d0394eee4f8b3f3883fe4b27d136'
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$candidate = Join-Path $repoRoot $ReleaseDirectory
$zipName = 'Taikiretsu-Seiri-App-OneComme-0.1.7-windows-x64.zip'
$names = @($zipName, 'SHA256SUMS.txt')
$checksums = Get-Content -LiteralPath (Join-Path $candidate 'SHA256SUMS.txt') -Raw
$zipHash = (Get-FileHash -LiteralPath (Join-Path $candidate $zipName)).Hash.ToLowerInvariant()
if (-not $checksums.Contains($zipHash + '  ' + $zipName)) { throw 'Candidate checksum mismatch' }
$commit = (& git -C $repoRoot rev-parse HEAD).Trim()
if ($commit -notmatch '^[a-f0-9]{40}$') { throw 'Missing source commit' }
$backup = Join-Path $repoRoot ('dist\release-backup-0.1.7-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backup | Out-Null
$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE = 'never'
$credentials = "protocol=https`nhost=github.com`n" | git -c credential.interactive=never credential fill
$password = ($credentials | Where-Object { $_ -like 'password=*' }) -replace '^password=',''
if (-not $password) { throw 'GitHub authentication unavailable' }
$headers = @{Authorization="Bearer $password";Accept='application/vnd.github+json';'X-GitHub-Api-Version'='2022-11-28'}
$api = 'https://api.github.com/repos/kyo563/plugin-3kHz'
$release = Invoke-RestMethod -Headers $headers -Uri "$api/releases/tags/onecomme-v0.1.7"
if ($release.id -ne 417430017 -or $release.draft -or $release.prerelease) { throw 'Unexpected release' }
$oldZip = @($release.assets | Where-Object name -eq $zipName)
if ($oldZip.Count -ne 1 -or $oldZip[0].digest -ne "sha256:$ExpectedOldHash") { throw 'Unexpected existing archive; do not replace it' }
$release | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $backup 'release.json') -Encoding utf8
function Download-Verified($url, $destination, $expected) {
    for ($attempt = 0; $attempt -lt 5; $attempt++) {
        & curl.exe --fail --location --silent --show-error --output $destination $url
        if ($LASTEXITCODE -eq 0 -and (Get-FileHash -LiteralPath $destination).Hash.ToLowerInvariant() -eq $expected) { return }
        if ($attempt -lt 4) { Start-Sleep -Seconds 3 }
    }
    throw 'Anonymous download verification failed; previous assets are retained'
}
$staged = @()
$uploadBase = $release.upload_url -replace '\{.*$',''
foreach ($name in $names) {
    $old = @($release.assets | Where-Object name -eq $name)
    if ($old.Count -ne 1) { throw 'Missing or ambiguous old asset' }
    Download-Verified $old[0].browser_download_url (Join-Path $backup $name) ($old[0].digest -replace '^sha256:','')
    $local = Join-Path $candidate $name
    $hash = (Get-FileHash -LiteralPath $local).Hash.ToLowerInvariant()
    $temporaryName = $name + '.audit-update-staged'
    $new = Invoke-RestMethod -Method Post -Headers $headers -Uri ($uploadBase + '?name=' + [Uri]::EscapeDataString($temporaryName)) -ContentType 'application/octet-stream' -InFile $local
    if ($new.digest -ne "sha256:$hash" -or $new.size -ne (Get-Item -LiteralPath $local).Length) { throw 'Staged digest mismatch' }
    Download-Verified $new.browser_download_url (Join-Path $backup ($name + '.staged-verified')) $hash
    $staged += [pscustomobject]@{name=$name;old=$old[0];new=$new;hash=$hash}
}
foreach ($item in $staged) {
    $null = Invoke-RestMethod -Method Patch -Headers $headers -Uri "$api/releases/assets/$($item.old.id)" -ContentType 'application/json' -Body (@{name=$item.name+'.previous-audit-update'} | ConvertTo-Json)
    $null = Invoke-RestMethod -Method Patch -Headers $headers -Uri "$api/releases/assets/$($item.new.id)" -ContentType 'application/json' -Body (@{name=$item.name} | ConvertTo-Json)
}
foreach ($item in $staged) {
    $new = Invoke-RestMethod -Headers $headers -Uri "$api/releases/assets/$($item.new.id)"
    Download-Verified $new.browser_download_url (Join-Path $backup ($item.name + '.final-verified')) $item.hash
}
$body = Get-Content -LiteralPath (Join-Path $repoRoot 'docs\RELEASE_ONECOMME_0.1.7.md') -Raw -Encoding utf8
$body = $body.Replace('/tree/onecomme-v0.1.7)', "/tree/$commit)")
$body += "`n`n配布ファイル更新（0.1.7のまま）：対応ソース $commit。タグは初回0.1.7の状態を保持しています。`n"
$json = @{body=$body;draft=$false;prerelease=$false;make_latest='true'} | ConvertTo-Json
$null = Invoke-RestMethod -Method Patch -Headers $headers -Uri "$api/releases/$($release.id)" -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($json))
# Exact old IDs were downloaded and verified before mutation; keep recoverable local copies.
foreach ($item in $staged) {
    $null = Invoke-RestMethod -Method Delete -Headers $headers -Uri "$api/releases/assets/$($item.old.id)"
}
[pscustomobject]@{published=$true;version='0.1.7';source=$commit;backup=$backup;url=$release.html_url;assets=@($staged | ForEach-Object { @{name=$_.name;id=$_.new.id;hash=$_.hash} })} | ConvertTo-Json -Depth 5
