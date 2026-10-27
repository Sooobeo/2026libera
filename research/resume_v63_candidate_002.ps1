# Execute only after an explicit instruction to resume the user-paused experiment.
$ErrorActionPreference='Stop'
$v63Workspace=Split-Path -Parent $PSScriptRoot
$v63RunId='de1b479b54d5b4429211059df1496be588c3c5af81ec21f4d4c355e3004f76ec'
$v63Config=Join-Path $v63Workspace 'data\v63_20261027\continuation\deployment\local_windows\candidate_002\campaign_config.json'
$v63Python=Join-Path $v63Workspace 'tmp\v63_numerics_venv\Scripts\python.exe'
$v63PausePath=Join-Path $v63Workspace 'data\v63_20261027\continuation\user_pause_20261027.json'
foreach($v63Required in @($v63Python,$v63Config,$v63PausePath,(Join-Path $v63Workspace 'tmp\v63_local_ollama\portable\ollama.exe'),(Join-Path $v63Workspace 'tmp\v63_local_ollama\models'))) {
    if (-not (Test-Path -LiteralPath $v63Required)) { throw ('Required local resume asset missing: '+$v63Required) }
}
$v63Pause=Get-Content -LiteralPath $v63PausePath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($v63Pause.schema -ne 'libera_user_pause_v1' -or $v63Pause.active -ne $true -or $v63Pause.run_id -ne $v63RunId) { throw 'Matching active explicit-user pause record is required.' }
$v63BudgetPath=Join-Path $v63Workspace ('data\v63_20261027\local_campaign_results\phases\'+$v63RunId+'\technical-smoke\budget_state.json')
$v63Budget=Get-Content -LiteralPath $v63BudgetPath -Raw | ConvertFrom-Json
$v63Deadline=([DateTimeOffset]::Parse($v63Budget.first_started_at_utc)).AddSeconds($v63Budget.limits.max_wall_seconds)
if ([DateTimeOffset]::UtcNow -ge $v63Deadline) { throw 'The persisted six-hour phase budget expired during downtime. An explicit recorded budget amendment is required; never reset budget_state.' }
$v63Verify=Get-Content -LiteralPath (Join-Path $v63Workspace 'data\v63_20261027\continuation\pause_20261027\offline_replay_verification.json') -Raw | ConvertFrom-Json
if ($v63Verify.status -ne 'passed_offline_replay_no_network' -or $v63Verify.runtime_identity_sha256 -ne $v63RunId) { throw 'Offline pause recovery verification is missing.' }
Push-Location $v63Workspace
try {
    & (Join-Path $v63Workspace 'tmp\v63_numerics_venv\Scripts\python.exe') -m research.verify_v63_pause_replay --identity-only
    if ($LASTEXITCODE -ne 0) { throw 'Frozen source/config/artifact verification failed before service restart.' }
} finally { Pop-Location }
& (Join-Path $PSScriptRoot 'start_v63_local_ollama.ps1') -KvCacheType f16
if (-not $?) { throw 'Pinned service restart failed.' }
$v63Record=Join-Path $v63Workspace ('data\v63_20261027\runtime\local_windows\resume_candidate_002_'+(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ'))
New-Item -ItemType Directory -Path $v63Record | Out-Null
$v63Arguments='-m research.v63.campaign '+$v63Config+' --phase technical-smoke'
$v63Process=Start-Process -FilePath $v63Python -ArgumentList $v63Arguments -WorkingDirectory $v63Workspace -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $v63Record 'campaign.stdout.log') -RedirectStandardError (Join-Path $v63Record 'campaign.stderr.log')
$v63MonitorArgs='-NoProfile -ExecutionPolicy Bypass -File '+(Join-Path $PSScriptRoot 'monitor_v63_local_smoke.ps1')+' -CampaignProcessId '+$v63Process.Id+' -RecordDirectory '+$v63Record
$v63Monitor=Start-Process powershell.exe -ArgumentList $v63MonitorArgs -WorkingDirectory $v63Workspace -WindowStyle Hidden -PassThru
$v63LaunchPath=Join-Path $v63Record 'launch.json'
[ordered]@{status='explicit_resume_launched';recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o');run_id=$v63RunId;campaign_pid=$v63Process.Id;monitor_pid=$v63Monitor.Id;phase='technical-smoke';config=$v63Config;phase_budget_expires_at_utc=$v63Deadline.ToString('o');main_model_frozen=$false;next_phases_auto_launch=$false} | ConvertTo-Json | Set-Content -LiteralPath $v63LaunchPath -Encoding UTF8
$v63Pause | Add-Member -NotePropertyName active -NotePropertyValue $false -Force
$v63Pause | Add-Member -NotePropertyName status -NotePropertyValue 'resumed_by_explicit_command' -Force
$v63Pause | Add-Member -NotePropertyName resumed_at_utc -NotePropertyValue ((Get-Date).ToUniversalTime().ToString('o')) -Force
$v63LaunchRelative=$v63LaunchPath.Substring($v63Workspace.Length+1).Replace('\','/')
$v63Pause | Add-Member -NotePropertyName resume_launch_ref -NotePropertyValue ([ordered]@{path=$v63LaunchRelative;sha256=(Get-FileHash -LiteralPath $v63LaunchPath -Algorithm SHA256).Hash.ToLowerInvariant()}) -Force
$v63PauseTemp=$v63PausePath+'.resuming'
$v63Pause | ConvertTo-Json -Depth 40 | Set-Content -LiteralPath $v63PauseTemp -Encoding UTF8
Move-Item -LiteralPath $v63PauseTemp -Destination $v63PausePath -Force
$v63Observer=Start-Process -FilePath $v63Python -ArgumentList '-m research.v63.observe_continuation --watch' -WorkingDirectory $v63Workspace -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $v63Record 'observer.stdout.log') -RedirectStandardError (Join-Path $v63Record 'observer.stderr.log')
[ordered]@{status='readonly_observer_restarted_after_explicit_resume';pid=$v63Observer.Id;recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o');model_generation_requests=0} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $v63Record 'observer_launch.json') -Encoding UTF8
Write-Output ('Resumed only technical-smoke; PID '+$v63Process.Id+'; '+$v63Record)
