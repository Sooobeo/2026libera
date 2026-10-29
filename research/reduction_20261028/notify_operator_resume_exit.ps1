param([Parameter(Mandatory=$true)][int]$ResumeProcessId)

# The normal campaign notifier is rearmed by the continuation coordinator.
# If that coordinator exits early, restore the local stopped-run alert instead.
$ErrorActionPreference='Stop'
$v64Root=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$v64StatePath=Join-Path $v64Root 'data\v64_20261028\main_only_results\operator_resume_state.json'
$v64ResumeProcess=Get-Process -Id $ResumeProcessId -ErrorAction SilentlyContinue
if ($v64ResumeProcess) { $v64ResumeProcess.WaitForExit() }
$v64State=Get-Content -LiteralPath $v64StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($v64State.status -eq 'original_campaign_resumed') { exit 0 }
& (Join-Path $PSScriptRoot 'watch_main_notification.ps1')
