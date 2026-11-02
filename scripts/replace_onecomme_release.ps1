param(
    [string]$Version = '0.1.9',
    [long]$ExpectedReleaseId = 426828116,
    [string]$ReleaseDirectory = 'dist\onecomme-release-0.1.9-copy-20261102',
    [string]$ExpectedOldHash = '27d94a5e4d2a155c1b02275b803a8b28cf75f1d7af9ccafb636c94f8bc2a26a5'
)
$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^\d+\.\d+\.\d+$' -or $ExpectedReleaseId -le 0 -or $ExpectedOldHash -notmatch '^[a-f0-9]{64}$') { throw 'Invalid expected release' }
$repoRoot = Split-Path -Parent $PSScriptRoot
$candidate = Join-Path $repoRoot $ReleaseDirectory
$zipName = "Taikiretsu-Seiri-App-OneComme-$Version-windows-x64.zip"
$names = @($zipName, 'SHA256SUMS.txt')
$checksums = Get-Content -LiteralPath (Join-Path $candidate 'SHA256SUMS.txt') -Raw
$zipHash = (Get-FileHash -LiteralPath (Join-Path $candidate $zipName)).Hash.ToLowerInvariant()
if (-not $checksums.Contains($zipHash + '  ' + $zipName)) { throw 'Candidate checksum mismatch' }
$commit = (& git -C $repoRoot rev-parse HEAD).Trim()
if ($commit -notmatch '^[a-f0-9]{40}$') { throw 'Missing source commit' }
$notes = Get-Content -LiteralPath (Join-Path $repoRoot "docs\RELEASE_ONECOMME_$Version.md") -Raw -Encoding utf8
foreach ($placeholder in @('__SOURCE_COMMIT__', '__ZIP_SHA256__', '__DOWNLOAD_QUERY__')) {
    if (-not $notes.Contains($placeholder)) { throw 'Missing release note placeholder' }
}
$backup = Join-Path $repoRoot ("dist\release-backup-$Version-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backup | Out-Null
$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE = 'never'
$credentials = "protocol=https`nhost=github.com`n" | git -c credential.interactive=never credential fill
$password = ($credentials | Where-Object { $_ -like 'password=*' }) -replace '^password=',''
if (-not $password) { throw 'GitHub authentication unavailable' }
$headers = @{Authorization="Bearer $password";Accept='application/vnd.github+json';'X-GitHub-Api-Version'='2022-11-28'}
$api = 'https://api.github.com/repos/kyo563/plugin-3kHz'
$release = Invoke-RestMethod -Headers $headers -Uri "$api/releases/tags/onecomme-v$Version"
if ($release.id -ne $ExpectedReleaseId -or $release.draft -or $release.prerelease -or $release.assets.Count -ne 3) { throw 'Unexpected release' }
$oldZip = @($release.assets | Where-Object name -eq $zipName)
if ($oldZip.Count -ne 1 -or $oldZip[0].digest -ne "sha256:$ExpectedOldHash") { throw 'Unexpected existing archive; do not replace it' }
$templateHash = (Get-FileHash -LiteralPath (Join-Path $candidate 'sankagata-seiretsu\Taikiretsu-Template.zip')).Hash.ToLowerInvariant()
$templateAsset = @($release.assets | Where-Object name -eq 'Taikiretsu-Template.zip')
if ($templateAsset.Count -ne 1 -or $templateAsset[0].digest -ne "sha256:$templateHash") { throw 'Unexpected template change' }
$release | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $backup 'release.json') -Encoding utf8
function Download-Verified($url, $destination, $expected, $cacheKey = $null) {
    if ($cacheKey) { $url += '?asset=' + $cacheKey }
    for ($attempt = 0; $attempt -lt 5; $attempt++) {
        $downloadUrl = $url
        if ($attempt -gt 0) {
            $separator = if ($url.Contains('?')) { '&' } else { '?' }
            $downloadUrl += $separator + 'verify=' + $expected + '&attempt=' + $attempt
        }
        & curl.exe --fail --location --silent --show-error --output $destination $downloadUrl
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
    Download-Verified $old[0].browser_download_url (Join-Path $backup $name) ($old[0].digest -replace '^sha256:','') $old[0].id
    $local = Join-Path $candidate $name
    $hash = (Get-FileHash -LiteralPath $local).Hash.ToLowerInvariant()
    $temporaryName = $name + '.copy-update-staged'
    $new = Invoke-RestMethod -Method Post -Headers $headers -Uri ($uploadBase + '?name=' + [Uri]::EscapeDataString($temporaryName)) -ContentType 'application/octet-stream' -InFile $local
    if ($new.digest -ne "sha256:$hash" -or $new.size -ne (Get-Item -LiteralPath $local).Length) { throw 'Staged digest mismatch' }
    Download-Verified $new.browser_download_url (Join-Path $backup ($name + '.staged-verified')) $hash $new.id
    $staged += [pscustomobject]@{name=$name;old=$old[0];new=$new;hash=$hash}
}
foreach ($item in $staged) {
    $null = Invoke-RestMethod -Method Patch -Headers $headers -Uri "$api/releases/assets/$($item.old.id)" -ContentType 'application/json' -Body (@{name=$item.name+'.previous-copy-update'} | ConvertTo-Json)
    $null = Invoke-RestMethod -Method Patch -Headers $headers -Uri "$api/releases/assets/$($item.new.id)" -ContentType 'application/json' -Body (@{name=$item.name} | ConvertTo-Json)
}
foreach ($item in $staged) {
    $new = Invoke-RestMethod -Headers $headers -Uri "$api/releases/assets/$($item.new.id)"
    Download-Verified $new.browser_download_url (Join-Path $backup ($item.name + '.final-verified')) $item.hash $new.id
}
$newZipId = ($staged | Where-Object name -eq $zipName).new.id
$body = $notes.Replace('__SOURCE_COMMIT__', $commit).Replace('__ZIP_SHA256__', $zipHash).Replace('__DOWNLOAD_QUERY__', "asset=$newZipId")
$json = @{body=$body;draft=$false;prerelease=$false;make_latest='true'} | ConvertTo-Json
$null = Invoke-RestMethod -Method Patch -Headers $headers -Uri "$api/releases/$($release.id)" -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($json))
# Exact old IDs were downloaded and verified before mutation; keep recoverable local copies.
foreach ($item in $staged) {
    $retained = Invoke-RestMethod -Headers $headers -Uri "$api/releases/assets/$($item.old.id)"
    $oldHash = $item.old.digest -replace '^sha256:',''
    if ($retained.name -ne $item.name+'.previous-copy-update' -or
        (Get-FileHash -LiteralPath (Join-Path $backup $item.name)).Hash.ToLowerInvariant() -ne $oldHash) { throw 'Previous asset backup mismatch; retain it' }
    $null = Invoke-RestMethod -Method Delete -Headers $headers -Uri "$api/releases/assets/$($item.old.id)"
}
[pscustomobject]@{published=$true;version=$Version;source=$commit;backup=$backup;url=$release.html_url;assets=@($staged | ForEach-Object { @{name=$_.name;id=$_.new.id;hash=$_.hash} })} | ConvertTo-Json -Depth 5
