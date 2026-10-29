param([switch]$SelfTest)

# Independent local observer. Does not change or restart the experiment.
$ErrorActionPreference = 'Stop'
$v64Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$v64Out = Join-Path $v64Root 'data\v64_20261028\main_only_results'

function Read-V64Json([string]$Path) {
    for ($v64ReadAttempt = 0; $v64ReadAttempt -lt 5; $v64ReadAttempt++) {
        try { return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json) }
        catch { if ($v64ReadAttempt -eq 4) { throw }; Start-Sleep -Milliseconds 100 }
    }
}

function Write-V64NoticeState([string]$Path, $Value) {
    $v64Temporary = $Path + '.writing'
    [IO.File]::WriteAllText($v64Temporary, ($Value | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
    $v64WriteDeadline = [DateTime]::UtcNow.AddSeconds(10)
    while ($true) {
        try { Move-Item -LiteralPath $v64Temporary -Destination $Path -Force; return }
        catch { if ([DateTime]::UtcNow -ge $v64WriteDeadline) { throw }; Start-Sleep -Milliseconds 100 }
    }
}

function Get-V64NoticeKind($Receipt, [string]$ExpectedRunId) {
    if ([string]$Receipt.run_id -cne $ExpectedRunId) { return 'identity_error' }
    if ($Receipt.status -eq 'completed') {
        if ($Receipt.exit_code -eq 0 -and $Receipt.terminal_trajectories -eq 160 -and
            $Receipt.analysis_status -eq 'completed_descriptive_analysis') { return 'completed' }
        return 'incomplete'
    }
    if ($Receipt.status -in @('stopped_incomplete', 'supervisor_error')) { return 'incomplete' }
    if ($Receipt.status -in @('starting', 'running')) { return 'running' }
    return 'incomplete'
}

if ($SelfTest) {
    $v64Fixture = [pscustomobject]@{ run_id='test'; status='completed'; exit_code=0;
        terminal_trajectories=160; analysis_status='completed_descriptive_analysis' }
    if ((Get-V64NoticeKind $v64Fixture 'test') -ne 'completed') { throw 'Complete receipt test failed' }
    $v64Fixture.terminal_trajectories=159
    if ((Get-V64NoticeKind $v64Fixture 'test') -ne 'incomplete') { throw 'Partial receipt test failed' }
    $v64Fixture.terminal_trajectories=160; $v64Fixture.analysis_status='incomplete'
    if ((Get-V64NoticeKind $v64Fixture 'test') -ne 'incomplete') { throw 'Analysis guard test failed' }
    $v64Fixture.analysis_status='completed_descriptive_analysis'; $v64Fixture.exit_code=2
    if ((Get-V64NoticeKind $v64Fixture 'test') -ne 'incomplete') { throw 'Exit guard test failed' }
    $v64Fixture.status='running'
    if ((Get-V64NoticeKind $v64Fixture 'test') -ne 'running') { throw 'Running test failed' }
    if ((Get-V64NoticeKind $v64Fixture 'another') -ne 'identity_error') { throw 'Identity test failed' }
    $v64Fixture.status='stopped_incomplete'
    if ((Get-V64NoticeKind $v64Fixture 'test') -ne 'incomplete') { throw 'Stopped test failed' }
    $v64Fixture.status='supervisor_error'
    if ((Get-V64NoticeKind $v64Fixture 'test') -ne 'incomplete') { throw 'Supervisor error test failed' }
    Write-Output '{"status":"passed","checks":8,"model_requests":0,"notifications_shown":0}'
    exit 0
}

$v64Active = Read-V64Json (Join-Path $v64Out 'active_execution.json')
$v64RunId = [string]$v64Active.run_id
$v64ReceiptPath = [string]$v64Active.receipt_path
$v64NoticeDirectory = Join-Path $v64Out ('notifications\' + $v64RunId)
New-Item -ItemType Directory -Path $v64NoticeDirectory -Force | Out-Null
$v64StatePath = Join-Path $v64NoticeDirectory 'notification_state.json'
$v64Lock = [IO.File]::Open((Join-Path $v64NoticeDirectory 'observer.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
$v64Watcher = $null
$v64Icon = $null
$v64State = [ordered]@{
    schema='libera_local_completion_notification_v1'; run_id=$v64RunId; watcher_pid=$PID
    status='starting'; activated_at_utc=[DateTime]::UtcNow.ToString('o'); receipt_path=$v64ReceiptPath
    event_driven=$true; safety_check_seconds=30; internet_required=$false
    completion_popup=$true; sound=$true; experiment_generation_requests=0
}

try {
    if (Test-Path -LiteralPath $v64StatePath) {
        $v64Previous = Read-V64Json $v64StatePath
        if ($v64Previous.status -eq 'acknowledged') { exit 0 }
    }
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $v64Icon = New-Object System.Windows.Forms.NotifyIcon
    $v64Icon.Icon = [System.Drawing.SystemIcons]::Information
    $v64Icon.Text = 'LIBERA experiment notification'
    $v64Icon.Visible = $true
    $v64Icon.BalloonTipTitle = 'LIBERA 알림 연결 완료'
    $v64Icon.BalloonTipText = '실험과 분석이 끝나거나 실행이 중단되면 팝업과 소리로 알려드립니다.'
    $v64Icon.ShowBalloonTip(10000)
    $v64Watcher = New-Object IO.FileSystemWatcher (Split-Path -Parent $v64ReceiptPath), (Split-Path -Leaf $v64ReceiptPath)
    $v64Watcher.NotifyFilter = [IO.NotifyFilters]::FileName -bor [IO.NotifyFilters]::LastWrite -bor [IO.NotifyFilters]::Size
    $v64State.status = 'armed'
    Write-V64NoticeState $v64StatePath $v64State
    $v64MissingSince = $null
    $v64InitialReceipt = Read-V64Json $v64ReceiptPath
    $v64ExpectedProcess = Get-Process -Id ([int]$v64InitialReceipt.campaign_pid) -ErrorAction SilentlyContinue
    $v64ExpectedStart = if ($v64ExpectedProcess) { $v64ExpectedProcess.StartTime.ToUniversalTime() } else { $null }

    while ($true) {
        $v64Receipt = Read-V64Json $v64ReceiptPath
        $v64Kind = Get-V64NoticeKind $v64Receipt $v64RunId
        if ($v64Kind -ne 'running') { break }
        $v64Process = Get-Process -Id ([int]$v64Receipt.campaign_pid) -ErrorAction SilentlyContinue
        $v64StillRunning = $null -ne $v64Process
        if ($v64StillRunning -and $null -ne $v64ExpectedStart) {
            $v64StillRunning = $v64Process.StartTime.ToUniversalTime() -eq $v64ExpectedStart
        }
        if ($v64StillRunning) { $v64MissingSince = $null }
        elseif ($null -eq $v64MissingSince) { $v64MissingSince = [DateTime]::UtcNow }
        elseif (([DateTime]::UtcNow - $v64MissingSince).TotalSeconds -ge 30) {
            $v64Kind = 'process_exited_without_final_receipt'; break
        }
        $null = $v64Watcher.WaitForChanged([IO.WatcherChangeTypes]::All, 30000)
    }

    $v64Watcher.Dispose(); $v64Watcher = $null
    $v64FinishedText = [DateTimeOffset]::Now.ToString('yyyy-MM-dd HH:mm:ss zzz')
    if ($v64Kind -eq 'completed') {
        $v64Title = 'LIBERA 실험·분석 완료'
        $v64ElapsedSeconds = [double]$v64Receipt.elapsed_seconds
        # A resumed supervisor times its own segment. Report the complete
        # same-run wall time, including an explicitly recorded interruption.
        $v64SameRunStarts = @(Get-ChildItem -Path (Join-Path $v64Out 'execution\*\process_receipt.json') -File | ForEach-Object {
            $v64Segment = Read-V64Json $_.FullName
            if ($v64Segment.run_id -eq $v64RunId -and $v64Segment.started_at.utc) {
                [DateTimeOffset]::Parse([string]$v64Segment.started_at.utc)
            }
        })
        if ($v64SameRunStarts.Count -gt 0 -and $v64Receipt.finished_at.utc) {
            $v64FirstStart = $v64SameRunStarts | Sort-Object | Select-Object -First 1
            $v64ElapsedSeconds = ([DateTimeOffset]::Parse([string]$v64Receipt.finished_at.utc) - $v64FirstStart).TotalSeconds
        }
        $v64Elapsed = [TimeSpan]::FromSeconds($v64ElapsedSeconds)
        $v64Duration = '{0}시간 {1}분 {2}초' -f [Math]::Floor($v64Elapsed.TotalHours), $v64Elapsed.Minutes, $v64Elapsed.Seconds
        $v64Message = "160개 작업 흐름의 종료 기록과 최종 분석이 완료됐습니다.`r`n`r`n전체 경과시간(중단 포함): $v64Duration`r`n확인 시각: $v64FinishedText`r`n`r`n이 채팅에서 '결과 확인해줘'라고 말씀하시면 결과를 확인할 수 있습니다."
        $v64Icon.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info
        [System.Media.SystemSounds]::Asterisk.Play()
    } else {
        $v64Title = 'LIBERA 실험 중단 — 확인 필요'
        $v64Message = "실험이 완료되지 않은 상태로 실행이 중단됐거나 종료 기록을 확인할 수 없습니다.`r`n`r`n확인 시각: $v64FinishedText`r`n`r`n이 채팅에서 '실험 상태 확인해줘'라고 말씀해 주세요."
        $v64Icon.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Warning
        [System.Media.SystemSounds]::Exclamation.Play()
    }
    $v64State.status = 'notification_shown'
    $v64State['result'] = $v64Kind
    $v64State['notified_at_utc'] = [DateTime]::UtcNow.ToString('o')
    $v64State['title'] = $v64Title
    $v64State['message'] = $v64Message
    Write-V64NoticeState $v64StatePath $v64State
    $v64Icon.BalloonTipTitle = $v64Title
    $v64Icon.BalloonTipText = $v64Title
    $v64Icon.ShowBalloonTip(15000)

    # The dialog remains until acknowledged, even if a transient toast is missed.
    $v64Form = New-Object System.Windows.Forms.Form
    $v64Form.Text = $v64Title
    $v64Form.ClientSize = New-Object Drawing.Size(540, 280)
    $v64Form.StartPosition = 'CenterScreen'
    $v64Form.TopMost = $true
    $v64Form.Font = New-Object Drawing.Font('Malgun Gothic', 11)
    $v64Form.FormBorderStyle = 'FixedDialog'
    $v64Form.MaximizeBox = $false
    $v64Label = New-Object System.Windows.Forms.Label
    $v64Label.Location = New-Object Drawing.Point(22, 20)
    $v64Label.Size = New-Object Drawing.Size(496, 190)
    $v64Label.Text = $v64Message
    $v64Form.Controls.Add($v64Label)
    $v64Button = New-Object System.Windows.Forms.Button
    $v64Button.Text = '확인'
    $v64Button.Location = New-Object Drawing.Point(414, 225)
    $v64Button.Size = New-Object Drawing.Size(100, 34)
    $v64Button.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $v64Form.AcceptButton = $v64Button
    $v64Form.Controls.Add($v64Button)
    $null = $v64Form.ShowDialog()
    $v64Form.Dispose()
    $v64State.status = 'acknowledged'
    $v64State['acknowledged_at_utc'] = [DateTime]::UtcNow.ToString('o')
    Write-V64NoticeState $v64StatePath $v64State
} catch {
    $v64State.status = 'observer_error'
    $v64State['error'] = $_.Exception.Message
    Write-V64NoticeState $v64StatePath $v64State
    throw
} finally {
    if ($null -ne $v64Watcher) { $v64Watcher.Dispose() }
    if ($null -ne $v64Icon) { $v64Icon.Visible=$false; $v64Icon.Dispose() }
    $v64Lock.Dispose()
}
