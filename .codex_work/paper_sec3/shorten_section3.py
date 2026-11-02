from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import json
from lxml import etree

WORK = Path(__file__).parent
SOURCE = WORK / 'source.docx'
OUTPUT = WORK / 'paper_section3_shortened.docx'
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W = '{' + NS['w'] + '}'

with ZipFile(SOURCE) as z:
    original_xml = z.read('word/document.xml')
root = etree.fromstring(original_xml)
body = root.find('w:body', NS)
nodes = list(body)

def text(node):
    return ''.join(node.xpath('.//w:t/text()', namespaces=NS))

start = next(i for i, n in enumerate(nodes) if text(n).strip() == '3. 실험설계')
end = next(i for i, n in enumerate(nodes) if text(n).strip() == '4. 실험과정과 평가방법')
old_nodes = nodes[start:end]
rest_before = [etree.tostring(n, method='c14n') for n in nodes[end:]]
body_template = next(n for n in old_nodes if text(n).startswith('본 실험은'))
heading_template = next(n for n in old_nodes if text(n).startswith('3.1 '))
caption_template = next(n for n in old_nodes if text(n).startswith('표 2.'))
table_template = [n for n in old_nodes if n.tag == W + 'tbl'][1]

def paragraph(value, template=body_template):
    p = deepcopy(template)
    rpr_candidates = p.xpath('./w:r/w:rPr', namespaces=NS)
    rpr = deepcopy(rpr_candidates[0]) if rpr_candidates else None
    for child in list(p):
        if child.tag != W + 'pPr':
            p.remove(child)
    r = etree.SubElement(p, W + 'r')
    if rpr is not None:
        r.append(rpr)
    t = etree.SubElement(r, W + 't')
    t.text = value
    return p

new_nodes = [deepcopy(nodes[start])]
new_nodes.append(paragraph('본 실험은 공통 GenAI가 펀드별 조건에 맞는 배분 차이를 유지하는지, 기관별 근거의 제공 단계에 따라 차이의 정합성과 기대수익 손실이 달라지는지 비교한다.'))
new_nodes.append(paragraph('3.1 자료와 배분 과제', heading_template))
new_nodes.append(paragraph('네 펀드(FCNTX, VPMCX, DODGX, TRBCX)의 2025년 말 보유자료를 사용하고, 공개자료의 마감은 2026년 3월 말로 정하였다. 분류 가능한 주식만 Fama–French 12개 산업(FF12)에 연결해 합계가 1이 되도록 정규화한 비중을 h로 정의하였다. 과제는 월간 사후 기대수익의 극대화이며, 목표비중은 비음수, 합계 1, 기존 보유비중의 분산 이하라는 세 조건을 충족해야 한다.'))
new_nodes.append(paragraph('사전 기대수익과 위험은 2016~2025년 French 산업별 월간 수익률[1]의 평균과 Ledoit–Wolf 수축 공분산[2]으로 추정하였다. 여기에 공통·펀드별 합성 전망을 결합하였다. 공통 전망과 해당 펀드의 전체 추가 전망을 사용해 동일한 제약하에서 계산한 최적 배분을 평가 기준으로 삼되 모델에는 제공하지 않았다. R0의 공통 전망만을 사용한 기준도 보조적으로 계산하였다.'))
new_nodes.append(paragraph('3.2 비교 조건', heading_template))
new_nodes.append(paragraph('전망 정밀도 두 수준(r=0.5, 2)에서 결과 확인 전에 선정한 상황 각 다섯 개에 네 펀드와 네 자료 조건을 적용하여 총 160개 업무 흐름을 실행하였다(조건별 1회 반복). 각 흐름은 계획, 배분안 작성, 점검·수정으로 구성하였다. R1~R3에는 BM25로 검색한 상위 네 문서 조각으로 이루어진 동일한 근거 패킷을 제공했으며, 산업별 추가 전망 열두 항목이 모두 포함되었음을 확인하였다.'))
new_nodes.append(paragraph('표 1. 단계별 근거 제공 조건', caption_template))

table = deepcopy(table_template)
values = [
    ['조건', '계획', '배분안 작성', '점검·수정'],
    ['R0', '공통 정보', '공통 정보', '공통 정보'],
    ['R1', '추가 근거 제공', '근거 유지', '근거 유지'],
    ['R2', '공통 정보', '추가 근거 제공', '근거 유지'],
    ['R3', '공통 정보', '공통 정보', '추가 근거 제공'],
]
for tr, row_values in zip(table.findall('w:tr', NS), values):
    for tc, value in zip(tr.findall('w:tc', NS), row_values):
        p = tc.find('w:p', NS)
        replacement = paragraph(value, p)
        for child in list(tc):
            if child.tag != W + 'tcPr':
                tc.remove(child)
        tc.append(replacement)
new_nodes.append(table)
new_nodes.append(paragraph('공통 정보와 이전 대화는 모든 조건에서 유지하고, 점검 단계에는 외부 코드의 제약 검사 결과를 전달하였다. 사후 기대수익 계산·제약 검사 도구의 사용은 선택 사항이며, 도구의 정보 범위는 해당 단계까지 제공된 자료로 제한하였다. 단계별 추가 왕복은 최대 두 번으로 제한하였다.'))
new_nodes.append(paragraph('조건 간에는 근거의 최초 제공 시점뿐 아니라 활용 가능한 단계 수와 대화 이력도 함께 달라진다. 따라서 결과는 합성 전망과 단일 반복을 사용한 탐색적 비교로 해석하며, 순수한 시점 효과나 실제 운용자의 판단·실현수익률을 직접 보여주는 결과로 해석하지 않는다.'))

for n in old_nodes:
    body.remove(n)
for offset, n in enumerate(new_nodes):
    body.insert(start + offset, n)

rest_after = [etree.tostring(n, method='c14n') for n in list(body)[start + len(new_nodes):]]
assert rest_before == rest_after, 'Content after section 3 changed'
new_xml = etree.tostring(root, encoding='UTF-8', xml_declaration=True, standalone=True)
with ZipFile(SOURCE) as src, ZipFile(OUTPUT, 'w', compression=ZIP_DEFLATED) as dst:
    for info in src.infolist():
        dst.writestr(info, new_xml if info.filename == 'word/document.xml' else src.read(info.filename))

old_chars = sum(len(text(n)) for n in old_nodes)
new_chars = sum(len(text(n)) for n in new_nodes)
stats = {'original_section3_characters': old_chars, 'revised_section3_characters': new_chars,
         'reduction_percent': round((1-new_chars/old_chars)*100, 1),
         'section3_subsections_before': 5, 'section3_subsections_after': 2,
         'section3_tables_before': 2, 'section3_tables_after': 1,
         'section4_xml_unchanged': rest_before == rest_after}
(WORK / 'edit_stats.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(stats, ensure_ascii=True))
print(str(OUTPUT))
