# Pure fixture validation: only launcher function definitions are evaluated.
# No listener, process, API, model-load or generation action is invoked.
$ErrorActionPreference = 'Stop'
$v63RealWorkspace = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$v63Launcher = Join-Path $v63RealWorkspace 'research\start_v63_vulkan_ollama.ps1'
$v63Tokens = $null
$v63Errors = $null
$v63Ast = [System.Management.Automation.Language.Parser]::ParseFile($v63Launcher, [ref]$v63Tokens, [ref]$v63Errors)
if (@($v63Errors).Count) { throw 'Launcher syntax invalid.' }
$v63Functions = @('Resolve-V63WorkspacePath', 'Get-V63Hash', 'Test-V63EnvironmentMatch', 'Get-V63EnvironmentEvidence')
foreach ($v63Function in $v63Ast.FindAll({ param($Node) $Node -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    if ($v63Function.Name -in $v63Functions) { . ([scriptblock]::Create($v63Function.Extent.Text)) }
}
$v63Workspace = Join-Path $v63RealWorkspace ('tmp\v63_vulkan_launcher_fixture_' + [Guid]::NewGuid().ToString('N'))
$v63RuntimeRoot = Join-Path $v63Workspace 'runtime'
$v63Origin = 'http://127.0.0.1:11436'
$v63Executable = Join-Path $v63Workspace 'portable\ollama.exe'
$v63Expected = [ordered]@{OLLAMA_HOST = '127.0.0.1:11436'; OLLAMA_VULKAN = '1'; OLLAMA_KV_CACHE_TYPE = 'f16'}
$v63OldStart = [DateTimeOffset]::Parse('2026-10-27T09:49:00Z').UtcDateTime
$v63NewStart = [DateTimeOffset]::Parse('2026-10-27T11:15:00Z').UtcDateTime
New-Item -ItemType Directory -Path $v63RuntimeRoot -Force | Out-Null

function Write-Fixture([string]$DirectoryName, $Record) {
    $v63Directory = Join-Path $v63RuntimeRoot $DirectoryName
    New-Item -ItemType Directory -Path $v63Directory -Force | Out-Null
    $v63Path = Join-Path $v63Directory 'server_launch.json'
    [System.IO.File]::WriteAllText($v63Path, ($Record | ConvertTo-Json -Depth 8), [System.Text.UTF8Encoding]::new($false))
    return $v63Path
}

function Assert-True([bool]$Value, [string]$Message) {
    if (-not $Value) { throw $Message }
}

function Assert-Rejected([scriptblock]$Operation, [string]$ExpectedMessage) {
    $v63Rejected = $false
    try { & $Operation | Out-Null } catch {
        $v63Rejected = $true
        if ($_.Exception.Message -notlike ('*' + $ExpectedMessage + '*')) { throw }
    }
    if (-not $v63Rejected) { throw ('Expected rejection: ' + $ExpectedMessage) }
}

$v63OldRecord = [ordered]@{pid = 101; origin = $v63Origin; binary = $v63Executable; started_at_utc = $v63OldStart.ToString('o'); environment = $v63Expected}
$v63PinPath = Write-Fixture 'vulkan_probe_001' $v63OldRecord
$v63PinnedBytes = [System.IO.File]::ReadAllBytes($v63PinPath)
$v63Configuration = [pscustomobject]@{server_environment_evidence = [pscustomobject]@{path = $v63PinPath.Substring($v63Workspace.Length + 1); sha256 = Get-V63Hash $v63PinPath}}
$v63NewRecord = [ordered]@{status = 'new_pinned_vulkan_service_ready'; pid = 202; origin = $v63Origin; binary = $v63Executable; process_started_at_utc = $v63NewStart.ToString('o'); environment = $v63Expected}
$v63NewPath = Write-Fixture 'vulkan_service_002' $v63NewRecord
$v63Results = @()

$v63Match = Get-V63EnvironmentEvidence $v63Configuration 202 $v63Executable $v63NewStart $v63Expected
Assert-True ($v63Match.path -eq 'runtime/vulkan_service_002/server_launch.json') 'New process receipt was ignored when an old probe was pinned.'
$v63Results += 'new_process_uses_new_receipt_with_old_probe_pin'

$v63Match = Get-V63EnvironmentEvidence $v63Configuration 101 $v63Executable $v63OldStart $v63Expected
Assert-True ($v63Match.path -eq 'runtime/vulkan_probe_001/server_launch.json') 'The original process should still reuse its pinned receipt.'
$v63Results += 'original_process_still_uses_pinned_probe'

[System.IO.File]::AppendAllText($v63PinPath, ' ')
Assert-Rejected { Get-V63EnvironmentEvidence $v63Configuration 202 $v63Executable $v63NewStart $v63Expected } 'Pinned environment evidence hash mismatch'
[System.IO.File]::WriteAllBytes($v63PinPath, $v63PinnedBytes)
$v63Results += 'tampered_pin_rejected_even_when_new_receipt_matches'

$v63WrongExpected = [ordered]@{OLLAMA_HOST = '127.0.0.1:11436'; OLLAMA_VULKAN = '0'; OLLAMA_KV_CACHE_TYPE = 'f16'}
Assert-Rejected { Get-V63EnvironmentEvidence $v63Configuration 202 $v63Executable $v63NewStart $v63WrongExpected } 'Pinned launch environment differs'
$v63Results += 'candidate_environment_must_match_pinned_definition'

Assert-Rejected { Get-V63EnvironmentEvidence $v63Configuration 202 $v63Executable ($v63NewStart.AddMinutes(10)) $v63Expected } 'No matching same-process launch record'
$v63Results += 'stale_receipt_after_pid_reuse_rejected'

$v63CorruptPath = Write-Fixture 'vulkan_service_999' @{}
[System.IO.File]::WriteAllText($v63CorruptPath, '{corrupt', [System.Text.UTF8Encoding]::new($false))
$v63Match = Get-V63EnvironmentEvidence $v63Configuration 202 $v63Executable $v63NewStart $v63Expected
Assert-True ($v63Match.path -eq 'runtime/vulkan_service_002/server_launch.json') 'Malformed unrelated receipt prevented a valid restart receipt.'
$v63Results += 'malformed_unrelated_recent_receipt_skipped'

$v63FailedRecord = [ordered]@{status = 'verification_or_startup_failed'; pid = 202; origin = $v63Origin; binary = $v63Executable; process_started_at_utc = $v63NewStart.ToString('o'); environment = $v63Expected}
[void](Write-Fixture 'vulkan_service_998' $v63FailedRecord)
$v63Match = Get-V63EnvironmentEvidence $v63Configuration 202 $v63Executable $v63NewStart $v63Expected
Assert-True ($v63Match.path -eq 'runtime/vulkan_service_002/server_launch.json') 'Failed-startup receipt was incorrectly accepted.'
$v63Results += 'failed_startup_receipt_not_accepted'

$v63Report = [ordered]@{status = 'passed'; checked_at_utc = [DateTime]::UtcNow.ToString('o'); launcher_sha256 = Get-V63Hash $v63Launcher; tests_passed = $v63Results.Count; cases = $v63Results; fixture_root = $v63Workspace; function_definitions_only = $true; real_service_changes = 0; network_requests = 0; model_load_requests = 0; generation_requests = 0}
$v63ReportPath = Join-Path $PSScriptRoot 'vulkan_launcher_environment_evidence_tests.json'
[System.IO.File]::WriteAllText($v63ReportPath, ($v63Report | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))
$v63Report | ConvertTo-Json -Depth 5
