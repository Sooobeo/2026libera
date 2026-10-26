"""Restore the original research problem and build the revised illustrated paper."""
from pathlib import Path
from copy import deepcopy
import hashlib
import importlib.util
import json

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
SOURCE = ROOT / 'paper/v520_manuscript_20261026.json'
NEW = ROOT / 'paper/v530_manuscript_20261026.json'
STEM = 'LIBERA_소논문_문제제기개선_v5.3_20261026'

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def p(text):
    return {'type': 'paragraph', 'text': text}

old = json.loads(SOURCE.read_text(encoding='utf-8'))
new = deepcopy(old)
new['title'] = '공통 생성형 AI와 기관별 투자판단의 차이'
new['subtitle'] = '공개 산업전망의 반영과 근거 검증 절차에 관한 탐색적 사례연구'
new['version'] = '5.3'
replacements = {
    1: [p('공통 생성형 AI가 여러 기관의 검색·요약과 배분안 작성을 지원할 때, 기관별로 필요한 판단의 차이도 약해질 수 있다. 이 가능성을 검토하려면 서로 다른 기관 근거가 최종 선택까지 어떻게 이어지는지 확인해야 한다. 본 연구는 동일한 시장 자료와 미국 주식 11개 산업을 대상으로 Fidelity와 UBS의 공개 전망을 초기·후기에 제공하거나 제공하지 않은 다섯 조건을 분석하였다. 기관 원문, 모델의 설명, 제출 비중을 대조하고 원응답과 외부 계산으로 합계를 맞춘 파생 배분을 구분하였다. 네 기관 자료 조건과 대조군의 배분 거리는 4.76~12.98%였다. 그러나 자료 요약이 정확한 뒤에도 서로 다른 배분에 같은 수치 오류가 남았고, 선택 이유와 실제 비중이 어긋났다. 정규화가 원비중의 증감 방향을 뒤집는 사례도 확인하였다. 이 결과는 자료를 제공하고 배분이 달라졌다는 사실만으로 기관별 근거가 보존되었다고 평가하기 어렵다는 점을 보여준다. 이에 기관의 전망과 모델의 추가 판단을 구분하고, 근거가 지지한 변경이 확정 비중까지 이어지는지 검증하는 절차를 제안한다. 본 사례는 과잉수렴이나 실제 시장 동질화를 직접 검증한 것이 아니며, 제안의 효과는 후속 검증 대상이다.')],
    2: [p('주제어  생성형 AI, 기관별 투자판단, 판단 차이, 산업배분, 근거 충실성')],
    4: [
        p('서로 다른 금융기관이 같은 생성형 AI를 사용하면, 기관별로 달라야 할 투자판단까지 비슷해질 수 있는가. 본 연구는 이 문제에서 출발한다. 그 영향은 투자결정 전체를 AI에 맡기는 경우에만 생기는 것은 아니다. 자료 검색과 요약, 투자논거 작성, 위험요인 검토에 쓰인 AI의 산출물도 다음 단계가 어떤 정보와 대안을 중요하게 볼지에 영향을 줄 수 있다. 금융안정위원회는 생성형 AI의 정보 검색·문서 요약 활용과 함께 공통 모델·자료원 의존에 따른 시장 상관성 증가를 잠재적 취약성으로 제시하였다(FSB, 2024).'),
        p('이때 살펴볼 경로는 개별 업무에서 사용한 공통 AI가 여러 기관의 판단 방식에 누적해서 관여할 가능성이다. 기관들이 동일한 투자 규칙을 공식적으로 채택하지 않았더라도, 같은 모델이 고른 정보와 해석이 중간산출물에 담겨 다음 판단의 입력이 될 수 있다. 최종 승인자가 서로 다르다는 사실만으로 그 이전의 판단 과정까지 독립적이라고 볼 수는 없다. 공통 모델이 어느 단계에서 기관별 근거의 차이를 유지하거나 약화시키는지 확인할 필요가 있다.'),
        p('여러 기관의 배분이 비슷하다는 사실 자체가 문제는 아니다. 같은 시장정보와 제약이 같은 결론을 지지한다면 수렴은 합리적일 수 있다. 반면 전망, 투자목표, 기존 보유자산과 위험한도가 다르면 적절한 판단도 달라질 수 있다. 본 연구가 관심을 두는 과잉수렴은 이러한 조건상 필요한 차이까지 줄어드는 경우이다. 따라서 배분이 얼마나 다른지와 함께 그 차이 또는 유사성이 어떤 근거에서 나왔는지를 살펴야 한다. 이 구분은 공통 알고리즘과 결과 동질화를 분리한 연구와도 연결된다(Kleinberg와 Raghavan, 2021; Bommasani 등, 2022).'),
        p('기관별 자료를 AI에 연결하는 방식은 이 문제에 대응할 한 방법이다. 다만 자료를 더했다는 사실과 그 자료가 지지하는 판단을 최종 배분까지 유지했다는 것은 별개의 문제다. 자료가 요약에 정확히 등장해도 비중을 정할 때 다른 이유가 덧붙거나, 이전 초안의 잘못된 전제가 남을 수 있다. 금융배분의 정보 조건 비교와 설명 충실성 연구를 함께 보면, 자료의 의미에서 선택 이유와 실제 비중으로 이어지는 연결을 확인해야 한다(Hornuf 등, 2025; Matton 등, 2025).'),
        p('본고는 이 연결을 관찰하기 위해 동일한 AI에 Fidelity와 UBS의 공개 산업전망을 초기 또는 후기에 제공한 네 조건과 기관 전망을 제공하지 않은 대조군을 분석하였다. 공통 시장 자료와 새 자금을 미국 주식 11개 산업에 배분하는 과제는 유지하였다. 실제 기관의 보유자산·고객 목적·위험한도와 그에 따른 정답 배분은 관측하지 않았으므로, 필요한 차이의 크기나 과잉수렴을 직접 판정하지 않는다. 기관은 공개 문서를 부여한 자료 조건을 뜻한다. 기관 자료는 직접 제공하였으며 검색을 수행하는 RAG의 효과를 비교한 실험도 아니다.'),
        p('분석에서는 기관 자료 조건의 최종 배분이 대조군과 달랐지만, 정확한 자료 요약 뒤에도 설명과 실제 비중이 어긋났고 서로 다른 배분에 같은 수치 오류가 남았다. 원비중의 변화와 반대 방향으로 움직인 정규화 결과도 확인하였다. 본고의 기여는 기관 자료를 제공한 뒤 어느 연결이 유지되고 어느 지점에서 끊기는지 구체화한 데 있다. 이를 토대로 기관의 전망과 모델이 덧붙인 판단을 구분하고, 그 판단이 지지한 변경을 확정 비중과 대조하는 절차를 설계한다. 사후 분석 변경을 공개한 다섯 탐색 사례이며, 제안이 판단의 차이와 품질을 함께 보존하는지는 후속 검증에서 확인해야 한다.')
    ],
    5: [], 6: [], 7: [], 8: [],
    20: [
        p('중심 질문은 공통 AI에 제공한 서로 다른 기관 전망이 요약을 넘어 배분 선택의 근거로 이어지는가이다. 이를 자료 해석, 배분 차이, 제공 절차라는 세 관찰 질문으로 나누었다.'),
        p('RQ1은 기관별 공개 산업전망의 의미가 설명과 실제 비중 사이에서 유지되는가이다. 원문의 방향·범위·이유를 산업행 요약과 선택 이유에 대조하고, 모델이 밝힌 이유가 제출 비중과 일치하는지 확인한다. 기관 전망을 따르지 않았더라도 원문을 정확히 이해하고 별도 판단의 이유를 밝혔으면 그 자체를 오독으로 분류하지 않는다.')
    ],
    21: [p('RQ2는 기관 전망을 제공한 조건의 최종 배분이 공통 시장 자료만 제공한 대조군과 어떻게 다른가이다. 동일한 외부 계산을 적용한 배분 사이의 거리를 비교한다. 이 값은 선택이 달라진 정도를 보여주며, 그 차이가 기관 근거에 충실한지는 RQ1의 대조로 별도 확인한다.')],
    22: [p('RQ3은 기관 자료를 초안부터 제공한 경우와 최종 검토 때 처음 제공한 경우에 근거 해석과 배분 수정이 어떻게 다른가이다. 같은 기관의 초기·후기 조건 및 각 조건의 초안·최종안을 비교한다. 자료 제공과 함께 초안·노출 횟수·대화 이력도 달라지므로, 관측된 수정 양상을 순수한 시점 효과나 절차의 우열로 해석하지 않는다.')],
    70: [p('D0와 F0의 파생 배분 거리는 두 E 조건에서 0%, Fidelity L 13.45%, UBS L 4.49%, C 0.55%였다. E는 초안부터 기관 자료를 제공받았으므로 무수정을 자료 무시로 해석할 수 없다. C에도 변화가 있어 모든 수정을 기관 자료의 효과로 귀속하기 어렵고, C의 거리를 빼서 순수 효과를 계산할 수도 없다. 배분이 달라진 정도만으로는 기관의 관점이 선택에 반영되었는지 답하기 어려우므로, 다음 절에서는 자료·이유·숫자의 대응을 살펴본다.')],
    77: [p('RQ1에서는 기관별 산업행의 등급과 요약이 보존되었으나, 이후 해석과 실제 비중의 연결은 일관되지 않았다. RQ2에서는 네 기관 자료 조건의 파생 배분이 C와 모두 달랐다. RQ3에서는 초기·후기 조건의 수정 양상이 달랐지만 어느 절차가 근거를 더 충실히 반영했는지는 확정하지 못하였다. 기관자료 조건과 대조군 사이의 배분 차이는 관찰되었지만, 이를 자료 제공의 순수 효과나 기관별 판단의 보존으로 평가하려면 추가 검증이 필요하다.')],
    80: [p('표 8의 사례는 기관 전망이 요약에 도달한 뒤에도 선택의 근거로 이어지는 연결이 끊길 수 있음을 보여준다. UBS L은 산업행에서 원문의 등급을 재현했지만 종합 설명에서는 일부 등급을 달리 불렀고, 정보기술 원비중을 줄인 뒤 늘렸다는 취지로 설명했다. 자료를 정확히 읽었는지, 그 자료를 어떤 이유로 사용했는지, 비중을 실제로 어떻게 바꾸었는지를 나누어 확인해야 이러한 단절이 드러난다.')],
    83: [p('서로 다른 최종 배분에 같은 수치 오류가 남았다는 관측은 배분 차이가 곧 독립적인 판단을 뜻하지 않는다는 점을 보여준다. 기관별 문구와 비중이 달라도, 공통 전제가 잘못되었다면 그 위에서 이루어진 선택은 함께 재검토해야 한다. Fidelity L·UBS L·C의 완료 D0는 동일하므로 오류 잔존을 독립된 세 번의 오류 발생으로 셀 수는 없다. 이 사례가 보여주는 것은 공유한 초안의 오류와 서로 다른 최종 배분이 공존했다는 점이다.')],
    86: [p(old['blocks'][86]['text'].split('최종 원비중', 1)[0].strip()), p('최종 원비중' + old['blocks'][86]['text'].split('최종 원비중', 1)[1])],
    93: [p('설명은 다음 선택을 검증할 가설로 사용할 수 있다. 예컨대 특정 기관 근거 때문에 정보기술을 줄였다고 밝혔다면, 그 근거를 제거·교체했을 때 관련 판단을 다시 검토하는지 확인하는 것이다. 본고가 수행하지 않은 이러한 개입 비교를 통해, 설명이 실제 선택을 예측하는지와 근거 변화에 타당하게 반응하는지를 후속 검증해야 한다.')],
    111: [p('최종 비중을 확정할 때에는 적용 근거와 판단 주체, 버전을 함께 기록한다. “늘렸다”거나 “기준보다 높다”는 설명은 확정한 숫자로 계산하여 작성한다. 이는 항공 연구에서 완료 보고를 실제 예약 상태와 대조한 구조를 본 과제에 적용한 것이다(Reddy 등, 2026). 숫자·근거·규칙이 바뀌면 관련 설명과 승인도 갱신해야 한다. 잘못된 검사 규칙이나 이전 버전의 결정을 재사용하면 새로운 오류가 생길 수 있다. 검사를 통과했다는 것은 명시한 관계가 일치한다는 뜻이며, 모든 투자판단이 적절하다는 보증은 아니다.')],
    117: [p('공개자료 과제에서는 같은 시장 전제를 확인하고, 기관의 전망과 모델의 추가 판단을 구분하며, 근거가 지지한 변경이 실제 비중까지 이어지는지 검사할 수 있다. 실제 기관에서 이 절차를 쓰려면 투자목적, 허용 위험, 기존 보유자산, 금지·예외 조건과 결정 권한도 입력해야 한다. 공통 모델이 기관별로 필요한 차이를 보존하는지는 이러한 운용조건까지 포함해야 평가할 수 있다. Hornuf 등(2025)이 논의한 배분 재량의 제한도 실제 기관 정보가 있어야 구체화할 수 있다.')],
    118: [p('기관별 판단을 유지하려면 원문과 승인된 운용조건이 모델의 설명에 섞여 사라지지 않도록 관리해야 한다. 자료 준비자는 원문과 버전을, 운용 담당자는 추가 판단과 허용 재량을, 검증 담당자는 설명·숫자의 불일치와 미해결 사항을 관리한다. 이 책임 구분은 NIST AI RMF 1.0을 참고한다(Tabassi, 2023). 기관의 전망, 모델이 덧붙인 해석, 실제 승인한 비중을 따로 기록하면 공통 모델의 어느 판단을 받아들였는지 확인할 수 있다.')],
    122: [p('본 과제에는 실제 보유비중·고객 목적·위험선호와 미래 투자성과가 없어, 기관별로 달라야 할 정답 배분이나 과잉수렴을 판정할 수 없다. 현재 결과는 서로 다른 공개 근거가 설명과 비중에 연결되는 과정에 관한 증거다. 사후 의미 검토도 부분 가림의 AI 보조 방식이므로 독립적인 사람 평가나 평가자 간 신뢰도를 대신하지 않는다. 8장의 절차가 필요한 차이를 지키면서 오류를 줄이는지는 새 자료와 독립 평가에서 검증해야 한다.')],
    130: [p('제안의 채택 여부는 근거 없는 판단이 줄고 필요한 근거 반응이 유지되는지를 함께 기준으로 삼는다. 타당한 공통 정보에 따른 수렴은 허용하고, 서로 다른 근거가 지지한 차이는 보존해야 한다. 공통 오류가 남은 채 설명만 길어지거나 정당한 선택의 차단·비용·누락이 늘면 제안을 수정하거나 제외한다. 통계적으로 유의한 차이가 없다는 사실만으로 품질 유지나 동등성을 선언할 수도 없다. 더 나아가 원래 문제인 과잉수렴을 검증하려면, 목표·보유자산·제약이 다른 과제에서 필요한 배분 차이와 판단 품질의 기준을 먼저 정해야 한다.')],
    132: [p('본고는 공통 생성형 AI의 사용이 기관별로 필요한 투자판단의 차이를 약화시킬 수 있다는 문제에서 출발하였다. 이 가운데 서로 다른 공개 산업전망이 설명과 배분 선택에 이어지는 과정을 다섯 조건으로 살펴보았다. 기관 자료 조건의 최종 배분은 대조군과 달랐지만, 등급과 요약의 보존이 일관된 선택 이유와 비중으로 이어지지는 않았다. 서로 다른 배분에 같은 수치 오류가 남았고, 외부 정규화로 증감 방향이 뒤집히기도 했다. 배분의 차이가 관찰되었다는 사실만으로 기관별 근거가 보존되었다고 평가하기 어려운 이유다.')],
    133: [p('이에 본고는 기관이 밝힌 전망과 모델이 덧붙인 판단을 구분하고, 근거가 지지한 변경이 확정 비중까지 이어지는지 대조하는 절차를 제안하였다. 핵심 근거를 바꾼 뒤 관련 판단을 재검토하는지, 공통 오류를 고친 뒤 그 오류에 의존한 선택도 다시 확인하는지가 후속 검증 대상이다. 현재 사례는 과잉수렴이나 금융시장 동질화를 입증하지 않으며 제안의 효과도 검증하지 않았다. 기관자료를 추가하는 대응이 실제로 의미를 가지려면, 어떤 근거가 어떤 선택을 지지했고 그 관계가 최종 배분에 남았는지 확인할 수 있어야 한다.')],
    179: [p(old['blocks'][179]['text'].replace('본 원고 v5.2', '본 원고 v5.3'))]
}
insert_after = {
    60: [p('기관 전망을 제공한 네 조건의 최종 배분은 대조군과 달랐다. 그러나 그 차이가 기관 근거의 충실한 반영에서 나왔는지는 별도 확인이 필요했다. 이를 판단하기 위해 원비중의 유효성, 최종 배분의 차이, 모델의 이유와 실제 숫자의 대응을 함께 살펴본다.')],
    78: [p('결과를 원래 문제와 연결할 때 중요한 점은 서로 다른 배분이 만들어졌어도 기관 근거가 선택까지 유지되었다고 단정할 수 없다는 것이다. 다음의 해석은 자료 제공만으로 필요한 차이가 보존되는지 확인하기 어려웠던 지점과, 이를 검증하려면 무엇을 구분해야 하는지를 설명한다.')],
    94: [p('대응의 목표는 공통 시장 사실을 함께 검증하면서 기관별 근거가 지지한 판단을 최종 비중까지 확인할 수 있게 하는 것이다. 이를 위해 원문과 추가 운용판단을 구분하고, 제안한 증감과 확정 비중이 일치하는지 대조하며, 공통 전제를 고쳤을 때 관련 선택을 다시 검토하는 절차를 제안한다. 기관별 근거를 검색·제공하는 단계에 이러한 검증을 연결해야 자료를 더한 효과를 평가할 수 있다. 아래 절차는 관측된 단절에 대응하는 설계 가설이며 아직 개선 효과를 검증하지 않았다.')]
}
blocks = []
log = []
for i, b in enumerate(old['blocks']):
    blocks.extend(deepcopy(replacements.get(i, [b])))
    if i in replacements:
        log.append({'original_block': i, 'before': b, 'after': replacements[i]})
    blocks.extend(deepcopy(insert_after.get(i, [])))
    if i in insert_after:
        log.append({'after_original_block': i, 'inserted': insert_after[i]})
new['blocks'] = blocks
assert [b for b in new['blocks'] if b['type'] == 'table'] == [b for b in old['blocks'] if b['type'] == 'table']
assert [b for b in new['blocks'] if b['type'] == 'reference'] == [b for b in old['blocks'] if b['type'] == 'reference']
assert [b for b in new['blocks'] if b['type'] == 'heading'] == [b for b in old['blocks'] if b['type'] == 'heading']
NEW.write_text(json.dumps(new, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(WORK / 'revision_log.json').write_text(json.dumps(log, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

publisher = module('libera_publish', ROOT / 'research/manuscript_v520_20261026/publish_manuscript.py')
publisher.render(NEW, ROOT / 'paper' / (STEM + '.md'), ROOT / 'paper' / (STEM + '.html'))
builder = module('libera_word', ROOT / 'research/document_v520_20261026/build_document.py')
builder.SOURCE = NEW
builder.OUT = ROOT / 'paper' / (STEM + '.docx')
builder.WORK = WORK
original_add_table = builder.add_table
def add_table_with_short_result_kept(doc, block):
    original_add_table(doc, block)
    if block['caption'].startswith('표 5 '):
        for row in doc.tables[-1].rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.keep_with_next = True
builder.add_table = add_table_with_short_result_kept
figures = json.loads(builder.MANIFEST.read_text(encoding='utf-8'))
if isinstance(figures, dict) and 'figures' in figures:
    figures = figures['figures']
figures = {b['id']: b for b in figures} if isinstance(figures, list) else figures
illustrated = builder.compose(new, figures)
illustrated['version'] = '5.3'
for index, block in enumerate(illustrated['blocks']):
    if block.get('id') == 'fig01_allocations':
        assert illustrated['blocks'][index - 1]['type'] == 'paragraph'
        illustrated['blocks'][index - 1:index + 1] = [block, illustrated['blocks'][index - 1]]
        break
for index, block in enumerate(illustrated['blocks']):
    if block.get('id') == 'fig04_normalization':
        figure = illustrated['blocks'].pop(index)
        next_heading = next(i for i in range(index, len(illustrated['blocks'])) if illustrated['blocks'][i]['type'] == 'heading')
        illustrated['blocks'].insert(next_heading, figure)
        break
ILL = WORK / 'illustrated_manuscript.json'
ILL.write_text(json.dumps(illustrated, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
doc = builder.make_doc(illustrated)
receipt = {'source': str(NEW), 'source_sha256': digest(NEW), 'previous_source_sha256': digest(SOURCE), 'docx': str(builder.OUT), 'docx_sha256': digest(builder.OUT), 'illustrated_source_sha256': digest(ILL), 'original_tables_preserved': True, 'original_headings_preserved': True, 'original_references_preserved': True, 'tables': len(doc.tables), 'figures': len(doc.inline_shapes), 'native_equations': 2, 'changed_blocks': len(replacements), 'inserted_chapter_bridges': len(insert_after)}
(WORK / 'build_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(receipt, ensure_ascii=False, indent=2))
