$ErrorActionPreference = 'Stop'
$latencyWorkspace = Split-Path -Parent $PSScriptRoot
$latencyInstaller = Join-Path $latencyWorkspace 'tmp\local_latency_20261018\OllamaSetup-0.35.1.exe'
$latencyRecordDir = Join-Path $latencyWorkspace 'data\local_sector_20261018\installation'
if (Test-Path -LiteralPath $latencyRecordDir) { throw 'Installation record already exists; do not overwrite.' }
$latencyHash = (Get-FileHash -LiteralPath $latencyInstaller -Algorithm SHA256).Hash.ToLowerInvariant()
if ($latencyHash -ne '2544c6dc60c57866f5cfbd32b8f7c5ffa5e1f7f0579ca59da5ff20bdc53ad3d2') { throw 'Official release hash mismatch.' }
$latencySignature = Get-AuthenticodeSignature -LiteralPath $latencyInstaller
if ($latencySignature.Status -ne 'Valid' -or $latencySignature.SignerCertificate.Subject -notlike '*Ollama*') { throw 'Official publisher signature was not verified.' }
New-Item -ItemType Directory -Path $latencyRecordDir -Force | Out-Null
$latencyStarted = (Get-Date).ToUniversalTime().ToString('o')
# Process-scoped configuration inherited by this installer and its Ollama child.
# No machine/user environment, firewall, network exposure or credentials changed.
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_VULKAN = '1'
$env:OLLAMA_IGPU_ENABLE = '1'
$latencyInstallLog = Join-Path $latencyRecordDir 'installer.log'
$latencyInstallArgs = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', ('/LOG="' + $latencyInstallLog + '"'))
$latencyProcess = Start-Process -FilePath $latencyInstaller -ArgumentList $latencyInstallArgs -WindowStyle Hidden -PassThru
$latencyProcess.WaitForExit()
$latencyExe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
[ordered]@{
    started_at_utc = $latencyStarted
    finished_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    source_url = 'https://github.com/ollama/ollama/releases/download/v0.35.1/OllamaSetup.exe'
    official_sha256 = $latencyHash
    authenticode_status = [string]$latencySignature.Status
    signer = $latencySignature.SignerCertificate.Subject
    installer_exit_code = $latencyProcess.ExitCode
    binary_path = $latencyExe
    binary_exists = (Test-Path -LiteralPath $latencyExe)
    requested_process_environment = @{ OLLAMA_HOST='127.0.0.1:11434'; OLLAMA_NO_CLOUD='1'; OLLAMA_VULKAN='1'; OLLAMA_IGPU_ENABLE='1' }
    environment_scope = 'Installer process and inherited children only; effective backend must be observed from logs and API.'
    research_pilot_calls = 0
    research_main_calls = 0
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $latencyRecordDir 'installation.json') -Encoding UTF8
if ($latencyProcess.ExitCode -ne 0) { throw ('Installer failed: ' + $latencyProcess.ExitCode) }
if (-not (Test-Path -LiteralPath $latencyExe)) { throw 'Installed CLI not found.' }
Write-Output 'Ollama installation completed; API and model verification remain.'
