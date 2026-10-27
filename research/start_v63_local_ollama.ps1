param([ValidateSet('f16','q8_0')][string]$KvCacheType='f16')
$ErrorActionPreference = 'Stop'
$v63Workspace = Split-Path -Parent $PSScriptRoot
$v63AssetRoot = Join-Path $v63Workspace 'tmp\v63_local_ollama'
$v63Exe = Join-Path $v63AssetRoot 'portable\ollama.exe'
$v63Origin = 'http://127.0.0.1:11435'
$v63ExpectedHash = '3cc17c238b081adf2bd3a206e52a063b637af1bf283d95b4ffd73a2bdec8b027'
if ((Get-FileHash -LiteralPath $v63Exe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $v63ExpectedHash) { throw 'CLI hash differs from the pinned signed release.' }
foreach ($v63Binary in Get-ChildItem -LiteralPath (Join-Path $v63AssetRoot 'portable') -Recurse -File | Where-Object {$_.Extension -in @('.exe','.dll')}) {
    $v63Signature = Get-AuthenticodeSignature -LiteralPath $v63Binary.FullName
    if ($v63Signature.Status -ne 'Valid' -or $v63Signature.SignerCertificate.Subject -notlike '*Ollama*') { throw 'Unverified portable binary publisher.' }
}
$v63Existing = $null
try { $v63Existing = Invoke-RestMethod -Uri ($v63Origin + '/api/version') -TimeoutSec 2 } catch { }
if ($null -ne $v63Existing) { throw 'Port 11435 is already serving. Preserve it and inspect its ownership instead of launching again.' }
$v63LogDir = Join-Path $v63Workspace ('data\v63_20261027\runtime\local_windows\service_' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ'))
New-Item -ItemType Directory -Path $v63LogDir | Out-Null
$v63Environment = [ordered]@{
    OLLAMA_HOST='127.0.0.1:11435'
    OLLAMA_MODELS=(Join-Path $v63AssetRoot 'models')
    OLLAMA_NO_CLOUD='1'
    OLLAMA_VULKAN='0'
    OLLAMA_NUM_PARALLEL='1'
    OLLAMA_MAX_LOADED_MODELS='1'
    OLLAMA_FLASH_ATTENTION='1'
    OLLAMA_KV_CACHE_TYPE=$KvCacheType
}
$v63Prior=@{}
try {
    foreach ($v63Name in $v63Environment.Keys) {
        $v63Prior[$v63Name]=[Environment]::GetEnvironmentVariable($v63Name,'Process')
        [Environment]::SetEnvironmentVariable($v63Name,$v63Environment[$v63Name],'Process')
    }
    $v63Process = Start-Process -FilePath $v63Exe -ArgumentList 'serve' -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $v63LogDir 'server.stdout.log') `
        -RedirectStandardError (Join-Path $v63LogDir 'server.stderr.log')
} finally {
    foreach ($v63Name in $v63Prior.Keys) { [Environment]::SetEnvironmentVariable($v63Name,$v63Prior[$v63Name],'Process') }
}
$v63Clock=[Diagnostics.Stopwatch]::StartNew();$v63Version=$null
while ($v63Clock.Elapsed.TotalSeconds -lt 20) {
    if ($v63Process.HasExited) { break }
    try { $v63Version=Invoke-RestMethod -Uri ($v63Origin+'/api/version') -TimeoutSec 1; if ($v63Version.version) { break } } catch { }
    Start-Sleep -Milliseconds 200
}
$v63Listeners=@(Get-NetTCPConnection -LocalPort 11435 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess)
$v63Owned=@($v63Listeners | Where-Object {$_.LocalAddress -eq '127.0.0.1' -and $_.OwningProcess -eq $v63Process.Id})
$v63Ready=$v63Version.version -eq '0.35.1' -and $v63Owned.Count -eq 1 -and -not $v63Process.HasExited
[ordered]@{
    recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o')
    status=$(if ($v63Ready) {'pinned_isolated_api_ready'} else {'startup_not_confirmed'})
    binary=$v63Exe; binary_sha256=$v63ExpectedHash;pid=$v63Process.Id;origin=$v63Origin
    version=$v63Version;listeners=$v63Listeners;listener_owner_verified=($v63Owned.Count -eq 1)
    process_scoped_environment=$v63Environment
    cpu=(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors)
    memory=(Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory)
    scope='Isolated portable background process; no service registration, firewall change, persistent environment or model generation.'
    generation_requests=0
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $v63LogDir 'server_launch.json') -Encoding UTF8
if (-not $v63Ready) {
    if (-not $v63Process.HasExited) {$v63Process.Kill();$v63Process.WaitForExit()}
    throw ('Local startup not verified: '+$v63LogDir)
}
Write-Output ('Ollama ready: '+$v63Origin+'; PID '+$v63Process.Id+'; record '+$v63LogDir)
