from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import csv
import hashlib
import json
from lxml import etree

WORK = Path(__file__).parent
ROOT = WORK.parent.parent
SOURCE = Path('C:/Users/Insun/Downloads/소_논문45.docx')
OUTPUT = Path('C:/Users/Insun/Downloads/소_논문45_5장축약본.docx')
SUMMARY = ROOT / 'research/paper_final_20261029/arm_summary.csv'
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W = '{' + NS['w'] + '}'

with SUMMARY.open(encoding='utf-8-sig', newline='') as f:
    summary = {row['arm']: row for row in csv.DictReader(f)}
assert set(summary) == {'R0', 'R1', 'R2', 'R3'}
assert all(int(row['trajectories']) == 40 and int(row['independent_scenarios']) == 10 for row in summary.values())
assert sum(int(row['effective_equal_h_1e12']) for row in summary.values()) == 113
assert sum(int(row['actual_calculator_tool_calls']) for row in summary.values()) == 0
assert all(row['raw_valid'] == row['raw_equal_h_1e12'] for row in summary.values())

with ZipFile(SOURCE) as z:
    source_parts = {item.filename: z.read(item.filename) for item in z.infolist()}
root = etree.fromstring(source_parts['word/document.xml'])
body = root.find('w:body', NS)
nodes = list(body)
def node_text(node):
    return ''.join(node.xpath('.//w:t/text()', namespaces=NS))

source_chars = sum(len(node_text(n)) for n in nodes)
body_template = next(n for n in nodes if node_text(n).startswith('本実験') or node_text(n).startswith('본 실험은'))
title_template = nodes[0]
caption_template = next(n for n in nodes if node_text(n).startswith('표 1.'))
table_template = next(n for n in nodes if n.tag == W + 'tbl')
section = deepcopy(body.find('w:sectPr', NS))

def set_child(parent, name, **attrs):
    element = parent.find('w:' + name, NS)
    if element is None:
        element = etree.SubElement(parent, W + name)
    for key, value in attrs.items():
        element.set(W + key, str(value))
    return element

def paragraph(value, role='body'):
    template = title_template if role == 'title' else caption_template if role == 'caption' else body_template
    p = deepcopy(template)
    for child in list(p):
        if child.tag != W + 'pPr':
            p.remove(child)
    ppr = p.find('w:pPr', NS)
    if ppr is None:
        ppr = etree.Element(W + 'pPr')
        p.insert(0, ppr)
    for name in ('numPr', 'pageBreakBefore', 'pBdr', 'shd', 'keepNext', 'ind'):
        for item in ppr.findall('w:' + name, NS):
            ppr.remove(item)
    set_child(ppr, 'spacing', before=0, after=100 if role == 'body' else 120, line=360 if role == 'title' else 240 if role == 'note' else 280, lineRule='exact')
    set_child(ppr, 'jc', val='left' if role != 'body' else 'both')
    set_child(ppr, 'widowControl', val=1)
    set_child(ppr, 'snapToGrid', val=0)
    if role in ('title', 'caption', 'note'):
        set_child(ppr, 'keepNext', val=1)
    run = etree.SubElement(p, W + 'r')
    rpr = etree.SubElement(run, W + 'rPr')
    set_child(rpr, 'rFonts', ascii='Malgun Gothic', hAnsi='Malgun Gothic', eastAsia='맑은 고딕', cs='Malgun Gothic')
    set_child(rpr, 'sz', val=26 if role == 'title' else 17 if role == 'note' else 20)
    set_child(rpr, 'color', val='000000')
    if role in ('title', 'caption'):
        set_child(rpr, 'b', val=1)
    t = etree.SubElement(run, W + 't')
    t.text = value
    return p

content = [
    ('title', '5. 실험 결과와 해석'),
    ('body', '공통 GenAI가 펀드별로 필요한 배분 차이를 유지하는지, Workflow RAG의 근거 제공 단계에 따라 결과가 달라지는지 비교하였다. 미국 액티브 주식형 펀드 4개의 2025년 말 보유자료를 FF12 산업으로 분류하고, 공통·펀드별 합성 전망 10개 상황을 적용하였다. Qwen3-1.7B 양자화 모델로 계획 → 배분안 작성 → 점검·수정의 3단계를 수행하였다. 근거 미제공(R0)과 계획(R1)·작성(R2)·점검(R3) 단계부터의 제공을 비교해 총 160개 업무 흐름을 실행하였다(조건별 1회). R1~R3에는 동일한 검색 근거를 제공하고 이후 단계에도 유지하였다.'),
    ('body', '평가 기준은 각 펀드의 전체 전망과 동일한 제약(비음수·합계 1·기존 보유 이하의 분산)에서 월간 사후 기대수익을 최대화한 수리 배분이다. 제약을 어긴 제안은 가능한 경우 외부 비례 정규화 후 재검사하고, 실패 시 기존 보유비중을 적용하였다. 실패를 포함한 최종 배분의 지표를 상황별로 평균해 비교하였다.'),
    ('caption', '표 1. 근거 제공 단계별 핵심 결과'),
]

for child in list(body):
    body.remove(child)
for role, value in content:
    body.append(paragraph(value, role))

table = deepcopy(table_template)
tblpr = table.find('w:tblPr', NS)
if tblpr is None:
    tblpr = etree.Element(W + 'tblPr')
    table.insert(0, tblpr)
set_child(tblpr, 'tblW', w=9360, type='dxa')
set_child(tblpr, 'jc', val='center')
set_child(tblpr, 'tblLayout', type='fixed')
borders = set_child(tblpr, 'tblBorders')
for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
    set_child(borders, side, val='single', sz=4, color='D9D9D9')
margins = set_child(tblpr, 'tblCellMar')
for side, width in [('top', 70), ('bottom', 70), ('left', 90), ('right', 90)]:
    set_child(margins, side, w=width, type='dxa')
widths = [3280, 1520, 1520, 1520, 1520]
grid = table.find('w:tblGrid', NS)
for child in list(grid):
    grid.remove(child)
for width in widths:
    etree.SubElement(grid, W + 'gridCol').set(W + 'w', str(width))
old_rows = table.findall('w:tr', NS)
row_template = deepcopy(old_rows[-1])
for row in old_rows:
    table.remove(row)

def metric(key, multiplier=1, precision=2):
    return [f"{float(summary[arm][key]) * multiplier:.{precision}f}" for arm in ('R0', 'R1', 'R2', 'R3')]

table_values = [
    ['평가 지표', 'R0 미제공', 'R1 계획', 'R2 작성', 'R3 점검'],
    ['과잉수렴 격차 G (%p)'] + metric('G_full', 100),
    ['거리 오차 A (%p)'] + metric('A_full', 100),
    ['산업별 차이 불일치 E (%p)'] + metric('E_full', 100),
    ['월간 기대수익 손실 (bp)'] + metric('R_full', 10000),
    ['최종 유효율 (%)'] + [f"{100 * int(summary[arm]['policy_valid']) / 40:.1f}" for arm in ('R0', 'R1', 'R2', 'R3')],
]
for row_index, values in enumerate(table_values):
    row = deepcopy(row_template)
    trpr = row.find('w:trPr', NS)
    if trpr is None:
        trpr = etree.Element(W + 'trPr')
        row.insert(0, trpr)
    for child in list(trpr):
        trpr.remove(child)
    set_child(trpr, 'cantSplit', val=1)
    if row_index == 0:
        set_child(trpr, 'tblHeader', val=1)
    cells = row.findall('w:tc', NS)
    assert len(cells) == 5
    for col_index, (cell, value) in enumerate(zip(cells, values)):
        tcpr = cell.find('w:tcPr', NS)
        if tcpr is None:
            tcpr = etree.Element(W + 'tcPr')
            cell.insert(0, tcpr)
        set_child(tcpr, 'tcW', w=widths[col_index], type='dxa')
        set_child(tcpr, 'vAlign', val='center')
        set_child(tcpr, 'shd', val='clear', fill='EDEDED' if row_index == 0 else 'FFFFFF')
        cell_borders = set_child(tcpr, 'tcBorders')
        for side in ('top', 'left', 'bottom', 'right'):
            set_child(cell_borders, side, val='single', sz=4, color='D9D9D9')
        for child in list(cell):
            if child.tag != W + 'tcPr':
                cell.remove(child)
        p = paragraph(value)
        ppr = p.find('w:pPr', NS)
        set_child(ppr, 'spacing', before=0, after=0, line=260, lineRule='exact')
        set_child(ppr, 'jc', val='left' if col_index == 0 and row_index > 0 else 'center')
        rpr = p.find('w:r/w:rPr', NS)
        set_child(rpr, 'sz', val=18)
        if row_index == 0:
            set_child(rpr, 'b', val=1)
        cell.append(p)
    table.append(row)
body.append(table)

tail = [
    ('note', '주: G는 기준 배분거리에서 실제 거리를 뺀 값으로, 양수는 차이의 축소를 뜻한다. A는 비교쌍별 절대 거리 오차, E는 산업별 비중 차이 벡터의 불일치다. 손실은 실현수익률이 아닌 모형상 기회비용이다. 유효율에는 외부 정규화로 구제된 제안이 포함된다.'),
    ('body', '계획·작성 단계 제공(R1·R2)에서는 펀드 간 차이가 기준보다 평균 1.92%p·2.85%p 축소되었다. 미제공·점검 단계 제공(R0·R3)에서는 오히려 기준보다 차이가 컸다. 그러나 모든 조건에서 거리 오차와 산업별 차이 불일치가 크게 남아, 평균 배분거리가 크다는 사실만으로 필요한 전략적 이질성이 보존되었다고 보기 어렵다.'),
    ('body', 'R3의 유효율은 62.5%로 가장 높았지만, 평균 기대수익 손실은 91.20bp로 R0의 90.16bp보다 낮아지지 않았다. R1·R2의 손실도 R0보다 컸으며, 모든 조건이 기존 보유 유지의 손실 87.84bp를 상회하였다. 따라서 이번 실험에서는 근거 제공에 따른 차이의 정합성과 판단 품질의 공동 개선이 확인되지 않았다.'),
    ('body', '최종 배분의 70.6%는 기존 보유에 머물렀고 실제 재배분은 29.4%였다. 원출력부터 유효했던 제안은 모두 기존 보유와 같았으며, 실제 재배분은 외부 정규화를 거친 경우에만 나타났다. 관측된 펀드 간 차이에는 모델의 판단뿐 아니라 기존 보유 유지와 외부 처리도 기여하였다. 이는 근거 제공 단계의 선택에 더해, 펀드별 근거를 비중 변경과 연결하고 계산·제약 검증을 수정에 반영하는 절차가 필요함을 시사한다.'),
    ('body', '결과는 단일 소형 양자화 모델과 10개 합성 상황의 탐색적 비교다. 근거 제공 시점과 활용 가능한 단계 수·대화 이력이 함께 달라지므로 순수한 시점 효과나 실제 기관투자자의 행동으로 일반화하지 않는다.'),
]
for role, value in tail:
    body.append(paragraph(value, role))
body.append(section)
for index, p in enumerate(body.xpath('.//w:p', namespaces=NS), start=256):
    p.set('{http://schemas.microsoft.com/office/word/2010/wordml}paraId', f'{index:08X}')

xml = etree.tostring(root, encoding='UTF-8', xml_declaration=True, standalone=True)
with ZipFile(OUTPUT, 'w', ZIP_DEFLATED) as z:
    for name, data in source_parts.items():
        z.writestr(name, xml if name == 'word/document.xml' else data)
with ZipFile(OUTPUT) as z:
    assert all(z.read(name) == data for name, data in source_parts.items() if name != 'word/document.xml')
output_chars = sum(len(node_text(n)) for n in body)
report = {
    'source': str(SOURCE), 'output': str(OUTPUT),
    'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'source_chars': source_chars, 'output_chars': output_chars,
    'reduction_percent': round((1 - output_chars/source_chars) * 100, 1),
    'table': table_values,
    'numeric_source': str(SUMMARY),
    'manuscript_source': str(ROOT / 'paper/LIBERA_소논문_최종결과반영_20261030.md'),
    'parts_changed': ['word/document.xml'],
}
(WORK / 'edit_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
