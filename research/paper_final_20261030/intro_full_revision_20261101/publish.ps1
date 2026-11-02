$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
Add-Type -AssemblyName System.IO.Compression.FileSystem
$root='C:\Users\Insun\2026libera'
$task=Join-Path $root 'research\paper_final_20261030\intro_full_revision_20261101'
$qa=Join-Path $root 'tmp\intro_full_revision_20261101\qa'
$utf8=New-Object Text.UTF8Encoding($false)
$record=Get-Content -LiteralPath (Join-Path $task 'revision_check.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$stage=$record.stage
$stem='LIBERA_소논문_최종결과반영_20261030'
$pdf=Get-Content -LiteralPath (Join-Path $qa 'pdf_check.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$word=Get-Content -LiteralPath (Join-Path $qa 'word_export_v2.json') -Encoding UTF8 -Raw | ConvertFrom-Json
if ($pdf.status -ne 'passed' -or $pdf.pages -ne 38 -or $word.status -ne 'completed') { throw 'Render checks have not passed.' }
if ($word.input_sha256_before -cne $word.input_sha256_after) { throw 'Read-only render changed the DOCX.' }
$html=[IO.File]::ReadAllText((Join-Path $stage ($stem+'.html')),$utf8)
$refs=@([regex]::Matches($html,'<sup class="intro-note-ref" id="intro-note-ref-(\d+)"'))
$notes=@([regex]::Matches($html,'<li id="intro-note-(\d+)"'))
if ($refs.Count -ne 8 -or $notes.Count -ne 8) { throw 'HTML footnote counts do not match.' }
for ($i=1; $i -le 8; $i++) {
    if (-not $html.Contains('href="#intro-note-'+$i+'"') -or -not $html.Contains('href="#intro-note-ref-'+$i+'"')) { throw 'Broken HTML note navigation.' }
}
$oldHtml=[IO.File]::ReadAllText((Join-Path $task ('before\'+$stem+'.html')),$utf8)
$unchangedPattern='(?s)<h2\b[^>]*>2\. 선행연구와 분석 틀</h2>.*?(?=<h2\b[^>]*>참고문헌</h2>)'
if ([regex]::Match($html,$unchangedPattern).Value -cne [regex]::Match($oldHtml,$unchangedPattern).Value) { throw 'HTML body outside introduction changed.' }
$bodyLinks=@([regex]::Matches($html,'href="#intro-note-\d+"')).Count
$docx=[IO.Compression.ZipFile]::OpenRead((Join-Path $stage ($stem+'.docx')))
try {
    foreach ($part in @('word/document.xml','word/footnotes.xml','word/_rels/footnotes.xml.rels','word/styles.xml','[Content_Types].xml','word/_rels/document.xml.rels')) {
        $reader=New-Object IO.StreamReader($docx.GetEntry($part).Open(),$utf8)
        try { $xml=New-Object Xml.XmlDocument; $xml.LoadXml($reader.ReadToEnd()) } finally { $reader.Dispose() }
        if ($part -eq 'word/document.xml') {
            $ns=New-Object Xml.XmlNamespaceManager($xml.NameTable); $ns.AddNamespace('w','http://schemas.openxmlformats.org/wordprocessingml/2006/main')
            $noteIds=@($xml.SelectNodes('//w:footnoteReference',$ns) | ForEach-Object { $_.GetAttribute('id','http://schemas.openxmlformats.org/wordprocessingml/2006/main') })
            if (($noteIds -join ',') -cne '1,2,3,4,5,6,7,8') { throw 'Native footnote numbering mismatch.' }
            if ($xml.SelectNodes('//w:tbl',$ns).Count -ne 15 -or $xml.SelectNodes('//w:drawing',$ns).Count -ne 2) { throw 'Original tables or figures changed.' }
        }
    }
} finally { $docx.Dispose() }
$artifacts=@()
foreach ($item in $record.originals) {
    if ((Get-FileHash -LiteralPath $item.path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $item.sha256) { throw ('Original changed while editing: '+$item.path) }
    $candidate=Join-Path $stage ([IO.Path]::GetFileName($item.path))
    if (-not (Test-Path -LiteralPath $candidate) -or (Get-Item -LiteralPath $candidate).Length -eq 0) { throw 'A deliverable is missing.' }
}
foreach ($item in $record.originals) {
    $candidate=Join-Path $stage ([IO.Path]::GetFileName($item.path))
    Copy-Item -LiteralPath $candidate -Destination $item.path -Force
    $hash=(Get-FileHash -LiteralPath $item.path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -cne (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()) { throw 'Published file differs from staged file.' }
    $artifacts += [ordered]@{ path=$item.path; sha256=$hash; bytes=(Get-Item -LiteralPath $item.path).Length }
}
$record.status='verified_and_published'
$record | Add-Member -NotePropertyName pdf_pages -NotePropertyValue 38 -Force
$record | Add-Member -NotePropertyName introduction_pdf_pages -NotePropertyValue @(2,3,4,5) -Force
$record | Add-Member -NotePropertyName all_pdf_pages_visually_reviewed -NotePropertyValue $true -Force
$record | Add-Member -NotePropertyName html_note_navigation_verified -NotePropertyValue $true -Force
$record | Add-Member -NotePropertyName native_word_export_verified -NotePropertyValue $true -Force
$record | Add-Member -NotePropertyName artifacts -NotePropertyValue $artifacts -Force
$record | Add-Member -NotePropertyName published_at_kst -NotePropertyValue ([DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(9)).ToString('o')) -Force
[IO.File]::WriteAllText((Join-Path $task 'revision_check.json'),($record | ConvertTo-Json -Depth 10)+"`n",$utf8)
$index=Join-Path $root 'paper\README.txt'
$readme=[IO.File]::ReadAllText($index,$utf8)
$readme=$readme.Replace('2026-11-01 부분 수정: 서론 첫 문단 뒤에 실무자의 성능 선호가 동일 모델 선택의 집중으로 이어질 수 있다는 출발 가정 세 문장을 추가했다. Word·PDF·HTML·본문 원본에 동일하게 반영했다.','2026-11-01 서론 개정: AI의 사회·업무 변화 → 예측과 전략적 판단의 한계 → 펀드 선정 이유 → 분산 사용과 공통 모델의 숨은 판단 계층 → 과잉수렴·부정적 동질화 → 거래·시장피드백의 확장 가능성 → 단계별 Workflow RAG 검증으로 재구성했다. 모델 선택 집중의 출발 가정 세 문장을 보존하고 각주 8개 및 추가 문헌 7편을 반영했다. Word·PDF·HTML·본문 원본을 함께 갱신했다. PDF 서론은 2~5쪽, 전체는 38쪽이다. 수정 전 네 파일은 ../research/paper_final_20261030/intro_full_revision_20261101/before/에 보존했다.')
$readme=$readme.Replace('본문 인용과 참고문헌 15편, 원문 링크, 재현 부록 포함','서론 각주 8개, 본문 인용과 참고문헌 22편, 원문 링크, 재현 부록 포함')
if (-not $readme.Contains('intro_full_revision_20261101/')) { throw 'README revision did not apply.' }
[IO.File]::WriteAllText($index,$readme,$utf8)
Write-Output ([pscustomobject]@{status=$record.status; formats=$artifacts.Count; native_footnotes=8; bibliography_count=22; pdf_pages=38; introduction_pdf_pages='2-5'; all_pages_reviewed=$true} | ConvertTo-Json)
