"""Render a final report only from complete, hash-checked real campaign records."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import shutil
import tempfile

from research.v63.record_continuation_snapshot import digest, read, write, main as snapshot
from research.v63.build_continuation_report import main as render_continuation,verify_completion_commit

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/v63_20261027'
COUNTS={'development-pilot':240,'B-main':2400,'x-replacement':360,'negative-control':192,'A':40,'C':40}
EXPECTED_ANALYSIS={'B-main':'completed_confirmatory_analysis','x-replacement':'completed_secondary_analysis',
                   'negative-control':'completed_secondary_analysis','C':'completed_actual_document_audit'}
TERMINAL={'completed','model_output_failure','operational_failure'}
CLAIM_NAMES={'H1':'FULL 정책의 충분정보 기준 대비 수축·손실','H2':'R0 대비 R1의 자료 제공 효과',
             'H3_R1_R2':'1단계·2단계 자료 제공 시점 비교','H3_R1_R3':'1단계·3단계 자료 제공 시점 비교',
             'H3_R2_R3':'2단계·3단계 자료 제공 시점 비교'}


def verify_main_completion_proofs(root,config,approval,approval_sha256,output_root,run_id):
    """Read-only counterpart of guardian promotion; never changes a freeze flag."""
    from research.v63 import longrun_guardian as g
    from research.v63.pilot_precision import _hash_object
    root=Path(root).resolve();directory=Path(output_root)/'guardian'/run_id
    frozen_path=g.resolve(root,config['runtime_freeze_path']);frozen=g.read(frozen_path)
    g.require(frozen.get('main_model_frozen') is True,'Main runtime was never frozen')
    g.require(g.freeze_hash(frozen)==approval['runtime_freeze_without_main_flag_sha256'],'Approved runtime changed')
    precision=directory/'pilot_precision_report.json';pilot=g.read(precision)
    g.require(pilot.get('status')=='development_precision_descriptive_ready' and pilot.get('ready_for_precision_report') is True and pilot.get('synthetic_verification') is False,'Finalization requires the actual ready pilot precision report')
    g.require(pilot.get('main_N_fixed')==60 and pilot.get('independent_scenarios')==12 and pilot.get('expected_trajectories')==240 and not pilot.get('missing') and not pilot.get('nonterminal'),'Pilot report cardinality differs')
    g.require(pilot.get('frozen_model_sha256')==approval['model_sha256'],'Pilot uses another model')
    inputs=g.pilot_inputs(root,config,run_id);input_path=precision.with_suffix('.inputs.json');proof=g.read(input_path)
    g.require(proof.get('runtime_identity_sha256')==run_id and proof.get('report')==g.file_ref(root,precision) and proof.get('inputs')==inputs,'Pilot same-run input proof differs')
    scenarios=g.read(g.resolve(root,inputs['scenarios']['path']));bank=g.read(g.resolve(root,inputs['reference_bank']['path']))
    g.require(pilot.get('input_fingerprint')==_hash_object([[s['scenario_id'] for s in scenarios],[s['r'] for s in scenarios],bank]),'Pilot references/scenarios changed')
    g.require(pilot.get('runtime_metadata')==g.read(g.resolve(root,inputs['runtime_metadata']['path'])),'Pilot runtime metadata changed')
    g.require(pilot.get('provenance')=={n:g.digest(root/'research/v63'/n) for n in ['pilot_precision.py','evaluate.py','numerics.py','statistics.py']},'Pilot evaluator provenance differs')
    transition_path=directory/'main_freeze_transition.json';transition=g.read(transition_path)
    g.require(transition.get('approval_sha256')==approval_sha256 and transition.get('runtime_identity_sha256')==run_id and transition.get('after_sha256')==g.digest(frozen_path) and transition.get('pilot_report_sha256')==g.digest(precision) and transition.get('changed_fields')==['main_model_frozen'],'Main freeze transition is missing or differs')
    review_path=g.verify_ref(root,transition.get('resource_review'));review=g.read(review_path)
    g.require(review.get('approval_sha256')==approval_sha256 and review.get('runtime_identity_sha256')==run_id and set(review.get('phase_forecasts',{}))==set(g.PHASES[1:]),'All-phase approved resource review is missing or changed')
    development_measurement=g.file_ref(root,Path(output_root)/'phases'/run_id/'development-pilot'/'measurements.json')
    g.require(transition.get('development_measurements')==development_measurement and review.get('development_measurements')==development_measurement,'Main review uses another development measurement')
    g.require(transition.get('effect_or_pvalue_read_for_decision') is False and review.get('effect_or_pvalue_read_for_decision') is False,'Effect/p-value selection is not permitted')
    return {'pilot_precision':g.file_ref(root,precision),'pilot_inputs':g.file_ref(root,input_path),
            'main_freeze_transition':g.file_ref(root,transition_path),'main_resource_review':g.file_ref(root,review_path)}


def atomic_bytes(path,content):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    pending=path.with_name(path.name+f'.writing.{os.getpid()}')
    with pending.open('wb') as handle:
        handle.write(content);handle.flush();os.fsync(handle.fileno())
    os.replace(pending,path)


def publish_validated_bundle(output_root,run_id,results,html,summaries):
    """Commit immutable results before aliases; roll back handled publish errors.

    A hard kill may leave a mixture of old/new aliases. Every new completed
    alias points to an already committed, hash-verifiable complete bundle.
    No completion label depends on an absent or partly written commit.
    """
    from research.v63.longrun_guardian import file_ref,require
    parent=Path(output_root)/'finalization'/run_id;parent.mkdir(parents=True,exist_ok=True)
    require(ROOT.resolve() in parent.resolve().parents,'Finalization bundle must remain in the workspace')
    bundle=Path(tempfile.mkdtemp(prefix='validated_',dir=parent))
    report_path=bundle/'report.html';results_path=bundle/'results.json'
    atomic_bytes(report_path,html.encode('utf-8'));write(results_path,results)
    staged=read(results_path,{})
    require(staged.get('status')=='completed_real_experiments' and staged.get('run_id')==run_id and staged.get('terminal_trajectories')==3272 and staged.get('planned_logical_stages')==9816,'Staged results are not the same complete run')
    commit_path=bundle/'commit.json'
    commit={'status':'validated_complete_run','committed_at_utc':datetime.now(timezone.utc).isoformat(),
            'run_id':run_id,'terminal_trajectories':3272,'planned_logical_stages':9816,
            'resource_approval':results['resource_approval'],'completion_proofs':results['completion_proofs'],
            'artifacts':{'report':file_ref(ROOT,report_path),'results':file_ref(ROOT,results_path)}}
    # This is the final write defining the immutable scientific result bundle.
    write(commit_path,commit);commit_ref=file_ref(ROOT,commit_path)
    verify_completion_commit({'selected_run_id':run_id,'finalization_commit':commit_ref},ROOT)
    target=ROOT/'실험참고자료_20261027/03_최종실험결과_20261027.html'
    aliases=[target,DATA/'final_results.json',DATA/'continuation/live_status.json',
             ROOT/'실험참고자료_20261027/02_계속실행기록_20261027.html',DATA/'execution_status.json',DATA/'artifact_manifest.json']
    backup_dir=bundle/'prior_aliases';backup_dir.mkdir();backups=[]
    for index,path in enumerate(aliases):
        prior=backup_dir/str(index)
        if path.is_file():shutil.copyfile(path,prior);backups.append((path,prior))
        else:backups.append((path,None))
    publication=bundle/'publication_receipt.json'
    write(publication,{'status':'publishing_validated_bundle','commit':commit_ref})
    try:
        atomic_bytes(target,report_path.read_bytes())
        published={**results,'final_report':file_ref(ROOT,target),'finalization_commit':commit_ref,
                   'immutable_results':file_ref(ROOT,results_path)}
        write(DATA/'final_results.json',published)
        live=read(DATA/'continuation/live_status.json',{})
        live.update(all_experiments_completed=True,observed_at_utc=results['recorded_at_utc'],status_ko='선택한 동결 설정의 3,272개 업무 궤적 처리와 최종 분석을 완료했습니다. C의 자료 범위 한계는 최종 보고서에 명시했습니다.',
                    final_report=str(target),selected_run_id=run_id,finalization_commit=commit_ref,
                    events_ko=['선택한 동일 실행 설정의 개발·본실험·전망 교체·음성대조·A/C 전체 업무 궤적과 분석을 검증했습니다.',
                               '이전 후보의 실패·중단과 선택한 실험의 최종 표본을 분리했고 누적 원요청은 모두 보존했습니다.',
                               '9,816개는 계획된 논리 단계이며, 실제 호출 수와 선행 실패 뒤 미호출 단계는 최종 결과에서 구분합니다.',
                               'C의 펀드별 신규 전망 미확보, 현재 공식 SIC의 회고적 분류 및 사람 감사 완료 가정을 명시했습니다.'],
                    model_execution=dict(selected_run_id=run_id,latest_progress=read(Path(output_root)/'progress.json',{}),
                                         phase_completion=summaries,past_remote_abort='continuation/deployment/remote_capacity_abort.json'))
        write(DATA/'continuation/live_status.json',live)
        render_continuation()
        snapshot(status_override=dict(status='completed_real_experiments',all_experiments_completed=True,
            main_started=True,successful_main_trajectories=summaries['B-main']['terminal_counts'].get('completed',0),
            terminal_trajectories=3272,logical_slots_accounted=9816,selected_run_id=run_id,remaining=[],
            finalization_commit=commit_ref,current_report='../../실험참고자료_20261027/03_최종실험결과_20261027.html'))
        verify_completion_commit(read(DATA/'execution_status.json',{}),ROOT)
        verify_completion_commit(read(DATA/'continuation/live_status.json',{}),ROOT)
        write(publication,{'status':'published_complete_aliases','commit':commit_ref,
                           'published_at_utc':datetime.now(timezone.utc).isoformat(),
                           'aliases':[file_ref(ROOT,path) for path in aliases]})
        return published
    except BaseException as exc:
        rollback_errors=[]
        for path,prior in backups:
            try:
                if prior is not None:atomic_bytes(path,prior.read_bytes())
                elif path.is_file():
                    require(ROOT.resolve() in path.resolve().parents,'Refusing rollback outside workspace')
                    path.unlink()
            except BaseException as rollback:rollback_errors.append({'path':str(path),'error':str(rollback)})
        write(publication,{'status':'publication_failed_prior_aliases_restored' if not rollback_errors else 'publication_failed_rollback_incomplete',
                           'commit':commit_ref,'error_type':type(exc).__name__,'error':str(exc),'rollback_errors':rollback_errors})
        raise


def verified_results(output_root,run_id):
    from research.v63.longrun_guardian import object_hash
    from research.v63.campaign_control import verify_frozen_artifacts
    from research.v63.evaluate import code_provenance,_hash_object
    phase_root=Path(output_root)/'phases'/run_id
    summaries={};analyses={};receipts=[];traces=[]
    for phase,count in COUNTS.items():
        directory=phase_root/phase
        measures=read(directory/'measurements.json',{})
        records=read(directory/'records.json',[])
        if (measures.get('status')!='completed' or measures.get('terminal_trajectories')!=count
                or measures.get('runtime_identity_sha256')!=run_id or len(records)!=count):
            raise ValueError('Incomplete or changed real phase: '+phase)
        if phase=='development-pilot' and measures.get('full_history_observed') is not True:
            raise ValueError('No actual three-stage FULL history in the selected development runtime')
        identity=read(directory/'runtime_identity.json',{})
        if object_hash(identity)!=run_id:
            raise ValueError('Phase identity differs from its frozen run: '+phase)
        prepared=read(directory/'prepared_inputs.json',{})
        cases=prepared.get('cases',{})
        frozen=read(directory/'frozen_runtime.json',{})
        if frozen.get('execution_phase')!=phase:
            raise ValueError('Wrong frozen phase: '+phase)
        required_inputs={str(p.resolve()) for p in [directory/'prepared_inputs.json',
            directory/'evaluator_only/reference_bank.json',directory/'evaluator_only/reference_bank_receipt.json',
            directory/'evaluator_only/frozen_scenarios.json',directory/'evaluator_only/hidden_truth.json',
            Path(output_root)/'runs'/run_id/'source_input_manifest.json']}
        frozen_refs=frozen.get('artifacts',[])
        if not required_inputs<={str((ROOT/r['path']).resolve()) for r in frozen_refs}:
            raise ValueError('Phase frozen input manifest is incomplete: '+phase)
        verify_frozen_artifacts(ROOT,directory/'frozen_runtime.json')
        receipts.extend(dict(path=str((ROOT/r['path']).resolve()),sha256=r['sha256']) for r in frozen_refs)
        for key,value in identity.items():
            if key in frozen and frozen[key]!=value:
                raise ValueError('Phase runtime setting drift: '+phase+'/'+key)
        phase_counts=Counter();stages=Counter();seen=set()
        for row in records:
            identity=tuple(row[k] for k in ('block','scenario','fund_id','arm','replicate'))
            if identity in seen:raise ValueError('Duplicate record: '+repr(identity))
            seen.add(identity)
            case_id=row['scenario']+'__'+row['fund_id']
            if case_id not in cases or object_hash(cases[case_id])!=row.get('input_sha256'):
                raise ValueError('Recorded input differs from prepared case: '+repr(identity))
            trace_path=Path(row['trace_path'])
            if digest(trace_path)!=row['trace_sha256']:raise ValueError('Changed raw trace: '+str(trace_path))
            trace=read(trace_path)
            if trace.get('engineering_only') or trace.get('status') not in TERMINAL:
                raise ValueError('Non-experimental/nonterminal record: '+str(trace_path))
            phase_counts[trace['status']]+=1
            stages.update(s.get('status','unknown') for s in trace.get('stages',[]))
            traces.append(trace)
        summaries[phase]=dict(trajectories=count,planned_logical_stages=3*count,
                              terminal_counts=dict(phase_counts),stage_status_counts=dict(stages))
        for name in ('measurements.json','records.json','frozen_runtime.json','runtime_identity.json'):
            p=directory/name
            receipts.append(dict(path=str(p),sha256=digest(p)))
        if phase in EXPECTED_ANALYSIS:
            analysis=read(directory/'analysis.json',{})
            if analysis.get('status')!=EXPECTED_ANALYSIS[phase] or analysis.get('missing') or analysis.get('nonterminal'):
                raise ValueError('Required actual analysis incomplete: '+phase)
            if analysis.get('source_hashes')!=code_provenance():
                raise ValueError('Analysis evaluator provenance differs: '+phase)
            if phase=='B-main':
                scenarios=read(directory/'evaluator_only/frozen_scenarios.json',[])
                bank=read(directory/'evaluator_only/reference_bank.json',{})
                if (analysis.get('frozen_model_sha256')!=frozen.get('model_sha256') or
                    analysis.get('input_fingerprint')!=_hash_object([[s['scenario_id'] for s in scenarios],[s['r'] for s in scenarios],bank])):
                    raise ValueError('Main analysis model/reference inputs differ')
            if phase=='x-replacement' and (analysis.get('expected')!=360 or len(analysis.get('rows',[]))!=360):
                raise ValueError('Replacement analysis must retain all 360 trajectories')
            if phase=='negative-control' and (analysis.get('expected')!=192 or len(analysis.get('rows',[]))!=288):
                raise ValueError('Negative analysis requires 192 trajectories and 288 within-replicate pair rows')
            analyses[phase]=analysis
            receipts.append(dict(path=str(directory/'analysis.json'),sha256=digest(directory/'analysis.json')))
    main=analyses['B-main']
    if main.get('trajectories')!=2400 or main.get('independent_scenarios')!=60 or set(main.get('inference',{}).get('claims',{}))!=set(CLAIM_NAMES):
        raise ValueError('Original sample or five-claim family is incomplete')
    if len(analyses['C'].get('rows',[]))!=80:
        raise ValueError('Joint A/C audit must contain all 80 trajectories')
    for phases,diagnostics in [(('B-main',),main.get('trajectory_diagnostics',[])),(('A','C'),analyses['C']['rows'])]:
        expected={tuple(r[k] for k in ('scenario','fund_id','arm','replicate')):r
                  for phase in phases for r in read(phase_root/phase/'records.json',[])}
        observed={tuple(row['identity']):row for row in diagnostics}
        if len(diagnostics)!=len(expected) or set(observed)!=set(expected):
            raise ValueError('Analysis trace identities do not match phase records: '+repr(phases))
        for key,row in expected.items():
            source=observed[key].get('source',{})
            if source.get('synthetic') is not False or source.get('sha256')!=row['trace_sha256'] or Path(source.get('path','')).resolve()!=Path(row['trace_path']).resolve():
                raise ValueError('Analysis was not computed from the preserved real trace: '+repr(key))
    receipts=list({(r['path'],r['sha256']):r for r in receipts}.values())
    return summaries,analyses,receipts,traces


def number(value):
    return '미산출' if value is None else f'{value:.6g}'


"""Report-only summaries. Inputs must already pass finalizer completion gates.
No model calls, new hypothesis tests, source edits, or output-selected exclusions.
"""
from collections import defaultdict,Counter
from html import escape
from pathlib import Path
import json,math

def fmt(x):
    if x is None:return '미산출'
    if isinstance(x,float):return f'{x:.6g}'
    return str(x)

def table(title,headers,rows,note=''):
    head=''.join('<th>'+escape(str(x))+'</th>' for x in headers)
    body=''.join('<tr>'+''.join('<td>'+escape(fmt(x))+'</td>' for x in row)+'</tr>' for row in rows)
    return '<h2>'+escape(title)+'</h2><div class="scroll"><table><thead><tr>'+head+'</tr></thead><tbody>'+body+'</tbody></table></div><p class="note">'+escape(note)+'</p>'

def avg(values):
    values=list(values);return sum(values)/len(values) if values else None

def scenario_avg(rows,key,function):
    grouped=defaultdict(list)
    for row in rows:grouped[key(row)].append(function(row))
    return avg(avg(values) for values in grouped.values())

def summary_cell(summary):
    return f"{fmt(summary['mean'])} [{fmt(summary['lower95'])}, {fmt(summary['upper95'])}]"

def recommendation_rows(main):
    """Observed rate criterion, not a failure-rate equivalence test."""
    diagnostics=main['trajectory_diagnostics'];claims=main['inference']['claims'];rates={}
    for arm in ('R0','R1','R2','R3','C-context'):
        rows=[r for r in diagnostics if r['identity'][2]==arm]
        if len(rows)!=480 or any(type(r.get('raw_valid')) is not bool or type(r.get('fallback')) is not bool for r in rows):
            raise ValueError('Recommendation needs every raw-valid/fallback diagnostic')
        rates[arm]={'n':480,'raw_failure':sum(not r['raw_valid'] for r in rows)/480,
                    'fallback':sum(r['fallback'] for r in rows)/480}
    out=[]
    for claim_name,a,b in [('H2','R1','R0'),('H3_R1_R2','R1','R2'),('H3_R1_R3','R1','R3'),('H3_R2_R3','R2','R3')]:
        claim=claims[claim_name];candidate,baseline=a,b;direction_ok=True
        if claim_name!='H2':
            directions=claim['directions'];pa=directions[a+'_better']['p'];pb=directions[b+'_better']['p']
            direction_ok=pa!=pb
            if pb<pa:candidate,baseline=b,a
            expected=min(1.,2*min(pa,pb))
            if not math.isclose(expected,claim['p'],rel_tol=0,abs_tol=1e-15):raise ValueError('H3 selection adjustment differs')
        rc,rb=rates[candidate],rates[baseline]
        increases=rc['raw_failure']>rb['raw_failure'] or rc['fallback']>rb['fallback']
        passed=claim['reject'] is True and claim['p_holm']<=.05 and direction_ok
        reason=('원출력 실패율 또는 h 유지율 증가: 권고 보류' if increases else
                '해당 비교 범위의 사전 권고 조건 충족' if passed else '결합검정/최종보정/방향 조건 미충족: 권고 보류')
        out.append([claim_name,candidate+' vs '+baseline,claim['p_holm'],
                    f"{rc['raw_failure']:.2%} / {rb['raw_failure']:.2%}",
                    f"{rc['fallback']:.2%} / {rb['fallback']:.2%}",reason])
    return out

def main_diagnostics_html(main):
    keys=['A_full','G_available','R_available','information_set_distance_component',
          'unidentified_reference_pair_fraction_available']
    rows=[[arm]+[summary_cell(values[k]) for k in keys] for arm,values in main['scenario_summaries'].items()]
    result=table('기준과 식별 범위',['군','평균 절대수축 |G|','공개정보 기준 G','공개정보 기준 R','정보집합 차이 성분','양의 기준거리 미식별 비율'],rows,
        'A_full은 쌍별 절댓값 후 평균이다. 정보집합 성분은 부호가 있으며 항상 양수이지 않다. fallback 기여는 전체 쌍/펀드 분모의 기여이고 조건부 평균이 아니다. 유효 원출력 진단을 주효과로 대체하지 않는다.')
    contribution_keys=['fallback_pair_fraction','G_full_fallback_pair_contribution','G_full_valid_pair_contribution','R_full_fallback_contribution','R_full_valid_contribution']
    result+=table('유효 원출력과 보유 유지 대체의 기여',['군','대체 포함 쌍 비율','대체 포함 G 기여','유효 원출력 G 기여','대체 R 기여','유효 원출력 R 기여'],
        [[arm]+[summary_cell(values[k]) for k in contribution_keys] for arm,values in main['scenario_summaries'].items()],
        '전체 쌍/펀드 분모를 사용하는 가산 기여이다. 유효한 출력만으로 주효과를 다시 계산하거나 대체에서 생긴 수축을 직접 모델 전략으로 해석하지 않는다.')
    result+=table('결합검정과 별도의 정책 권고 조건',
        ['주장','검토 방향','Holm p','원출력 실패율 후보/비교','h 유지율 후보/비교','판정'],recommendation_rows(main),
        '각 군 480개 궤적을 모두 포함한다. 관측 실패율·h 유지율 중 하나라도 증가하면 권고를 보류한다. 비유의성이나 관측 비증가를 동등성으로 해석하지 않는다. H1은 권고 검정이 아니며, fallback에서 생긴 수축은 직접 모델 전략으로 귀속하지 않는다.')
    untestable=[]
    for name,claim in main['inference']['claims'].items():
        tests=claim.get('directions',{'joint':claim})
        for direction,test in tests.items():
            for component,value in test.get('components',{}).items():
                if value.get('testable') is False:untestable.append([name,direction,component,value.get('reason')])
    result+=table('검정 불가능 성분',['주장','방향','성분','이유'],untestable,
        '빈 표는 저장된 성분 중 검정 불가능 표식이 없다는 뜻이다. p=1의 퇴화 표본을 효과 없음으로 해석하지 않는다.')
    return result

def secondary_html(analyses):
    cf=analyses['x-replacement'];nc=analyses['negative-control'];rows=[]
    for arm,s in cf['scenario_summaries'].items():
        part=[r for r in cf['rows'] if r['identity'][2]==arm]
        mean=lambda function:scenario_avg(part,lambda r:r['identity'][0],function)
        ci=s.get('bootstrap95');ci_text='미산출' if ci is None else f"[{fmt(ci['lower'])}, {fmt(ci['upper'])}]"
        rows.append([arm,s['independent_units'],s['mean'],ci_text,
            mean(lambda r:r['response_error_interval'][0]),mean(lambda r:r['response_error_interval'][1]),
            mean(lambda r:r['actual_change_tv']),mean(lambda r:r['reference_change_tv']),
            sum(r['zero_reference_change'] for r in part),sum(r['fallback_a'] or r['fallback_b'] for r in part),
            sum(r['both_raw_valid'] for r in part),sum(not r['retrieved_logical_ids_unchanged'] for r in part),len(part)])
    result=table('개별 전망 교체 반응',['군','독립 N','반응오차 평균','개별95%CI','수치하한 평균','수치상한 평균',
        '실제변화TV','기준변화TV','기준변화0','fallback 개입','양쪽 원출력 유효','회수ID 집합 변경','반복 포함 짝수'],rows,
        '60개 시나리오 안에서 두 반복을 먼저 평균한다. 기준 변화가 0인 사례도 남긴다. 더 큰 변화가 개선은 아니다. 수치 경계 평균과 표본 CI는 다르다. 회수 ID가 달라진 경우 검색을 포함한 전체 경로 반응이다. 사전 주검정 가족에 새 p값을 추가하지 않는다.')
    rows=[]
    for arm,s in nc['scenario_summaries'].items():
        part=[r for r in nc['rows'] if r['arm']==arm]
        lower=scenario_avg(part,lambda r:r['scenario'],lambda r:r['mean_full_regret_interval'][0])
        upper=scenario_avg(part,lambda r:r['scenario'],lambda r:r['mean_full_regret_interval'][1])
        rows.append([arm,s['independent_units']]+[s['means'][k] for k in ('D','G','E','A','mean_full_regret')]+[
            lower,upper,sum(r['fallback_involved'] for r in part),len(part)])
    return result+table('완전 동일정보 음성대조',['군','독립 N','D','G','E','A','후회손실','손실하한 평균','손실상한 평균','fallback 쌍','반복 포함 쌍수'],rows,
        '독립 단위는 8개 시나리오다. 6쌍·2반복을 독립 표본으로 세지 않는다. Dstar=0, G=-D이며 D는 라벨/생성 변동의 크기다. 차이 자체를 경제적 오류로 부르지 않고 손실·수치 불확실성을 함께 해석한다. 현재 산출물에는 음성대조 표본 CI가 없다.')

def retrieval_html(prepared_by_phase):
    rows=[]
    for phase,package in prepared_by_phase.items():
        cases=list(package['cases'].values());ds=[c['retrieval']['diagnostics_evaluator_only'] for c in cases]
        valid=[d for d in ds if d['gold_recall_at_4'] is not None];den=sum(d['gold_unit_count'] for d in valid)
        num=sum(d['recovered_gold_count'] for d in valid)
        numeric_complete=sum(bool(c.get('evidence_registry')) and set(c['evidence_registry'])<=set(c['retrieval']['packet']['exposed_evidence_ids']) for c in cases)
        rows.append([phase,len(cases),avg(d['gold_recall_at_4'] for d in valid),f'{num}/{den}',
            len(ds)-len(valid),avg(c['retrieval']['packet']['tokens'] for c in cases),max(c['retrieval']['packet']['tokens'] for c in cases),
            max(c['retrieval']['full']['tokens'] for c in cases),sum(d['same_atomic_content_as_full'] for d in ds),numeric_complete])
    return table('검색 회수와 원문량',['모듈','고유 입력','macro recall@4','회수/gold','gold 미정','packet 평균','packet 최대','FULL 최대','원자내용 FULL과 동일','B 수치12개 전부회수'],rows,
        '입력별 한 번만 집계하며 군·반복으로 분모를 늘리지 않는다. B의 수치관측12개 전부회수와 FULL 원문 전체동일은 다르다. 수치정보가 같으면 검색 대 FULL의 정보 차이는 식별되지 않을 수 있다. A/C gold는 사전 사실 부분집합이며 의미적 충분성 점수가 아니다.')

def raw_and_source_html(main,ac):
    diagnostics=main['trajectory_diagnostics']+ac['rows'];by_stage=defaultdict(list);statuses=Counter();reasons=Counter()
    for d in diagnostics:
        for stage in d['stage_diagnostics']:
            statuses[(stage['stage'],stage['status'])]+=1
            if stage.get('reason'):reasons[(stage['stage'],stage['reason'])]+=1
            if stage.get('raw_validation') is not None:by_stage[stage['stage']].append(stage['raw_validation'])
    rows=[]
    for stage,vs in sorted(by_stage.items()):
        residuals=[v['budget_residual'] for v in vs if v.get('budget_residual') is not None]
        rows.append([stage,len(vs),len(residuals),min(residuals) if residuals else None,max(residuals) if residuals else None,
            max(map(abs,residuals)) if residuals else None]+[sum(k in v['failures'] for v in vs) for k in ('budget','lower_bound','risk_cap','explicit_constraint')])
    result=table('원비중 기계 검증: B 주분석과 A/C',['단계','실제 원벡터','잔차 산출','예산잔차 최소','최대','최대절댓값','예산','음수','위험상한','명시제약'],rows,
        'h 대체값을 원비중으로 검사하지 않는다. 벡터 미출력/형상오류에서 잔차가 없으면 NA이며 0으로 채우지 않는다. 다른 블록과 운송 오류는 원 trace.stages/calls에서도 별도 집계한다.')
    result+=table('단계 상태와 실패 이유',['종류','단계','상태/이유','횟수'],
        [['status',s,k,n] for (s,k),n in sorted(statuses.items())]+[['reason',s,k,n] for (s,k),n in sorted(reasons.items())])
    facts=ac['fact_checks'];matches=[f for f in facts if f.get('source_fact_scored') is True]
    counts=[['전체 인용 기록',len(facts)],['독립 출처 목록 대조',len(matches)],['numeric fact 대조',sum(f.get('numeric_fact_scored') is True for f in facts)],
        ['미노출 근거 ID',sum(f.get('exposed') is False for f in facts)],['literal value/unit/date 불일치 후보',sum(any(v is False for v in f.get('literal_field_matches',{}).values()) for f in matches)],
        ['잘못된 펀드/기간/게시일',sum(any(f.get(k) is False for k in ('correct_fund_attribution','correct_period','publication_within_cutoff')) for f in matches)],
        ['의미검토 필요 표식',sum(f.get('requires_semantic_review') is True for f in facts)],['gold 없는 미채점',sum(f.get('source_fact_scored') is not True for f in facts)]]
    return result+table('사실·출처 검증 범위',['항목','수/분모는 전체 인용 기록'],counts,
        '의미검토 표식은 확정 오류수가 아니다. 아래 반복 후보 표는 원 trace에서 동일 ID와 동일 value/unit/date의 기계적 불일치 후보를 연결한다. 의미적 공유 오류 확정 수는 미산출이며 0이 아니다. 사용자 사람감사 가정은 실제 의미채점 수행 증거가 아니다.')

def collect_original_costs(run_root):
    """Original HTTP attempts only; never sum replay trace usage a second time."""
    def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
    counts=Counter();seconds=[]
    for folder in sorted(Path(run_root).rglob('attempt_*')):
        if not folder.is_dir():continue
        receipt=folder/'attempt_receipt.json'
        if receipt.is_file():
            count=read(receipt)['generation_requests']
            if type(count) is not int or count not in (0,1):raise ValueError('Invalid original attempt receipt')
            counts['confirmed_generation_requests']+=count
        elif (folder/'runner_request.bin').is_file():count=1;counts['uncertain_generation_dispatches']+=1
        else:continue
        if not count:continue
        timing=folder/'generation.receipt.json'
        if timing.is_file():seconds.append(read(timing)['elapsed_seconds'])
        else:counts['requests_missing_timing']+=1
        try:response=read(folder/'generation.response.bin')
        except (OSError,ValueError):response={}
        for key in ('prompt_eval_count','eval_count'):
            value=response.get(key)
            if type(value) is int and value>=0:counts[key]+=value
            else:counts[key+'_missing_requests']+=1
    return {**counts,'known_original_generation_http_seconds':sum(seconds),
        'known_request_latency_count':len(seconds),'known_request_latency_mean':avg(seconds),
        'known_request_latency_max':max(seconds) if seconds else None}

def costs_html(costs,historical_costs):
    labels={'confirmed_generation_requests':'원영수증으로 확인한 생성 시도','uncertain_generation_dispatches':'최종 영수증 없는 불확실한 전송',
        'requests_missing_timing':'HTTP 시간 미관측 요청','prompt_eval_count':'관측 입력 토큰 합','eval_count':'관측 출력 토큰 합',
        'prompt_eval_count_missing_requests':'입력 토큰 미관측 요청','eval_count_missing_requests':'출력 토큰 미관측 요청',
        'known_original_generation_http_seconds':'관측 HTTP 시간 합(초)','known_request_latency_count':'시간 관측 요청 수',
        'known_request_latency_mean':'관측 요청 평균 시간(초)','known_request_latency_max':'관측 요청 최대 시간(초)'}
    rows=[[labels.get(key,key),value] for key,value in costs.items()]
    rows.extend([['이전 원요청(승인 원장 범위)',historical_costs['generation_requests']],
                 ['이전 원요청 기록 지연(초)',historical_costs['recorded_request_seconds']],
                 ['이전 원장 범위',historical_costs['scope']]])
    return table('실제 원요청 비용',['원장 항목','값'],rows,
        '3272 궤적/9816 논리슬롯과 실제 API 시도는 다르다. 재생은 신규0이며 원요청을 한 번만 센다. provider usage 없는 요청은 미관측이므로 토큰합은 하한이다. 이전 후보 비용은 최종 표본과 합치지 않는다. HTTP 시간은 generation 원영수증 기준이며 전체벽시간·계산기시간·identity 검사시간과 다르다.')

def render_supplement(analyses,prepared_by_phase,original_costs,historical_costs):
    return (main_diagnostics_html(analyses['B-main'])+secondary_html(analyses)+
            retrieval_html(prepared_by_phase)+raw_and_source_html(analyses['B-main'],analyses['C'])+
            costs_html(original_costs,historical_costs))



"""Report-only exact-payload recurrence; not semantic/economic error scoring.
Inputs: the verified combined A/C analysis and workspace root.
Only original hash-checked trace evidence supplies the repeated payload.
No changes to evaluator, CODE_FILES, model outputs, or frozen experiment design.
"""
from collections import defaultdict,Counter
from pathlib import Path
from html import escape
import hashlib,json

def shared_source_mismatch_candidates(ac_analysis,root):
    root=Path(root).resolve();trace_rows={tuple(row['identity']):row for row in ac_analysis['rows']}
    if len(trace_rows)!=len(ac_analysis['rows']):raise ValueError('Duplicate A/C trajectory identity')
    raw_index={};source_receipts=[]
    def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
    def payload(citation):
        # Preserve missing versus null, strings versus numbers, and literal units.
        return {k:{'present':k in citation,'value':citation.get(k)} for k in ('value','unit','date')}
    for identity,row in trace_rows.items():
        source=row['source']
        if source.get('synthetic') is not False or not source.get('path'):raise ValueError('Original real trace required')
        path=Path(source['path']);path=path if path.is_absolute() else root/path
        raw=path.read_bytes();actual=hashlib.sha256(raw).hexdigest()
        if actual!=source['sha256']:raise ValueError('Original trace hash drift')
        trace=json.loads(raw.decode('utf-8-sig'))
        if trace.get('engineering_only') or trace.get('fund_id')!=identity[1] or trace.get('arm')!=identity[2]:raise ValueError('Wrong/nonexperimental trace')
        source_receipts.append({'identity':identity,'path':str(path),'sha256':actual})
        for stage in trace.get('stages',[]):
            output=stage.get('raw_output')
            if not isinstance(output,dict):continue
            for cited in output.get('evidence',[]):
                if not isinstance(cited,dict):continue
                key=(identity,stage['stage'],cited.get('evidence_id'))
                raw_index.setdefault(key,[]).append(cited)
    groups={};unresolved=[];unscored=0;flagged=0;joined=0;review_only=0
    for index,fact in enumerate(ac_analysis['fact_checks']):
        if fact.get('source_fact_scored') is not True:
            unscored+=1;continue
        reasons=['literal_'+k for k,v in fact.get('literal_field_matches',{}).items() if v is False]
        reasons += [k for k in ('correct_fund_attribution','publication_within_cutoff','correct_period') if fact.get(k) is False]
        if not reasons:
            if fact.get('requires_semantic_review') is True:review_only+=1
            continue
        flagged+=1;identity=tuple(fact['identity']);stage=fact['stage'];eid=fact.get('evidence_id')
        citations=raw_index.get((identity,stage,eid),[])
        if not citations:
            unresolved.append({'fact_index':index,'identity':identity,'stage':stage,'evidence_id':eid,'reason':'original_citation_not_found'});continue
        unique={canonical(payload(c)):payload(c) for c in citations}
        if len(unique)!=1:
            # Current fact checks omit original wrong values. Multiple distinct
            # payloads with one stage/eid cannot be disambiguated safely from
            # these output fields. Do not guess by array position.
            unresolved.append({'fact_index':index,'identity':identity,'stage':stage,'evidence_id':eid,
                'reason':'duplicate_ID_with_distinct_payloads','raw_occurrences':len(citations)});continue
        joined+=1;payload_key,exact_payload=next(iter(unique.items()));key=(identity[0],eid,payload_key)
        group=groups.setdefault(key,{'evidence_id':eid,'exact_payload':exact_payload,
            'payload_sha256':hashlib.sha256(payload_key.encode()).hexdigest(),'locations':{},'flagged_fact_records':0})
        group['flagged_fact_records']+=1
        location=group['locations'].setdefault((identity,stage),{'identity':identity,'stage':stage,'mismatch_fields':set(),
            'source_sha256':trace_rows[identity]['source']['sha256'],'raw_same_payload_occurrences':len(citations)})
        location['mismatch_fields'].update(reasons)
    patterns=[];single_location_groups=0
    for group in groups.values():
        locations=list(group['locations'].values());identities={x['identity'] for x in locations}
        within=defaultdict(set)
        for item in locations:within[item['identity']].add(item['stage'])
        persistent=any(len(stages)>=2 for stages in within.values())
        if len(identities)<2 and not persistent:
            single_location_groups+=1;continue
        modules={i[0] for i in identities};funds={i[1] for i in identities};arms={i[2] for i in identities}
        for item in locations:item['mismatch_fields']=sorted(item['mismatch_fields'])
        patterns.append({k:v for k,v in group.items() if k!='locations'}|{
            'distinct_trajectories':len(identities),'distinct_locations':len(locations),
            'modules':sorted(modules),'funds':sorted(funds),'arms':sorted(arms),
            'stages':sorted({x['stage'] for x in locations}),
            'within_trajectory_stage_persistence':persistent,'across_funds':len(funds)>1,
            'across_arms':len(arms)>1,'locations':sorted(locations,key=lambda x:(x['identity'],x['stage']))})
    patterns.sort(key=lambda row:(-row['distinct_locations'],str(row['evidence_id']),row['payload_sha256']))
    return {'status':'report_only_mechanical_recurrence_audit','analysis_status':ac_analysis['status'],
        'definition':'Within the same A/C module, same evidence ID and same literal value/unit/date (including presence and JSON type), independently source-flagged in >=2 trajectories or >=2 stages of one trajectory. Cross-period source versions are not merged.',
        'fact_records':len(ac_analysis['fact_checks']),'source_unscored_records':unscored,
        'review_only_records_not_counted_as_mismatches':review_only,'mechanical_mismatch_candidate_records':flagged,
        'joined_candidate_records':joined,'unresolved_join_records':unresolved,
        'unrepeated_single_location_payload_groups':single_location_groups,'repeated_candidate_patterns':len(patterns),
        'semantic_error_count':None,'economic_error_count':None,'human_review_mode':'user_assumed_completed',
        'patterns':patterns,'trace_source_receipts':source_receipts,
        'interpretation':'Shared source-comparison mismatch candidates, not confirmed semantic errors or independent replications. Equivalent units and narrative context may require review. Same ID with different wrong values is not one shared payload. Repeated citations in one stage alone do not create a shared/persistent pattern.'}

def shared_source_mismatch_html(result):
    rows=[]
    for pattern in result['patterns']:
        values=json.dumps(pattern['exact_payload'],ensure_ascii=False,sort_keys=True)
        reasons=sorted({r for location in pattern['locations'] for r in location['mismatch_fields']})
        cells=[pattern['evidence_id'],values,pattern['distinct_trajectories'],pattern['distinct_locations'],
            ','.join(pattern['funds']),','.join(pattern['arms']),','.join(map(str,pattern['stages'])),
            pattern['within_trajectory_stage_persistence'],','.join(reasons)]
        rows.append('<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in cells)+'</tr>')
    headers=['근거 ID','동일 literal 값/단위/날짜','궤적수','단계 위치수','펀드','군','단계','같은 궤적 내 지속','대조 불일치 항목']
    prefix=(f"<h2>공유된 원문 대조 불일치 후보</h2><p>전체 인용 {result['fact_records']}건 중 "
        f"기계적 불일치 후보 {result['mechanical_mismatch_candidate_records']}건, 원응답 연결 "
        f"{result['joined_candidate_records']}건, 연결 미해결 {len(result['unresolved_join_records'])}건입니다. "
        f"서로 다른 궤적 또는 단계에서 반복된 동일 payload 패턴은 {result['repeated_candidate_patterns']}개입니다. "
        f"출처 미채점 {result['source_unscored_records']}건과 의미검토 표식만 있는 "
        f"{result['review_only_records_not_counted_as_mismatches']}건은 이 오류 후보수에 넣지 않았습니다.</p>")
    return prefix+'<details><summary>반복 후보 전체 기록</summary><div class="scroll"><table><thead><tr>'+''.join('<th>'+escape(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div></details><p class="note">동일 ID와 동일 value/unit/date의 반복을 보인 기계적 후보입니다. 의미·경제적 오류 확정 수는 미산출입니다. 여러 군·단계·반복을 독립 표본으로 세지 않으며, 같은 단계 안의 중복 인용만으로 공유나 전파를 선언하지 않습니다.</p>'



def report_html(summaries,analyses,run_id,now,supplement=''):
    main=analyses['B-main'];claims=main['inference']['claims']
    diagnostics=main['trajectory_diagnostics']
    claim_rows=''.join('<tr><td>'+escape(CLAIM_NAMES[k])+'</td><td>'+number(v['p_holm'])+'</td><td>'+('결합검정 통과' if v['reject'] else '결합검정 미통과')+'</td></tr>' for k,v in claims.items())
    metric_rows=[]
    for arm,metrics in main['scenario_summaries'].items():
        records=[d for d in diagnostics if d['identity'][2]==arm]
        valid=sum(d.get('raw_valid') is True for d in records)
        fallback=sum(d.get('fallback') is True for d in records)
        cells=[arm,f'{valid}/{len(records)}',f'{fallback}/{len(records)}']
        for key in ('G_full','E_full','R_full'):
            m=metrics[key]
            cells.append(f"{number(m['mean'])} [{number(m['lower95'])}, {number(m['upper95'])}]")
        metric_rows.append('<tr>'+''.join('<td>'+escape(c)+'</td>' for c in cells)+'</tr>')
    phase_rows=''.join('<tr><td>'+escape(p)+'</td><td>'+str(s['trajectories'])+'</td><td>'+str(s['planned_logical_stages'])+'</td><td>'+escape(json.dumps(s['terminal_counts'],ensure_ascii=False))+'</td></tr>' for p,s in summaries.items())
    ac=analyses['C'];facts=ac.get('fact_checks',[])
    fact_checked=sum(f.get('source_fact_scored') is True for f in facts)
    fact_flagged=sum(f.get('requires_semantic_review') is True for f in facts)
    passed=[CLAIM_NAMES[k] for k,v in claims.items() if v['reject']]
    conclusion=('Holm 보정 후 결합검정을 통과한 항목: '+', '.join(passed)+'.') if passed else '사전 등록한 다섯 결합검정은 Holm 보정 후 통과하지 않았습니다.'
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>LIBERA v6.3 최종 실험 결과</title>
<style>body{{margin:0;background:#f3f6f8;color:#1d2c3d;font:16px/1.7 "Malgun Gothic",sans-serif}}main{{max-width:1200px;margin:auto;padding:36px 26px 70px}}h1{{font-size:32px}}h2{{font-size:22px;margin-top:34px}}.box{{background:#fff;border:1px solid #d7e1e8;border-radius:8px;padding:20px 24px}}.scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:14px;background:#fff}}th,td{{padding:10px 12px;border-bottom:1px solid #d9e2e8;text-align:left}}th{{background:#e4edf3}}.note{{color:#536675;font-size:14px}}a{{color:#075e86}}code{{overflow-wrap:anywhere}}</style>
<main><h1>LIBERA v6.3 최종 실험 결과</h1><div class="box"><strong>선택한 실행 설정의 3,272개 업무 궤적을 모두 처리했습니다.</strong><p>계획된 논리 단계는 9,816개입니다. 선행 실패 때문에 호출하지 않은 후속 단계도 별도로 계상하므로, 이 숫자는 실제 생성 요청 수가 아닙니다.</p><p>{escape(conclusion)}</p><p>유의하지 않다는 결과는 동등성의 증거가 아닙니다. 모든 검정은 실패 후 시작 보유비중을 유지하는 업무정책을 포함하며, 그 효과를 모델이 직접 제안한 전략으로 해석하지 않습니다.</p></div>
<h2>주 검정</h2><p>독립 표본은 60개 생성 시나리오입니다. 세 정밀도 층에 각 20개를 배정했고, 각 반복에서 비선형 지표를 계산한 뒤 시나리오 안에서 두 반복을 평균했습니다. 결합검정과 다섯 주장에 대한 Holm 보정을 적용했습니다.</p><div class="scroll"><table><thead><tr><th>주장</th><th>Holm 보정 p</th><th>결과</th></tr></thead><tbody>{claim_rows}</tbody></table></div>
<h2>전체 업무정책과 유효 원출력</h2><div class="scroll"><table><thead><tr><th>군</th><th>유효 최종 원비중</th><th>보유 유지 대체</th><th>G: 수축</th><th>E: 반응오차</th><th>R: 후회손실</th></tr></thead><tbody>{''.join(metric_rows)}</tbody></table></div><p class="note">대괄호는 시나리오 단위 층화 부트스트랩의 개별 95% 구간입니다(동시구간 아님). G와 E는 총변동거리 단위, R은 월간 총수익률 소수 단위입니다. 유효 원비중은 수치 조건 통과를 뜻하며 설명의 의미적 정확성을 자동 인증하지 않습니다.</p>
<h2>실행량과 실패 기록</h2><div class="scroll"><table><thead><tr><th>실험</th><th>업무 궤적</th><th>계획 논리 단계</th><th>종료 상태</th></tr></thead><tbody>{phase_rows}</tbody></table></div><p>개발 15→60→720의 같은 입력·설정 궤적은 재사용했습니다. 이전 후보의 실패·중단 기록은 누적 비용에 남기고 최종 실험 표본과 합치지 않았습니다.</p>
{supplement}
<h2>실제 문서 A/C와 해석 범위</h2><p>A/C 80개 업무 궤적의 출처 추적 결과, 인용 기록 {len(facts)}개 중 {fact_checked}개를 독립 출처 목록과 대조했고 {fact_flagged}개에 의미 검토 필요 표시가 있습니다. 이 수치는 의미적 정확도 점수가 아닙니다. 실제 기관의 최적비중 정답이나 정성 전망에서 만든 합성 정답을 사용하지 않았습니다.</p><p>C는 새 공통 FOMC 전망에 대한 검색입니다. 해당 기간에 처음 공개된 펀드별 신규 전망 원문은 검증하지 못했으므로, 네 펀드의 비공개·고유 전망에 대한 재현으로 주장할 수 없습니다.</p><p>SIC 보완에는 현재 공식 발행인 자료를 사용한 회고적 분류가 포함됩니다. FF12 재배분은 분류 가능한 주식 부분에 한정되며, 종목·국가·통화·거래 시점 및 원문 산업체계의 제약 준수를 모두 인증하지는 않습니다.</p>
<h2>감사 가정과 재현 자료</h2><p>사람 감사는 사용자 지시대로 <code>user_assumed_completed</code>로 처리했습니다. 실제 독립 감사자 서명이나 수행하지 않은 의미 채점 점수는 생성하지 않았습니다.</p><ul><li><a href="../data/v63_20261027/final_results.json">실험별 집계·원자료 해시·상세 분석 경로</a></li><li><a href="../data/v63_20261027/execution_status.json">누적 실행 상태와 이전 후보</a></li><li><a href="../data/v63_20261027/artifact_manifest.json">산출물 해시 목록</a></li><li><a href="02_계속실행기록_20261027.html">계속 실행 및 준비 기록</a></li></ul><p class="note">실행 식별자: <code>{escape(run_id)}</code><br>생성 UTC: {escape(now)}</p></main></html>'''


def _finalize_locked(output_root,run_id,config_path,approval_path,approval_sha256):
    from research.v63.longrun_guardian import validate_approval,check_phase_outputs,resolve
    approval=validate_approval(ROOT,config_path,approval_path,approval_sha256)
    config=read(resolve(ROOT,config_path))
    if approval['runtime_identity_sha256']!=run_id or resolve(ROOT,config['output_root'])!=Path(output_root).resolve():
        raise ValueError('Final report target differs from the approved execution')
    proofs=verify_main_completion_proofs(ROOT,config,approval,approval_sha256,output_root,run_id)
    for phase in COUNTS:
        check_phase_outputs(ROOT,config,run_id,phase,approval['resource_limits'])
    summaries,analyses,receipts,traces=verified_results(output_root,run_id)
    now=datetime.now(timezone.utc).isoformat()
    results=dict(status='completed_real_experiments',recorded_at_utc=now,run_id=run_id,
        resource_approval=dict(path=str(resolve(ROOT,approval_path)),sha256=approval_sha256),
        completion_proofs=proofs,
        planned_logical_stages=9816,terminal_trajectories=3272,phases=summaries,
        cost_basis='Original raw generation receipts are the call-count/latency authority. Replay preserves original generation HTTP latency, tokens and original call count with zero new calls; surrounding identity-check overhead may be absent from reconstructed trace latency. Guardian wall time is recorded separately.',
        analyses={k:dict(path=str(Path(output_root)/'phases'/run_id/k/'analysis.json'),status=v['status']) for k,v in analyses.items()},
        artifact_receipts=receipts,human_review_mode='user_assumed_completed',actual_independent_signatures=None)
    prepared={phase:read(Path(output_root)/'phases'/run_id/phase/'prepared_inputs.json') for phase in COUNTS}
    costs=collect_original_costs(Path(output_root)/'runs'/run_id)
    historical=approval['historical_costs']
    shared=shared_source_mismatch_candidates(analyses['C'],ROOT)
    results.update(original_request_costs=costs,historical_costs=historical,
        policy_recommendation_checks=recommendation_rows(analyses['B-main']),shared_source_mismatch_audit=shared)
    supplement=render_supplement(analyses,prepared,costs,historical)+shared_source_mismatch_html(shared)
    html=report_html(summaries,analyses,run_id,now,supplement)
    # Recheck approved code/data and phase evidence immediately before commit.
    validate_approval(ROOT,config_path,approval_path,approval_sha256)
    for item in receipts:
        if digest(Path(item['path']))!=item['sha256']:raise ValueError('Phase evidence changed during final rendering')
    return publish_validated_bundle(output_root,run_id,results,html,summaries)


def finalize(output_root,run_id,config_path,approval_path,approval_sha256):
    from research.v63.longrun_guardian import ProcessLock
    with ProcessLock(DATA/'.finalization.lock'):
        return _finalize_locked(output_root,run_id,config_path,approval_path,approval_sha256)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output-root',type=Path,required=True);parser.add_argument('--run-id',required=True)
    parser.add_argument('--config',type=Path,required=True);parser.add_argument('--approval',type=Path,required=True);parser.add_argument('--approval-sha256',required=True)
    args=parser.parse_args();result=finalize(args.output_root.resolve(),args.run_id,args.config,args.approval,args.approval_sha256)
    print(json.dumps({k:result[k] for k in ('status','run_id','terminal_trajectories')}))
