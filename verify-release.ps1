$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$buildExe = Join-Path $root 'czkawka/target/release/krokiet.exe'
$releaseDir = Join-Path $root 'release-staging'
$releaseZip = Join-Path $root 'krokiet-classic-release.zip'
$evidence = Join-Path $root 'security-evidence'
$scanLog = Join-Path $evidence 'verification.log'
$report = Join-Path $evidence 'verification-summary.txt'
$manifest = Join-Path $evidence 'sha256-manifest.csv'
$failed = $false
$problems = [System.Collections.Generic.List[string]]::new()

New-Item -ItemType Directory -Path $evidence -Force | Out-Null
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
Start-Transcript -Path $scanLog -Force | Out-Null
try {
    Write-Host "BUILD_SHA=$env:GITHUB_SHA"
    Write-Host "BUILD_RUN=$env:GITHUB_RUN_ID"
    if (-not (Test-Path -LiteralPath $buildExe -PathType Leaf)) { throw "Missing executable: $buildExe" }

    Copy-Item -LiteralPath $buildExe -Destination (Join-Path $releaseDir 'krokiet.exe') -Force
    if (Test-Path -LiteralPath $releaseZip) { Remove-Item -LiteralPath $releaseZip -Force }
    Compress-Archive -Path (Join-Path $releaseDir '*') -DestinationPath $releaseZip -CompressionLevel Optimal -ErrorAction Stop
    if (-not (Test-Path -LiteralPath $releaseZip -PathType Leaf)) { throw 'Release archive was not produced' }

    $scanTargets = @((Join-Path $releaseDir 'krokiet.exe'), $releaseZip)
    $items = @(Get-ChildItem -LiteralPath $releaseDir -File -Recurse -ErrorAction Stop)
    $items += Get-Item -LiteralPath $releaseZip -ErrorAction Stop
    $items | ForEach-Object {
        Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256 -ErrorAction Stop |
            Select-Object Path, Algorithm, Hash
    } | Export-Csv -LiteralPath $manifest -NoTypeInformation -Encoding UTF8
    Write-Host 'SHA-256 manifest:'
    Get-Content -LiteralPath $manifest | ForEach-Object { Write-Host $_ }

    if (-not (Get-Command Get-MpComputerStatus -ErrorAction SilentlyContinue)) {
        throw 'Microsoft Defender cmdlets unavailable; verification cannot proceed'
    }
    Write-Host 'Refreshing Microsoft Defender signatures...'
    Update-MpSignature -ErrorAction Stop
    $status = Get-MpComputerStatus -ErrorAction Stop
    $status | Select-Object AMServiceEnabled, AntivirusEnabled, RealTimeProtectionEnabled, AntivirusSignatureVersion, AntivirusSignatureLastUpdated |
        Format-List | Out-String | Write-Host
    if (-not $status.AMServiceEnabled -or -not $status.AntivirusEnabled) {
        throw 'Defender antivirus is not active'
    }

    # Snapshot existing detection identifiers so unrelated pre-existing records do not cause failure.
    foreach ($target in $scanTargets) {
        Write-Host "Scanning: $target"
        Start-MpScan -ScanType CustomScan -ScanPath $target -ErrorAction Stop
        Write-Host "Scan command completed: $target"
    }
    $after = @(Get-MpThreatDetection -ErrorAction Stop)
    $scannedNames = @('krokiet.exe', 'krokiet-classic-release.zip')
    $hits = @($after | Where-Object {
        $resources = @($_.Resources) -join ' '
        @($scannedNames | Where-Object { $resources -like "*$_*" }).Count -gt 0
    })
    if ($hits.Count -gt 0) {
        $hits | Format-List * | Out-String | Write-Host
        throw "Defender detection associated with staged release: $($hits.Count)"
    }
    foreach ($target in $scanTargets) {
        if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "Target missing after scan: $target" }
    }
    $hashes = @(Import-Csv -LiteralPath $manifest)
    foreach ($h in $hashes) {
        $current = (Get-FileHash -LiteralPath $h.Path -Algorithm SHA256 -ErrorAction Stop).Hash
        if ($current -ne $h.Hash) { throw "SHA-256 changed after scan: $($h.Path)" }
    }
    Write-Host 'SECURITY_VERIFICATION_PASSED'
} catch {
    $failed = $true
    $problems.Add($_.Exception.Message)
    Write-Host "SECURITY_VERIFICATION_FAILED: $($_.Exception.Message)"
} finally {
    @(
        "TimestampUtc=$([datetime]::UtcNow.ToString('o'))",
        "GitHubSha=$env:GITHUB_SHA",
        "GitHubRunId=$env:GITHUB_RUN_ID",
        "Status=$(if ($failed) { 'FAILED' } else { 'PASSED' })",
        "ReleaseArchive=$releaseZip",
        "Notes=Defender scan covers the staged executable and inner release ZIP, not the outer GitHub Actions artifact wrapper.",
        "Errors=$($problems -join ' | ')"
    ) | Set-Content -LiteralPath $report -Encoding UTF8
    Stop-Transcript | Out-Null
}
if ($failed) { exit 1 }
