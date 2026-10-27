"""Synthetic filesystem and mocked-child checks; no real approvals/model calls."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from research.v63 import longrun_guardian as g


def put(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding='utf-8');return path


@pytest.fixture
def approval_fixture(tmp_path,monkeypatch):
    root=tmp_path/'synthetic_workspace';root.mkdir()
    freeze={'model_sha256':'m'*64,'main_model_frozen':False,'temperature':0,'request_timeout':120}
    put(root/'freeze.json',freeze)
    budgets={p:{'max_generation_requests':10000,'max_wall_seconds':100000} for p in g.PHASES}
    config={'output_root':'outputs','runtime_freeze_path':'freeze.json','phase_budgets':budgets,'smoke_fund_id':'F01'}
    config_path=put(root/'config.json',config)
    bound=put(root/'bound_code_data.json',{'synthetic':True})
    bindings={'config':g.file_ref(root,config_path),'runtime_identity_sha256':'r'*64,
        'runtime_freeze_without_main_flag_sha256':g.freeze_hash(freeze),'model_sha256':'m'*64,
        'response_schema_sha256':'s'*64,'python_executable':g.file_ref(root,bound),
        'python_package_versions':{'fake-package':'1'},'phase_budgets':budgets,
        'bound_files':[g.file_ref(root,bound)]}
    monkeypatch.setattr(g,'required_bindings',lambda *a,**kw:deepcopy(bindings))
    monkeypatch.setattr(g,'check_phase_outputs',lambda *a,**kw:{'phase':a[3],'measurements':{'synthetic':True},
        'mean_generation_requests':3,'mean_request_seconds':2})
    evidence={}
    for phase in ['technical-smoke','paired-feasibility']:
        d=root/'outputs/phases'/bindings['runtime_identity_sha256']/phase
        evidence[phase]={label:g.file_ref(root,put(d/name,{'synthetic_fixture_only':True})) for label,name in
            [('measurements','measurements.json'),('prepared_inputs','prepared_inputs.json'),('records','records.json'),('runtime_identity','runtime_identity.json')]}
    approval={**bindings,'schema':g.SCHEMA,'issued_by':'/root','decision':'authorize_guardian_after_measured_feasibility',
        'issued_at_utc':'2026-10-27T00:00:00+00:00','main_N':60,'main_replicates':2,
        'effect_or_pvalue_used_for_selection':False,'allow_main_only_after_ready_pilot':True,'recovery_required':True,
        'resource_limits':{'max_total_generation_requests':100000,'max_total_request_seconds':1e7,
            'max_guardian_wall_seconds':1e7,'max_prompt_tokens':16000,'forecast_safety_factor':1.1},
        'historical_costs':{'generation_requests':0,'recorded_request_seconds':0.,'evidence':[],
            'scope':'Synthetic fixture; no earlier real model calls.'},
        'measurement_evidence':evidence,'synthetic_test_fixture_only':True}
    path=put(root/'synthetic_approval.json',approval)
    return root,config_path,path,approval,bindings


def test_approval_requires_separately_supplied_exact_hash(approval_fixture):
    root,config,path,a,b=approval_fixture
    assert g.validate_approval(root,config,path,g.digest(path))['synthetic_test_fixture_only']
    for sha in [None,'','0'*63,'0'*64]:
        with pytest.raises(g.GuardianStop):g.validate_approval(root,config,path,sha)
    old=g.digest(path);put(path,{**a,'changed_after_review':True})
    with pytest.raises(g.GuardianStop):g.validate_approval(root,config,path,old)


@pytest.mark.parametrize('field,value',[
    ('issued_by','sub-agent'),('decision','auto_approve'),('main_N',61),('main_replicates',3),
    ('effect_or_pvalue_used_for_selection',True),('allow_main_only_after_ready_pilot',False),
    ('recovery_required',False),('model_sha256','changed-model'),('runtime_identity_sha256','changed-code')])
def test_wrong_authority_design_or_frozen_binding_rejected(approval_fixture,field,value):
    root,config,path,a,b=approval_fixture;put(path,{**a,field:value})
    with pytest.raises(g.GuardianStop):g.validate_approval(root,config,path,g.digest(path))


def test_missing_or_changed_data_code_binding_rejected(approval_fixture):
    root,config,path,a,b=approval_fixture
    put(path,{**a,'bound_files':[]})
    with pytest.raises(g.GuardianStop):g.validate_approval(root,config,path,g.digest(path))
    put(path,a);put(root/'bound_code_data.json',{'synthetic':'changed'})
    with pytest.raises(g.GuardianStop):g.validate_approval(root,config,path,g.digest(path))


def test_measurement_evidence_must_match_phase_and_runtime(approval_fixture):
    root,config,path,a,b=approval_fixture
    a=deepcopy(a);wrong=put(root/'other_runtime_measurements.json',{'synthetic_fixture_only':True})
    a['measurement_evidence']['technical-smoke']['measurements']=g.file_ref(root,wrong);put(path,a)
    with pytest.raises(g.GuardianStop):g.validate_approval(root,config,path,g.digest(path))


@pytest.mark.parametrize('limit',[0,-1,float('inf'),float('nan'),True])
def test_resource_limit_must_be_positive_finite_numeric(approval_fixture,limit):
    root,config,path,a,b=approval_fixture;a=deepcopy(a);a['resource_limits']['max_total_generation_requests']=limit;put(path,a)
    with pytest.raises(g.GuardianStop):g.validate_approval(root,config,path,g.digest(path))


def phase_fixture(tmp_path,monkeypatch):
    from research.v63 import build_run
    root=tmp_path;config={'output_root':'outputs','smoke_fund_id':'F01'};run_id='synthetic-runtime'
    folder=root/'outputs/phases'/run_id/'technical-smoke';records=[]
    for i,arm in enumerate(['R0','R1','R2','R3','C-context']):
        row=dict(block='B-development',scenario='development-001',fund_id='F01',arm=arm,replicate=1)
        trace={'fund_id':'F01','arm':arm,'status':'completed','effective_weights':[1.]+[0.]*11,
            'actual_model_calls':3,'calls':[{'elapsed_seconds':1.,'stage':s,'status':'response',
                'raw_response':{'usage':{'prompt_eval_count':100+s},'model_sha256':'m'*64}} for s in [1,2,3]],
            'stages':[{'stage':s,'status':'completed','prompt_token_counts':[100+s]} for s in [1,2,3]]}
        p=put(root/f'trace_{i}.json',trace);row.update(trace_path=str(p),trace_sha256=g.digest(p));records.append(row)
    put(folder/'records.json',records)
    put(folder/'measurements.json',{'status':'completed','runtime_identity_sha256':run_id,
        'phase_trajectories':5,'terminal_trajectories':5,'full_history_observed':True,'max_observed_prompt_tokens':103})
    monkeypatch.setattr(build_run,'select_phase_schedule',lambda phase,fid:deepcopy(records))
    return root,config,run_id,folder,records,{'max_prompt_tokens':400}


def test_real_gate_rejects_partial_synthetic_unattempted_or_wrong_owner(tmp_path,monkeypatch):
    root,config,run,folder,records,limits=phase_fixture(tmp_path,monkeypatch)
    assert g.check_phase_outputs(root,config,run,'technical-smoke',limits)['trajectories']==5
    target=Path(records[-1]['trace_path']);original=g.read(target)
    for update in [{'status':'interrupted'},{'engineering_only':True},{'calls':[]},{'fund_id':'F02'},
                   {'stages':[{'stage':1,'status':'completed','prompt_token_counts':[100]}]}]:
        put(target,{**original,**update});records[-1]['trace_sha256']=g.digest(target);put(folder/'records.json',records)
        with pytest.raises(g.GuardianStop):g.check_phase_outputs(root,config,run,'technical-smoke',limits)
    put(target,original);records[-1]['trace_sha256']=g.digest(target);put(folder/'records.json',records[:-1])
    with pytest.raises(g.GuardianStop):g.check_phase_outputs(root,config,run,'technical-smoke',limits)


def test_gate_rejects_trace_hash_drift_without_overwriting_it(tmp_path,monkeypatch):
    root,config,run,folder,records,limits=phase_fixture(tmp_path,monkeypatch)
    p=Path(records[0]['trace_path']);put(p,{'tampered':True});before=p.read_bytes()
    with pytest.raises(g.GuardianStop):g.check_phase_outputs(root,config,run,'technical-smoke',limits)
    assert p.read_bytes()==before


def test_raw_costs_counts_original_receipts_and_reserves_unknown(tmp_path):
    run=tmp_path/'runs'
    put(run/'task/http/attempt_000001/attempt_receipt.json',{'generation_requests':1})
    put(run/'task/http/attempt_000001/generation.receipt.json',{'elapsed_seconds':20.})
    put(run/'task/http/attempt_000002/runner_request.bin',{'uncertain':True})
    put(run/'task/http/attempt_000003/attempt_receipt.json',{'generation_requests':0})
    put(run/'task/replayed_trace.json',{'actual_model_calls':30,'elapsed_seconds':600})
    r=g.raw_costs(run)
    assert r['confirmed_generation_requests']==1 and r['possibly_sent_without_receipt']==1
    assert r['generation_request_budget_count']==2 and r['recorded_generation_request_seconds']==20


def test_forecast_and_cumulative_reservation_fail_closed(approval_fixture):
    root,config,path,a,b=approval_fixture
    observed={'phase':'paired-feasibility','mean_generation_requests':3,'mean_request_seconds':2}
    assert g.forecast_budget('development-pilot',a,observed,{'generation_request_budget_count':0})['generation_requests']==pytest.approx(792)
    with pytest.raises(g.GuardianStop):g.forecast_budget('development-pilot',a,{**observed,'mean_generation_requests':1000},{'generation_request_budget_count':0})
    with pytest.raises(g.GuardianStop):g.forecast_budget('development-pilot',a,observed,{'generation_request_budget_count':99999})


def test_kernel_lock_rejects_concurrent_guardian_and_releases(tmp_path):
    p=tmp_path/'guardian.lock'
    with g.ProcessLock(p):
        with pytest.raises(g.GuardianStop):
            with g.ProcessLock(p):pass
    with g.ProcessLock(p):pass


def pilot_fixture(root):
    from research.v63.pilot_precision import _hash_object
    config=g.read(root/'config.json');run_id='r'*64
    phase=root/'outputs/phases'/run_id/'development-pilot'
    scenarios=[{'scenario_id':'synthetic-'+str(i),'r':1.} for i in range(12)]
    bank={'synthetic_test_reference':True};runtime={'synthetic_runtime':True}
    put(phase/'records.json',[]);put(phase/'evaluator_only/reference_bank.json',bank)
    put(phase/'evaluator_only/frozen_scenarios.json',scenarios);put(phase/'frozen_runtime.json',runtime)
    names=['pilot_precision.py','evaluate.py','numerics.py','statistics.py']
    for name in names:put(root/'research/v63'/name,{'synthetic_code':name})
    path=put(root/'synthetic_pilot_precision.json',{'status':'development_precision_descriptive_ready',
        'ready_for_precision_report':True,'synthetic_verification':False,'main_N_fixed':60,
        'independent_scenarios':12,'expected_trajectories':240,'missing':[],'nonterminal':[],
        'frozen_model_sha256':'m'*64,'test_fixture_not_real_experiment':True,'runtime_metadata':runtime,
        'input_fingerprint':_hash_object([[s['scenario_id'] for s in scenarios],[s['r'] for s in scenarios],bank]),
        'provenance':{n:g.digest(root/'research/v63'/n) for n in names}})
    put(path.with_suffix('.inputs.json'),{'runtime_identity_sha256':run_id,
        'report':g.file_ref(root,path),'inputs':g.pilot_inputs(root,config,run_id)})
    return path


@pytest.mark.parametrize('update',[{'status':'pilot_not_ready'},{'synthetic_verification':True},{'main_N_fixed':59},
    {'independent_scenarios':11},{'missing':['one']},{'frozen_model_sha256':'other'}])
def test_main_flag_not_promoted_for_partial_synthetic_or_drifted_pilot(approval_fixture,update):
    root,config,path,a,b=approval_fixture;p=pilot_fixture(root);put(p,{**g.read(p),**update})
    old=(root/'freeze.json').read_bytes()
    with pytest.raises(g.GuardianStop):g.promote_main(root,g.read(config),a,g.digest(path),root/'guardian',p)
    assert (root/'freeze.json').read_bytes()==old


def test_main_transition_changes_only_flag_and_is_restart_bound(approval_fixture):
    root,config,path,a,b=approval_fixture;p=pilot_fixture(root);directory=root/'guardian';directory.mkdir()
    original=g.read(root/'freeze.json')
    g.promote_main(root,g.read(config),a,g.digest(path),directory,p)
    assert g.read(root/'freeze.json')=={**original,'main_model_frozen':True}
    receipt=directory/'main_freeze_transition.json';before=receipt.read_bytes()
    g.promote_main(root,g.read(config),a,g.digest(path),directory,p)
    assert receipt.read_bytes()==before
    p.write_text(p.read_text()+' ')
    with pytest.raises(g.GuardianStop):g.promote_main(root,g.read(config),a,g.digest(path),directory,p)


def test_existing_true_main_flag_without_transition_cannot_be_adopted(approval_fixture):
    root,config,path,a,b=approval_fixture;p=pilot_fixture(root);f=g.read(root/'freeze.json');f['main_model_frozen']=True;put(root/'freeze.json',f)
    with pytest.raises(g.GuardianStop):g.promote_main(root,g.read(config),a,g.digest(path),root/'guardian',p)


class FakeProcess:
    def __init__(self,returncode=0):self.pid=12345;self.returncode=None;self.next_returncode=returncode;self.terminated=False
    def poll(self):return self.returncode
    def wait(self,timeout=None):self.returncode=self.next_returncode;return self.returncode
    def terminate(self):self.terminated=True;self.returncode=-15
    def kill(self):self.terminated=True;self.returncode=-9


def test_subprocess_launch_is_mocked_and_failure_never_fills_records(approval_fixture,monkeypatch):
    root,config,path,a,b=approval_fixture
    guardian=g.Guardian(root,config,path,g.digest(path));child=FakeProcess(1);calls=[]
    monkeypatch.setattr(g.subprocess,'Popen',lambda *args,**kw:(calls.append((args,kw)) or child))
    monkeypatch.setattr(guardian,'unchanged',lambda:None)
    before={str(p):p.read_bytes() for p in (root/'outputs/phases').rglob('records.json')}
    with pytest.raises(g.GuardianStop):guardian.subprocess(['fake-program','synthetic-only'],'synthetic-child',100)
    assert len(calls)==1
    assert {str(p):p.read_bytes() for p in (root/'outputs/phases').rglob('records.json')}==before
    assert not (guardian.directory/'completion_receipt.json').exists()


def test_running_child_is_terminated_when_bound_data_drifts(approval_fixture,monkeypatch):
    root,config,path,a,b=approval_fixture;guardian=g.Guardian(root,config,path,g.digest(path));child=FakeProcess()
    def launch(*args,**kw):put(root/'bound_code_data.json',{'changed':True});return child
    monkeypatch.setattr(g.subprocess,'Popen',launch);monkeypatch.setattr(guardian,'unchanged',lambda:None)
    with pytest.raises(g.GuardianStop):guardian.subprocess(['fake-program'],'synthetic-child',100)
    assert child.terminated and guardian.process is None


def test_historical_cost_evidence_is_explicit_and_immutable(approval_fixture):
    root,config,path,a,b=approval_fixture
    prior=put(root/'prior_requests.json',{'synthetic_prior_requests':7})
    a=deepcopy(a);a['historical_costs']={'generation_requests':7,'recorded_request_seconds':13.,
        'evidence':[g.file_ref(root,prior)],'scope':'Synthetic prior candidate only; excludes current run.'}
    put(path,a)
    assert g.validate_approval(root,config,path,g.digest(path))['historical_costs']['generation_requests']==7
    assert g.historical_costs(root,a)==(7,13.)
    prior.write_text('changed',encoding='utf-8')
    with pytest.raises(g.GuardianStop):g.validate_approval(root,config,path,g.digest(path))
    a.pop('historical_costs');put(path,a)
    with pytest.raises(g.GuardianStop):g.validate_approval(root,config,path,g.digest(path))


def test_untimed_requests_reserve_timeout_and_prior_costs_are_added(approval_fixture):
    root,config,path,a,b=approval_fixture
    prior=put(root/'prior.json',{'synthetic_only':True})
    a=deepcopy(a);a['historical_costs']={'generation_requests':7,'recorded_request_seconds':13.,
        'evidence':[g.file_ref(root,prior)],'scope':'Prior synthetic candidate'};put(path,a)
    guardian=g.Guardian(root,config,path,g.digest(path))
    put(guardian.run_root/'task/http/attempt_000001/runner_request.bin',{'uncertain':True})
    put(guardian.run_root/'task/http/attempt_000002/attempt_receipt.json',{'generation_requests':1})
    costs=guardian.limits()
    assert costs['generation_request_budget_count']==9
    assert costs['generation_requests_without_timing']==2
    assert costs['request_seconds_budget_count']==253.
    guardian.approval['resource_limits']['max_total_request_seconds']=252.
    with pytest.raises(g.GuardianStop):guardian.limits()


@pytest.mark.parametrize('value',[None,0,104])
def test_measured_prompt_maximum_must_match_native_counts(tmp_path,monkeypatch,value):
    root,config,run,folder,records,limits=phase_fixture(tmp_path,monkeypatch)
    m=g.read(folder/'measurements.json');m['max_observed_prompt_tokens']=value;put(folder/'measurements.json',m)
    with pytest.raises(g.GuardianStop):g.check_phase_outputs(root,config,run,'technical-smoke',limits)


def test_full_history_requires_actual_stage_three_response(tmp_path,monkeypatch):
    root,config,run,folder,records,limits=phase_fixture(tmp_path,monkeypatch)
    target=Path(records[-1]['trace_path']);tr=g.read(target)
    tr['calls'][-1]={'elapsed_seconds':1.,'stage':3,'status':'infra_failure'}
    put(target,tr);records[-1]['trace_sha256']=g.digest(target);put(folder/'records.json',records)
    with pytest.raises(g.GuardianStop):g.check_phase_outputs(root,config,run,'technical-smoke',limits)


def test_restart_forecast_uses_remaining_capacity_and_persisted_wall(approval_fixture):
    root,config,path,a,b=approval_fixture
    observed={'phase':'paired-feasibility','mean_generation_requests':3,'mean_request_seconds':2}
    result=g.forecast_budget('development-pilot',a,observed,{'generation_request_budget_count':99990},
        phase_used_requests=9990,phase_elapsed_seconds=99990,remaining_trajectories=1)
    assert result['generation_requests']==pytest.approx(3.3)
    assert result['already_used_phase_requests']==9990 and result['trajectories']==1
    with pytest.raises(g.GuardianStop):g.forecast_budget('development-pilot',a,observed,
        {'generation_request_budget_count':0},phase_used_requests=9999,remaining_trajectories=1)
    with pytest.raises(g.GuardianStop):g.forecast_budget('development-pilot',a,observed,
        {'generation_request_budget_count':0},phase_elapsed_seconds=99999,remaining_trajectories=1)


@pytest.mark.parametrize('field,value',[('input_fingerprint','changed'),('runtime_metadata',{}),('provenance',{})])
def test_pilot_provenance_cannot_be_rebound_by_rehashing_report(approval_fixture,field,value):
    root,config,path,a,b=approval_fixture;p=pilot_fixture(root)
    put(p,{**g.read(p),field:value});proof=g.read(p.with_suffix('.inputs.json'))
    proof['report']=g.file_ref(root,p);put(p.with_suffix('.inputs.json'),proof)
    with pytest.raises(g.GuardianStop):g.promote_main(root,g.read(config),a,g.digest(path),root/'guardian',p)
    assert g.read(root/'freeze.json')['main_model_frozen'] is False


def test_all_later_phase_cap_authority_required_before_main(approval_fixture):
    root,config,path,a,b=approval_fixture;p=pilot_fixture(root)
    a=deepcopy(a);a['resource_limits']['max_total_generation_requests']=15000
    with pytest.raises(g.GuardianStop):g.promote_main(root,g.read(config),a,g.digest(path),root/'guardian',p)
    assert g.read(root/'freeze.json')['main_model_frozen'] is False


def test_checkpoint_is_reloaded_after_construction(approval_fixture):
    root,config,path,a,b=approval_fixture;guardian=g.Guardian(root,config,path,g.digest(path))
    changed={**guardian.state,'completed_phases':['development-pilot'],'elapsed_guardian_seconds':25.}
    put(guardian.state_path,changed);guardian.reload_checkpoint()
    assert guardian.state['completed_phases']==['development-pilot'] and guardian.prior_elapsed==25.
    put(guardian.state_path,{**changed,'completed_phases':['B-main']})
    with pytest.raises(g.GuardianStop):guardian.reload_checkpoint()


@pytest.mark.parametrize('finalizer_result',['valid','raises','wrong_run'])
def test_completion_requires_last_finalizer_success_same_run(approval_fixture,monkeypatch,finalizer_result):
    root,config,path,a,b=approval_fixture;guardian=g.Guardian(root,config,path,g.digest(path))
    put(guardian.directory/'pilot_precision_report.json',{'synthetic_mock_only':True})
    calls=[];checks=[]
    monkeypatch.setattr(guardian,'unchanged',lambda:None)
    monkeypatch.setattr(guardian,'limits',lambda *a:{'generation_request_budget_count':0})
    monkeypatch.setattr(guardian,'phase_usage',lambda p:{'remaining_trajectories':g.COUNTS[p]})
    monkeypatch.setattr(g,'promote_main',lambda *a,**kw:None)
    def check(*args,**kw):
        checks.append(args[3]);return {'phase':args[3],'measurements':{'synthetic':True},
            'mean_generation_requests':3,'mean_request_seconds':2}
    monkeypatch.setattr(g,'check_phase_outputs',check)
    def child(command,label,max_wall):
        calls.append(label)
        if label=='final-report':
            assert checks[-len(g.PHASES):]==list(g.PHASES)
            assert command[command.index('--config')+1]==str(guardian.config_path)
            assert command[command.index('--approval')+1]==str(guardian.approval_path)
            assert command[command.index('--approval-sha256')+1]==guardian.approval_sha
            if finalizer_result=='raises':raise g.GuardianStop('Synthetic finalizer failure')
            put(root/'data/v63_20261027/final_results.json',{'status':'completed_real_experiments',
                'run_id':guardian.run_id if finalizer_result=='valid' else 'another-run',
                'terminal_trajectories':3272,'planned_logical_stages':9816,'synthetic_fixture_only':True})
    monkeypatch.setattr(guardian,'subprocess',child)
    if finalizer_result=='valid':
        result=guardian.run();assert result['status']=='all_required_phases_and_analyses_completed'
        assert (guardian.directory/'completion_receipt.json').is_file()
    else:
        with pytest.raises(g.GuardianStop):guardian.run()
        assert not (guardian.directory/'completion_receipt.json').exists()
    assert calls==list(g.PHASES)+['final-report']
