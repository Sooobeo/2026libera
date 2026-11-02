$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.Web
$root = 'C:\Users\Insun\2026libera'
$task = Join-Path $root 'research\paper_final_20261030\intro_full_revision_20261101'
$stage = Join-Path $root 'tmp\intro_full_revision_20261101\staged'
$before = Join-Path $task 'before'
$stem = 'LIBERA_소논문_최종결과반영_20261030'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$data = Get-Content -LiteralPath (Join-Path $task 'content.json') -Encoding UTF8 -Raw | ConvertFrom-Json
[void][IO.Directory]::CreateDirectory($stage)
[void][IO.Directory]::CreateDirectory($before)
$originals = @()
foreach ($ext in @('md','html','docx','pdf')) {
    $path = Join-Path $root ('paper\' + $stem + '.' + $ext)
    $backup = Join-Path $before ($stem + '.' + $ext)
    if (-not (Test-Path -LiteralPath $backup)) { Copy-Item -LiteralPath $path -Destination $backup }
    $originals += [ordered]@{ path=$path; sha256=(Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash.ToLowerInvariant() }
}

function Save-Text($path, $text) { [IO.File]::WriteAllText($path, $text, $utf8) }
function Plain($text) { return [regex]::Replace([regex]::Replace($text, '\[([^\]]+)\]\((https?://[^)]+)\)', '$1'), '\[\^intro\d+\]|\*', '') }
function Rich-Html($text) {
    $out = [System.Web.HttpUtility]::HtmlEncode($text)
    $out = [regex]::Replace($out, '\[([^\]]+)\]\((https?://[^)]+)\)', '<a href="$2">$1</a>')
    $out = [regex]::Replace($out, '\[\^intro(\d+)\]', '<sup class="intro-note-ref" id="intro-note-ref-$1"><a href="#intro-note-$1" role="doc-noteref">$1</a></sup>')
    return [regex]::Replace($out, '\*([^*]+)\*', '<em>$1</em>')
}
$oldMd = [IO.File]::ReadAllText((Join-Path $before ($stem+'.md')), $utf8).Replace("`r`n", "`n")
$introStart = $oldMd.IndexOf("## 1. 문제 제기`n`n")
$introEnd = $oldMd.IndexOf("## 2. 선행연구와 분석 틀`n")
if ($introStart -lt 0 -or $introEnd -le $introStart) { throw 'Introduction boundary not found.' }
$notesMd = ($data.notes | ForEach-Object { '[^intro' + $_.id + ']: ' + $_.text }) -join "`n`n"
$introMd = "## 1. 문제 제기`n`n" + ($data.paragraphs -join "`n`n") + "`n`n" + $notesMd + "`n`n"
$newMd = $oldMd.Substring(0,$introStart) + $introMd + $oldMd.Substring($introEnd)
$refMatch = [regex]::Match($oldMd, '(?s)(?<=## 참고문헌\n\n).*?(?=## 부록 A\.)')
if (-not $refMatch.Success) { throw 'Bibliography boundary not found.' }
$oldRefs = @($refMatch.Value.Trim() -split '\n\n')
if ($oldRefs.Count -ne 15) { throw 'Unexpected original bibliography count.' }
$allRefs = @(@($oldRefs) + @($data.new_references) | Sort-Object)
$newMd = [regex]::Replace($newMd, '(?s)(?<=## 참고문헌\n\n).*?(?=## 부록 A\.)', [System.Text.RegularExpressions.MatchEvaluator]{ param($m) ($allRefs -join "`n`n") + "`n`n" })
if ($oldMd.Split(@('## 2. 선행연구와 분석 틀'), [StringSplitOptions]::None)[1].Split(@('## 참고문헌'), [StringSplitOptions]::None)[0] -cne $newMd.Split(@('## 2. 선행연구와 분석 틀'), [StringSplitOptions]::None)[1].Split(@('## 참고문헌'), [StringSplitOptions]::None)[0]) { throw 'Body outside introduction changed.' }
if ($oldMd.Substring($oldMd.IndexOf('## 부록 A.')) -cne $newMd.Substring($newMd.IndexOf('## 부록 A.'))) { throw 'Appendices changed.' }
Save-Text (Join-Path $stage ($stem+'.md')) $newMd

$oldHtml = [IO.File]::ReadAllText((Join-Path $before ($stem+'.html')), $utf8)
$introHtml = ($data.paragraphs | ForEach-Object { '<p>' + (Rich-Html $_) + '</p>' }) -join "`n"
$introHtml += "`n" + '<aside class="intro-footnotes" role="doc-endnotes" aria-label="서론 각주"><p><strong>서론 각주</strong></p><ol>' + "`n"
$introHtml += ($data.notes | ForEach-Object { '<li id="intro-note-' + $_.id + '" role="doc-endnote">' + (Rich-Html $_.text) + ' <a class="intro-backlink" href="#intro-note-ref-' + $_.id + '" aria-label="본문으로 돌아가기">↩</a></li>' }) -join "`n"
$introHtml += "`n</ol></aside>`n"
$htmlPattern = '(?s)(<h2\b[^>]*>1\. 문제 제기</h2>\s*).*?(?=<h2\b[^>]*>2\. 선행연구와 분석 틀</h2>)'
if ([regex]::Matches($oldHtml,$htmlPattern).Count -ne 1) { throw 'HTML introduction boundary is not unique.' }
$newHtml = [regex]::Replace($oldHtml, $htmlPattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $m.Groups[1].Value + $introHtml })
$refHtml = ($allRefs | ForEach-Object { '<p>' + (Rich-Html $_) + '</p>' }) -join "`n"
$newHtml = [regex]::Replace($newHtml, '(?s)(<h2\b[^>]*>참고문헌</h2>\s*).*?(?=<h2\b[^>]*>부록 A\.)', [System.Text.RegularExpressions.MatchEvaluator]{param($m) $m.Groups[1].Value + $refHtml + "`n"})
$noteCss = '.intro-note-ref{font-size:.72em;line-height:0;vertical-align:super;margin-left:2px}.intro-note-ref a{border-bottom:0}.intro-footnotes{margin:26px 0 36px;padding:18px 20px;background:#f8fafb;font-size:12px;line-height:1.7;word-break:normal;overflow-wrap:anywhere}.intro-footnotes ol{padding-left:22px;margin-bottom:0}.intro-footnotes li{margin:10px 0}.intro-backlink{white-space:nowrap}'
$newHtml = $newHtml.Replace('</style>', $noteCss+'</style>')
Save-Text (Join-Path $stage ($stem+'.html')) $newHtml

$w = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
$rns = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
$relsns = 'http://schemas.openxmlformats.org/package/2006/relationships'
$ctns = 'http://schemas.openxmlformats.org/package/2006/content-types'
function Read-ZipText($zip, $name) {
    $entry = $zip.GetEntry($name)
    if ($null -eq $entry) { throw "Missing package entry: $name" }
    $reader = New-Object IO.StreamReader($entry.Open(),$utf8)
    try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
}
function Read-Xml($text) { $d = New-Object Xml.XmlDocument; $d.PreserveWhitespace=$true; $d.LoadXml($text); return ,$d }
function W-El($doc,$name) { return ,$doc.CreateElement('w',$name,$w) }
function W-Attr($el,$name,$val) { [void]$el.SetAttribute($name,$w,[string]$val) }
function W-Child($doc,$parent,$name,$val) { $el=W-El $doc $name; if ($null -ne $val) { W-Attr $el 'val' $val }; [void]$parent.AppendChild($el); return ,$el }
function Get-PText($p) { return -join @($p.SelectNodes('.//w:t',$ns) | ForEach-Object { $_.InnerText }) }
function Add-Rel($rels,$id,$type,$target,$external=$false) {
    $el=$rels.CreateElement('Relationship',$relsns); $el.SetAttribute('Id',$id); $el.SetAttribute('Type',$type); $el.SetAttribute('Target',$target)
    if ($external) { $el.SetAttribute('TargetMode','External') }; [void]$rels.DocumentElement.AppendChild($el)
}
$script:linkCounter=0
function Add-RichText($doc,$p,$text,$rels) {
    $pattern='\[\^intro(\d+)\]|\[([^\]]+)\]\((https?://[^)]+)\)'
    $cursor=0
    foreach ($m in [regex]::Matches($text,$pattern)) {
        if ($m.Index -gt $cursor) { Add-Run $doc $p ($text.Substring($cursor,$m.Index-$cursor).Replace('*','')) }
        if ($m.Groups[1].Success) {
            $run=W-El $doc 'r'; $rp=W-Child $doc $run 'rPr' $null; [void](W-Child $doc $rp 'rStyle' 'FootnoteReference')
            $ref=W-El $doc 'footnoteReference'; W-Attr $ref 'id' $m.Groups[1].Value; [void]$run.AppendChild($ref); [void]$p.AppendChild($run)
        } else {
            $script:linkCounter++; $id='rIdIntroLink'+$script:linkCounter
            Add-Rel $rels $id ($rns+'/hyperlink') $m.Groups[3].Value $true
            $link=W-El $doc 'hyperlink'; [void]$link.SetAttribute('id',$rns,$id)
            $run=W-El $doc 'r'; $rp=W-Child $doc $run 'rPr' $null; [void](W-Child $doc $rp 'rStyle' 'Hyperlink')
            $t=W-El $doc 't'; $t.InnerText=$m.Groups[2].Value; [void]$run.AppendChild($t); [void]$link.AppendChild($run); [void]$p.AppendChild($link)
        }
        $cursor=$m.Index+$m.Length
    }
    if ($cursor -lt $text.Length) { Add-Run $doc $p ($text.Substring($cursor).Replace('*','')) }
}
function Add-Run($doc,$p,$text) {
    $run=W-El $doc 'r'; $t=W-El $doc 't'; $space=$doc.CreateAttribute('xml','space','http://www.w3.org/XML/1998/namespace'); $space.Value='preserve'; [void]$t.Attributes.Append($space); $t.InnerText=$text; [void]$run.AppendChild($t); [void]$p.AppendChild($run)
}
function New-Para($doc,$text,$template,$rels) {
    $p=W-El $doc 'p'; $pp=$template.SelectSingleNode('./w:pPr',$ns)
    if ($pp) { [void]$p.AppendChild($doc.ImportNode($pp,$true)) }; Add-RichText $doc $p $text $rels; return ,$p
}
$zip=[IO.Compression.ZipFile]::OpenRead((Join-Path $before ($stem+'.docx')))
try {
    if ($zip.GetEntry('word/footnotes.xml')) { throw 'Existing footnotes require a merge; no changes made.' }
    $document=Read-Xml (Read-ZipText $zip 'word/document.xml')
    $rels=Read-Xml (Read-ZipText $zip 'word/_rels/document.xml.rels')
    $styles=Read-Xml (Read-ZipText $zip 'word/styles.xml')
    $types=Read-Xml (Read-ZipText $zip '[Content_Types].xml')
    $ns=New-Object Xml.XmlNamespaceManager($document.NameTable); $ns.AddNamespace('w',$w)
    $body=$document.SelectSingleNode('/w:document/w:body',$ns)
    $ps=@($body.SelectNodes('./w:p',$ns)); $start=$null; $end=$null; $refsHead=$null; $appendix=$null
    foreach ($p in $ps) { $t=Get-PText $p; switch ($t) { '1. 문제 제기' { $start=$p }; '2. 선행연구와 분석 틀' { $end=$p }; '참고문헌' { $refsHead=$p }; '부록 A. 자료와 재현 정보' { $appendix=$p } } }
    if (-not ($start -and $end -and $refsHead -and $appendix)) { throw 'DOCX section boundaries missing.' }
    $originalBody=@(); $walk=$end
    while ($walk -and $walk -ne $refsHead) { $originalBody += $walk.OuterXml; $walk=$walk.NextSibling }
    $appendixXml=@(); $walk=$appendix
    while ($walk) { $appendixXml += $walk.OuterXml; $walk=$walk.NextSibling }
    $template=$start.NextSibling.CloneNode($true); $walk=$start.NextSibling
    while ($walk -ne $end) { $next=$walk.NextSibling; [void]$body.RemoveChild($walk); $walk=$next }
    foreach ($text in $data.paragraphs) { $p=New-Para $document $text $template $rels; [void]$body.InsertBefore($p,$end); if ((Get-PText $p) -cne (Plain $text)) { throw 'DOCX introduction text mismatch.' } }
    $refTemplate=$refsHead.NextSibling.CloneNode($true); $walk=$refsHead.NextSibling
    while ($walk -ne $appendix) { $next=$walk.NextSibling; [void]$body.RemoveChild($walk); $walk=$next }
    foreach ($text in $allRefs) { $p=New-Para $document $text $refTemplate $rels; [void]$body.InsertBefore($p,$appendix) }
    $afterBody=@(); $walk=$end
    while ($walk -and $walk -ne $refsHead) { $afterBody += $walk.OuterXml; $walk=$walk.NextSibling }
    $afterAppendix=@(); $walk=$appendix
    while ($walk) { $afterAppendix += $walk.OuterXml; $walk=$walk.NextSibling }
    if (($originalBody -join '') -cne ($afterBody -join '') -or ($appendixXml -join '') -cne ($afterAppendix -join '')) { throw 'DOCX body outside intro and bibliography changed.' }
    $foot=Read-Xml ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:footnotes xmlns:w="'+$w+'" xmlns:r="'+$rns+'"/>')
    $footRels=Read-Xml ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="'+$relsns+'"/>')
    foreach ($sep in @(@(-1,'separator'),@(0,'continuationSeparator'))) {
        $n=W-El $foot 'footnote'; W-Attr $n 'id' $sep[0]; W-Attr $n 'type' $sep[1]
        $p=W-Child $foot $n 'p' $null; $rr=W-Child $foot $p 'r' $null; [void](W-Child $foot $rr $sep[1] $null); [void]$foot.DocumentElement.AppendChild($n)
    }
    foreach ($note in $data.notes) {
        $n=W-El $foot 'footnote'; W-Attr $n 'id' $note.id; $p=W-Child $foot $n 'p' $null; $pp=W-Child $foot $p 'pPr' $null; [void](W-Child $foot $pp 'pStyle' 'FootnoteText')
        $rr=W-Child $foot $p 'r' $null; $rp=W-Child $foot $rr 'rPr' $null; [void](W-Child $foot $rp 'rStyle' 'FootnoteReference'); [void](W-Child $foot $rr 'footnoteRef' $null)
        Add-Run $foot $p ' '; Add-RichText $foot $p $note.text $footRels; [void]$foot.DocumentElement.AppendChild($n)
    }
    $styleNs=New-Object Xml.XmlNamespaceManager($styles.NameTable); $styleNs.AddNamespace('w',$w)
    foreach ($id in @('FootnoteText','FootnoteReference')) {
        if ($styles.SelectSingleNode("//w:style[@w:styleId='$id']",$styleNs)) { continue }
        $s=W-El $styles 'style'; W-Attr $s 'type' $(if ($id -eq 'FootnoteText') {'paragraph'} else {'character'}); W-Attr $s 'styleId' $id
        [void](W-Child $styles $s 'name' $(if ($id -eq 'FootnoteText') {'footnote text'} else {'footnote reference'}))
        [void](W-Child $styles $s 'basedOn' $(if ($id -eq 'FootnoteText') {'Normal'} else {'DefaultParagraphFont'}))
        if ($id -eq 'FootnoteText') { $pp=W-Child $styles $s 'pPr' $null; $sp=W-Child $styles $pp 'spacing' $null; W-Attr $sp 'before' '0'; W-Attr $sp 'after' '0'; W-Attr $sp 'line' '240'; W-Attr $sp 'lineRule' 'auto' }
        $rp=W-Child $styles $s 'rPr' $null
        if ($id -eq 'FootnoteText') { $fonts=W-Child $styles $rp 'rFonts' $null; foreach ($f in @('ascii','hAnsi','eastAsia','cs')) { W-Attr $fonts $f 'Malgun Gothic' }; [void](W-Child $styles $rp 'sz' '17'); [void](W-Child $styles $rp 'szCs' '17') }
        else { [void](W-Child $styles $rp 'vertAlign' 'superscript') }
        [void]$styles.DocumentElement.AppendChild($s)
    }
    Add-Rel $rels 'rIdIntroFootnotes' ($rns+'/footnotes') 'footnotes.xml'
    $override=$types.CreateElement('Override',$ctns); $override.SetAttribute('PartName','/word/footnotes.xml'); $override.SetAttribute('ContentType','application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml'); [void]$types.DocumentElement.AppendChild($override)
    $replacements=@{ 'word/document.xml'=$document.OuterXml; 'word/_rels/document.xml.rels'=$rels.OuterXml; 'word/styles.xml'=$styles.OuterXml; '[Content_Types].xml'=$types.OuterXml; 'word/footnotes.xml'=$foot.OuterXml; 'word/_rels/footnotes.xml.rels'=$footRels.OuterXml }
    foreach ($part in $replacements.Keys) { [void](Read-Xml $replacements[$part]) }
    $outPath=Join-Path $stage ($stem+'.docx')
    $fs=New-Object IO.FileStream($outPath,[IO.FileMode]::Create,[IO.FileAccess]::Write)
    $out=New-Object IO.Compression.ZipArchive($fs,[IO.Compression.ZipArchiveMode]::Create,$false)
    try {
        foreach ($entry in $zip.Entries) {
            $dest=$out.CreateEntry($entry.FullName,[IO.Compression.CompressionLevel]::Optimal); $stream=$dest.Open()
            try { if ($replacements.ContainsKey($entry.FullName)) { $bytes=$utf8.GetBytes($replacements[$entry.FullName]); $stream.Write($bytes,0,$bytes.Length) } else { $src=$entry.Open(); try {$src.CopyTo($stream)} finally {$src.Dispose()} } } finally {$stream.Dispose()}
        }
        foreach ($name in @('word/footnotes.xml','word/_rels/footnotes.xml.rels')) { $dest=$out.CreateEntry($name,[IO.Compression.CompressionLevel]::Optimal); $stream=$dest.Open(); try { $bytes=$utf8.GetBytes($replacements[$name]); $stream.Write($bytes,0,$bytes.Length) } finally {$stream.Dispose()} }
    } finally { $out.Dispose(); $fs.Dispose() }
} finally { $zip.Dispose() }
$record=[ordered]@{ revision_date='2026-11-01'; status='staged_for_render'; paragraphs=$data.paragraphs.Count; native_footnotes=$data.notes.Count; bibliography_count=$allRefs.Count; original_bibliography_preserved=$true; body_sections_2_to_9_unchanged=$true; appendices_unchanged=$true; originals=$originals; stage=$stage; runtime_note='No workspace dependency loader or managed Python/LibreOffice was exposed. DOCX authoring uses native .NET OOXML; PDF export uses an isolated Microsoft Word instance.' }
Save-Text (Join-Path $task 'revision_check.json') ($record | ConvertTo-Json -Depth 8)
Write-Output ([pscustomobject]$record | Select-Object status,paragraphs,native_footnotes,bibliography_count,body_sections_2_to_9_unchanged,appendices_unchanged | ConvertTo-Json)
