$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
Add-Type -AssemblyName System.IO.Compression.FileSystem
$root='C:\Users\Insun\2026libera'
$source=Join-Path $root 'paper\LIBERA_소논문_최종결과반영_20261030.docx'
$output=Join-Path $root 'paper\LIBERA_소논문_서론_각주포함_20261101.docx'
$qa=Join-Path $root 'tmp\intro_standalone_20261101'
$utf8=New-Object Text.UTF8Encoding($false)
if (Test-Path -LiteralPath $output) { throw 'Standalone output already exists.' }
[void][IO.Directory]::CreateDirectory($qa)
$sourceHash=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
$zip=[IO.Compression.ZipFile]::OpenRead($source)
try {
    $reader=New-Object IO.StreamReader($zip.GetEntry('word/document.xml').Open(),$utf8)
    try { $doc=New-Object Xml.XmlDocument; $doc.PreserveWhitespace=$true; $doc.LoadXml($reader.ReadToEnd()) } finally { $reader.Dispose() }
    $ns=New-Object Xml.XmlNamespaceManager($doc.NameTable)
    $w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'; $ns.AddNamespace('w',$w)
    $body=$doc.SelectSingleNode('/w:document/w:body',$ns)
    $start=$null; $end=$null
    foreach ($p in $body.SelectNodes('./w:p',$ns)) {
        $text=-join @($p.SelectNodes('.//w:t',$ns) | ForEach-Object {$_.InnerText})
        if ($text -ceq '1. 문제 제기') { $start=$p }
        if ($text -ceq '2. 선행연구와 분석 틀') { $end=$p }
    }
    if (-not ($start -and $end)) { throw 'Introduction boundaries are missing.' }
    $keep=@(); $node=$start
    while ($node -ne $end) { $keep += $node.CloneNode($true); $node=$node.NextSibling }
    if ($keep.Count -ne 11) { throw 'Unexpected introduction paragraph count.' }
    $originalParagraphs=@($keep | Select-Object -Skip 1 | ForEach-Object {$_.OuterXml})
    $section=$body.SelectSingleNode('./w:sectPr',$ns).CloneNode($true)
    foreach ($node in @($body.ChildNodes)) { [void]$body.RemoveChild($node) }
    foreach ($node in $keep) { [void]$body.AppendChild($node) }
    [void]$body.AppendChild($section)
    $title=$body.SelectSingleNode('./w:p',$ns)
    foreach ($node in @($title.ChildNodes)) { if ($node.LocalName -ne 'pPr') {[void]$title.RemoveChild($node)} }
    $run=$doc.CreateElement('w','r',$w); $rp=$doc.CreateElement('w','rPr',$w)
    $color=$doc.CreateElement('w','color',$w); [void]$color.SetAttribute('val',$w,'000000'); [void]$rp.AppendChild($color); [void]$run.AppendChild($rp)
    $text=$doc.CreateElement('w','t',$w); $text.InnerText='서론'; [void]$run.AppendChild($text); [void]$title.AppendChild($run)
    $afterParagraphs=@($body.SelectNodes('./w:p',$ns) | Select-Object -Skip 1 | ForEach-Object {$_.OuterXml})
    if (($originalParagraphs -join '') -cne ($afterParagraphs -join '')) { throw 'Extracted introduction text changed.' }
    $ids=@($doc.SelectNodes('//w:footnoteReference',$ns) | ForEach-Object {$_.GetAttribute('id',$w)})
    if (($ids -join ',') -cne '1,2,3,4,5,6,7,8') { throw 'Footnote references changed.' }
    if ($doc.SelectNodes('//w:tbl|//w:drawing',$ns).Count -ne 0) { throw 'Unexpected non-introduction content.' }
    $check=New-Object Xml.XmlDocument; $check.LoadXml($doc.OuterXml)
    $stream=New-Object IO.FileStream($output,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
    $out=New-Object IO.Compression.ZipArchive($stream,[IO.Compression.ZipArchiveMode]::Create,$false)
    try {
        foreach ($entry in $zip.Entries) {
            $dest=$out.CreateEntry($entry.FullName,[IO.Compression.CompressionLevel]::Optimal); $to=$dest.Open()
            try {
                if ($entry.FullName -ceq 'word/document.xml') { $bytes=$utf8.GetBytes($doc.OuterXml); $to.Write($bytes,0,$bytes.Length) }
                else { $from=$entry.Open(); try {$from.CopyTo($to)} finally {$from.Dispose()} }
            } finally {$to.Dispose()}
        }
    } finally {$out.Dispose(); $stream.Dispose()}
} finally {$zip.Dispose()}
if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -cne $sourceHash) { throw 'Source document changed.' }
$record=[ordered]@{status='created_pending_render'; path=$output; paragraphs=10; footnotes=8; original_source_unchanged=$true; body_paragraphs_preserved_exactly=$true; source_sha256=$sourceHash.ToLowerInvariant(); output_sha256=(Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant()}
[IO.File]::WriteAllText((Join-Path $qa 'extraction_check.json'),($record | ConvertTo-Json)+"`n",$utf8)
Write-Output ($record | ConvertTo-Json)
