"""Write the independent methods review; this does not authorize generation."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ref(path):
    return {'path':path,'sha256':hashlib.sha256((ROOT/path).read_bytes()).hexdigest()}


def write_r2():
    previous_path='research/v491_runtime_methods_review_20261019.json'
    previous=json.loads((ROOT/previous_path).read_text(encoding='utf-8'))
    history=ROOT/'research/artifacts/v491_runtime_review_history_20261019/methods_r2'
    history.mkdir(parents=True,exist_ok=True)
    supporting=[]
    for source in ['research/build_v491_runtimeprep_report.py','research/verify_v491_runtimeprep_round3.py']:
        destination=history/Path(source).name
        if destination.exists():
            raise ValueError('Methods r2 snapshots already exist; use a new revision instead of overwriting')
        destination.write_bytes((ROOT/source).read_bytes())
        supporting.append({**ref(str(destination.relative_to(ROOT)).replace('\\','/')),'original_path_at_review':source,'scope':'Source-level report/integration logic review; generated final numerical evidence remains subject to root integration audit.'})
    implementation=[ref(p) for p in ['research/sector_v491_runtime.py','research/test_sector_v491_runtime.py','research/sector_v491_human_gate.py','research/test_sector_v491_human_gate.py','research/sector_v491_contract.py','research/prepare_sector_v491.py']]
    old_gate=next(r for r in previous['implementation_refs'] if r['path']=='research/sector_v491_human_gate.py')
    assert ref(old_gate['path'])==old_gate, 'Human gate implementation changed; repeat the earlier ten independent tests'
    checks=previous['checks']+[{'name':'same_run_case_actual_D0_provenance','pass':True,'finding':'F0 binds response, D0 worker specification, worker summary, supervisor result and transport result by exact hashes and same run/case paths. Response content must equal raw_draft verbatim; pinned model, normal stop, one generation attempt, continuation, cleanup and all records must agree. D0 specification is revalidated. Wrong or missing provenance fails before generation.'},{'name':'root_diagnostic_payload_integrity','pass':True,'finding':'Latest root integration logic compares actual saved HTTP request body with diagnostic declaration and uses publisher word boundaries in addition to source identifiers. This is a stronger source-free check; generated final report remains pending root execution.'}]
    result={'reviewer_role':'independent_methods_and_topic_review_agent','revision':'r2','status':'PASS','recorded_at_utc':datetime.now(timezone.utc).isoformat(),'prior_review':ref(previous_path),'review_scope':'Final v2 runtime methods/topic review, fifteen targeted runtime tests and fourteen human-gate tests. No live model calls or human semantic review. Source-level report-builder review is separate from final evidence integration.','implementation_refs':implementation,'supporting_source_snapshots':supporting,'control_document_refs':[ref(p) for p in ['research/v491_human_review_pack_20261019_R1.json','research/v491_human_review_pack_20261019_R2.json','research/v491_evaluation_protocol_20261019.json','plan/LIBERA_실험설정_v4.9.1_20261019.json']],'checks':checks,'check_count':len(checks),'targeted_runtime_tests_passed':15,'targeted_runtime_tests_failed':0,'human_gate_tests_passed':14,'human_gate_tests_note':'Earlier ten tests passed against the same unchanged human-gate implementation; four added tests for duplicate names, future timestamps, changed input and changed submission bytes also passed independently.','model_calls':0,'human_review_completed':False,'open_findings':[],'resolved_findings':[{'id':'F0_D0_ARTIFACT_LINEAGE','resolution':'Five exact same-run/same-case prior D0 artifacts are required and cross-checked; independent targeted mutation tests passed. Normal coordinator still propagates its exact raw first draft.','scope_limit':'Artifact identity and internal consistency guard against accidental substitution and provenance loss; they do not authenticate deliberately fabricated files.'}],'remaining_research_gates':['Two actual independent human source/common-context reviews and reconciliation before pilot research outputs.','Four-case pilot with first D0/F0 attempts, actual token/memory/latency and complete failed/missing case accounting.','Main-source review plus exact inputs/model/runtime/evaluation/order/resource freeze before main.','Current per-request exact token guard does not prove a universal bound for every possible future F0 or full two-stage completion.'],'interpretation_limits':['CPU diagnostic results remain engineering evidence; maximum 32 generated tokens cannot forecast full investment-task latency with up to 8192 output tokens.','No semantic pass, source difference, E advantage, arithmetic success or model reliability is required as a tuning target.','Finite document-conditioned cases cannot establish market-wide harmful convergence, profitability, population effects or pure anchoring.']}
    output=ROOT/'research/v491_runtime_methods_review_20261019_r2.json'
    if output.exists():
        raise ValueError('r2 review already exists; preserve it and use a new revision')
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    prior_human=ROOT/'research/artifacts/v491_runtimeprep_20261019/human_gate_independent_review.json'
    updated=json.loads(prior_human.read_text(encoding='utf-8'))
    updated.update(reviewed_at_utc=result['recorded_at_utc'],revision='r2',files=[ref('research/sector_v491_human_gate.py'),ref('research/test_sector_v491_human_gate.py')],tests_passed=14,prior_review=ref(str(prior_human.relative_to(ROOT)).replace('\\','/')),change_note='Four new negative cases were independently checked against the unchanged gate implementation; earlier ten tests remain applicable.')
    (prior_human.parent/'human_gate_independent_review_r2.json').write_text(json.dumps(updated,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'status':result['status'],'checks_passed':len(checks),'runtime_tests_passed':15,'human_gate_tests_passed':14,'open_findings':0}))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--revision',choices=['r1','r2'],default='r1')
    args=p.parse_args()
    if args.revision=='r2':
        write_r2()
        return
    history='research/artifacts/v491_runtime_review_history_20261019/r1/'
    refs=[ref(history+'sector_v491_runtime.py'),ref(history+'test_sector_v491_runtime.py'),ref('research/sector_v491_human_gate.py'),ref('research/test_sector_v491_human_gate.py'),ref('research/build_v491_runtimeprep_report.py'),ref(history+'verify_v491_runtimeprep_round3.py'),ref('research/v491_human_review_pack_20261019_R1.json'),ref('research/v491_human_review_pack_20261019_R2.json'),ref('research/v491_evaluation_protocol_20261019.json'),ref('plan/LIBERA_실험설정_v4.9.1_20261019.json')]
    checks=[
        ('topic_alignment','The same public-source judgment to interpretation to stated decision to actual weight chain is retained. Common AI, common market, and early/late source timing remain the research comparison.'),
        ('fixed_common_context','load_bundle rebuilds exact assigned D0 messages from hash-bound common context and public source packet; L source identity stays hidden until F0.'),
        ('four_case_two_stage_design','Two pilot sources by E/L, own D0 per case, first F0 only, at most eight generation attempts; no main entrypoint.'),
        ('calculator_role','Actual raw draft arithmetic is support supplied to both procedures, not a strategy-setting comparator or target-weight generator.'),
        ('no_behavioral_heuristics','No new risk coefficient, target return, rating-to-weight conversion, semantic score, or forced source diversity is introduced.'),
        ('pre_output_human_gate','Human gate is checked in prepare, run, transport and worker validation; blank forms fail before model HTTP. Two attestations preserve original file hashes and reconciliation.'),
        ('pilot_then_main_review','129 relevant pilot fields are required per reviewer; the 99 main-only fields may remain null until main review. Uncertainty or similar source meaning is permitted.'),
        ('readability_not_success_censoring','Raw-sum failures and wrong output citations do not prohibit a structurally readable draft from proceeding to F0.'),
        ('structural_failure_denominators','Unreadable drafts skip their dependent F0 while other prespecified cases remain eligible; infrastructure/integrity incidents stop later cases and preserve not-attempted statuses.'),
        ('no_retry_or_repair','Exclusive output reservation and execution marker prevent retry/resume; no post-F0 repair or replacement of missing/invalid allocations.'),
        ('evidence_visibility','Exact body reconstruction rejects L source injection and controller metadata in model messages. Evaluator forms and cross-source contrast matrices remain outside requests.'),
        ('capacity_scope','Native counting applies to the exact actual request plus full allowed output; unknown future F0 is not claimed bounded. This remains a pre-main requirement, not a completed feasibility guarantee.'),
        ('engineering_counts_separate','Report builder labels synthetic CPU calls separately from zero pilot/main generations; synthetic maximum 32 output tokens cannot forecast full 8192-token task latency.'),
        ('engineering_setting_status','CPU threads, context and deadline are engineering choices rather than claimed paper-optimal behavioral conditions. No empirical inference comes from CPU probes.'),
        ('human_completion_not_fabricated','Delivered forms remain blank and report human review/freeze false. Software validates completeness and hashes, not human identity or semantic truth.'),
        ('research_scope_limits','Two documents, one model, one common market snapshot remain finite descriptive cases; no profitability, market-wide harmful convergence or pure anchoring claim.'),
    ]
    result={'reviewer_role':'independent_methods_and_topic_review_agent','revision':'r1','status':'OPEN_FINDING_REQUIRES_F0_LINEAGE_BINDING','recorded_at_utc':datetime.now(timezone.utc).isoformat(),'review_scope':'Source-level runtime/report-method review, nine targeted coordinator tests and ten human-gate tests; no live generation. The report builder has not yet executed and its future numerical result rows are not certified here.','implementation_refs':refs,'checks':[{'name':name,'pass':True,'finding':finding} for name,finding in checks],'targeted_runtime_tests_passed':9,'human_gate_tests_passed':10,'model_calls':0,'human_review_completed':False,'open_findings':[{'id':'F0_D0_ARTIFACT_LINEAGE','severity':'required_integrity_fix_before_final_runtime_signoff','finding':'Normal coordinator uses its actual raw D0, but direct F0 worker specs only check internal text consistency. They do not yet bind that raw string to the same run/case completed D0 response artifact. A copied or synthetic raw_draft could satisfy the first revision spec validator.','required_change':'Bind F0 to exact same-run/same-case D0 response, worker request/spec, worker summary and supervisor evidence with SHA checks and single completed D0 attempt; fail closed before render/generation if missing or mismatched.','resolution_status':'runtime agent implementing; initial code snapshot retained'}],'additional_review_notes':['Final root audit should compare each actual diagnostic request body with its declared spec and check issuer words with word boundaries, not substring ubs matching.','Final root audit must bind the new r2 method/technical/code receipts after the lineage change; this initial receipt is not final approval.'],'no_conclusions_about':['Actual research response quality','Human semantic agreement','Full D0/F0 runtime completion','Statistical significance or population effects']}
    out=ROOT/'research/v491_runtime_methods_review_20261019.json'
    initial_copy=ROOT/history/'v491_runtime_methods_review_initial_reference_locations.json'
    if out.exists() and not initial_copy.exists():
        initial_copy.write_bytes(out.read_bytes())
        result['prior_receipt_reference_relocation']={'preserved_initial':ref(str(initial_copy.relative_to(ROOT)).replace('\\','/')),'reason':'Root integration checker was amended after review; its exact reviewed bytes are now linked at the SHA-identical r1 snapshot. Findings and unresolved F0 lineage status are unchanged.'}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'status':result['status'],'checks_passed':len(checks),'tests_passed':19}))


if __name__=='__main__':main()
