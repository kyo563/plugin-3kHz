param(
    [string]$Version = '0.1.5',
    [string]$ReleaseDirectory = 'dist\onecomme-release-0.1.5'
)
$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid version' }
$repoRoot = Split-Path -Parent $PSScriptRoot
$candidate = Join-Path $repoRoot $ReleaseDirectory
$zipName = "Taikiretsu-Seiri-App-OneComme-$Version-windows-x64.zip"
$files = @(
    @{name=$zipName;path=(Join-Path $candidate $zipName)},
    @{name='Taikiretsu-Template.zip';path=(Join-Path $candidate 'sankagata-seiretsu\Taikiretsu-Template.zip')},
    @{name='SHA256SUMS.txt';path=(Join-Path $candidate 'SHA256SUMS.txt')}
)
foreach ($file in $files) {
    if (-not (Test-Path -LiteralPath $file.path -PathType Leaf)) { throw 'Missing release asset' }
}
$checksums = Get-Content -LiteralPath (Join-Path $candidate 'SHA256SUMS.txt') -Raw
foreach ($file in $files | Where-Object name -ne 'SHA256SUMS.txt') {
    $file.hash = (Get-FileHash -LiteralPath $file.path -Algorithm SHA256).Hash.ToLowerInvariant()
    if (-not $checksums.Contains($file.hash + '  ' + $file.name)) { throw 'Candidate checksum mismatch' }
}
$commit = (& git -C $repoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $commit -notmatch '^[a-f0-9]{40}$') { throw 'Missing source commit' }
$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE = 'never'
$credentials = "protocol=https`nhost=github.com`n" | git -c credential.interactive=never credential fill
$password = ($credentials | Where-Object { $_ -like 'password=*' }) -replace '^password=',''
if (-not $password) { throw 'GitHub authentication unavailable' }
$headers = @{Authorization="Bearer $password";Accept='application/vnd.github+json';'X-GitHub-Api-Version'='2022-11-28'}
$api = 'https://api.github.com/repos/kyo563/plugin-3kHz'
$tag = "onecomme-v$Version"
try {
    $null = Invoke-RestMethod -Headers $headers -Uri "$api/releases/tags/$tag"
    throw 'Release already exists; inspect it before updating'
} catch {
    if (-not $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 404) { throw }
}
$body = Get-Content -LiteralPath (Join-Path $repoRoot "docs\RELEASE_ONECOMME_$Version.md") -Raw -Encoding utf8
$json = @{tag_name=$tag;target_commitish=$commit;name="待機列整理アプリ・わんコメ版 $Version";body=$body;draft=$true;prerelease=$false} | ConvertTo-Json
$release = Invoke-RestMethod -Method Post -Headers $headers -Uri "$api/releases" -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($json))
if (-not $release.draft -or $release.tag_name -ne $tag) { throw 'Unexpected draft release' }
$uploadBase = $release.upload_url -replace '\{.*$',''
$assets = @()
foreach ($file in $files) {
    $uploaded = Invoke-RestMethod -Method Post -Headers $headers -Uri ($uploadBase + '?name=' + [Uri]::EscapeDataString($file.name)) -ContentType 'application/octet-stream' -InFile $file.path
    $hash = (Get-FileHash -LiteralPath $file.path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($uploaded.size -ne (Get-Item -LiteralPath $file.path).Length -or $uploaded.digest -ne "sha256:$hash") {
        throw 'Uploaded digest mismatch; draft retained and not published'
    }
    $assets += @{name=$file.name;id=$uploaded.id;hash=$hash;url=$uploaded.browser_download_url}
}
$release = Invoke-RestMethod -Method Patch -Headers $headers -Uri "$api/releases/$($release.id)" -ContentType 'application/json' -Body (@{draft=$false;prerelease=$false;make_latest='true'} | ConvertTo-Json)
if ($release.draft -or $release.prerelease) { throw 'Release not public' }
$verified = Join-Path $candidate 'public-download-verification'
New-Item -ItemType Directory -Path $verified -Force | Out-Null
foreach ($asset in $assets) {
    $download = Join-Path $verified $asset.name
    Invoke-WebRequest -Uri ($asset.url + '?verify=' + $asset.id) -OutFile $download
    if ((Get-FileHash -LiteralPath $download).Hash.ToLowerInvariant() -ne $asset.hash) { throw 'Anonymous download checksum mismatch' }
}
[pscustomobject]@{published=$true;releaseId=$release.id;url=$release.html_url;tag=$tag;source=$commit;assets=$assets} | ConvertTo-Json -Depth 5
