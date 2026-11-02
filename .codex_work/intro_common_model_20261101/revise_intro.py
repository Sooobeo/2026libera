from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile
import hashlib
import json
import shutil

from docx import Document
from docx.oxml import OxmlElement
from lxml import etree

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
STEM = 'LIBERA_소논문_최종결과반영_20261030'
STAGE = WORK / 'stage'
BEFORE = WORK / 'before'
STAGE.mkdir(exist_ok=True)
BEFORE.mkdir(exist_ok=True)

ADDITION = (
    '업무 성과를 높이려는 실무자는 이용 가능한 GenAI 가운데 해당 시점에 업무 성능이 가장 우수하다고 판단하는 모델을 선택할 유인이 있다. '
    '이러한 평가가 여러 실무자와 기관에서 겹치면, 서로 독립적으로 도구를 선택하더라도 동일한 모델로 선택이 집중될 수 있다. '
    '본 연구는 이러한 선택의 집중 가능성을 출발 가정으로 삼아, 동일한 모델을 활용할 때 기관별 정보와 운용조건에 근거한 판단 차이가 유지되는지 살핀다.'
)
ANCHOR = '공통 모델에 대한 의존은 최종 배분을 자동화하기 전부터 형성될 수 있다.'

for ext in ['.md', '.html', '.docx', '.pdf']:
    source = ROOT / 'paper' / (STEM + ext)
    backup = BEFORE / source.name
    assert not backup.exists(), 'Do not overwrite a prior backup'
    shutil.copy2(source, backup)

original_md = (BEFORE / (STEM + '.md')).read_text(encoding='utf-8')
assert original_md.count(ANCHOR) == 1
new_md = original_md.replace(ANCHOR, ADDITION + '\n\n' + ANCHOR, 1)
(STAGE / (STEM + '.md')).write_text(new_md, encoding='utf-8', newline='\n')
assert new_md.replace(ADDITION + '\n\n', '', 1) == original_md

original_html = (BEFORE / (STEM + '.html')).read_text(encoding='utf-8')
assert original_html.count('<p>' + ANCHOR) == 1
new_html = original_html.replace('<p>' + ANCHOR, '<p>' + ADDITION + '</p>\n<p>' + ANCHOR, 1)
(STAGE / (STEM + '.html')).write_text(new_html, encoding='utf-8', newline='\n')
assert new_html.replace('<p>' + ADDITION + '</p>\n', '', 1) == original_html

doc = Document(BEFORE / (STEM + '.docx'))
matches = [p for p in doc.paragraphs if p.text.startswith(ANCHOR)]
assert len(matches) == 1
anchor_p = matches[0]
new_p = deepcopy(anchor_p._p)
for child in list(new_p):
    if child.tag != '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pPr':
        new_p.remove(child)
run = OxmlElement('w:r')
if anchor_p.runs and anchor_p.runs[0]._r.rPr is not None:
    run.append(deepcopy(anchor_p.runs[0]._r.rPr))
text = OxmlElement('w:t')
text.text = ADDITION
run.append(text)
new_p.append(run)
anchor_p._p.addprevious(new_p)
new_xml = etree.tostring(doc._element, encoding='UTF-8', xml_declaration=True, standalone=True)

with ZipFile(BEFORE / (STEM + '.docx')) as source, ZipFile(STAGE / (STEM + '.docx'), 'w') as out:
    for info in source.infolist():
        out.writestr(info, new_xml if info.filename == 'word/document.xml' else source.read(info.filename))

reloaded = Document(STAGE / (STEM + '.docx'))
original_paragraphs = [p.text for p in Document(BEFORE / (STEM + '.docx')).paragraphs]
assert [p.text for p in reloaded.paragraphs if p.text != ADDITION] == original_paragraphs
assert sum(p.text == ADDITION for p in reloaded.paragraphs) == 1
with ZipFile(BEFORE / (STEM + '.docx')) as source, ZipFile(STAGE / (STEM + '.docx')) as out:
    changed_parts = [n for n in source.namelist() if source.read(n) != out.read(n)]
assert changed_parts == ['word/document.xml'], changed_parts

receipt = {
    'revision_date': '2026-11-01', 'addition': ADDITION,
    'placement': 'Section 1, after the first paragraph',
    'changed_docx_parts': changed_parts,
    'all_original_paragraphs_preserved': True,
    'originals': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in BEFORE.iterdir()},
}
(WORK / 'revision_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'status': 'staged', 'addition': ADDITION}, ensure_ascii=False))
