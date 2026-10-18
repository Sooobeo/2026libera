param([int]$StartupTimeoutSeconds = 20)
$ErrorActionPreference = 'Stop'
if ($StartupTimeoutSeconds -lt 1 -or $StartupTimeoutSeconds -gt 60) { throw 'Startup timeout must be 1..60 seconds.' }
$sectorOrigin = 'http://127.0.0.1:11434'
$sectorExe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
$sectorExpectedHash = '3cc17c238b081adf2bd3a206e52a063b637af1bf283d95b4ffd73a2bdec8b027'
if (-not (Test-Path -LiteralPath $sectorExe -PathType Leaf)) { throw 'Install the verified Ollama 0.35.1 package first.' }
$sectorHash = (Get-FileHash -LiteralPath $sectorExe -Algorithm SHA256).Hash.ToLowerInvariant()
if ($sectorHash -ne $sectorExpectedHash) { throw 'The installed CLI changed from the measured 0.35.1 binary; revalidate it before starting.' }

# Reuse a responsive pinned service without changing or restarting its workload.
$sectorExisting = $null
try { $sectorExisting = Invoke-RestMethod -Uri ($sectorOrigin + '/api/version') -TimeoutSec 2 } catch { }
if ($null -ne $sectorExisting) {
    if ($sectorExisting.version -ne '0.35.1') { throw 'Another Ollama engine version is already serving this port; it was left unchanged.' }
    [ordered]@{
        status = 'existing_service_left_unchanged'
        origin = $sectorOrigin
        version = $sectorExisting.version
        backend = 'Not inferred from the version endpoint; verify logs and inference placement.'
        generation_requests = 0
    } | ConvertTo-Json
    return
}

$sectorWorkspace = Split-Path -Parent $PSScriptRoot
$sectorRunId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$sectorLogDir = Join-Path $sectorWorkspace ('data\local_sector_runtime\service_' + $sectorRunId)
if (Test-Path -LiteralPath $sectorLogDir) { throw 'A service record already exists; preserve it.' }
New-Item -ItemType Directory -Path $sectorLogDir -Force | Out-Null
$sectorRequestedEnvironment = [ordered]@{
    OLLAMA_HOST = '127.0.0.1:11434'
    OLLAMA_NO_CLOUD = '1'
    OLLAMA_VULKAN = '1'
    OLLAMA_IGPU_ENABLE = '1'
}
$sectorPreviousEnvironment = @{}
$sectorProcess = $null
try {
    foreach ($sectorName in $sectorRequestedEnvironment.Keys) {
        $sectorPreviousEnvironment[$sectorName] = [Environment]::GetEnvironmentVariable($sectorName, 'Process')
        [Environment]::SetEnvironmentVariable($sectorName, $sectorRequestedEnvironment[$sectorName], 'Process')
    }
    $sectorProcess = Start-Process -FilePath $sectorExe -ArgumentList 'serve' -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $sectorLogDir 'server.stdout.log') `
        -RedirectStandardError (Join-Path $sectorLogDir 'server.stderr.log')
} finally {
    foreach ($sectorName in $sectorPreviousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($sectorName, $sectorPreviousEnvironment[$sectorName], 'Process')
    }
}
$sectorClock = [Diagnostics.Stopwatch]::StartNew()
$sectorVersion = $null
while ($sectorClock.Elapsed.TotalSeconds -lt $StartupTimeoutSeconds) {
    if ($sectorProcess.HasExited) { break }
    try {
        $sectorVersion = Invoke-RestMethod -Uri ($sectorOrigin + '/api/version') -TimeoutSec 1
        if ($sectorVersion.version) { break }
    } catch { }
    Start-Sleep -Milliseconds 200
}
$sectorListeners = @()
$sectorOwnershipError = $null
$sectorOwnerVerified = $false
try {
    $sectorListeners = @(Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction Stop |
        Select-Object LocalAddress, LocalPort, OwningProcess)
    $sectorOwnedListeners = @($sectorListeners | Where-Object {
        $_.LocalAddress -eq '127.0.0.1' -and $_.OwningProcess -eq $sectorProcess.Id
    })
    $sectorRunningPath = (Get-Process -Id $sectorProcess.Id -ErrorAction Stop).Path
    $sectorOwnerVerified = ($sectorOwnedListeners.Count -eq 1) -and ($sectorRunningPath -eq $sectorExe)
} catch { $sectorOwnershipError = $_.Exception.Message }
$sectorReady = (-not $sectorProcess.HasExited) -and ($sectorVersion.version -eq '0.35.1') -and $sectorOwnerVerified
[ordered]@{
    status = $(if ($sectorReady) { 'pinned_api_ready' } else { 'startup_not_confirmed' })
    recorded_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    pid = $sectorProcess.Id
    binary = $sectorExe
    binary_sha256 = $sectorHash
    origin = $sectorOrigin
    observed_version = $sectorVersion
    listener_observations = $sectorListeners
    listener_owner_verified = $sectorOwnerVerified
    ownership_observation_error = $sectorOwnershipError
    requested_child_environment = $sectorRequestedEnvironment
    scope = 'Local process only. No persistent environment, driver, firewall or protocol changes. No model generation.'
    backend = 'Requested Vulkan iGPU; actual backend requires log and inference observations.'
    generation_requests = 0
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $sectorLogDir 'server_launch.json') -Encoding UTF8
if (-not $sectorReady) {
    # Only the process created by this script can be stopped here.
    if (-not $sectorProcess.HasExited) { $sectorProcess.Kill(); $sectorProcess.WaitForExit() }
    throw ('Startup was not confirmed. Inspect ' + $sectorLogDir)
}
Write-Output ('Ollama 0.35.1 ready at ' + $sectorOrigin + '; logs: ' + $sectorLogDir)
