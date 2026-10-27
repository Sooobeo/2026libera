param([Parameter(Mandatory=$true)][int]$CampaignProcessId,[Parameter(Mandatory=$true)][string]$RecordDirectory)
$ErrorActionPreference='Stop'
$monitorStart=Get-Date
$monitorOutput=Join-Path $RecordDirectory 'memory_observations.jsonl'
$monitorPeak=0L;$monitorMinimumAvailable=[double]::PositiveInfinity;$monitorCount=0
while ($true) {
    $monitorCampaign=Get-Process -Id $CampaignProcessId -ErrorAction SilentlyContinue
    $monitorMemory=Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory,TotalVirtualMemorySize,FreeVirtualMemory
    $monitorWorkers=@(Get-Process -Name 'ollama','llama-server' -ErrorAction SilentlyContinue | Where-Object {$_.Path -like '*\tmp\v63_local_ollama\portable\*'} | Select-Object Id,Name,WorkingSet64,PrivateMemorySize64,CPU)
    if ($monitorCampaign) {
        $monitorWorkers += $monitorCampaign | Select-Object Id,Name,WorkingSet64,PrivateMemorySize64,CPU
        $monitorChildren=@(Get-CimInstance Win32_Process -Filter "ParentProcessId=$CampaignProcessId" | Where-Object {$_.Name -eq 'python.exe'})
        foreach ($monitorChild in $monitorChildren) {
            $monitorWorkers += Get-Process -Id $monitorChild.ProcessId -ErrorAction SilentlyContinue | Select-Object Id,Name,WorkingSet64,PrivateMemorySize64,CPU
        }
    }
    $monitorTotal=($monitorWorkers | Measure-Object WorkingSet64 -Sum).Sum
    $monitorPeak=[Math]::Max($monitorPeak,$monitorTotal);$monitorMinimumAvailable=[Math]::Min($monitorMinimumAvailable,$monitorMemory.FreePhysicalMemory)
    [ordered]@{recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o');campaign_alive=($null -ne $monitorCampaign);memory=$monitorMemory;processes=$monitorWorkers;combined_working_set_bytes=$monitorTotal} | ConvertTo-Json -Depth 5 -Compress | Add-Content -LiteralPath $monitorOutput -Encoding UTF8
    $monitorCount++
    if (-not $monitorCampaign) { break }
    Start-Sleep -Seconds 10
}
[ordered]@{status='campaign_process_exited';observations=$monitorCount;elapsed_seconds=((Get-Date)-$monitorStart).TotalSeconds;peak_combined_working_set_bytes=$monitorPeak;minimum_available_physical_memory_KiB=$monitorMinimumAvailable;recorded_at_utc=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $RecordDirectory 'memory_summary.json') -Encoding UTF8
