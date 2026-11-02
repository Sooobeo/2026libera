$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
Add-Type -AssemblyName System.IO.Compression.FileSystem
$root='C:\Users\Insun\2026libera'
$task=Join-Path $root 'research\paper_final_20261030\intro_condensed_20261101'
$qa=Join-Path $root 'tmp\intro_condensed_20261101'
$source=Join-Path $root 'paper\LIBERA_소논문_서론_각주포함_20261101.docx'
$output=Join-Path $root 'paper\LIBERA_소논문_서론_축약본_각주포함_20261101.docx'
$utf8=New-Object Text.UTF8Encoding($false)
$data=Get-Content -LiteralPath (Join-Path $task 'content.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$old=Get-Content -LiteralPath (Join-Path $root 'research\paper_final_20261030\intro_full_revision_20261101\content.json') -Encoding UTF8 -Raw | ConvertFrom-Json
if ($data.paragraphs[4] -cne $old.paragraphs[4]) { throw 'Requested model-selection assumption changed.' }
if (Test-Path -LiteralPath $output) { throw 'Output already exists.' }
[void][IO.Directory]::CreateDirectory($qa)
$sourceHash=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
$w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
$rns='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
function Xml($text) { $d=New-Object Xml.XmlDocument; $d.PreserveWhitespace=$true; $d.LoadXml($text); return ,$d }
function Read-Zip($zip,$name) { $rd=New-Object IO.StreamReader($zip.GetEntry($name).Open(),$utf8); try {return $rd.ReadToEnd()} finally {$rd.Dispose()} }
function El($d,$name) {return ,$d.CreateElement('w',$name,$w)}
function Attr($el,$name,$value) {[void]$el.SetAttribute($name,$w,[string]$value)}
function Add-Text($d,$p,$value) {
    $r=El $d 'r'; $t=El $d 't'; $a=$d.CreateAttribute('xml','space','http://www.w3.org/XML/1998/namespace'); $a.Value='preserve'; [void]$t.Attributes.Append($a); $t.InnerText=$value; [void]$r.AppendChild($t); [void]$p.AppendChild($r)
}
function Add-Rich($d,$p,$value,$links) {
    $cursor=0
    foreach ($m in [regex]::Matches($value,'\[\^intro(\d+)\]|\[([^\]]+)\]\((https?://[^)]+)\)')) {
        if ($m.Index -gt $cursor) {Add-Text $d $p $value.Substring($cursor,$m.Index-$cursor)}
        $r=El $d 'r'; $rp=El $d 'rPr'; $s=El $d 'rStyle'
        if ($m.Groups[1].Success) {
            Attr $s 'val' 'FootnoteReference'; [void]$rp.AppendChild($s); [void]$r.AppendChild($rp)
            $ref=El $d 'footnoteReference'; Attr $ref 'id' $m.Groups[1].Value; [void]$r.AppendChild($ref); [void]$p.AppendChild($r)
        } else {
            $id=$links[$m.Groups[3].Value]; if (-not $id) {throw 'Footnote hyperlink is not in the verified original package.'}
            Attr $s 'val' 'Hyperlink'; [void]$rp.AppendChild($s); [void]$r.AppendChild($rp)
            $t=El $d 't'; $t.InnerText=$m.Groups[2].Value; [void]$r.AppendChild($t)
            $link=El $d 'hyperlink'; [void]$link.SetAttribute('id',$rns,$id); [void]$link.AppendChild($r); [void]$p.AppendChild($link)
        }
        $cursor=$m.Index+$m.Length
    }
    if ($cursor -lt $value.Length) {Add-Text $d $p $value.Substring($cursor)}
}
function Plain($text) {return [regex]::Replace([regex]::Replace($text,'\[\^intro\d+\]',''),'\[([^\]]+)\]\(https?://[^)]+\)','$1')}
$zip=[IO.Compression.ZipFile]::OpenRead($source)
try {
    $doc=Xml (Read-Zip $zip 'word/document.xml'); $foot=Xml (Read-Zip $zip 'word/footnotes.xml'); $footRels=Xml (Read-Zip $zip 'word/_rels/footnotes.xml.rels')
    $ns=New-Object Xml.XmlNamespaceManager($doc.NameTable); $ns.AddNamespace('w',$w)
    $body=$doc.SelectSingleNode('/w:document/w:body',$ns); $ps=@($body.SelectNodes('./w:p',$ns))
    if ($ps.Count -ne 11) {throw 'Source is not the standalone introduction.'}
    $template=$ps[1].SelectSingleNode('./w:pPr',$ns)
    $section=$body.SelectSingleNode('./w:sectPr',$ns)
    foreach ($p in @($ps | Select-Object -Skip 1)) {[void]$body.RemoveChild($p)}
    foreach ($text in $data.paragraphs) {
        $p=El $doc 'p'; if ($template) {[void]$p.AppendChild($template.CloneNode($true))}; Add-Rich $doc $p $text @{}; [void]$body.InsertBefore($p,$section)
        $actual=-join @($p.SelectNodes('.//w:t',$ns) | ForEach-Object {$_.InnerText}); if ($actual -cne (Plain $text)) {throw 'Body text mismatch.'}
    }
    $links=@{}; foreach ($rel in $footRels.DocumentElement.ChildNodes) {$links[$rel.GetAttribute('Target')]=$rel.GetAttribute('Id')}
    $footNS=New-Object Xml.XmlNamespaceManager($foot.NameTable); $footNS.AddNamespace('w',$w)
    foreach ($note in $data.notes) {
        $node=$foot.SelectSingleNode('/w:footnotes/w:footnote[@w:id="'+$note.id+'"]',$footNS); if (-not $node) {throw 'Original note missing.'}
        $p=$node.SelectSingleNode('./w:p',$footNS)
        foreach ($child in @($p.ChildNodes)) {if ($child.LocalName -ne 'pPr') {[void]$p.RemoveChild($child)}}
        $r=El $foot 'r'; $rp=El $foot 'rPr'; $s=El $foot 'rStyle'; Attr $s 'val' 'FootnoteReference'; [void]$rp.AppendChild($s); [void]$r.AppendChild($rp); [void]$r.AppendChild((El $foot 'footnoteRef')); [void]$p.AppendChild($r)
        Add-Text $foot $p ' '; Add-Rich $foot $p $note.text $links
        $actual=(-join @($p.SelectNodes('.//w:t',$footNS) | ForEach-Object {$_.InnerText})).Trim(); if ($actual -cne (Plain $note.text)) {throw 'Footnote text mismatch.'}
    }
    $ids=@($doc.SelectNodes('//w:footnoteReference',$ns) | ForEach-Object {$_.GetAttribute('id',$w)}); if (($ids -join ',') -cne '1,2,3,4,5,6,7,8') {throw 'Footnote numbering mismatch.'}
    $replacements=@{'word/document.xml'=$doc.OuterXml; 'word/footnotes.xml'=$foot.OuterXml}
    foreach ($xml in $replacements.Values) {[void](Xml $xml)}
    $stream=New-Object IO.FileStream($output,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write); $out=New-Object IO.Compression.ZipArchive($stream,[IO.Compression.ZipArchiveMode]::Create,$false)
    try {
        foreach ($entry in $zip.Entries) {
            $to=$out.CreateEntry($entry.FullName,[IO.Compression.CompressionLevel]::Optimal).Open()
            try {if ($replacements.ContainsKey($entry.FullName)) {$bytes=$utf8.GetBytes($replacements[$entry.FullName]); $to.Write($bytes,0,$bytes.Length)} else {$from=$entry.Open(); try {$from.CopyTo($to)} finally {$from.Dispose()}}} finally {$to.Dispose()}
        }
    } finally {$out.Dispose(); $stream.Dispose()}
} finally {$zip.Dispose()}
if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -cne $sourceHash) {throw 'Previous version changed.'}
$oldChars=($old.paragraphs | ForEach-Object {(Plain $_).Length} | Measure-Object -Sum).Sum
$newChars=($data.paragraphs | ForEach-Object {(Plain $_).Length} | Measure-Object -Sum).Sum
$record=[ordered]@{status='created_pending_render'; output=$output; original_body_characters=$oldChars; condensed_body_characters=$newChars; reduction_percent=[Math]::Round(100*(1-$newChars/$oldChars),1); paragraphs=$data.paragraphs.Count; native_footnotes=$data.notes.Count; requested_assumption_preserved=$true; source_unchanged=$true; output_sha256=(Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant()}
[IO.File]::WriteAllText((Join-Path $qa 'revision_check.json'),($record | ConvertTo-Json)+"`n",$utf8)
Write-Output ($record | ConvertTo-Json)
