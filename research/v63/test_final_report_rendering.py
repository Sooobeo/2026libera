"""Synthetic evaluator-to-report checks. No model calls or completion aliases."""
from copy import deepcopy
import hashlib,itertools,json
from pathlib import Path
from datetime import datetime,timezone
import pytest
import numpy as np

from research.v63 import finalize_experiment_report as report
from research.v63.test_evaluate import main_fixture,profile,trace,evaluate
from research.v63.evaluate import ARMS,FUNDS,evaluate_counterfactual,evaluate_negative_control,evaluate_actual_documents
from research.v63.retrieval import AtomicUnit,Document,TokenCounter,b_documents,retrieve


def synthetic_bundle():
    rows,bank,scenarios=main_fixture.__wrapped__()
    main=evaluate(rows,bank,scenarios)
    assignments=[dict(scenario_id=s['scenario_id'],fund_id=FUNDS[i%4]) for i,s in enumerate(scenarios)]
    replacement=[dict(r,block='x-replacement') for a in assignments for r in rows if r['scenario']==a['scenario_id'] and r['fund_id']==a['fund_id'] and r['arm'] in ('R1','R3','C-context')]
    cf=evaluate_counterfactual(rows,replacement,bank,bank,assignments,frozen_model_sha256='synthetic-pinned',allow_synthetic=True)
    ids=[f'negative_control-{i+1:03d}' for i in range(8)]
    negative_bank={sid:{f'N{i:02d}':profile('F01') for i in range(1,5)} for sid in ids}
    negative=[dict(block='negative-control',scenario=sid,fund_id=label,arm=arm,replicate=rep,
                   trace=trace(label,arm,np.eye(12)[int(label[-2:])-1]))
              for sid,label,arm,rep in itertools.product(ids,tuple(f'N{i:02d}' for i in range(1,5)),('R1','R3','C-context'),(1,2))]
    nc=evaluate_negative_control(negative,negative_bank,ids,frozen_model_sha256='synthetic-pinned',allow_synthetic=True)
    profiles={module:{fid:profile(fid) for fid in FUNDS} for module in ('A','C')};actual=[]
    for module,fid,arm,rep in itertools.product(('A','C'),FUNDS,ARMS,(1,2)):
        tr=trace(fid,arm,profiles[module][fid]['h'])
        tr['stages'][-1]['raw_output']['evidence']=[dict(evidence_id='x',value='synthetic quoted fact',unit='text',date='2026-01-01')]
        actual.append(dict(block='actual-documents',scenario=module,fund_id=fid,arm=arm,replicate=rep,trace=tr))
    ac=evaluate_actual_documents(actual,profiles,frozen_model_sha256='synthetic-pinned',allow_synthetic=True)
    analyses={'B-main':main,'x-replacement':cf,'negative-control':nc,'C':ac}
    counter=TokenCounter('synthetic-word-counter',lambda text:len(text.split()),False)
    docs=b_documents('F01','synthetic-render-only',[0.01]*12,1.,'2026-01-01','Synthetic mandatory fact. Not empirical data.')
    gold=[e for d in docs for u in d.units for e in u.evidence_ids]
    retrieved=retrieve(docs,'F01','2026-03-31','B',counter,engineering=True,gold_ids=gold)
    prepared={p:{'cases':{'synthetic-case':{'retrieval':retrieved,'evidence_registry':{e:{} for e in gold}}}} for p in ('development-pilot','B-main','x-replacement','negative-control')}
    for phase,day in [('A','2026-03-01'),('C','2026-04-01')]:
        document=Document('synthetic-'+phase,'F01',day,phase,'official_text','SYNTHETIC TEST INPUT ONLY',
                          (AtomicUnit('Synthetic forecast expected return risk portfolio.',('synthetic-'+phase,)),))
        result=retrieve([document],'F01','2026-06-30' if phase=='C' else '2026-03-31',phase,counter,engineering=True)
        prepared[phase]={'cases':{'synthetic-case':{'retrieval':result,'evidence_registry':{}}}}
    summaries={p:{'trajectories':n,'planned_logical_stages':3*n,'terminal_counts':{'completed':n},'stage_status_counts':{'completed':3*n}} for p,n in report.COUNTS.items()}
    return analyses,prepared,summaries


@pytest.fixture(scope='module')
def rendered_inputs():return synthetic_bundle()


def file_backed_synthetic_ac(directory):
    """File-backed unit fixtures, explicitly marked fake; never real model data."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    profiles={module:{fid:profile(fid) for fid in FUNDS} for module in ('A','C')};rows=[]
    for module,fid,arm,rep in itertools.product(('A','C'),FUNDS,ARMS,(1,2)):
        tr=trace(fid,arm,profiles[module][fid]['h'])
        # This exercises the file-backed-source branch. The non-hex synthetic
        # model hash and explicit fixture flag cannot be a real pinned run.
        tr.update(engineering_only=False,synthetic_software_fixture_only=True)
        if module=='A' and fid in ('F01','F02') and arm=='R1' and rep==1:
            for stage in tr['stages'][:2]:
                stage['raw_output']['evidence']=[dict(evidence_id='x',value=9,unit='percent',date='2026-01-01')]
        path=directory/f'{module}_{fid}_{arm}_{rep}.json';path.write_text(json.dumps(tr),encoding='utf8')
        rows.append(dict(block='actual-documents',scenario=module,fund_id=fid,arm=arm,replicate=rep,
                         trace_path=str(path.resolve()),trace_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    catalog={'x':dict(fund_id='COMMON',period='A',publication_date='2026-01-01',value=3,unit='percent',date='2026-01-01')}
    return evaluate_actual_documents(rows,profiles,frozen_model_sha256='synthetic-pinned',allow_synthetic=True,source_catalog=catalog)


def render(inputs,shared=None):
    analyses,prepared,summaries=inputs
    costs={'confirmed_generation_requests':0,'known_original_generation_http_seconds':0.,'known_request_latency_count':0,'known_request_latency_mean':None,'known_request_latency_max':None}
    historical={'generation_requests':0,'recorded_request_seconds':0.,'scope':'Synthetic software verification only; no actual inference.'}
    supplement=report.render_supplement(analyses,prepared,costs,historical)
    if shared is not None:supplement+=report.shared_source_mismatch_html(shared)
    html=report.report_html(summaries,analyses,'SYNTHETIC-SOFTWARE-VERIFICATION-NOT-AN-EXPERIMENT',datetime.now(timezone.utc).isoformat(),supplement)
    banner='<div style="background:#ffd96a;color:#111;padding:24px;font-weight:bold">합성 소프트웨어 검증 전용 — 실제 실험 결과 아님. 실제 모델 호출 0회.</div>'
    return html.replace('<main>','<main>'+banner,1).replace('<title>','<title>합성 소프트웨어 검증 · ',1)


def test_real_evaluator_outputs_render_all_report_sections(rendered_inputs,tmp_path):
    analyses,prepared,summaries=rendered_inputs
    assert all(x['status']=='synthetic_verification_only' for x in analyses.values())
    assert len(analyses['x-replacement']['rows'])==360 and len(analyses['negative-control']['rows'])==288 and len(analyses['C']['rows'])==80
    ac=file_backed_synthetic_ac(tmp_path/'synthetic_sources')
    shared=report.shared_source_mismatch_candidates(ac,tmp_path)
    html=render(rendered_inputs,shared);(tmp_path/'synthetic_only_report.html').write_text(html,encoding='utf8')
    for text in ('기준과 식별 범위','개별 전망 교체 반응','완전 동일정보 음성대조','검색 회수와 원문량','원비중 기계 검증','사실·출처 검증 범위','실제 원요청 비용','실제 실험 결과 아님','공유된 원문 대조 불일치 후보'):
        assert text in html
    assert '동등성의 증거가 아닙니다' in html


def test_nonsignificance_never_becomes_policy_recommendation(rendered_inputs):
    rows=report.recommendation_rows(rendered_inputs[0]['B-main'])
    assert len(rows)==4 and all('권고 보류' in r[-1] for r in rows)


def test_failure_increase_withholds_even_if_joint_claim_rejects(rendered_inputs):
    main=deepcopy(rendered_inputs[0]['B-main'])
    main['inference']['claims']['H2'].update(reject=True,p_holm=.01,p=.01)
    assert '조건 충족' in report.recommendation_rows(main)[0][-1]
    changed=next(row for row in main['trajectory_diagnostics'] if row['identity'][2]=='R1')
    changed.update(raw_valid=False,fallback=True)
    assert '증가: 권고 보류' in report.recommendation_rows(main)[0][-1]


def test_timing_direction_tie_withholds_even_with_significant_flags(rendered_inputs):
    main=deepcopy(rendered_inputs[0]['B-main']);claim=main['inference']['claims']['H3_R1_R2']
    claim.update(reject=True,p_holm=.03,p=.02)
    claim['directions']['R1_better']['p']=.01;claim['directions']['R2_better']['p']=.01
    assert '권고 보류' in report.recommendation_rows(main)[1][-1]


def test_original_costs_do_not_count_replay_trace_or_invent_missing_usage(tmp_path):
    def save(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value),encoding='utf8')
    save(tmp_path/'http/attempt_000001/attempt_receipt.json',{'generation_requests':1})
    save(tmp_path/'http/attempt_000001/generation.receipt.json',{'elapsed_seconds':2.5})
    save(tmp_path/'http/attempt_000001/generation.response.bin',{'prompt_eval_count':10,'eval_count':3})
    save(tmp_path/'http/attempt_000002/runner_request.bin',{'unknown_dispatch':True})
    save(tmp_path/'recovery_001/trajectory/trace.json',{'actual_model_calls':99,'usage':{'input_tokens':999}})
    costs=report.collect_original_costs(tmp_path)
    assert costs['confirmed_generation_requests']==1 and costs['uncertain_generation_dispatches']==1
    assert costs['known_original_generation_http_seconds']==2.5 and costs['prompt_eval_count']==10 and costs['eval_count']==3
    assert costs['requests_missing_timing']==1 and costs['prompt_eval_count_missing_requests']==1


def test_shared_mismatch_uses_original_payload_and_does_not_claim_semantic_error(tmp_path):
    ac=file_backed_synthetic_ac(tmp_path/'sources');shared=report.shared_source_mismatch_candidates(ac,tmp_path)
    assert ac['status']=='synthetic_verification_only'
    assert shared['repeated_candidate_patterns']==1 and shared['joined_candidate_records']==4
    assert shared['patterns'][0]['across_funds'] and shared['patterns'][0]['within_trajectory_stage_persistence']
    assert shared['semantic_error_count'] is None and shared['economic_error_count'] is None
    changed=next(r for r in ac['rows'] if r['identity']==['A','F02','R1',1]);path=Path(changed['source']['path'])
    raw=json.loads(path.read_text())
    for stage in raw['stages'][:2]:stage['raw_output']['evidence'][0]['value']=11
    path.write_text(json.dumps(raw),encoding='utf8');changed['source']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    different=report.shared_source_mismatch_candidates(ac,tmp_path)
    assert different['repeated_candidate_patterns']==2 and all(not p['across_funds'] for p in different['patterns'])


def test_shared_mismatch_rejects_changed_original_trace(tmp_path):
    ac=file_backed_synthetic_ac(tmp_path/'sources');path=Path(ac['rows'][0]['source']['path']);path.write_text('{}')
    with pytest.raises(ValueError,match='hash drift'):report.shared_source_mismatch_candidates(ac,tmp_path)


def test_shared_mismatch_does_not_merge_A_and_C_source_versions(tmp_path):
    ac=file_backed_synthetic_ac(tmp_path/'sources')
    first=deepcopy(next(f for f in ac['fact_checks'] if f['identity']==['A','F01','R1',1] and f['stage']==1))
    second=deepcopy(first);second['identity']=['C','F01','R1',1];second['correct_period']=False
    ac['fact_checks']=[first,second]
    row=next(r for r in ac['rows'] if r['identity']==second['identity']);path=Path(row['source']['path']);raw=json.loads(path.read_text())
    raw['stages'][0]['raw_output']['evidence']=[dict(evidence_id='x',value=9,unit='percent',date='2026-01-01')]
    path.write_text(json.dumps(raw),encoding='utf8');row['source']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    shared=report.shared_source_mismatch_candidates(ac,tmp_path)
    assert shared['joined_candidate_records']==2 and shared['repeated_candidate_patterns']==0


def write_verification(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True);inputs=synthetic_bundle()
    ac=file_backed_synthetic_ac(directory/'synthetic_file_backed_sources');shared=report.shared_source_mismatch_candidates(ac,directory)
    html=render(inputs,shared)
    target=directory/'synthetic_only_report.html'
    if target.exists():raise ValueError('Preserve existing rendering evidence; choose a new directory')
    target.write_text(html,encoding='utf8')
    receipt={'status':'synthetic_software_render_verification_only','actual_model_calls':0,'actual_approval_issued':False,'canonical_completion_files_changed':False,
        'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'analysis_statuses':{k:v['status'] for k,v in inputs[0].items()},
        'rows':{'main':2400,'replacement':360,'negative_pairs':288,'actual_document':80},
        'evaluator':'Actual evaluate_main/counterfactual/negative_control/actual_documents with allow_synthetic=True; source traces are explicit engineering fixtures.',
        'retrieval':'Actual retrieve() with explicit engineering-only synthetic word counter, never represented as native-model token measurements.',
        'shared_source_test':'Actual evaluate_actual_documents and actual shared_source_mismatch_candidates using explicit file-backed synthetic fixtures (not empirical model responses).',
        'shared_source_patterns':shared['repeated_candidate_patterns'],
        'report':{'path':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()},
        'code':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(report.__file__)]}}
    (directory/'verification_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();write_verification(args.output)
