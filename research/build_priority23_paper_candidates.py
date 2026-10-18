"""Primary-source screening only: does not select or implement priorities 2/3."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import urllib.request
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'research/evidence/priority23_candidates_20261018'
OUT = ROOT / 'research/priority23_paper_candidates_20261018.json'
PAPERS = [
    {
        'id': 'externalization', 'arxiv': '2609.38869', 'version': 1,
        'title': 'Reasoning Externalization for Faithful Large Language Model Narratives of Stock Return Predictions',
        'priority': [2], 'rank_within_scope': 'primary_method_candidate',
        'locators': ['Sections 3.1, 3.4-3.5; Table 1', 'Sections 4.1.2-4.1.3', 'Section 4.4, Tables 4-5'],
        'verified': [
            '동일한 evidence registry에서 수치·관계 정보의 노출 범위를 바꾸고, 각 근거에 고유 ID를 부여한다. 시스템 지시와 출력 스키마는 조건 간 유지한다.',
            '구조화된 사실 주장의 subject–predicate–value와 허용된 evidence ID를 대조한다. 자유 서술의 의미는 이 자동 검사만으로 판정하지 않고 별도 검토한다.',
            'Qwen3 8B/14B/32B 등에서 수치·관계의 외부 계산을 연구하며, 현재 Qwen3.5-4B 양자화 실행의 검증 결과는 아니다.'
        ],
        'possible_transfer_after_gate': '현재 공개 시장자료의 필드·단위·기간과 계산 결과를 명시적인 출처로 두고, 설명 속 수치 주장과 분리해 대조하는 후속 설계 후보.',
        'limits': [
            'CRSP/WRDS 자료를 사용하므로 원 데이터셋을 민간 무료 공개자료로 간주하지 않는다. 방법만 전용하고 현재 공개 데이터는 유지할 수 있다.',
            'SHAP 기반 예측 설명 연구이며 기관 문서 해석·배분 전략의 정답을 주지 않는다.',
            '추가로 계산된 값을 모델에 제공하면 정보 조건 자체가 바뀐다. 사전에 입력·평가 계약을 고정해야 하며 개선을 보장하지 않는다.'
        ],
        'numbers_not_adopted': '표의 효과 크기, 기간, 모델 크기, 추론 설정을 LIBERA 조건으로 자동 채택하지 않는다.'
    },
    {
        'id': 'finfirst', 'arxiv': '2609.25192', 'version': 1,
        'title': 'FinFIRST: Benchmarking Search Agents for Financial Information Retrieval, Sourcing and Traceability',
        'priority': [2, 3], 'rank_within_scope': 'primary_traceability_and_evaluation_candidate',
        'locators': ['Sections 2.2.2-2.2.3', 'Section 2.3, Independent re-solving and Rubric audit', 'Appendix tool descriptions, Python'],
        'verified': [
            '근거 패키지는 정확한 문서 위치, 입력값, 정의, 기간, 단위, 자료 버전, 중간 계산과 동등하게 허용되는 다른 근거 경로를 포함한다.',
            '수집·출처검증·계산과 답변 형성을 나눠 평가하고, 핵심 사실부터 중간 계산과 결론까지 추적한다.',
            'rubric에는 과제에 없는 요건을 사후에 추가하지 않도록 규정한다. 계산 도구는 금융 근거 자체를 제공하지 않는다.'
        ],
        'possible_transfer_after_gate': '숫자의 존재뿐 아니라 그 숫자의 산업·지표·기간·단위를 확인하고, 원문 사실과 모델의 배분 판단을 구분하는 평가 항목 후보.',
        'limits': [
            '검색형 금융 과제의 평가 선례이며 산업별 배분 비중의 유일한 정답이나 인과적 효과를 제공하지 않는다.',
            '기존 파일럿의 점수를 개선하기 위해 평가 요건을 소급 변경하면 안 된다. 새로운 요건은 다음 버전의 프롬프트와 함께 사전 고정해야 한다.',
            '동등한 출처 경로를 인정한다는 것은 모든 전략 대안이 같다는 뜻이 아니다.'
        ],
        'numbers_not_adopted': '논문의 rubric 가중치, 허용오차, 성공률, 도구 예산을 복사하지 않는다.'
    },
    {
        'id': 'same_number', 'arxiv': '2610.08675', 'version': 1,
        'title': 'Same-Number Citation Swaps: Stress-Testing Jev as a Financial Evidence Judge',
        'priority': [2, 3], 'rank_within_scope': 'recent_counterexample_and_validation_candidate',
        'locators': ['Section II-B', 'Section III-B', 'Section VI'],
        'verified': [
            '숫자와 연산을 고정하고 같은 숫자가 있는 다른 셀로 인용만 바꾸어, 수치 일치와 금융 역할의 근거 충족을 분리한다.',
            '잘못된 기간·지표 인용과 문맥상 동등한 근거를 구분한다. 명시적인 열 표시도 오류 탐지와 유효 근거 보존에 서로 다른 영향을 줄 수 있다.'
        ],
        'possible_transfer_after_gate': '현재 시장 수치 또는 근거 ID가 실제로 같은 산업·같은 지표·같은 기간의 주장을 지원하는지 확인하는 반례 점검 후보.',
        'limits': [
            '단일 연산 위주의 선택된 자료와 제한된 검토자 근거이므로 일반적 오류율을 전용할 수 없다.',
            '이 논문의 확률적 judge나 임계값을 채택하는 제안이 아니다. 결정적 계산 일치와 의미적 지원을 별도로 검토해야 한다.',
            '다른 산업을 비교하는 유효한 근거를 단순 ID 범위 검사만으로 거짓이라고 판단하면 안 된다.'
        ],
        'numbers_not_adopted': 'Jev 임계값 0.8, 반복 수, 표본 수와 생성 조건은 채택하지 않는다.'
    },
    {
        'id': 'e2a', 'arxiv': '2609.14302', 'version': 1,
        'title': 'E2A-Bench: Benchmarking Evidence-to-Action Reliability in Financial Chart Reasoning',
        'priority': [3], 'rank_within_scope': 'primary_action_explanation_consistency_analogy',
        'locators': ['Sections 3.2-3.4', 'Section 4.3.3', 'Limitations', 'Appendix B'],
        'verified': [
            '차트가 유일한 매수·매도 정답을 제공하지 않는다고 명시하고, 검증 가능한 사실·설명의 방향·행동·확신을 분리해 평가한다.',
            '근거의 사실성과 설명–행동의 일관성은 서로 다른 차원이며, 미래 수익 성과로 해석하지 않는다.',
            'Qwen3.5-4B도 평가하지만 차트/텍스트 입력의 다른 과제와 실행 조건이므로 현재 GGUF 성능의 보증이 아니다.'
        ],
        'possible_transfer_after_gate': '기관 문서에서 읽은 근거가 어떤 판단을 지지하는지, 그 판단과 실제 제안 비중에 대한 설명이 일치하는지를 별도로 검토하는 후보.',
        'limits': [
            '중국 주식 차트의 고정 시점 평가이며 기관 house view와 GICS 배분 과제는 다르다.',
            '패턴 검출과 기술지표 기준은 미묘한 문장이나 예외를 놓칠 수 있다.',
            'OW/UW 문구를 공통 S&P 500 기준 대비 강제 부호 정답으로 바꾸거나, 숫자 비중의 정답으로 전환할 근거가 아니다.'
        ],
        'numbers_not_adopted': 'NDR 합성식, 강한 신호 기준, 확신 척도와 기술지표 임계값은 전용하지 않는다.'
    },
    {
        'id': 'fundapod', 'arxiv': '2605.27864', 'version': 5,
        'title': 'FundaPod: A Multi-Persona Agent Pod Architecture with Knowledge Graph Memory for AI-Assisted Fundamental Investment Research',
        'priority': [3], 'rank_within_scope': 'domain_aligned_design_precedent_not_effectiveness_evidence',
        'locators': ['Section 3, DP2-DP4', 'Sections 5.1 and 5.4', 'Section 7, Limitations'],
        'verified': [
            '기관 투자연구를 검토 가능한 판단을 만드는 과제로 정의하고, 서로 다른 투자 관점과 원문 출처가 연결된 분석 메모를 보존한다.',
            '재현 가능한 데이터 처리와 판단 작업을 나누며, 중간·최종 주장에 원천 자료의 안정적 ID를 연결한다.',
            'v5는 시스템 설계 및 사례 설명이다. 논문이 정량적 성능·persona 충실성·투자 신호의 공식 검증을 아직 하지 않았다고 명시한다.'
        ],
        'possible_transfer_after_gate': '원문 근거 → 해석과 가정 → 선택한 배분의 이유와 가능한 반론을 구분하는 설명 계약 후보. 출처 문장과 새로 만든 투자 판단을 혼동하지 않도록 한다.',
        'limits': [
            '반론 또는 대안 개수, 비교 항목 수, 설명 길이나 목표 비중을 정하는 직접 수치 근거가 없다.',
            '기관의 sector view를 전체 운용 목적이나 실제 투자자 persona로 확대할 수 없다.',
            '다중 에이전트, 지식그래프, 유료·비공개 자료를 이번 실험에 도입해야 한다는 근거가 아니다.'
        ],
        'numbers_not_adopted': '설계 원칙만 후보로 둔다. 수치 효과나 성공 보증은 주장하지 않는다.'
    }
]


def collect(item):
    pid, label, url = item
    path = EVIDENCE / f'{pid}_{label}.html'
    req = urllib.request.Request(url, headers={'User-Agent': 'LIBERA-primary-research/1.0'})
    with urllib.request.urlopen(req, timeout=45) as response:
        blob, status, final = response.read(), response.status, response.url
    if status != 200 or not blob:
        raise RuntimeError(url)
    if path.exists() and path.read_bytes() != blob:
        raise RuntimeError('Preserved source differs: ' + str(path))
    if not path.exists():
        path.write_bytes(blob)
    result = {'source_id': pid + '_' + label, 'path': path.relative_to(ROOT).as_posix(),
              'url': url, 'resolved_url': final, 'http_status': status,
              'sha256': hashlib.sha256(blob).hexdigest(), 'size_bytes': len(blob)}
    if label == 'abs':
        soup = BeautifulSoup(blob, 'html.parser')
        history = soup.select_one('.dateline')
        result['version_dateline_observed'] = history.get_text(' ', strip=True) if history else None
    return result


def main():
    if OUT.exists() or OUT.with_suffix('.html').exists():
        raise SystemExit('Refusing to overwrite screening evidence.')
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    items = []
    for paper in PAPERS:
        base = paper['arxiv']
        items += [(paper['id'], 'fulltext', f'https://arxiv.org/html/{base}v{paper["version"]}'),
                  (paper['id'], 'abs', f'https://arxiv.org/abs/{base}')]
    with ThreadPoolExecutor(max_workers=4) as executor:
        sources = list(executor.map(collect, items))
    d = {
        'schema_version': 'libera_priority23_paper_screening_1.0',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'literature_candidates_only_not_protocol_selection_or_implementation',
        'priority2_implementation_started': False, 'priority3_implementation_started': False,
        'prerequisite': 'Three independent priority-1 checks must pass before starting priority-2; finish its three checks before priority-3, according to user instruction.',
        'main_experiment_authorized': False, 'model_calls_by_researcher': 0,
        'prior_files_modified': False, 'primary_sources': sources, 'candidates': PAPERS,
        'candidate_grouping': {
            'priority2': ['externalization', 'finfirst', 'same_number'],
            'priority3': ['finfirst', 'e2a', 'fundapod'],
            'interpretation': 'These papers support separate observable checks and possible interface designs, not a shared complete method or proven LIBERA fix.'
        },
        'not_selected_and_not_set': [
            'No new prompt, output schema, judge, metric weights or acceptance threshold has been selected.',
            'No alternative count, rationale word count, sector tilt magnitude or target weight has been selected.',
            'No model/runtime change or newly published performance value has been adopted.',
            'No claim that the current institutional sector documents specify complete investment mandates or a unique correct allocation.'
        ],
        'questions_for_later_design_after_priority1': [
            'How to identify an explicit numerical claim and its source field, unit, period and calculation without treating free-form prose extraction as a sound oracle?',
            'Whether to expose only existing values or additional deterministic computations; any exposure change must be registered as a new information condition.',
            'How to distinguish an original institutional claim, a model inference and an explicit assumption within the existing response contract?',
            'How to recognize supported alternative interpretations without imposing a unique allocation target?',
            'Which requested claim relationships need semantic review beyond code/ID/arithmetic checks?'
        ],
        'current_research_limits': [
            'Screening is targeted, not a systematic literature review or proof that no more recent relevant work exists.',
            'Public paper access does not imply all underlying datasets are free or redistributable.',
            'Deterministic fact checks, human semantic assessment and portfolio performance are different endpoints.',
            'The current one-case development outputs must not be regraded under newly selected criteria as if those criteria were frozen before the outputs.'
        ]
    }
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    rows = []
    for paper in PAPERS:
        url = f'https://arxiv.org/html/{paper["arxiv"]}v{paper["version"]}'
        rows.append('<tr><td>' + '/'.join(map(str, paper['priority'])) + '<br><a href="' + url + '">' + html.escape(paper['title']) + '</a><p>' + html.escape('; '.join(paper['locators'])) + '</p></td><td>' + html.escape(paper['possible_transfer_after_gate']) + '</td><td>' + '<br>'.join(html.escape(x) for x in paper['limits']) + '</td></tr>')
    markup = '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>②·③ 후속 연구근거 후보</title><style>body{max-width:1100px;margin:36px auto;padding:0 20px;font:16px/1.7 system-ui;color:#182a3c}table{width:100%;border-collapse:collapse}td,th{border:1px solid #ddd;padding:12px;vertical-align:top}td{width:33%}a{overflow-wrap:anywhere}</style><main><h1>② 숫자·설명 일치 / ③ 배분 근거 연결: 논문 후보</h1>
<p><b>자료 조사만 마친 상태입니다.</b> ① 계산 피드백 반영의 검증 세 차례를 통과하기 전에는 ②를 구현하거나 실행하지 않습니다. ③도 앞 단계가 검증된 뒤 진행합니다. 새 점수·임계값·프롬프트·비중 정답을 정하지 않았습니다.</p>
<p>②에는 숫자의 출처·산업·지표·기간·단위를 연결하고 설명과 계산을 따로 검증하는 연구가 적합합니다. ③에는 사실 근거, 그에 대한 해석, 실제 선택 사이의 연결을 확인하는 연구가 적합합니다. 근거가 정확하다는 것과 선택이 유일한 정답이라는 것은 별개로 다룹니다.</p>
<table><tr><th>대상 / 논문·원문 위치</th><th>검토할 적용 후보</th><th>근거의 한계</th></tr>''' + ''.join(rows) + '''</table>
<p>정량적 효과 연구와 시스템 설계 사례를 구분했습니다. FundaPod는 기관 연구와 주제가 가깝지만 정량적 효과 검증은 없습니다. Reasoning Externalization은 설명과 수치를 연결하는 직접 선례이나 유료 CRSP/WRDS 원자료를 사용하므로 방법만 검토합니다. E2A-Bench의 현재 모델 계열 실험도 이 산업 배분 과제의 성능을 보장하지 않습니다.</p>
<p>다음 단계에서 선택할 경우 입력 노출·출력 계약·검증 범위를 먼저 고정해야 합니다. 기존 파일럿 결과를 새 기준으로 소급 합격 처리하지 않습니다. <a href="priority23_paper_candidates_20261018.json">전체 후보·확인 사항·원문 SHA JSON</a></p></main></html>'''
    OUT.with_suffix('.html').write_text(markup, encoding='utf-8')
    print(json.dumps({'path':str(OUT), 'sha256':hashlib.sha256(OUT.read_bytes()).hexdigest(), 'source_count':len(sources)}, indent=2))


if __name__ == '__main__':
    main()
