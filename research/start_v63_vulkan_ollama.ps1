param(
    [string]$CandidateDirectory = 'data\v63_20261027\continuation\deployment\local_windows\candidate_005'
)

# This launcher performs only file/signature checks and read-only API requests.
# It never loads a model, sends generation requests, or alters the user's 11434 service.
$ErrorActionPreference = 'Stop'
$v63Workspace = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$v63Origin = 'http://127.0.0.1:11436'
$v63RuntimeRoot = Join-Path $v63Workspace 'data\v63_20261027\runtime\local_windows'
$v63NewProcess = $null
$v63Ready = $false

function Resolve-V63WorkspacePath([string]$Value) {
    if ([System.IO.Path]::IsPathRooted($Value)) {
        $v63Resolved = [System.IO.Path]::GetFullPath($Value)
    } else {
        $v63Resolved = [System.IO.Path]::GetFullPath((Join-Path $v63Workspace $Value))
    }
    if (-not $v63Resolved.StartsWith($v63Workspace + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw ('Path escapes the experiment workspace: ' + $Value)
    }
    return $v63Resolved
}

function Get-V63Hash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-V63Json([string]$Path, $Value) {
    $v63Temporary = $Path + '.writing.' + [Guid]::NewGuid().ToString('N')
    $v63Json = $Value | ConvertTo-Json -Depth 20
    [System.IO.File]::WriteAllText($v63Temporary, $v63Json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $v63Temporary -Destination $Path -Force
}

function Test-V63EnvironmentMatch($Recorded, $Expected) {
    if ($null -eq $Recorded) { return $false }
    $v63RecordedNames = @($Recorded.PSObject.Properties.Name)
    $v63ExpectedNames = @($Expected.Keys)
    if ($v63RecordedNames.Count -ne $v63ExpectedNames.Count) { return $false }
    foreach ($v63Key in $v63ExpectedNames) {
        if ($v63Key -notin $v63RecordedNames -or [string]$Recorded.$v63Key -cne [string]$Expected[$v63Key]) { return $false }
    }
    return $true
}

function Get-V63EnvironmentEvidence($Configuration, [int]$ProcessId, [string]$Executable, [DateTime]$StartedUtc, $Expected) {
    $v63EvidenceCandidates = @()
    $v63PinnedEvidence = $Configuration.server_environment_evidence
    $v63PinnedEvidencePath = $null
    if ($null -ne $v63PinnedEvidence) {
        $v63PinnedEvidencePath = Resolve-V63WorkspacePath ([string]$v63PinnedEvidence.path)
        if ((Get-V63Hash $v63PinnedEvidencePath) -ne [string]$v63PinnedEvidence.sha256) { throw 'Pinned environment evidence hash mismatch.' }
        $v63PinnedDefinition = Get-Content -LiteralPath $v63PinnedEvidencePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not (Test-V63EnvironmentMatch $v63PinnedDefinition.environment $Expected)) { throw 'Pinned launch environment differs from the candidate environment.' }
        $v63EvidenceCandidates = @($v63PinnedEvidencePath)
    }
    # The pinned probe fixes the environment definition, not a permanent PID.
    # A restart creates a new process whose own launch receipt must be eligible.
    $v63EvidenceCandidates += @(Get-ChildItem -LiteralPath $v63RuntimeRoot -Directory |
        Where-Object { $_.Name -like 'vulkan_probe_*' -or $_.Name -like 'vulkan_service_*' } |
        Sort-Object Name -Descending |
        ForEach-Object { Join-Path $_.FullName 'server_launch.json' } |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
    $v63EvidenceCandidates = @($v63EvidenceCandidates | Select-Object -Unique)
    foreach ($v63EvidencePath in $v63EvidenceCandidates) {
        try {
            $v63Evidence = Get-Content -LiteralPath $v63EvidencePath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($v63Evidence.status -and [string]$v63Evidence.status -notin @('new_pinned_vulkan_service_ready', 'existing_pinned_vulkan_service_reused')) { continue }
            if ([int]$v63Evidence.pid -ne $ProcessId -or [string]$v63Evidence.origin -ne $v63Origin) { continue }
            if (-not [string]::Equals([System.IO.Path]::GetFullPath([string]$v63Evidence.binary), $Executable, [System.StringComparison]::OrdinalIgnoreCase)) { continue }
            $v63StartValue = [string]$v63Evidence.process_started_at_utc
            if (-not $v63StartValue) { $v63StartValue = [string]$v63Evidence.started_at_utc }
            $v63EvidenceStart = [DateTimeOffset]::Parse($v63StartValue).UtcDateTime
            if ([Math]::Abs(($StartedUtc - $v63EvidenceStart).TotalSeconds) -gt 5) { continue }
            if (-not (Test-V63EnvironmentMatch $v63Evidence.environment $Expected)) { continue }
            return [ordered]@{
                path = $v63EvidencePath.Substring($v63Workspace.Length + 1).Replace('\', '/')
                sha256 = Get-V63Hash $v63EvidencePath
                process_start_difference_seconds = [Math]::Abs(($StartedUtc - $v63EvidenceStart).TotalSeconds)
                verification = 'Matched recorded launch overrides; live process environment was not read.'
            }
        } catch {
            if ($v63EvidencePath -eq $v63PinnedEvidencePath) { throw }
        }
    }
    throw 'No matching same-process launch record proves the existing server environment; existing service preserved.'
}

$v63CandidatePath = Resolve-V63WorkspacePath $CandidateDirectory
$v63EnvironmentPath = Join-Path $v63CandidatePath 'execution_environment.json'
if (-not (Test-Path -LiteralPath $v63EnvironmentPath -PathType Leaf)) { throw ('Candidate environment is missing: ' + $v63EnvironmentPath) }
$v63Config = Get-Content -LiteralPath $v63EnvironmentPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$v63Config.engine_revision -ne '0.35.1') { throw 'The Vulkan launcher requires an explicit engine_revision of 0.35.1.' }
$v63Environment = [ordered]@{}
foreach ($v63Property in $v63Config.server_environment.PSObject.Properties) { $v63Environment[$v63Property.Name] = [string]$v63Property.Value }
$v63Required = [ordered]@{
    OLLAMA_HOST = '127.0.0.1:11436'; OLLAMA_NO_CLOUD = '1'; OLLAMA_VULKAN = '1'
    OLLAMA_IGPU_ENABLE = '1'; GGML_VK_VISIBLE_DEVICES = '0'; OLLAMA_NUM_PARALLEL = '1'
    OLLAMA_MAX_LOADED_MODELS = '1'; OLLAMA_CONTEXT_LENGTH = '32768'; OLLAMA_FLASH_ATTENTION = '1'
    OLLAMA_KV_CACHE_TYPE = 'f16'
}
foreach ($v63Key in $v63Required.Keys) {
    if (-not $v63Environment.Contains($v63Key) -or $v63Environment[$v63Key] -cne $v63Required[$v63Key]) {
        throw ('Required frozen Vulkan setting differs: ' + $v63Key)
    }
}
$v63ModelsPath = Resolve-V63WorkspacePath ([string]$v63Environment['OLLAMA_MODELS'])
if (-not (Test-Path -LiteralPath $v63ModelsPath -PathType Container)) { throw 'Frozen task-local model store is missing.' }
$v63LogDir = Join-Path $v63RuntimeRoot ('vulkan_service_' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '_' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $v63LogDir | Out-Null
$v63Record = [ordered]@{
    schema = 'libera_vulkan_service_launch_v1'; status = 'validating'; started_at_utc = [DateTime]::UtcNow.ToString('o')
    candidate_directory = $v63CandidatePath; candidate_environment_sha256 = Get-V63Hash $v63EnvironmentPath
    origin = $v63Origin; environment = $v63Environment; engine_revision = [string]$v63Config.engine_revision
    model_load_requests = 0; generation_requests = 0; user_service_changes = 0; persistent_environment_changes = 0
}
try {
    $v63Checks = @()
    $v63Executables = @()
    $v63PinnedPaths = @{}
    foreach ($v63Artifact in @($v63Config.binary_artifacts)) {
        if ([System.IO.Path]::IsPathRooted([string]$v63Artifact.path)) { throw 'Pinned binary paths must be workspace-relative.' }
        $v63BinaryPath = Resolve-V63WorkspacePath ([string]$v63Artifact.path)
        if ($v63PinnedPaths.ContainsKey($v63BinaryPath)) { throw 'Duplicate frozen binary path.' }
        $v63PinnedPaths[$v63BinaryPath] = $true
        $v63ExpectedPublisher = [string]$v63Artifact.expected_publisher_substring
        if (-not $v63ExpectedPublisher) { $v63ExpectedPublisher = 'Ollama' }
        $v63ActualHash = Get-V63Hash $v63BinaryPath
        $v63Signature = Get-AuthenticodeSignature -LiteralPath $v63BinaryPath
        $v63Publisher = [string]$v63Signature.SignerCertificate.Subject
        $v63Passed = $v63ActualHash -eq [string]$v63Artifact.sha256 -and $v63Signature.Status -eq 'Valid' -and $v63Publisher.IndexOf($v63ExpectedPublisher, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
        $v63Checks += [ordered]@{path = $v63BinaryPath; sha256 = $v63ActualHash; expected_sha256 = [string]$v63Artifact.sha256; signature_status = $v63Signature.Status.ToString(); publisher = $v63Publisher; expected_publisher_substring = $v63ExpectedPublisher; passed = $v63Passed}
        if (-not $v63Passed) { throw ('Frozen binary hash or signature verification failed: ' + $v63BinaryPath) }
        if ([System.IO.Path]::GetFileName($v63BinaryPath) -ieq 'ollama.exe') { $v63Executables += $v63BinaryPath }
    }
    Write-V63Json (Join-Path $v63LogDir 'binary_verification.json') $v63Checks
    if ($v63Executables.Count -ne 1) { throw 'Exactly one pinned ollama.exe is required.' }
    $v63Executable = $v63Executables[0]
    $v63PortableRoot = Split-Path -Parent $v63Executable
    foreach ($v63File in Get-ChildItem -LiteralPath $v63PortableRoot -Recurse -File | Where-Object { $_.Extension -in @('.exe', '.dll') }) {
        if (-not $v63PinnedPaths.ContainsKey($v63File.FullName)) { throw ('Unlisted binary in frozen portable directory: ' + $v63File.FullName) }
    }
    $v63Record['binary'] = $v63Executable
    $v63Record['binary_sha256'] = Get-V63Hash $v63Executable
    $v63Listeners = @(Get-NetTCPConnection -LocalPort 11436 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, OwningProcess)
    $v63Reused = $v63Listeners.Count -gt 0
    if ($v63Reused) {
        if ($v63Listeners.Count -ne 1 -or $v63Listeners[0].LocalAddress -ne '127.0.0.1') { throw 'Port 11436 has an unexpected listener; existing service preserved.' }
        $v63ServicePid = [int]$v63Listeners[0].OwningProcess
    } else {
        $v63Prior = @{}
        try {
            foreach ($v63Key in $v63Environment.Keys) {
                $v63Prior[$v63Key] = [Environment]::GetEnvironmentVariable($v63Key, 'Process')
                [Environment]::SetEnvironmentVariable($v63Key, $v63Environment[$v63Key], 'Process')
            }
            $v63NewProcess = Start-Process -FilePath $v63Executable -ArgumentList 'serve' -WorkingDirectory $v63Workspace -WindowStyle Hidden -PassThru `
                -RedirectStandardOutput (Join-Path $v63LogDir 'server.stdout.log') -RedirectStandardError (Join-Path $v63LogDir 'server.stderr.log')
        } finally {
            foreach ($v63Key in $v63Prior.Keys) { [Environment]::SetEnvironmentVariable($v63Key, $v63Prior[$v63Key], 'Process') }
        }
        $v63ServicePid = $v63NewProcess.Id
        $v63Clock = [Diagnostics.Stopwatch]::StartNew()
        while ($v63Clock.Elapsed.TotalSeconds -lt 20) {
            $v63NewProcess.Refresh()
            if ($v63NewProcess.HasExited) { throw 'New dedicated server exited during startup.' }
            $v63Listeners = @(Get-NetTCPConnection -LocalPort 11436 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, OwningProcess)
            if ($v63Listeners.Count -gt 0) { break }
            Start-Sleep -Milliseconds 200
        }
    }
    if ($v63Listeners.Count -ne 1 -or $v63Listeners[0].LocalAddress -ne '127.0.0.1' -or [int]$v63Listeners[0].OwningProcess -ne $v63ServicePid) {
        throw 'Dedicated loopback listener ownership was not verified.'
    }
    $v63ProcessInfo = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $v63ServicePid)
    if ($null -eq $v63ProcessInfo -or -not [string]::Equals([System.IO.Path]::GetFullPath([string]$v63ProcessInfo.ExecutablePath), $v63Executable, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Listener process executable differs from the frozen task binary.'
    }
    if ((Get-V63Hash ([string]$v63ProcessInfo.ExecutablePath)) -ne $v63Record['binary_sha256']) { throw 'Listener binary hash changed.' }
    $v63ProcessStart = (Get-Process -Id $v63ServicePid).StartTime.ToUniversalTime()
    $v63Version = Invoke-RestMethod -Uri ($v63Origin + '/api/version') -TimeoutSec 5
    if ([string]$v63Version.version -ne [string]$v63Config.engine_revision) { throw 'Dedicated server engine version differs from the freeze.' }
    $v63Record['pid'] = $v63ServicePid
    $v63Record['process_started_at_utc'] = $v63ProcessStart.ToString('o')
    $v63Record['listeners'] = $v63Listeners
    $v63Record['listener_owner_verified'] = $true
    $v63Record['version'] = $v63Version
    if ($v63Reused) {
        $v63Record['environment_evidence'] = Get-V63EnvironmentEvidence $v63Config $v63ServicePid $v63Executable $v63ProcessStart $v63Environment
        $v63Record['status'] = 'existing_pinned_vulkan_service_reused'
    } else {
        $v63Record['environment_verification'] = 'This launcher supplied the recorded process-scoped overrides and restored its own prior environment.'
        $v63Record['status'] = 'new_pinned_vulkan_service_ready'
    }
    $v63Record['models_observed_without_loading'] = Invoke-RestMethod -Uri ($v63Origin + '/api/ps') -TimeoutSec 5
    $v63Record['recorded_at_utc'] = [DateTime]::UtcNow.ToString('o')
    $v63Ready = $true
    Write-V63Json (Join-Path $v63LogDir 'server_launch.json') $v63Record
    Write-Output ('Vulkan Ollama ready: ' + $v63Origin + '; PID ' + $v63ServicePid + '; reused=' + $v63Reused + '; record ' + $v63LogDir)
} catch {
    $v63Record['status'] = 'verification_or_startup_failed'
    $v63Record['error'] = $_.Exception.Message
    $v63Record['recorded_at_utc'] = [DateTime]::UtcNow.ToString('o')
    Write-V63Json (Join-Path $v63LogDir 'server_launch.json') $v63Record
    throw
} finally {
    if (-not $v63Ready -and $null -ne $v63NewProcess) {
        $v63NewProcess.Refresh()
        if (-not $v63NewProcess.HasExited) { $v63NewProcess.Kill(); $v63NewProcess.WaitForExit() }
    }
}
