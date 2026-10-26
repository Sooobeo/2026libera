param([Parameter(Mandatory=$true)][string]$EvidenceDirectory)
$ErrorActionPreference = 'Stop'
$target = [IO.Path]::GetFullPath($EvidenceDirectory)
if (-not $target.StartsWith(($PSScriptRoot + [IO.Path]::DirectorySeparatorChar), [StringComparison]::OrdinalIgnoreCase)) { throw 'Evidence must stay under recovery_20261025/runtime' }
$outPath = Join-Path $target 'service_shutdown_receipt.json'
if (Test-Path -LiteralPath $outPath) { throw 'Shutdown receipt already exists' }
$start = Get-Content -LiteralPath (Join-Path $target 'service_receipt.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($start.origin -ne 'http://127.0.0.1:11435' -or $start.status -ne 'ready') { throw 'Unexpected owned service receipt' }
$owned = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + [int]$start.pid)
if (-not $owned -or $owned.ExecutablePath -ne $start.executable -or $owned.CommandLine -notmatch '\bserve\s*$') { throw 'Owned process identity differs' }
if ((Get-FileHash -LiteralPath $owned.ExecutablePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $start.executable_sha256) { throw 'Owned executable hash differs' }
$created = $owned.CreationDate.ToUniversalTime()
$expectedCreated = [DateTime]::Parse($start.process_created_at_utc).ToUniversalTime()
if ([Math]::Abs(($created - $expectedCreated).TotalSeconds) -gt 1) { throw 'PID creation time differs from startup receipt' }
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 11435)
if ($listeners.Count -ne 1 -or $listeners[0].OwningProcess -ne $start.pid -or $listeners[0].LocalAddress -ne '127.0.0.1') { throw 'Owned listener differs' }
$residency = Invoke-RestMethod -Uri ($start.origin + '/api/ps') -TimeoutSec 5
if (@($residency.models).Count -ne 0) { throw 'A model is still resident; do not stop active work' }
$existingBefore = @(Get-NetTCPConnection -State Listen -LocalPort 11434 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess)
Stop-Process -Id $start.pid -Force
Wait-Process -Id $start.pid -Timeout 10 -ErrorAction SilentlyContinue
if (@(Get-NetTCPConnection -State Listen -LocalPort 11435 -ErrorAction SilentlyContinue).Count -ne 0) { throw 'Owned listener remains after shutdown' }
$existingAfter = @(Get-NetTCPConnection -State Listen -LocalPort 11434 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess)
$unchanged = (ConvertTo-Json -InputObject $existingBefore -Compress) -eq (ConvertTo-Json -InputObject $existingAfter -Compress)
$record = [ordered]@{
    recorded_at_utc=[DateTime]::UtcNow.ToString('o'); status='owned_service_stopped';
    stopped_pid=$start.pid; executable=$owned.ExecutablePath; executable_sha256=$start.executable_sha256;
    process_created_at_utc=$created.ToString('o'); no_resident_models_before_stop=$true;
    owned_port_closed=$true; existing_11434_before=$existingBefore; existing_11434_after=$existingAfter;
    existing_11434_listener_unchanged=$unchanged; persistent_environment_changed=$false
}
$record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $outPath -Encoding UTF8
if (-not $unchanged) { throw 'Existing listener changed during observation; see receipt' }
$record | ConvertTo-Json -Depth 8
