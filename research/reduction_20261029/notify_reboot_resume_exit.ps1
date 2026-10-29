param([Parameter(Mandatory=$true)][int]$ResumeProcessId)

# Restore the existing local stopped-run alert if reboot recovery exits early.
$ErrorActionPreference='Stop'
$v64Root=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$v64StatePath=Join-Path $v64Root 'data\v64_20261028\main_only_results\reboot_resume_state_20261029.json'
$v64ResumeProcess=Get-Process -Id $ResumeProcessId -ErrorAction SilentlyContinue
if ($v64ResumeProcess) { $v64ResumeProcess.WaitForExit() }
$v64State=Get-Content -LiteralPath $v64StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($v64State.status -eq 'original_campaign_resumed') { exit 0 }
& (Join-Path $v64Root 'research\reduction_20261028\watch_main_notification.ps1')
