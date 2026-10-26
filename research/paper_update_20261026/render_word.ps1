param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$PdfPath,
    [Parameter(Mandatory = $true)][string]$ReceiptPath
)

# Windows-only fallback for the managed renderer's unavailable LibreOffice.
# This script creates its own Word COM instance; it never attaches to a running
# instance, terminates a process, changes a template, or saves the input DOCX.
$ErrorActionPreference = 'Stop'
$startedAt = [DateTime]::UtcNow
$word = $null
$documents = $null
$document = $null
$documentWindow = $null
$ownedProcess = $null
$ownedStartTime = $null
$oldSecurity = $null
$oldAlerts = $null
$failure = $null
$exitCode = 1
$receipt = [ordered]@{
    receipt_version = 'v500_native_word_render_1'
    status = 'started'
    renderer = 'native_Microsoft_Word_independent_COM_fallback'
    managed_LibreOffice_available = $false
    started_at_utc = $startedAt.ToString('o')
    input_docx = $null
    input_sha256_before = $null
    input_sha256_after = $null
    pdf_path = $null
    pdf_sha256 = $null
    existing_word_pids_before = @()
    existing_word_pids_still_running_after = @()
    owned_word_pid = $null
    owned_word_start_time_utc = $null
    owned_word_executable = $null
    fresh_process_verified = $false
    document_window_pid_verified = $false
    open_read_only = $true
    add_to_recent_files = $false
    input_saved = $false
    document_closed_without_saving = $false
    quit_requested_only_for_owned_instance = $false
    owned_process_exited = $null
    process_kill_called = $false
    cleanup_errors = @()
    error = $null
}

function Release-ComReference([object]$Reference) {
    if ($null -ne $Reference -and [Runtime.InteropServices.Marshal]::IsComObject($Reference)) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($Reference)
    }
}

function Test-OwnedWordProcess {
    if ($null -eq $script:ownedProcess -or $null -eq $script:ownedStartTime) { return $false }
    try {
        $current = Get-Process -Id $script:ownedProcess.Id -ErrorAction SilentlyContinue
        if ($null -eq $current) { return $false }
        return (
            $current.ProcessName -eq 'WINWORD' -and
            $current.StartTime.ToUniversalTime() -eq $script:ownedStartTime -and
            [string]::Equals($current.Path, $script:expectedWordExe, [StringComparison]::OrdinalIgnoreCase) -and
            $script:existingPids -notcontains $current.Id
        )
    } catch {
        # A process can exit between lookup and reading its start time.
        return $false
    }
}

try {
    $resolvedInput = (Resolve-Path -LiteralPath $InputPath).Path
    $resolvedPdf = [IO.Path]::GetFullPath($PdfPath)
    $resolvedReceipt = [IO.Path]::GetFullPath($ReceiptPath)
    if ([IO.Path]::GetExtension($resolvedInput) -ine '.docx') { throw 'Input must be a DOCX file.' }
    if ([IO.Path]::GetExtension($resolvedPdf) -ine '.pdf') { throw 'PdfPath must end in .pdf.' }
    if ([IO.Path]::GetExtension($resolvedReceipt) -ine '.json') { throw 'ReceiptPath must end in .json.' }
    if ([string]::Equals($resolvedPdf, $resolvedReceipt, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'PDF and receipt paths must differ.'
    }
    if ((Test-Path -LiteralPath $resolvedPdf) -or (Test-Path -LiteralPath $resolvedReceipt)) {
        throw 'Refusing to overwrite an existing PDF or receipt.'
    }
    foreach ($parentDir in @([IO.Path]::GetDirectoryName($resolvedPdf), [IO.Path]::GetDirectoryName($resolvedReceipt))) {
        if (-not (Test-Path -LiteralPath $parentDir)) {
            [void][IO.Directory]::CreateDirectory($parentDir)
        }
    }
    $receipt.input_docx = $resolvedInput
    $receipt.input_sha256_before = (Get-FileHash -LiteralPath $resolvedInput -Algorithm SHA256).Hash.ToLowerInvariant()
    $receipt.pdf_path = $resolvedPdf
    $expectedWordExe = (Resolve-Path -LiteralPath 'C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE').Path
    $existingPids = @(Get-Process -Name WINWORD -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    $receipt.existing_word_pids_before = @($existingPids)

    if (-not ('V493WordNativeWindow' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class V493WordNativeWindow {
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
'@
    }

    # CreateObject semantics: do not substitute GetActiveObject or GetObject.
    $word = New-Object -ComObject Word.Application
    $newProcesses = @()
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        $newProcesses = @(Get-Process -Name WINWORD -ErrorAction SilentlyContinue | Where-Object {
            $existingPids -notcontains $_.Id -and $_.StartTime.ToUniversalTime() -ge $startedAt
        })
        if ($newProcesses.Count -gt 0) { break }
        Start-Sleep -Milliseconds 500
    }
    if ($newProcesses.Count -ne 1) { throw 'Cannot uniquely identify a new Word process; no instance will be quit.' }
    $candidate = $newProcesses[0]
    if (-not [string]::Equals($candidate.Path, $expectedWordExe, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'New Word process executable does not match the installed Word path.'
    }
    $documents = $word.Documents
    if ($documents.Count -ne 0) { throw 'The new COM instance already has documents; refusing to operate on it.' }
    $ownedProcess = $candidate
    $ownedStartTime = $candidate.StartTime.ToUniversalTime()
    $receipt.owned_word_pid = $candidate.Id
    $receipt.owned_word_start_time_utc = $ownedStartTime.ToString('o')
    $receipt.owned_word_executable = $candidate.Path
    $receipt.fresh_process_verified = $true
    $word.Visible = $false
    $oldAlerts = $word.DisplayAlerts
    $word.DisplayAlerts = 0
    $oldSecurity = $word.AutomationSecurity
    $word.AutomationSecurity = 3
    $missing = [Type]::Missing
    try {
        $wordOpenArgs = [object[]]@($resolvedInput, $false, $true, $false)
        $document = $documents.GetType().InvokeMember('Open', [Reflection.BindingFlags]::InvokeMethod, $null, $documents, $wordOpenArgs)
    } finally {
        if (Test-OwnedWordProcess) { $word.AutomationSecurity = $oldSecurity }
    }
    if (-not $document.ReadOnly) { throw 'Word did not open the DOCX read-only.' }
    $documentWindow = $document.ActiveWindow
    [uint32]$windowProcessId = 0
    [void][V493WordNativeWindow]::GetWindowThreadProcessId([IntPtr]$documentWindow.Hwnd, [ref]$windowProcessId)
    if ($windowProcessId -ne $ownedProcess.Id -or -not (Test-OwnedWordProcess)) {
        throw 'Opened document window does not belong to the verified new Word process.'
    }
    $receipt.document_window_pid_verified = $true
    $document.ExportAsFixedFormat($resolvedPdf, 17, $false)
    if (-not (Test-Path -LiteralPath $resolvedPdf) -or (Get-Item -LiteralPath $resolvedPdf).Length -eq 0) {
        throw 'Word did not produce a nonempty PDF.'
    }
    $receipt.pdf_sha256 = (Get-FileHash -LiteralPath $resolvedPdf -Algorithm SHA256).Hash.ToLowerInvariant()
    $receipt.status = 'exported_pending_cleanup'
    $exitCode = 0
} catch {
    $failure = $_.Exception.Message
    $receipt.status = 'failed'
    $receipt.error = $failure
} finally {
    if ($null -ne $document) {
        try {
            $wordCloseNoSave = [object]0; $document.Close([ref]$wordCloseNoSave)
            $receipt.document_closed_without_saving = $true
        } catch { $receipt.cleanup_errors += ('Document.Close: ' + $_.Exception.Message) }
    }
    if ($null -ne $word -and (Test-OwnedWordProcess)) {
        try {
            if ($null -ne $oldSecurity) { $word.AutomationSecurity = $oldSecurity }
            if ($null -ne $oldAlerts) { $word.DisplayAlerts = $oldAlerts }
            $wordQuitNoSave = [object]0; $word.Quit([ref]$wordQuitNoSave)
            $receipt.quit_requested_only_for_owned_instance = $true
        } catch { $receipt.cleanup_errors += ('Owned Application.Quit: ' + $_.Exception.Message) }
    }
    foreach ($comReference in @($documentWindow, $document, $documents, $word)) {
        try { Release-ComReference $comReference } catch { $receipt.cleanup_errors += ('COM release: ' + $_.Exception.Message) }
    }
    $documentWindow = $null
    $document = $null
    $documents = $null
    $word = $null
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
    if ($null -ne $ownedProcess) {
        for ($attempt = 0; $attempt -lt 10; $attempt++) {
            if (-not (Test-OwnedWordProcess)) { break }
            Start-Sleep -Milliseconds 500
        }
        $receipt.owned_process_exited = -not (Test-OwnedWordProcess)
        if (-not $receipt.owned_process_exited) { $receipt.cleanup_errors += 'Owned Word process remains running; no process was killed.' }
    }
    $receipt.existing_word_pids_still_running_after = @(Get-Process -Name WINWORD -ErrorAction SilentlyContinue | Where-Object {
        $existingPids -contains $_.Id
    } | Select-Object -ExpandProperty Id)
    if ($null -ne $receipt.input_docx -and (Test-Path -LiteralPath $receipt.input_docx)) {
        $receipt.input_sha256_after = (Get-FileHash -LiteralPath $receipt.input_docx -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($receipt.input_sha256_after -ne $receipt.input_sha256_before) {
            $receipt.cleanup_errors += 'Input DOCX SHA256 changed during read-only conversion.'
        }
    }
    if ($exitCode -eq 0 -and $receipt.cleanup_errors.Count -eq 0) {
        $receipt.status = 'completed'
    } elseif ($exitCode -eq 0) {
        $receipt.status = 'exported_with_cleanup_failure'
        $exitCode = 1
    }
    $receipt.finished_at_utc = [DateTime]::UtcNow.ToString('o')
    if ($null -ne $resolvedReceipt -and -not (Test-Path -LiteralPath $resolvedReceipt)) {
        $json = $receipt | ConvertTo-Json -Depth 8
        [IO.File]::WriteAllText($resolvedReceipt, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    }
}

if ($exitCode -eq 0) {
    Write-Output ('PDF written: ' + $receipt.pdf_path)
} else {
    Write-Error -Message ('Word fallback failed: ' + $receipt.error + ' Cleanup: ' + ($receipt.cleanup_errors -join '; ')) -ErrorAction Continue
}
exit $exitCode
