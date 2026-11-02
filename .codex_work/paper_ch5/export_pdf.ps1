param([string]$InputDocx, [string]$OutputPdf)
$ErrorActionPreference = 'Stop'
$word = $null
$doc = $null
try {
    Write-Output 'CREATE_WORD'
    $word = New-Object -ComObject Word.Application
    Write-Output 'WORD_CREATED'
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    Write-Output 'OPEN_DOCUMENT'
    $doc = $word.Documents.Open($InputDocx, $false, $true, $false)
    Write-Output 'DOCUMENT_OPENED'
    $doc.SaveAs2([ref]$OutputPdf, [ref]17)
    Write-Output 'PDF_EXPORTED'
} finally {
    if ($null -ne $doc) {
        $doc.Close(0)
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc)
    }
    if ($null -ne $word) {
        $word.Quit()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
    }
}
