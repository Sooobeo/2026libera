param()
$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$recovery = Join-Path $workspace 'research\recovery_20261025'
$run = Join-Path $workspace 'data\local_sector_runtime\v494_pilot_20261025'
$reports = Join-Path $recovery 'new_pilot'
$launch = Join-Path $recovery 'launch'
if ((Test-Path -LiteralPath $run) -or (Test-Path -LiteralPath $reports) -or (Test-Path -LiteralPath $launch)) {
    throw 'A run/report/launch directory already exists. No automatic retry or resume.'
}
$service = Get-Content -LiteralPath (Join-Path $recovery 'runtime\service_ready\service_receipt.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$owner = Get-CimInstance Win32_Process -Filter "ProcessId = $($service.pid)"
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 11435 -ErrorAction SilentlyContinue)
if (-not $owner -or $service.status -ne 'ready' -or $service.origin -ne 'http://127.0.0.1:11435' -or
    $owner.ExecutablePath -ne $service.executable -or $owner.CommandLine -notmatch '\bserve\b' -or
    [Math]::Abs(($owner.CreationDate.ToUniversalTime() - [DateTime]::Parse($service.process_created_at_utc).ToUniversalTime()).TotalMilliseconds) -gt 1 -or
    $listeners.Count -ne 1 -or $listeners[0].OwningProcess -ne $service.pid -or $listeners[0].LocalAddress -ne '127.0.0.1') {
    throw 'Recovered service ownership differs; no launch.'
}
if ((Get-FileHash -LiteralPath $owner.ExecutablePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $service.executable_sha256) {
    throw 'Recovered service executable changed.'
}
$version = Invoke-RestMethod -Uri 'http://127.0.0.1:11435/api/version' -TimeoutSec 5
$models = Invoke-RestMethod -Uri 'http://127.0.0.1:11435/api/ps' -TimeoutSec 5
if ($version.version -ne '0.35.1' -or @($models.models).Count -ne 0) { throw 'Pinned service is not idle/ready.' }
$python = (Get-Command python.exe).Source
$arguments = @('-B', '-X', 'utf8', (Join-Path $workspace 'research\run_v494_recovery.py'),
    '--runtime', (Join-Path $recovery 'runtime_candidate.json'),
    '--run-dir', $run, '--origin', 'http://127.0.0.1:11435',
    '--server-log', (Join-Path $recovery 'runtime\service_ready\server.stderr.log'),
    '--review-gate', (Join-Path $recovery 'review_gate.json'), '--output-root', $reports)
foreach ($item in $arguments) { if ($item.Contains('"')) { throw 'Unexpected quote in launch argument' } }
$quoted = @($arguments | ForEach-Object { '"' + $_ + '"' })
New-Item -ItemType Directory -Path $launch -ErrorAction Stop | Out-Null
$process = Start-Process -FilePath $python -ArgumentList $quoted -WorkingDirectory $workspace -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $launch 'coordinator.stdout.log') `
    -RedirectStandardError (Join-Path $launch 'coordinator.stderr.log')
$receipt = [ordered]@{ launched_at_utc=[DateTime]::UtcNow.ToString('o'); coordinator_pid=$process.Id;
    python=$python; arguments=$arguments; working_directory=$workspace; run_directory=$run;
    report_directory=$reports; service_pid=$service.pid; origin=$service.origin;
    launch_scope='One new prospectively frozen development pilot, ten maximum first attempts; no resume/retry';
    status='launched_completion_not_yet_observed' }
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $launch 'launch_receipt.json') -Encoding UTF8
$receipt | ConvertTo-Json -Depth 8
