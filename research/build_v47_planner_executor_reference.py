"""Freeze the selected finite planner/executor adaptation, without running it."""
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/v47_planner_executor_reference_20261018.json'


def record(path):
    blob = (ROOT / path).read_bytes()
    return {'path': path, 'sha256': hashlib.sha256(blob).hexdigest(), 'size_bytes': len(blob)}


def main():
    if OUT.exists() or OUT.with_suffix('.html').exists():
        raise SystemExit('Refusing to overwrite frozen selection evidence.')
    comparison_path = 'research/v47_priority1_revision_options_20261018.json'
    comparison = json.loads((ROOT / comparison_path).read_text(encoding='utf-8'))
    sources = [s for s in comparison['primary_sources'] if not s['source_id'].startswith('order_')]
    for s in sources:
        if record(s['path'])['sha256'] != s['sha256']:
            raise RuntimeError('Primary-source hash mismatch')
    uptake = next(s for s in sources if s['source_id'] == 'uptake_fulltext')
    text = BeautifulSoup((ROOT / uptake['path']).read_bytes(), 'html.parser').get_text(' ', strip=True)
    phrases = ['without producing a final answer', 'The Executor sees',
               'concrete plan updates', 'question-scoped repair ledgers',
               'ACK-required is a failed compliance-style control']
    source_checks = [{'claim_locator': p, 'observed': p in text} for p in phrases]
    if not all(c['observed'] for c in source_checks):
        raise RuntimeError('Primary-source phrase verification failed')
    data = {
        'schema_version': 'libera_planner_executor_reference_1.0',
        'protocol_version': '4.7', 'phase': 'priority1',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'frozen_reference_for_selected_finite_development_diagnostic_not_execution_result',
        'change_scope': 'two_call_model_authored_plan_then_model_authored_full_response_with_actual_feedback',
        'comparison_memo': record(comparison_path),
        'primary_sources': sources,
        'source_checks': source_checks,
        'inherited_conditions': record('research/v44_conditions_reference_20261018.json'),
        'renderer_policy': record('research/v44_renderer_policy_20261018.json'),
        'previous_schema_evidence': record('research/v45_revision_reference_20261018.json'),
        'preserved_failed_diagnostic': {
            'summary': record('data/local_sector_runtime/feedback_diagnostic_v46_20261018/summary.json'),
            'revision_record': record('data/local_sector_runtime/feedback_diagnostic_v46_20261018/revision_record.json'),
            'round2': record('research/v46_priority1_round2_20261018.json'),
            'round3': record('research/v46_priority1_round3_20261018.json'),
        },
        'selection': {
            'candidate': 'B_minimal',
            'selected_by': 'Root coordination under user-authorized sequential priority1 repair work.',
            'purpose': 'Observe a model-authored future correction plan separately from the subsequent model-authored submitted allocation.',
            'planned_max_generation_calls': 2,
            'call_roles': ['planner', 'executor'],
            'call_budget_basis': 'Finite local development scope consisting of one planning call and one execution call; not a reported optimal paper setting.',
            'automatic_retries': 0, 'automatic_fallback_A_or_C': False,
            'main_experiment_authorized': False,
        },
        'direct_paper_basis': {
            'paper': 'Precise but Uncoupled', 'url': 'https://arxiv.org/html/2607.15388v1',
            'locators': ['Section3.3', 'AppendixI Table12', 'AppendixI.1 PER', 'AppendixI.3', 'AppendixI.5'],
            'direct_claim': 'Planner receives task, previous plan and advice and states concrete plan updates without giving a final answer; Executor receives task, the plan and advice to form the candidate. Failed-answer memory and candidate transitions are explicit.',
            'short_exact_quote': 'without producing a final answer',
            'warning': 'The same paper shows that precise criticism, acknowledgment and a separated planner/executor/reviewer pipeline do not guarantee actual correction. Its model/task is gpt-oss-120b on mathematics, not this Qwen3.5-4B finance task.',
            'replication_not_claimed': 'The original PER includes a Reviewer and inner/outer budgets. This two-call development diagnostic is a deliberate simplification, not PER reproduction.',
        },
        'supporting_sources': [
            {'url': 'https://arxiv.org/html/2606.27757v1', 'locator': 'SectionIII-B, Equation2',
             'supported': 'Original task, real error feedback and previous attempts can inform new model plans; terminate on validation or a predefined limit.',
             'not_supported': 'Does not select2calls, this model, portfolio weights or a particular repair target.'},
            {'url': 'https://arxiv.org/html/2609.25192v1', 'locator': 'Sections2.2.2–2.3',
             'supported': 'Trace inputs, intermediate claims/calculations and final conclusions; do not add absent rubric requirements retrospectively.',
             'not_supported': 'Does not demonstrate performance improvement from this planner/executor split.'}
        ],
        'planner_contract': {
            'inputs': 'Original public task/source/market, preserved invalid answer, its actual calculator feedback, and factual v45-to-v46 unchanged-weight/unchanged-sum diagnostics.',
            'output': 'Model-authored future correction plan, using the existing seven field names; weights is the empty array and no complete submitted allocation is emitted in this role.',
            'plan_fields': 'Use alternatives/risk_discussion for concrete intended changes and budget adjustment planning; this is an observable output artifact, not access to hidden thinking.',
            'no_host_target': 'No sector, corrected sector weight, exact target vector or normalization recipe is supplied by the host. Existing task sum1 remains a public constraint.',
            'assessment_scope': 'A planning-role empty weights array is intentional, not an allocation candidate with sum0 and not a successful numeric portfolio. Its content can still be contradicted or unsupported.',
            'schema_precision': 'Reusing seven field names does not imply identical full JSONSchema if planning changes the permitted array cardinality. Record any role-specific contract exactly.',
        },
        'executor_contract': {
            'inputs': 'Original public task and preserved failure, all newly generated planner text, actual calculator/error records and the registered new message history.',
            'output': 'The model itself emits the existing complete final seven-key response with all11 public sectors and their numeric weights.',
            'host_role': 'The host never applies the plan, creates sector weights or repairs the vector. It calculates raw validity and factual comparisons only.',
            'plan_execution_comparison': 'Retain the plan and final vector for direct comparison. Record what was executed and whether claims of execution are true; do not silently treat plan prose as a changed portfolio.',
        },
        'validation_and_stop_contract': [
            'Preserve every raw plan, request, stream, final response and error. A transport/shape failure stops under the existing fail-closed rules; no substitute answer is produced.',
            'At most one planner and one executor generation; no outcome-based extension or automatic A/C fallback.',
            'Final allocation is checked under existing finite11sector/bounds/sum rules with the inherited1e-6 serialization tolerance, without normalization, clipping, projection, cash imputation or gold.',
            'Final acceptance requires independent provenance, exact raw arithmetic and narrow correction-claim reviews. A claim of having corrected the answer is not proof.',
            'If the final vector or correction claims fail, preserve failure and remain at priority1. Do not begin priority2/3 or the main experiment.',
            'Existing per-call900s/time-output limits are inherited runtime choices; no new optimum is asserted.'
        ],
        'paper_vs_local_choice': {
            'direct_pattern': 'Separate model-authored planning from model-authored execution, with critique/failure information available.',
            'local_adaptations': ['Seven existing field names and weights=[] planning shape', 'One planner plus one executor maximum', 'Factual cross-version sector deltas as deterministic feedback', 'Retain existing finance task and small quantized model', 'No new Reviewer generation; independent offline reviews remain separate'],
            'unchanged_research_targets': ['No automatic weight repair', 'No unique weight gold', 'No priority2 market-number or priority3 institutional-reason revision task', 'No main experiment'],
        },
        'limitations': [
            'This is another known-failure development intervention after observing v45/v46, not an untouched test or independent replication. Count and retain all previous failed attempts.',
            'Success would not isolate planning, extra compute, task wording, feedback placement or retained history as the causal factor.',
            'Success would not establish that the original four-stage protocol, institution-strategy comparison or source-grounded allocation quality is repaired.',
            'A false or non-actionable plan can still be followed by an invalid execution; planning-role separation is not a correctness guarantee.',
            'Failure mechanisms remain hypotheses unless separately tested; current output does not identify hidden model intent or reasoning.'
        ],
        'model_calls_by_researcher': 0, 'prior_files_modified': False,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    markup = '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>① 계획 후 실행: 선택 근거</title><style>body{max-width:900px;margin:36px auto;padding:0 20px;font:16px/1.7 system-ui;color:#17293b}li{margin:10px 0}</style><main><h1>① 계획 후 실행: 최대 두 호출의 개발 진단</h1><p>첫 호출은 모델이 앞으로 어떤 수정을 할지 계획만 쓰고, 둘째 호출은 모델이 실제11개 비중과 완전한 응답을 생성합니다. 프로그램은 계획을 대신 적용하지 않고 원문 보존과 계산만 합니다. 계획의 빈 비중 배열은 의도된 중간 산출물이며 배분 합격이나 합계0의 제출안으로 평가하지 않습니다.</p><p><a href="https://arxiv.org/html/2607.15388v1">Precise but Uncoupled (2026), §3.3·부록I.1</a>은 계획자가 최종 답 없이 변경 계획을 만들고 실행자가 계획을 받아 답을 내는 직접 선례입니다. 같은 논문은 정확한 피드백과 역할분리가 실제 수정을 보장하지 않는다는 한계도 보여줍니다.</p><ul><li>논문에서 가져오는 것은 계획→실행의 구분입니다. 기존7개 필드·빈배열 계약과 최대2회는 이 개발 진단의 구현·범위 선택입니다. 논문 재현이나 최적 횟수로 쓰지 않습니다.</li><li>v45와 v46의 실제 비중 변화0 및 계산 오류를 기록하되 특정 산업을 얼마로 고치라는 정답은 주지 않습니다. 모델의 계획과 실제 제출이 일치하는지 검토합니다.</li><li>최종 비중은 원래 산술 기준으로 계산하고 수정 설명의 진실성까지 세 차례 독립 검토합니다. 실패하면 보존하고 종료하며 다른 후보나 추가 반복을 자동 실행하지 않습니다.</li><li>이미 관찰한 실패에 대한 후속 개발이므로 반복 설계 위험을 명시합니다. 성공해도 계획 분리의 인과효과, 원래4단계의 복구, 전략품질을 입증하지 않습니다. ②·③와 본실험은 아직 진행하지 않습니다.</li></ul><p><a href="v47_planner_executor_reference_20261018.json">고정된 근거·입출력 범위·원문 해시 JSON</a></p></main></html>'''
    OUT.with_suffix('.html').write_text(markup, encoding='utf-8')
    print(json.dumps({'path': OUT.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(OUT.read_bytes()).hexdigest(), 'sources': len(sources)}, indent=2))


if __name__ == '__main__':
    main()
