param([string]$InputDocx, [string]$OutputPdf)
$ErrorActionPreference = 'Stop'
$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $doc = $word.Documents.Open($InputDocx, $false, $true, $false)
    $doc.Repaginate()
    $doc.ExportAsFixedFormat($OutputPdf, 17)
    Write-Output ('PAGES=' + $doc.ComputeStatistics(2))
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
