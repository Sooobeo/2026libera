"""Primary-source comparison of finite priority1 changes; no execution."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import urllib.request
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/v47_priority1_revision_options_20261018.json'
EDIR = ROOT / 'research/evidence/v47_priority1_options_20261018'
SOURCES = [
    ('uptake_fulltext', 'https://arxiv.org/html/2607.15388v1'),
    ('uptake_abs', 'https://arxiv.org/abs/2607.15388'),
    ('order_fulltext', 'https://arxiv.org/html/2601.22035v1'),
    ('order_abs', 'https://arxiv.org/abs/2601.22035'),
    ('symbolic_fulltext', 'https://arxiv.org/html/2606.27757v1'),
    ('symbolic_abs', 'https://arxiv.org/abs/2606.27757'),
    ('finfirst_fulltext', 'https://arxiv.org/html/2609.25192v1'),
    ('finfirst_abs', 'https://arxiv.org/abs/2609.25192'),
]


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def collect(item):
    sid, url = item
    path = EDIR / (sid + '.html')
    req = urllib.request.Request(url, headers={'User-Agent': 'LIBERA-public-research/1.0'})
    with urllib.request.urlopen(req, timeout=45) as response:
        blob, status, final = response.read(), response.status, response.url
    if status != 200 or not blob:
        raise RuntimeError(url)
    if path.exists() and path.read_bytes() != blob:
        raise RuntimeError('Preserved source differs')
    if not path.exists():
        path.write_bytes(blob)
    soup = BeautifulSoup(blob, 'html.parser')
    result = {'source_id': sid, 'url': url, 'path': path.relative_to(ROOT).as_posix(),
              'sha256': sha(blob), 'size_bytes': len(blob), 'http_status': status, 'resolved_url': final}
    dateline = soup.select_one('.dateline')
    if dateline:
        result['version_dateline_observed'] = dateline.get_text(' ', strip=True)
    return result


def main():
    if OUT.exists() or OUT.with_suffix('.html').exists():
        raise SystemExit('Refusing overwrite of evidence memo')
    EDIR.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as executor:
        sources = list(executor.map(collect, SOURCES))
    evidence = [
        {'paper': 'Precise but Uncoupled', 'arxiv_version': '2607.15388v1',
         'source_ids': ['uptake_fulltext', 'uptake_abs'],
         'locators': ['Section3.3', 'Section3.4', 'Appendix I Table12 and I.1', 'Appendix I.3 and I.5'],
         'direct': 'Single-Agent Iterative는 이전 답변과 실패 기록을 사용해 최대3 outer attempts를 수행한다. PER은 Planner의 변경 계획을 Executor가 읽는 구조다. Planner는 최종 답을 쓰지 않고 계획을 낸다. 검출·후속 후보 변경·수정 성공을 분리한다.',
         'limit': 'gpt-oss-120b 수학 연구이며 역할분리만으로 반영이 보장되지 않는다. ACK 강제도 개선을 보장하지 않았다. B의 완전한 11비중 계획·외부 검사·2call 구성은 논문의 그대로인 조건이 아니다. code/data는 기관 승인 후 공개 예정으로 명시되어 구현 복제는 주장하지 않는다.'},
        {'paper': 'Towards Reliable and Robust LLM Planning: A Symbolic Feedback-Driven Iterative Self-Refinement Framework',
         'arxiv_version': '2606.27757v1', 'source_ids': ['symbolic_fulltext', 'symbolic_abs'],
         'locators': ['SectionIII-B, Equation2', 'SectionIII-C'],
         'direct': '원래 과제·실제 오류 피드백·이전 계획을 함께 제공하고, 검증 성공 또는 사전 반복 상한에 도달하면 종료한다.',
         'limit': 'PDDL 계획·VAL 검증과 목표 인식 연구이다. 금융 비중 정답, 본2call 상한 또는 모델별 개선을 지지하지 않는다. 계획 인식·정답 방향 안내를 이번 진단에 전용하지 않는다.'},
        {'paper': 'Thinking Out of Order', 'arxiv_version': '2601.22035v1',
         'source_ids': ['order_fulltext', 'order_abs'], 'locators': ['Section2 Task Formulation', 'Section4', 'AppendixA'],
         'direct': '설명 먼저와 답 먼저의 출력 순서를 비교하며 Qwen2.5-7B-Instruct를 포함한 수학 실험에서 순서 민감성을 관측한다.',
         'limit': '현재 Qwen3.5-4B, Ollama JSON 문법, 비중수정 과제를 검증하지 않았다. JSON key order만 바꾸면 개선된다는 직접 증거는 아니다. 출력 계획은 관측 가능한 산출물이며 숨은 내부 추론의 증거가 아니다.'},
        {'paper': 'FinFIRST', 'arxiv_version': '2609.25192v1',
         'source_ids': ['finfirst_fulltext', 'finfirst_abs'], 'locators': ['Sections2.2.2–2.2.3', 'Section2.3'],
         'direct': '입력·출처·중간 계산·결론을 추적하고, 과제에 없는 요건을 평가에 사후 추가하지 않는 선례이다.',
         'limit': '평가 근거이지 계획 분리나 산술 흔적 노출의 성능 보장이 아니다. 여기서 새 시장수치나 기관배분 정답을 만들지 않는다.'},
    ]
    candidates = [
        {'id': 'A', 'name': '실제 오류와 전후 변화 기록을 사용하는 유한 수정 반복',
         'evidence_level': 'direct_bounded_feedback_loop_precedent_with_domain_transfer',
         'basis': ['2607.15388v1 AppendixI Table12/I.1/I.5', '2606.27757v1 SectionIII-B'],
         'strength': '기존 실패를 기억하고 새 후보·계산 결과를 반복 대조하는 직접 선례가 가장 가깝다.',
         'adaptation': '비중 delta=0과 합계 잔차는 관측된 계산 사실로 제공할 수 있다. 어느 산업을 얼마나 바꾸라는 정답은 제공하지 않는다.',
         'budget': '논문의3은 총 outer candidate attempts이며3추가수정이라는 뜻이 아니다. 과거 v45/v46을 새 예산에 포함할지 사전 명시해야 하고 과거 실패를 소거하면 안 된다.',
         'tradeoff': '비슷한 전체 답변을 반복할 수 있다. 최적 상한·해결 보장이 아니며, 매 반복의 실제 결과를 남기고 상한 후 중단해야 한다.'},
        {'id': 'B', 'name': '모델 계획 산출물 → 실제 검사 → 별도 실행 응답',
         'evidence_level': 'direct_planner_executor_pattern_but_exact_two_call_vector_plan_is_local_adaptation',
         'basis': ['2607.15388v1 Section3.3/AppendixI.1', '2609.25192v1 Sections2.2.2–2.3'],
         'strength': '계획에서 무엇을 바꾸려 했는지와 최종 제출이 무엇인지 별도로 관측할 수 있다. 현재의 수정 주장·실제 비중 불일치를 조사하는 개발 진단으로 합리적이다.',
         'adaptation': '모델이 계획에서 전체11비중을 직접 쓸 경우 이는 계산 가능한 중간 후보이다. 원 논문의 최종답을 쓰지 않는 Planner와 다르므로 명시한다. host는 그 후보를 검증할 뿐 적용·완성·수정하지 않는다.',
         'budget': '최대2generation은 계획1회+실행1회라는 선택한 개발 범위다. 논문 최적수치나 PER 전체 재현이 아니다.',
         'tradeoff': '비용과 입력량이 늘고 실행자가 잘못된 계획을 그대로 옮길 수 있다. 역할분리의 성능 우위는 주장하지 않는다. 계획 실패·실행 실패·최종 설명 모순을 각각 남긴다.'},
        {'id': 'C', 'name': '계획·산술 산출물을 비중보다 먼저 생성하는 출력 순서',
         'evidence_level': 'cross_model_output_order_analogy_not_validated_for_current_schema',
         'basis': ['2601.22035v1 Sections2/4, AppendixA'],
         'strength': '자기회귀 모델이 최종 값을 먼저 확정하는 출력 순서의 영향을 별도로 조사할 수 있다.',
         'adaptation': '제안하는 것은 명시적 계획/계산 산출물이며 내부 thinking 접근이 아니다. 실제 렌더·문법이 요구한 순서를 보장하는지는 별도 구현 점검이 필요하다.',
         'budget': '한call 여부는 국소 설계 선택이고 논문 표본/토큰 수를 전용하지 않는다.',
         'tradeoff': '현재 모델·JSON 적용의 직접 효과 증거가 약하다. B와 동시에 넣으면 계획분리와 출력순서의 개별 효과를 구분할 수 없다.'},
    ]
    prior_paths = ['research/v46_priority1_round3_20261018.json', 'research/v46_priority1_round2_20261018.json',
                   'research/v46_single_revision_basis_addendum_20261018.json', 'research/v44_conditions_reference_20261018.json']
    prior_files = [{'path': p, 'sha256': sha((ROOT / p).read_bytes())} for p in prior_paths]
    data = {
        'schema_version': 'libera_priority1_revision_options_1.0', 'proposed_protocol_version': '4.7',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'primary_reference_comparison_not_execution_registration', 'phase': 'priority1',
        'observed_failure': 'v46 recognizes prior sum0.965 but leaves every weight unchanged and falsely claims corrected sum1.',
        'primary_sources': sources, 'evidence_review': evidence, 'candidate_comparison': candidates,
        'conditional_recommendation': {
            'candidate': 'B',
            'reason': 'Root is considering B as a finite development diagnostic. Separate plan and execution provides observable evidence about whether a concrete model-authored candidate changes before explanatory text is completed. This is a design judgment, not an empirically proven improvement for LIBERA.',
            'strongest_loop_precedent': 'A', 'weakest_exact_current_task_support': 'C',
            'not_selected_automatically': ['A', 'C'],
        },
        'if_B_selected_contract_to_register_before_calls': [
            'Plan call sees same public task, preserved invalid candidate and genuine calculator feedback. It authors its own proposed change; any complete weights are model-produced intermediate candidate values.',
            'Host computes only raw validity and exact before/after differences. It never applies edits, fills missing weights, normalizes, projects, clips, creates cash, or supplies suggested corrected weights.',
            'Executor sees the original task, model-authored plan and actual plan-check result; it itself emits the complete final response. Preserve literal outputs and all intermediate artifacts.',
            'Predeclare whether a numerically invalid but well-formed plan can still be passed to the sole executor with its true failed check; do not improvise a retry after observing its content.',
            'A deviation between model plan and final vector is recorded. Do not silently require equality unless the registered task contract does; judge any claimed faithful execution against actual values.',
            'Maximum2 generation calls, no automatic retry, no fallback A/C and no until-pass selection; existing per-call900s limit remains an engineering bound.',
            'Keep model/runtime/options, public market/documents and existing raw numeric acceptance rules; disclose the changed task, history, intermediate output contract and extra verifier boundary.',
            'Three audits assess input/provenance, independent raw arithmetic and narrow correction-claim truth. A calculator pass alone is insufficient for priority1 gate.',
            'Do not add priority2 market-explanation tasks or priority3 institution-rationale tasks; main remains forbidden.'
        ],
        'limits': [
            'Known failure selected for development after prior outputs; this is iterative design/tuning, not an untouched test case or independent replication.',
            'Even a successful B run would not isolate planning, additional compute, new prompt or feedback placement as a cause.',
            'Success would not demonstrate recovery of the original four-stage retained-history protocol, source fidelity, investment quality or general model reliability.',
            'No new hidden gold, target vector, paper-derived success threshold or optimal call budget is established.',
            'Targeted current primary-source search is not an exhaustive literature review.'
        ],
        'prior_files': prior_files,
        'model_calls_by_reviewer': 0, 'priority2_implementation_started': False,
        'priority3_implementation_started': False, 'main_experiment_authorized': False,
        'prior_files_modified': False,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    rows = ''.join('<tr><td>' + c['id'] + ' ' + html.escape(c['name']) + '</td><td>' + html.escape(c['strength']) + '</td><td>' + html.escape(c['adaptation'] + ' ' + c['budget'] + ' ' + c['tradeoff']) + '</td></tr>' for c in candidates)
    links = ''.join('<li><a href="' + s['url'] + '">' + s['source_id'] + '</a></li>' for s in sources if s['source_id'].endswith('fulltext'))
    markup = '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>① 다음 수정 후보의 논문 근거</title><style>body{max-width:1100px;margin:36px auto;padding:0 20px;font:16px/1.65 system-ui;color:#17293b}table{border-collapse:collapse;width:100%}td,th{border:1px solid #cbd2db;padding:12px;vertical-align:top}</style><main><h1>① 계산 피드백 반영: 다음 유한 수정 후보</h1><p><b>B: 계획과 실행을 나누는 개발 진단을 조건부로 권고합니다.</b> 이유는 이번 모델의 수정 계획과 실제 비중을 별도로 관찰할 수 있기 때문입니다. 더 높은 성공률이 입증된 방법이라는 뜻은 아닙니다.</p><p>2026년 Precise but Uncoupled는 계획자→실행자 구조를 직접 설명하지만, 정확한 비판과 인정이 실제 수정으로 연결되지 않을 수 있다는 한계도 보여줍니다. 원 논문의 계획자는 최종 답을 내지 않습니다. 따라서 계획에서 전체11개 비중을 먼저 쓰고 검사하는 방식과 총2회 상한은 명시적인 국소 전용입니다.</p><table><tr><th>후보</th><th>근거와 장점</th><th>전용 범위·비용·한계</th></tr>''' + rows + '''</table><p>계획과 최종 비중은 모두 모델이 직접 생성하고 host는 실제 계산만 합니다. 계획 검사가 실패했을 때에도 단 한 번의 실행 호출을 허용할지 사전에 정해야 하며, 결과를 본 뒤 반복을 늘리지 않습니다. 실패하면 기록하고 종료합니다. ②·③와 본실험은 진행하지 않습니다.</p><p>FinFIRST는 중간 계산·결론 추적의 평가 선례이며 개선 효과의 증거가 아닙니다. 성공하더라도 추가 계산량·프롬프트·계획 분리의 효과를 각각 식별할 수 없고, 원래 네 단계 실험의 복구를 입증하지 않습니다.</p><ul>''' + links + '''</ul><p><a href="v47_priority1_revision_options_20261018.json">정확한 절·근거 수준·보존 SHA JSON</a></p></main></html>'''
    OUT.with_suffix('.html').write_text(markup, encoding='utf-8')
    print(json.dumps({'path': OUT.relative_to(ROOT).as_posix(), 'sha256': sha(OUT.read_bytes()), 'source_count': len(sources)}, indent=2))


if __name__ == '__main__':
    main()
