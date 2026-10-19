param([Parameter(Mandatory=$true)][string]$EvidenceDirectory)
$ErrorActionPreference = 'Stop'
# Isolated diagnostic service. The existing 11434 service is never changed.
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$target = [IO.Path]::GetFullPath($EvidenceDirectory)
if (-not $target.StartsWith(($workspace + [IO.Path]::DirectorySeparatorChar), [StringComparison]::OrdinalIgnoreCase)) { throw 'Evidence must stay inside workspace' }
if (Test-Path -LiteralPath $target) { throw 'A new evidence directory is required' }
$exe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
$expected = '3cc17c238b081adf2bd3a206e52a063b637af1bf283d95b4ffd73a2bdec8b027'
if ((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Pinned Ollama binary differs' }
if (Get-NetTCPConnection -State Listen -LocalPort 11435 -ErrorAction SilentlyContinue) { throw 'Port 11435 is already in use; no existing process is stopped' }
[IO.Directory]::CreateDirectory($target) | Out-Null
$environment = [ordered]@{
    OLLAMA_HOST='127.0.0.1:11435'; OLLAMA_NO_CLOUD='1';
    OLLAMA_VULKAN='0'; OLLAMA_IGPU_ENABLE='0'; OLLAMA_NUM_PARALLEL='1';
    OLLAMA_MAX_LOADED_MODELS='1'; CUDA_VISIBLE_DEVICES='-1'; ROCR_VISIBLE_DEVICES='-1'
}
$oldEnvironment = @{}
$process = $null
try {
    foreach ($key in $environment.Keys) {
        $oldEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        [Environment]::SetEnvironmentVariable($key, $environment[$key], 'Process')
    }
    $process = Start-Process -FilePath $exe -ArgumentList 'serve' -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $target 'server.stdout.log') `
        -RedirectStandardError (Join-Path $target 'server.stderr.log')
} finally {
    foreach ($key in $oldEnvironment.Keys) { [Environment]::SetEnvironmentVariable($key, $oldEnvironment[$key], 'Process') }
}
$record = [ordered]@{
    recorded_at_utc=[DateTime]::UtcNow.ToString('o'); purpose='isolated CPU engineering preflight, not pilot';
    pid=$process.Id; executable=$exe; executable_sha256=$expected; origin='http://127.0.0.1:11435';
    child_environment=$environment; existing_service_changed=$false; persistent_environment_changed=$false;
    model_generation_requests=0; status='starting'; require_request_num_gpu_zero=$true
}
try {
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        if ($process.HasExited) { throw 'Owned Ollama process exited during startup' }
        try { $version = Invoke-RestMethod -Uri 'http://127.0.0.1:11435/api/version' -TimeoutSec 2 } catch { $version = $null }
        if ($version) { break }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not $version -or $version.version -ne '0.35.1') { throw 'Pinned service did not become ready' }
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort 11435)
    if ($listeners.Count -ne 1 -or $listeners[0].OwningProcess -ne $process.Id -or $listeners[0].LocalAddress -ne '127.0.0.1') { throw 'Listener ownership/address mismatch' }
    $record.status='ready'; $record.version=$version.version
} catch {
    $record.status='failed'; $record.error=$_.Exception.Message
    if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    throw
} finally {
    $record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $target 'service_receipt.json') -Encoding utf8
}
$record | ConvertTo-Json -Depth 8
