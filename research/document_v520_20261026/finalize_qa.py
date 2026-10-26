"""Bind the finished DOCX to its structural and complete visual QA evidence."""
from pathlib import Path
from hashlib import sha256
from zipfile import ZipFile
from lxml import etree
import json

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
DOCX = ROOT / 'paper/LIBERA_소논문_시각화포함_v5.2_20261026.docx'
QA = WORK / 'qa/word_r3'
def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p):
    return sha256(p.read_bytes()).hexdigest()

build = read(WORK / 'build_receipt.json')
structural = read(WORK / 'final_structural_audit.json')
word = read(QA / 'word_receipt.json')
raster = read(QA / 'raster_receipt.json')
comparison = read(QA / 'render_comparison.json')
assert structural['overall_pass']
assert build['docx_sha256'] == word['input_sha256_before'] == word['input_sha256_after'] == raster['docx_sha256'] == digest(DOCX)
assert build['input_sha256'] == 'fa8ac61e87e9d559b7fc937a94f5dd51853f496f60412b488642d52b0e9cd3d7'
assert build['illustrated_source_sha256'] == digest(WORK / 'illustrated_manuscript.json')
assert word['pdf_sha256'] == raster['pdf_sha256'] == digest(QA / 'manuscript.pdf')
assert comparison['identical_pages'] == list(range(1, 26))
assert comparison['changed_pages'] == list(range(26, 32))
assert len(raster['pages']) == 31
reviews = [WORK / 'qa/word_r2/visual_review_01_10.md', WORK / 'qa/word_r2/visual_review_11_20.md', WORK / 'qa/word_r2/visual_review_21_31.md', QA / 'visual_review_26_31.md']
assert all(p.is_file() for p in reviews)
assert all((QA / f'page-{n}.png').is_file() for n in range(1, 32))
with ZipFile(DOCX) as z:
    xml = etree.fromstring(z.read('word/document.xml'))
ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main', 'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}
assert len(xml.findall('.//w:tbl', ns)) == 16
assert len(xml.findall('.//w:drawing', ns)) == 5
assert len(xml.findall('.//m:oMath', ns)) == 2
assert not xml.findall('.//w:pageBreakBefore', ns)
assert not xml.findall('.//w:ins', ns) and not xml.findall('.//w:del', ns)
report = {
    'status': 'complete', 'docx': str(DOCX), 'docx_sha256': digest(DOCX),
    'source_sha256': build['input_sha256'], 'illustrated_source_sha256': build['illustrated_source_sha256'],
    'pages': 31, 'body_figures': 4, 'appendix_figures': 1, 'body_tables': 8, 'appendix_tables': 8, 'native_equations': 2,
    'structural_audit': str(WORK / 'final_structural_audit.json'),
    'final_layout_change': 'Only removed the forced page break before numeric appendix. Illustrated manuscript JSON is byte-identical to the independently audited revision.',
    'render': str(QA / 'raster_receipt.json'),
    'visual_review': {'status': 'passed_all_31_pages', 'pages_1_25': 'Individually inspected r2 page images, pixel-identical in final r3.', 'pages_26_31': 'Individually inspected final r3 page images.', 'evidence': [str(p) for p in reviews]},
    'delivery': 'DOCX only; PDF and page PNGs retained as internal QA artifacts.'
}
(WORK / 'final_qa_receipt.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
raster['visual_review'] = report['visual_review']
(QA / 'raster_receipt.json').write_text(json.dumps(raster, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': report['status'], 'pages': report['pages'], 'docx_sha256': report['docx_sha256'], 'size_bytes': DOCX.stat().st_size}, ensure_ascii=False))
