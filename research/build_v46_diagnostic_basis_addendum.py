"""Record the selected one-call development scope without altering prior evidence."""
import datetime as dt
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/v46_single_revision_basis_addendum_20261018.json'


def file_ref(path):
    p = ROOT / path
    return {'path': path, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'size_bytes': p.stat().st_size}


def main():
    if OUT.exists() or OUT.with_suffix('.html').exists():
        raise SystemExit('Refusing to replace an existing evidence addendum.')
    basis = file_ref('research/v46_feedback_basis_20261018.json')
    original = json.loads((ROOT / basis['path']).read_text(encoding='utf-8'))
    sources = original['primary_sources']
    for source in sources:
        if file_ref(source['path'])['sha256'] != source['sha256']:
            raise ValueError('Primary source changed: ' + source['path'])
    d = {
        'schema_version': 'libera_v46_single_revision_basis_addendum_1.0',
        'protocol_version': '4.6',
        'created_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'change_scope': 'one_call_feedback_grounded_revision_of_preserved_invalid_final_candidate',
        'status': 'reference_addendum_for_predeclared_development_diagnostic_not_main_protocol',
        'prior_basis': basis,
        'inherited_conditions': file_ref('research/v44_conditions_reference_20261018.json'),
        'renderer_policy': file_ref('research/v44_renderer_policy_20261018.json'),
        'schema_evidence': file_ref('research/v45_revision_reference_20261018.json'),
        'primary_sources': sources,
        'original_basis_unchanged': True,
        'selection_record': {
            'decision_source': 'Root task instruction implementing the user-approved ordered priority-1 development work.',
            'selected_candidate': 'one_call_diagnostic',
            'max_new_model_generations': 1,
            'one_call_origin': 'A predeclared development resource bound and scope choice; not a paper-reported optimum, sample size, or proof of success.',
            'superseded_recommendation_only': 'The original memo preferred changing the active task within the existing four-stage budget. The root instead selected a separate one-call diagnostic; original evidence remains valid and unedited.',
            'unselected_alternative': 'The memo\'s three-candidate/two-revision loop is not selected and is not an authorization to retry.'
        },
        'input_contract': {
            'included': [
                'Original stage-1 public task, source/market values and system instruction.',
                'Preserved complete stage-4 raw assistant response from v4.5 as the candidate being reconsidered.',
                'The actual calculator feedback for that same preserved final candidate.',
                'A revision task that embeds that feedback and asks the model to determine a revised allocation under the existing public conditions.'
            ],
            'not_included': ['Intermediate stage-1, stage-2 and stage-3 assistant responses and their histories.'],
            'scope_consequence': 'This tests whether one frozen invalid final candidate can be revised when given its actual arithmetic error explicitly. It does not test complete four-stage retained-history behavior, anchoring persistence, or the main R1/R4 comparison.',
            'no_hidden_gold': True,
            'no_suggested_sector_weights_or_corrected_vector': True,
            'same_output_contract': 'Keep the existing seven top-level response fields and the existing schema; do not insert correct ratings or sector-specific target weights.',
            'priority_scope': 'Only calculator feedback uptake; no priority-2 number/explanation correction program or priority-3 rationale enrichment is added.'
        },
        'runtime_contract': {
            'model_and_options': 'Use the model, digest, template, engine and full options pinned in the inherited conditions; preserve all settings except the explicitly registered diagnostic input scope.',
            'new_temperature_seed_or_penalty_choice': False,
            'automatic_retry': False,
            'unregistered_continuation': False,
            'model_calls_by_evidence_author': 0,
            'main_calls_authorized': 0
        },
        'paper_to_adaptation_map': [
            {'source_id': 'code_repair', 'locator': 'Section III-A; Section V-H',
             'direct': 'A model revises its previous candidate with the original task and actual execution error; the new candidate is tested again.',
             'adaptation': 'Financial JSON and a deterministic portfolio calculator replace code and program tests. Only one new revision is authorized; the paper uses different total-attempt budgets and larger models.'},
            {'source_id': 'uptake', 'locator': 'Sections 3.2-3.4; Appendix I.1 and I.3; Figure 4',
             'direct': 'Feedback, candidate change and successful repair are separate; active-context feedback is studied, while mandatory acknowledgment alone has negative evidence.',
             'adaptation': 'Exact vector comparison and a deterministic arithmetic gate replace math answer extraction and an LLM evaluator. A diagnostic prompt cannot establish causal efficacy or faithful reasoning.'},
            {'source_id': 'openpm', 'locator': 'Sections 4 and 6.3',
             'direct': 'Raw constructor adherence is distinguished from feasibility after deterministic projection.',
             'adaptation': 'Retain the distinction but do not project, normalize, clip, add cash or otherwise repair the proposed weights.'},
            {'source_id': 'critic', 'locator': 'Algorithm 1; Section 3',
             'direct': 'External feedback conditions a later model correction under a finite budget.',
             'adaptation': 'One predeclared correction is a local resource decision, not the paper\'s iteration budget; its stochastic correction setup is not imported.'}
        ],
        'measurement_and_terminal_contract': {
            'raw_output_preserved': True,
            'new_calculation_required': True,
            'acceptance_rules': 'Existing finite/complete/long-only/full-investment calculator constraints and existing implementation tolerances only. Keep exact sum and residual separately; no new acceptance threshold.',
            'uptake': 'Describe whether the vector changed from the preserved invalid candidate; change alone is not successful repair or proof of reasoning.',
            'repair': 'A new raw allocation passes only if independently recalculated under the same public constraints without automatic repair.',
            'feedback_claim': 'Independently check any statement that the prior or new allocation met the constraint against the actual respective calculator result.',
            'if_invalid': 'Preserve the new raw invalid candidate and report unsuccessful diagnostic; stop after the single call.',
            'if_incomplete': 'Preserve partial bytes, mark missing complete results as unobserved, and stop without inference from a prefix.',
            'if_numeric_pass_only': 'Do not call priority 1 solved if the required independent provenance, arithmetic and narrow feedback-use reviews have not all passed.',
            'priority2_and_priority3_start': 'Only after the three user-requested priority-1 checks pass; current literature screening does not start their implementation.',
            'main_experiment': 'Not authorized and not started.'
        },
        'limits': [
            'No cited study tests this exact quantized Qwen3.5-4B financial diagnostic.',
            'The deliberately selected previously failed case is a development case, not an independent confirmatory sample.',
            'Prior intermediate history is absent by design; improvement cannot establish that the original four-stage workflow is repaired.',
            'One corrected allocation cannot establish general reliability, strategy quality, future returns or rationale faithfulness.',
            'Failure and successful workflow termination remain separate from numeric acceptance.'
        ]
    }
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    markup = '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>① 단일 수정 진단 근거 추가서</title><style>body{max-width:850px;margin:40px auto;padding:0 20px;font:17px/1.8 system-ui;color:#182a3c}</style><main>
<h1>① 계산 피드백 반영: 별도 한 번의 수정 진단</h1>
<p>v4.5 마지막 원안과 그 원안에 대한 실제 계산 오류를 원래 공개 과제와 함께 제시하고, 모델에게 한 번만 수정을 요청하는 개발용 진단입니다. 비중은 모델이 결정하며 계산기가 대신 고치지 않습니다.</p>
<p><b>중간 1–3단계 답변 이력은 이번 진단에 포함하지 않습니다.</b> 따라서 성공해도 네 단계 전체의 이력 유지·수정 과정이 해결됐다고 해석하지 않습니다. 원래 실패 원본과 근거 메모는 보존합니다.</p>
<p>최근 코딩 연구에는 원래 과제·이전 답안·실제 오류를 함께 제시해 모델이 재작성하고 재검증하는 선례가 있습니다. 금융 JSON, 포트폴리오 계산기, 기존 모델과 디코딩을 사용하는 이번 방식은 이를 전용한 설계입니다. 새로운 호출 한 번은 사전에 정한 개발 범위이며 논문의 최적 반복 횟수가 아닙니다.</p>
<p>새 원안이 실제로 바뀌었는지, 그대로 재계산했을 때 조건을 충족하는지, 오류에 대한 설명이 실제 전후 결과와 맞는지를 따로 검토합니다. 오류 인정 문장만으로는 성공으로 보지 않습니다. 실패하거나 응답이 미완료이면 원문과 실패 상태를 남기고 추가 호출 없이 끝냅니다.</p>
<p>①의 독립 검증 세 차례가 통과하기 전에는 ② 수치·설명 교정과 ③ 배분 근거 보강을 실행하지 않습니다. 본실험도 실행하지 않습니다.</p>
<p><a href="v46_single_revision_basis_addendum_20261018.json">출처·조건 해시와 직접 근거/전용 범위 JSON</a> · <a href="v46_feedback_basis_20261018.html">수정하지 않은 기존 근거 메모</a></p></main></html>'''
    OUT.with_suffix('.html').write_text(markup, encoding='utf-8')
    print(json.dumps({'path': str(OUT), 'sha256': hashlib.sha256(OUT.read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    main()
