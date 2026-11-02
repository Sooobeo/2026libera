from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import json
from lxml import etree

WORK = Path(__file__).parent
SOURCE = WORK / 'paper_section3_shortened.docx'
OUTPUT = WORK / 'paper_section3_minimal.docx'
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W = '{' + NS['w'] + '}'
with ZipFile(SOURCE) as z:
    root = etree.fromstring(z.read('word/document.xml'))
body = root.find('w:body', NS)
nodes = list(body)

def text(node):
    return ''.join(node.xpath('.//w:t/text()', namespaces=NS))

start = next(i for i, n in enumerate(nodes) if text(n).strip() == '3. 실험설계')
end = next(i for i, n in enumerate(nodes) if text(n).strip() == '4. 실험과정과 평가방법')
old_nodes = nodes[start:end]
template = next(n for n in old_nodes if text(n).startswith('본 실험은'))
rest_before = [etree.tostring(n, method='c14n') for n in nodes[end:]]
paragraphs = [
    '공통 GenAI의 펀드별 배분 차이와 근거 제공 단계의 영향을 비교하였다. 네 펀드(FCNTX, VPMCX, DODGX, TRBCX)의 2025년 말 주식 보유자료를 FF12 산업으로 분류·정규화하고, 2016~2025년 산업수익률[1]과 Ledoit–Wolf 공분산[2]으로 기대수익과 위험을 추정하였다.',
    '공통·펀드별 합성 전망 아래 월간 사후 기대수익을 최대화하되, 비중은 비음수·합계 1·기존 보유수준 이하의 분산을 충족하게 하였다. 전체 전망으로 구한 최적 배분은 평가에만 사용하고 모델에는 제공하지 않았다.',
    '근거 미제공(R0)과 계획(R1)·작성(R2)·점검(R3)부터 동일 검색 근거를 제공하는 조건을 비교하였다. 제공된 근거는 이후 대화에 유지하였다.',
    '전망 정밀도 두 수준에서 각 다섯 상황에 네 펀드·네 조건을 1회 적용해 160개 업무 흐름을 실행하였다. 조건 간에는 근거 활용 단계 수와 대화 이력도 달라지므로 순수한 시점 효과로 해석하지 않는다.',
]
new_nodes = [deepcopy(nodes[start])]
for value in paragraphs:
    p = deepcopy(template)
    rprs = p.xpath('./w:r/w:rPr', namespaces=NS)
    rpr = deepcopy(rprs[0]) if rprs else None
    for child in list(p):
        if child.tag != W + 'pPr':
            p.remove(child)
    r = etree.SubElement(p, W + 'r')
    if rpr is not None:
        r.append(rpr)
    etree.SubElement(r, W + 't').text = value
    new_nodes.append(p)

old_chars = sum(len(text(n)) for n in old_nodes)
new_chars = sum(len(text(n)) for n in new_nodes)
assert new_chars < old_chars / 2, (old_chars, new_chars)
for n in old_nodes:
    body.remove(n)
for offset, n in enumerate(new_nodes):
    body.insert(start + offset, n)
rest_after = [etree.tostring(n, method='c14n') for n in list(body)[start + len(new_nodes):]]
assert rest_before == rest_after
new_xml = etree.tostring(root, encoding='UTF-8', xml_declaration=True, standalone=True)
with ZipFile(SOURCE) as src, ZipFile(OUTPUT, 'w', compression=ZIP_DEFLATED) as dst:
    for info in src.infolist():
        dst.writestr(info, new_xml if info.filename == 'word/document.xml' else src.read(info.filename))
stats = {'previous_characters': old_chars, 'current_characters': new_chars,
         'additional_reduction_percent': round((1 - new_chars / old_chars) * 100, 1),
         'original_reduction_percent': round((1 - new_chars / 4335) * 100, 1),
         'section4_unchanged': rest_before == rest_after}
(WORK / 'minimal_stats.json').write_text(json.dumps(stats, indent=2), encoding='utf-8')
print(json.dumps(stats))
