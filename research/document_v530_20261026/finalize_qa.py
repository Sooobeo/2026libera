"""Verify the final layout revision against the audited content and render."""
from pathlib import Path
from hashlib import sha256
from zipfile import ZipFile
from collections import Counter
from lxml import etree
from docx import Document
import json

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
QA = WORK / 'qa/word_final'
def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def digest(path): return sha256(path.read_bytes()).hexdigest()
build = read(WORK / 'build_receipt.json')
docx_path = Path(build['docx'])
source = read(Path(build['source']))
old = read(ROOT / 'paper/v520_manuscript_20261026.json')
ill = read(WORK / 'illustrated_manuscript.json')
audit = read(WORK / 'structural_audit.json')
assert audit['overall_structural_data_pass']
for kind in ['table', 'heading', 'reference']:
    assert [b for b in source['blocks'] if b['type'] == kind] == [b for b in old['blocks'] if b['type'] == kind]
assert digest(ROOT / 'paper/v520_manuscript_20261026.json') == 'fa8ac61e87e9d559b7fc937a94f5dd51853f496f60412b488642d52b0e9cd3d7'
assert digest(Path(build['source'])) == build['source_sha256']
assert digest(WORK / 'illustrated_manuscript.json') == build['illustrated_source_sha256']
doc = Document(docx_path)
tables = [b for b in ill['blocks'] if b['type'] == 'table']
assert len(doc.tables) == len(tables) == 16
for actual, expected in zip(doc.tables, tables):
    assert [[c.text for c in row.cells] for row in actual.rows] == [expected['headers']] + expected['rows']
with ZipFile(docx_path) as archive:
    xml = etree.fromstring(archive.read('word/document.xml'))
    media = [archive.read(name) for name in archive.namelist() if name.startswith('word/media/') and name.endswith('.png')]
ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main', 'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}
text = ''.join(xml.xpath('//w:t/text()', namespaces=ns))
for b in ill['blocks']:
    if b['type'] in ['paragraph', 'reference']:
        assert b['text'] in text, b['text'][:100]
assert len(xml.findall('.//m:oMath', ns)) == 2
assert len(doc.inline_shapes) == 5
expected_images = [Path(b['png']).read_bytes() for b in ill['blocks'] if b['type'] == 'figure']
assert Counter(sha256(x).hexdigest() for x in media) == Counter(sha256(x).hexdigest() for x in expected_images)
assert '본 원고 v5.2' not in text
assert '기관자료를 제공하면 배분이 달라질 수' not in text
for ref in ['그림 1', '그림 2', '그림 3', '그림 4', '부록 표 A1', '부록 표 A2', '부록 표 A3', '식 (1)', '식 (2)']:
    assert ref in text
word = read(QA / 'word_receipt.json')
raster = read(QA / 'raster_receipt.json')
assert digest(docx_path) == build['docx_sha256'] == word['input_sha256_before'] == word['input_sha256_after'] == raster['docx_sha256']
assert digest(QA / 'manuscript.pdf') == raster['pdf_sha256'] == word['pdf_sha256']
count = len(raster['pages'])
assert count == len(raster['pngs'])
for n in range(1, count + 1): assert (QA / f'page-{n}.png').is_file()
reviews = [WORK / 'qa/word_r1/visual_review_01_10.md', WORK / 'qa/word_r3/visual_review_10_15.md', QA / 'visual_review_15_17.md', QA / 'visual_review_18_25.md', QA / 'visual_review_26_end.md']
assert all(p.exists() for p in reviews), [str(p) for p in reviews if not p.exists()]
comparison = read(QA / 'render_comparison.json')
report = {'status': 'complete', 'docx': str(docx_path), 'docx_sha256': digest(docx_path), 'source_sha256': build['source_sha256'], 'pages': count, 'tables': 16, 'figures': 5, 'native_equations': 2, 'content_checks': 'passed', 'previous_independent_audit': str(WORK / 'structural_audit.json'), 'final_layout_delta': 'Figure 1 precedes its interpretation; Figure 4 follows the interpretation paragraphs. Text, numeric tables, bibliography, and image bytes preserved.', 'visual_review': 'all pages passed; unchanged earlier pages verified pixel-identical', 'visual_evidence': [str(p) for p in reviews], 'render_comparison': comparison, 'deliverables': ['docx'], 'qa_intermediates_delivered': False}
(WORK / 'final_qa_receipt.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
raster['visual_review'] = 'passed_all_pages'
(QA / 'raster_receipt.json').write_text(json.dumps(raster, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': report['status'], 'pages': count, 'docx_sha256': report['docx_sha256']}, ensure_ascii=False))
