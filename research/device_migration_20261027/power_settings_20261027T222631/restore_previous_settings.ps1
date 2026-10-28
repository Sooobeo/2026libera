$ErrorActionPreference = 'Stop'
$taskScheme = 'ab6534a3-bc02-4c44-94d1-a8535b2eb070'
& powercfg.exe /setacvalueindex $taskScheme SUB_SLEEP STANDBYIDLE 180
if ($LASTEXITCODE -ne 0) { throw 'Could not restore original power setting.' }
& powercfg.exe /setdcvalueindex $taskScheme SUB_SLEEP STANDBYIDLE 180
if ($LASTEXITCODE -ne 0) { throw 'Could not restore original power setting.' }
& powercfg.exe /setacvalueindex $taskScheme SUB_SLEEP HIBERNATEIDLE 2592000
if ($LASTEXITCODE -ne 0) { throw 'Could not restore original power setting.' }
& powercfg.exe /setdcvalueindex $taskScheme SUB_SLEEP HIBERNATEIDLE 259200
if ($LASTEXITCODE -ne 0) { throw 'Could not restore original power setting.' }
& powercfg.exe /setacvalueindex $taskScheme SUB_BUTTONS LIDACTION 1
if ($LASTEXITCODE -ne 0) { throw 'Could not restore original power setting.' }
& powercfg.exe /setdcvalueindex $taskScheme SUB_BUTTONS LIDACTION 1
if ($LASTEXITCODE -ne 0) { throw 'Could not restore original power setting.' }
& powercfg.exe /setactive $taskScheme
if ($LASTEXITCODE -ne 0) { throw 'Could not reactivate original scheme.' }
