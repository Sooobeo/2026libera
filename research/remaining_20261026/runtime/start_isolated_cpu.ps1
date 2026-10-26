param(
    [Parameter(Mandatory=$true)][string]$EvidenceDirectory,
    [Parameter(Mandatory=$true)][string]$Executable,
    [Parameter(Mandatory=$true)][string]$ModelDirectory
)
$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$ownedRuntimeRoot = [IO.Path]::GetFullPath((Join-Path $workspace 'tmp\libera_ollama0351_20261025'))
$target = [IO.Path]::GetFullPath($EvidenceDirectory)
$exe = [IO.Path]::GetFullPath($Executable)
$modelRoot = [IO.Path]::GetFullPath($ModelDirectory)
$expected = '3cc17c238b081adf2bd3a206e52a063b637af1bf283d95b4ffd73a2bdec8b027'
if (-not $target.StartsWith(($PSScriptRoot + [IO.Path]::DirectorySeparatorChar), [StringComparison]::OrdinalIgnoreCase)) { throw 'Evidence must stay under remaining_20261026/runtime' }
if (-not $exe.StartsWith(($ownedRuntimeRoot + [IO.Path]::DirectorySeparatorChar), [StringComparison]::OrdinalIgnoreCase)) { throw 'Executable must be the isolated recovered distribution' }
if (Test-Path -LiteralPath $target) { throw 'A new evidence directory is required' }
if ((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Pinned Ollama binary differs' }
if (-not (Test-Path -LiteralPath $modelRoot -PathType Container)) { throw 'Model directory missing' }
if (Get-NetTCPConnection -State Listen -LocalPort 11435 -ErrorAction SilentlyContinue) { throw 'Port 11435 is already in use; existing process left unchanged' }
$existingBefore = @(Get-NetTCPConnection -State Listen -LocalPort 11434 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess)
[IO.Directory]::CreateDirectory($target) | Out-Null
$childEnvironment = [ordered]@{
    OLLAMA_HOST='127.0.0.1:11435'; OLLAMA_NO_CLOUD='1';
    OLLAMA_VULKAN='0'; OLLAMA_IGPU_ENABLE='0'; OLLAMA_NUM_PARALLEL='1';
    OLLAMA_MAX_LOADED_MODELS='1'; CUDA_VISIBLE_DEVICES='-1'; ROCR_VISIBLE_DEVICES='-1';
    OLLAMA_MODELS=$modelRoot; OLLAMA_NOPRUNE='1'
}
$inheritedOllama = [ordered]@{}
Get-ChildItem Env:OLLAMA* | Sort-Object Name | ForEach-Object { $inheritedOllama[$_.Name] = $_.Value }
$oldEnvironment = @{}
$process = $null
try {
    foreach ($key in $childEnvironment.Keys) {
        $oldEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        [Environment]::SetEnvironmentVariable($key, $childEnvironment[$key], 'Process')
    }
    $process = Start-Process -FilePath $exe -ArgumentList 'serve' -WorkingDirectory (Split-Path -Parent $exe) -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $target 'server.stdout.log') `
        -RedirectStandardError (Join-Path $target 'server.stderr.log')
} finally {
    foreach ($key in $oldEnvironment.Keys) { [Environment]::SetEnvironmentVariable($key, $oldEnvironment[$key], 'Process') }
}
$record = [ordered]@{
    recorded_at_utc=[DateTime]::UtcNow.ToString('o');
    purpose='Recovered original CPU runtime; startup and read-only checks perform no generation';
    pid=$process.Id; executable=$exe; executable_sha256=$expected; origin='http://127.0.0.1:11435';
    process_created_at_utc=$process.StartTime.ToUniversalTime().ToString('o');
    child_environment=$childEnvironment; inherited_ollama_environment=$inheritedOllama;
    persistent_environment_changed=$false; global_installation_changed=$false;
    model_generation_requests=0; status='starting'; require_request_num_gpu_zero=$true;
    request_configuration='The caller must retain the frozen 65536 context, 8192 output allowance, 8 threads and model digest. No inference or options are supplied by this launcher.'
}
try {
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        if ($process.HasExited) { throw 'Owned Ollama process exited during startup' }
        try { $version = Invoke-RestMethod -Uri ($record.origin + '/api/version') -TimeoutSec 2 } catch { $version = $null }
        if ($version) { break }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not $version -or $version.version -ne '0.35.1') { throw 'Pinned service did not become ready' }
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort 11435)
    if ($listeners.Count -ne 1 -or $listeners[0].OwningProcess -ne $process.Id -or $listeners[0].LocalAddress -ne '127.0.0.1') { throw 'Listener ownership/address mismatch' }
    $running = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $process.Id)
    if ($running.ExecutablePath -ne $exe -or $running.CommandLine -notmatch '\bserve\s*$') { throw 'Running executable identity differs' }
    $existingAfter = @(Get-NetTCPConnection -State Listen -LocalPort 11434 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess)
    $record.existing_11434_before=$existingBefore
    $record.existing_11434_after=$existingAfter
    $record.existing_11434_listener_unchanged=(ConvertTo-Json -InputObject $existingBefore -Compress) -eq (ConvertTo-Json -InputObject $existingAfter -Compress)
    if (-not $record.existing_11434_listener_unchanged) { throw 'Existing 11434 listener changed during observation' }
    $record.listener_owner_verified=$true
    $record.status='ready'; $record.version=$version.version
} catch {
    $record.status='failed'; $record.error=$_.Exception.Message
    if ($process -and -not $process.HasExited) { $process.Kill(); $process.WaitForExit() }
    throw
} finally {
    $record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $target 'service_receipt.json') -Encoding utf8
}
$record | ConvertTo-Json -Depth 8

