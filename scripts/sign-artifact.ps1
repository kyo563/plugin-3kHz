param([Parameter(Mandatory=$true)][string]$Path, [Parameter(Mandatory=$true)][string]$CertificateThumbprint, [Parameter(Mandatory=$true)][string]$TimestampServer)
$ErrorActionPreference="Stop"
if ($CertificateThumbprint -notmatch '^[a-fA-F0-9]{40}$') { throw "Invalid certificate thumbprint." }
$certificate=Get-Item -LiteralPath "Cert:/CurrentUser/My/$CertificateThumbprint"
if (!$certificate.HasPrivateKey) { throw "A code-signing certificate with a private key is required." }
$result=Set-AuthenticodeSignature -LiteralPath $Path -Certificate $certificate -HashAlgorithm SHA256 -TimestampServer $TimestampServer
if ($result.Status -ne 'Valid') { throw "Signature validation failed: $($result.Status)" }
Get-AuthenticodeSignature -LiteralPath $Path | Select-Object Path,Status
