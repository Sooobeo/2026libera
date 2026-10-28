"""Approval-bound, resumable phase supervisor. This module NEVER issues approval.

Root must review measured 15/60-stage feasibility and pass the separately
reviewed approval SHA-256 on the CLI. Existing campaign recovery handles partial
requests; the guardian never deletes, repairs, replays, or fills a trajectory.
"""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

PHASES=('development-pilot','B-main','x-replacement','negative-control','A','C')
COUNTS={'technical-smoke':5,'paired-feasibility':20,'development-pilot':240,
        'B-main':2400,'x-replacement':360,'negative-control':192,'A':40,'C':40}
ANALYSIS_STATUS={'B-main':'completed_confirmatory_analysis','x-replacement':'completed_secondary_analysis',
                 'negative-control':'completed_secondary_analysis','C':'completed_actual_document_audit'}
TERMINAL={'completed','model_output_failure','operational_failure'}
SCHEMA='libera-resource-review-v1'


class GuardianStop(RuntimeError):pass


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()
def object_hash(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def write(path,value):
    # Reuse the campaign's fsync and bounded Windows sharing-error handling.
    from research.v63.campaign_control import atomic_json
    atomic_json(path,value)


def _execution_state(flags):
    import ctypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.SetThreadExecutionState.argtypes=[ctypes.c_uint]
    kernel.SetThreadExecutionState.restype=ctypes.c_uint
    return kernel.SetThreadExecutionState(flags)


@contextmanager
def system_awake():
    """Prevent automatic idle sleep while owned work runs; no persistent change.

    Explicit user sleep/restart remains possible and is never subtracted from
    recorded phase clocks or original request durations.
    """
    if os.name!='nt':
        yield False
        return
    previous=_execution_state(0x80000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    require(previous!=0,'Could not establish temporary Windows system-sleep prevention')
    try:yield True
    finally:_execution_state(previous)


def stop_owned_process_tree(process):
    """Stop only this child and its descendants, including Windows venv stubs."""
    result={'owned_pid':process.pid,'windows_tree_command':None}
    if process.poll() is not None:
        result.update(already_exited=True,returncode=process.returncode)
        return result
    if os.name=='nt':
        command=['taskkill.exe','/PID',str(process.pid),'/T','/F']
        result['windows_tree_command']=command
        try:
            stopped=subprocess.run(command,capture_output=True,text=True,timeout=15,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            result.update(tree_command_exit_code=stopped.returncode,
                          tree_command_stdout=stopped.stdout,tree_command_stderr=stopped.stderr)
            if stopped.returncode and process.poll() is None:process.terminate()
        except (OSError,subprocess.TimeoutExpired) as exc:
            result['tree_command_error']=type(exc).__name__+': '+str(exc)
            if process.poll() is None:process.terminate()
    else:process.terminate()
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
    result['returncode']=process.returncode
    return result
def resolve(root,path):
    p=Path(path);return (p if p.is_absolute() else Path(root)/p).resolve()
def require(ok,message):
    if not ok:raise GuardianStop(message)
def file_ref(root,path):
    p=resolve(root,path)
    try:name=p.relative_to(Path(root).resolve()).as_posix()
    except ValueError:name=str(p)
    return {'path':name,'sha256':digest(p)}
def verify_ref(root,ref):
    require(isinstance(ref,dict) and set(('path','sha256'))<=set(ref),'Missing immutable file reference')
    p=resolve(root,ref['path']);require(p.is_file() and digest(p)==ref['sha256'],'Bound file changed: '+str(p));return p
def freeze_hash(freeze):return object_hash({k:v for k,v in freeze.items() if k!='main_model_frozen'})


def historical_costs(root,approval):
    """Keep historical observations and explicit untimed reservations separate."""
    h=approval.get('historical_costs');require(isinstance(h,dict),'Explicit prior-candidate cost accounting is required')
    count=h.get('generation_requests');seconds=h.get('recorded_request_seconds')
    require(type(count) is int and count>=0,'Invalid historical generation request count')
    require(type(seconds) in (int,float) and math.isfinite(seconds) and seconds>=0,'Invalid historical request seconds')
    supplemental=h.get('supplemental_recorded_request_seconds');untimed=h.get('generation_requests_without_timing')
    reserved=h.get('request_seconds_reserved_for_missing_timing');per_request=h.get('reservation_seconds_per_untimed_request')
    require(type(supplemental) in (int,float) and math.isfinite(supplemental) and supplemental>=0,'Explicit finite supplemental historical observations required')
    require(type(untimed) is int and 0<=untimed<=count,'Explicit historical untimed count required; legacy omission is not zero')
    require(all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in (reserved,per_request)),'Explicit finite historical time reservations required')
    require((untimed==0 and reserved==0 and per_request==0) or
            (untimed>0 and per_request>0 and reserved>0 and math.isclose(reserved,untimed*per_request,rel_tol=1e-12,abs_tol=1e-9)),
            'Historical reservation must cover each untimed request exactly once')
    require(isinstance(h.get('reservation_basis'),str) and bool(h['reservation_basis'].strip()),'Historical reservation basis required; reserved time is not observed time')
    require(isinstance(h.get('evidence'),list) and (count==0 or h['evidence']),'Prior request costs require immutable evidence')
    require(isinstance(h.get('scope'),str) and bool(h['scope']),'Historical cost scope must exclude the current run to avoid double counting')
    for ref in h['evidence']:verify_ref(root,ref)
    if count:
        audit=read(verify_ref(root,h.get('timing_evidence')))
        require(audit.get('schema')=='libera_historical_request_timing_audit_v1','Historical timing audit schema required')
        for key in ('generation_requests','recorded_request_seconds','supplemental_recorded_request_seconds','generation_requests_without_timing'):
            require(audit.get(key)==h[key],'Historical timing audit disagrees with approval: '+key)
        require(type(audit.get('timed_generation_requests')) is int and audit['timed_generation_requests']+untimed==count,'Historical timed/untimed counts do not partition the request count')
        require(audit.get('scope')==h['scope'],'Historical timing audit scope differs')
    else:require(seconds==0 and supplemental==0,'Zero historical requests cannot carry observed request time')
    return {'generation_requests':count,'recorded_request_seconds':seconds,
            'supplemental_recorded_request_seconds':supplemental,'generation_requests_without_timing':untimed,
            'request_seconds_reserved_for_missing_timing':reserved}


def accounted_costs(root,approval,raw,timeout):
    """Combine fresh raw costs once; reservations never become observations."""
    require('historical_generation_requests' not in raw,'Historical costs must not be added twice')
    require(type(timeout) in (int,float) and math.isfinite(timeout) and timeout>0,'Frozen request timeout must be positive for unknown-timing reservations')
    historical=historical_costs(root,approval);costs=dict(raw)
    current_reserved=raw['generation_requests_without_timing']*timeout
    historical_reserved=historical['request_seconds_reserved_for_missing_timing']
    costs.update(historical_generation_requests=historical['generation_requests'],
        historical_recorded_request_seconds=historical['recorded_request_seconds'],
        historical_supplemental_recorded_request_seconds=historical['supplemental_recorded_request_seconds'],
        historical_generation_requests_without_timing=historical['generation_requests_without_timing'],
        current_run_recorded_generation_request_seconds=raw['recorded_generation_request_seconds'],
        current_run_request_seconds_reserved_for_missing_timing=current_reserved,
        historical_request_seconds_reserved_for_missing_timing=historical_reserved,
        total_generation_requests_without_timing=raw['generation_requests_without_timing']+historical['generation_requests_without_timing'])
    costs['generation_request_budget_count']+=historical['generation_requests']
    costs['recorded_generation_request_seconds']+=historical['recorded_request_seconds']+historical['supplemental_recorded_request_seconds']
    costs['request_seconds_reserved_for_missing_timing']=current_reserved+historical_reserved
    costs['request_seconds_budget_count']=costs['recorded_generation_request_seconds']+costs['request_seconds_reserved_for_missing_timing']
    return costs


class ProcessLock:
    """One guardian per output directory. Kernel releases lock after a crash."""
    def __init__(self,path):self.path=Path(path);self.handle=None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True);self.handle=self.path.open('a+b')
        if self.path.stat().st_size==0:self.handle.write(b'0');self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt;msvcrt.locking(self.handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl;fcntl.flock(self.handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close();self.handle=None;raise GuardianStop('Another guardian owns the process lock') from exc
        return self
    def __exit__(self,*args):
        if self.handle:
            self.handle.seek(0)
            if os.name=='nt':
                import msvcrt;msvcrt.locking(self.handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl;fcntl.flock(self.handle.fileno(),fcntl.LOCK_UN)
            self.handle.close();self.handle=None


def required_bindings(root,config_path):
    """Read-only evidence for root's review, never an approval or decision."""
    from research.v63.campaign import CODE_FILES,runtime_identity
    from research.v63.build_run import file_ref as campaign_ref
    root=Path(root).resolve();config_path=resolve(root,config_path);config=read(config_path)
    freeze_path=resolve(root,config['runtime_freeze_path']);freeze=read(freeze_path)
    tokenizer=campaign_ref(root/config['tokenizer_config_path'],root)
    run_id,identity=runtime_identity(root,freeze,tokenizer,config['execution_amendment'])
    require('recovery.py' in identity.get('code',{}),'Campaign identity must bind the integrated recovery implementation')
    paths={str(config_path),str(root/'data/french/manifest.json'),str(root/'data/french/monthly_returns.json')}
    french=read(root/'data/french/manifest.json');paths.add(str(root/french['sources']['ff12_returns']['path']))
    for key,value in config.items():
        if key.endswith('_path') and key!='runtime_freeze_path' and isinstance(value,str):paths.add(str(resolve(root,value)))
    paths.add(str(resolve(root,config['execution_amendment']['path'])))
    for name in set(CODE_FILES)|{'recovery.py','pilot_precision.py','longrun_guardian.py',
                                'finalize_experiment_report.py','record_continuation_snapshot.py','build_continuation_report.py'}:
        paths.add(str(root/'research/v63'/name))
    refs=[file_ref(root,p) for p in sorted(paths)]
    versions={name:importlib.metadata.version(name) for name in ['numpy','scipy','cvxpy','clarabel','scikit-learn','jsonschema']}
    return {'config':file_ref(root,config_path),'runtime_identity_sha256':run_id,
            'runtime_freeze_without_main_flag_sha256':freeze_hash(freeze),'model_sha256':freeze['model_sha256'],
            'response_schema_sha256':object_hash(identity['response_schemas']),
            'python_executable':file_ref(root,sys.executable),'python_package_versions':versions,
            'bound_files':refs,'phase_budgets':{p:config['phase_budgets'][p] for p in PHASES}}


def validate_approval(root,config_path,approval_path,expected_sha):
    """No side effects and no model calls; an external hash is mandatory."""
    root=Path(root).resolve();approval_path=resolve(root,approval_path)
    require(isinstance(expected_sha,str) and len(expected_sha)==64,'Explicit root-reviewed approval SHA-256 is required')
    require(approval_path.is_file() and digest(approval_path)==expected_sha,'Resource-review approval hash mismatch or approval absent')
    a=read(approval_path)
    require(a.get('schema')==SCHEMA and a.get('issued_by')=='/root' and a.get('decision')=='authorize_guardian_after_measured_feasibility','Only a root-issued measured-feasibility approval is accepted')
    require(a.get('main_N')==60 and a.get('main_replicates')==2 and a.get('effect_or_pvalue_used_for_selection') is False,'Main N/replicates must remain fixed; effect/p-value selection is forbidden')
    require(a.get('allow_main_only_after_ready_pilot') is True and a.get('recovery_required') is True,'Approval must preserve pilot and recovery gates')
    require(isinstance(a.get('issued_at_utc'),str) and bool(a['issued_at_utc']),'Approval issue time required')
    actual=required_bindings(root,config_path)
    for key in ('config','runtime_identity_sha256','runtime_freeze_without_main_flag_sha256','model_sha256','response_schema_sha256','python_executable','python_package_versions','phase_budgets'):
        require(a.get(key)==actual[key],'Approved binding changed: '+key)
    supplied={str(resolve(root,r['path'])):r for r in a.get('bound_files',[])}
    for ref in actual['bound_files']:
        expected=supplied.get(str(resolve(root,ref['path'])));require(expected==ref,'Required code/data binding absent or changed: '+ref['path'])
    for ref in a.get('bound_files',[]):verify_ref(root,ref)
    limits=a.get('resource_limits',{})
    for key in ('max_total_generation_requests','max_total_request_seconds','max_guardian_wall_seconds','max_prompt_tokens','forecast_safety_factor'):
        v=limits.get(key);require(type(v) in (int,float) and math.isfinite(v) and v>0,'Positive finite resource limit required: '+key)
    require(limits['forecast_safety_factor']>=1,'Forecast safety factor must be at least one')
    historical_costs(root,a)
    for phase in PHASES:
        b=a['phase_budgets'][phase]
        require(all(type(b.get(k)) in (int,float) and math.isfinite(b[k]) and b[k]>0 for k in ('max_generation_requests','max_wall_seconds')),'Invalid phase budget: '+phase)
    config=read(resolve(root,config_path));run_id=a['runtime_identity_sha256']
    for phase in ('technical-smoke','paired-feasibility'):
        evidence=a.get('measurement_evidence',{}).get(phase,{})
        directory=resolve(root,config['output_root'])/'phases'/run_id/phase
        for label,name in [('measurements','measurements.json'),('prepared_inputs','prepared_inputs.json'),('records','records.json'),('runtime_identity','runtime_identity.json')]:
            p=verify_ref(root,evidence.get(label));require(p==(directory/name).resolve(),'Feasibility evidence belongs to another phase/runtime')
        check_phase_outputs(root,config,run_id,phase,limits)
    return a


def check_phase_outputs(root,config,run_id,phase,limits):
    from research.v63.build_run import select_phase_schedule
    directory=resolve(root,config['output_root'])/'phases'/run_id/phase
    m=read(directory/'measurements.json');records=read(directory/'records.json')
    require(m.get('status')=='completed' and m.get('runtime_identity_sha256')==run_id,'Phase is incomplete or uses another identity: '+phase)
    require(m.get('phase_trajectories')==COUNTS[phase] and m.get('terminal_trajectories')==COUNTS[phase],'Wrong measured phase cardinality: '+phase)
    key=lambda r:(r['block'],r['scenario'],r['fund_id'],r['arm'],int(r['replicate']))
    expected={key(r) for r in select_phase_schedule(phase,config['smoke_fund_id'])}
    require(len(records)==COUNTS[phase] and len(expected)==COUNTS[phase] and {key(r) for r in records}==expected,'Missing/extra/duplicate terminal records: '+phase)
    frozen_model=read(resolve(root,config['runtime_freeze_path']))['model_sha256'] if config.get('runtime_freeze_path') else None
    latencies=[];calls=[];stages=Counter();full_history=False;prompt_counts=[]
    for row in records:
        tp=resolve(root,row['trace_path']);require(tp.is_file() and digest(tp)==row.get('trace_sha256'),'Trace content changed: '+str(tp));tr=read(tp)
        require(not tr.get('engineering_only') and tr.get('status') in TERMINAL,'Nonterminal/synthetic trace cannot complete a phase')
        require(tr.get('fund_id')==row['fund_id'] and tr.get('arm')==row['arm'],'Trace owner mismatch')
        require(tr.get('calls') and tr.get('effective_weights') is not None,'Unattempted trace cannot be filled with zero/hold-h')
        for call in tr['calls']:
            response=call.get('raw_response')
            if frozen_model and response and response.get('finish_reason')!='incomplete':
                require(response.get('model_sha256')==frozen_model,'A terminal response uses another model snapshot')
        latencies.append(sum(float(c.get('elapsed_seconds',0)) for c in tr['calls']));calls.append(tr.get('actual_model_calls',len(tr['calls'])))
        stages.update(s.get('status','unknown') for s in tr.get('stages',[]))
        prompt_counts.extend(n for s in tr.get('stages',[]) for n in s.get('prompt_token_counts',[]))
        reached={int(s['stage']) for s in tr.get('stages',[]) if s.get('status') not in {'parent_failure','not_attempted'} and s.get('prompt_token_counts')}
        actual_final_response=any(c.get('stage')==3 and c.get('status')=='response' and
                                  type((c.get('raw_response') or {}).get('usage',{}).get('prompt_eval_count')) is int and
                                  (c.get('raw_response') or {})['usage']['prompt_eval_count']>0
                                  for c in tr['calls'])
        if row['arm']=='C-context' and reached=={1,2,3} and actual_final_response:full_history=True
    require(prompt_counts and all(type(n) is int and n>0 for n in prompt_counts),'Actual positive native prompt counts are required')
    require(m.get('max_observed_prompt_tokens')==max(prompt_counts),'Measured prompt maximum must agree with original traces')
    require(max(prompt_counts)<=limits['max_prompt_tokens'],'Measured prompt exceeds approved capacity')
    if phase in config.get('phase_budgets',{}):
        budget=config['phase_budgets'][phase]
        require(type(m.get('phase_generation_requests')) is int and m['phase_generation_requests']<=budget['max_generation_requests'],'Actual phase requests missing or exceed the approved budget')
        require(type(m.get('cumulative_wall_seconds')) in (int,float) and 0<=m['cumulative_wall_seconds']<=budget['max_wall_seconds'],'Actual phase wall time missing or exceeds the approved budget')
    if phase in ('technical-smoke','paired-feasibility','development-pilot'):
        require(m.get('full_history_observed') is True and full_history,'A real C-context three-stage full-history observation is required')
    if phase in ANALYSIS_STATUS:
        analysis=read(directory/'analysis.json');require(analysis.get('status')==ANALYSIS_STATUS[phase],'Analysis is incomplete/synthetic: '+phase)
        require(not analysis.get('missing') and not analysis.get('nonterminal'),'Analysis retains missing/nonterminal observations')
        if phase=='B-main':require(analysis.get('independent_scenarios')==60 and analysis.get('trajectories')==2400,'Main analysis must retain N60 and 2400 trajectories')
        if phase=='C':require(analysis.get('expected_trajectories')==80 and len(analysis.get('rows',[]))==80,'Combined A/C audit must contain all 80 trajectories')
    require(all(math.isfinite(x) and x>=0 for x in latencies+calls),'Nonfinite or negative measured cost')
    return {'phase':phase,'trajectories':len(records),'mean_generation_requests':sum(calls)/len(calls),
            'mean_request_seconds':sum(latencies)/len(latencies),'max_trajectory_request_seconds':max(latencies),
            'logical_stage_status_counts':dict(stages),'full_history_observed':full_history,
            'measurements':file_ref(root,directory/'measurements.json'),'records':file_ref(root,directory/'records.json'),
            'analysis':file_ref(root,directory/'analysis.json') if phase in ANALYSIS_STATUS else None}


def raw_costs(run_root):
    """Original attempt receipts, never copies or reconstructed replay traces."""
    requests=0;seconds=0.;pending=0;untimed=0
    for folder in Path(run_root).rglob('attempt_*'):
        if not folder.is_dir():continue
        receipt=folder/'attempt_receipt.json'
        if receipt.is_file():
            r=read(receipt);count=r.get('generation_requests');require(type(count) is int and count in (0,1),'Malformed original attempt receipt');requests+=count
        else:pending+=1;count=1 # reserve one possibly-sent request; do not assert it succeeded
        timing=folder/'generation.receipt.json'
        if timing.is_file():
            elapsed=read(timing).get('elapsed_seconds');require(type(elapsed) in (int,float) and math.isfinite(elapsed) and elapsed>=0,'Malformed generation timing');seconds+=elapsed
        elif count:untimed+=count
    return {'confirmed_generation_requests':requests,'possibly_sent_without_receipt':pending,
            'generation_request_budget_count':requests+pending,'recorded_generation_request_seconds':seconds,
            'generation_requests_without_timing':untimed}


def forecast_budget(phase,approval,observed,costs,*,phase_used_requests=0,phase_elapsed_seconds=0.,remaining_trajectories=None):
    limit=approval['phase_budgets'][phase];factor=approval['resource_limits']['forecast_safety_factor'];n=COUNTS[phase] if remaining_trajectories is None else remaining_trajectories
    require(0<=n<=COUNTS[phase] and 0<=phase_used_requests<=limit['max_generation_requests'] and 0<=phase_elapsed_seconds<=limit['max_wall_seconds'],'Invalid or exhausted persisted phase budget')
    forecast={'phase':phase,'trajectories':n,'generation_requests':observed['mean_generation_requests']*n*factor,
              'request_seconds':observed['mean_request_seconds']*n*factor,'safety_factor':factor,
              'basis_phase':observed['phase'],'assumption':'Conditional on comparable cost/failure mix; measured limits continue to be enforced. No effect size or p-value is read.'}
    require(forecast['generation_requests']<=limit['max_generation_requests']-phase_used_requests,'Measured cost forecast exceeds remaining phase request budget: '+phase)
    require(forecast['request_seconds']<=limit['max_wall_seconds']-phase_elapsed_seconds,'Measured request-time forecast exceeds remaining phase wall budget: '+phase)
    # Reserve the full approved phase cap, so total request authority is never
    # inferred from an optimistic forecast. Root can issue a tighter new budget.
    require(costs['generation_request_budget_count']+limit['max_generation_requests']-phase_used_requests<=approval['resource_limits']['max_total_generation_requests'],'Insufficient total request authority to reserve remaining phase cap: '+phase)
    forecast.update(already_used_phase_requests=phase_used_requests,persisted_phase_elapsed_seconds=phase_elapsed_seconds)
    return forecast


def pilot_inputs(root,config,run_id):
    directory=resolve(root,config['output_root'])/'phases'/run_id/'development-pilot'
    return {name:file_ref(root,directory/path) for name,path in [('records','records.json'),('reference_bank','evaluator_only/reference_bank.json'),('scenarios','evaluator_only/frozen_scenarios.json'),('runtime_metadata','frozen_runtime.json')]}


def promote_main(root,config,approval,approval_sha,guardian_dir,pilot_report_path):
    run_id=approval['runtime_identity_sha256'];measured=check_phase_outputs(root,config,run_id,'development-pilot',approval['resource_limits']);p=read(pilot_report_path)
    require(p.get('status')=='development_precision_descriptive_ready' and p.get('ready_for_precision_report') is True and p.get('synthetic_verification') is False,'A real complete pilot precision report is required before main')
    require(p.get('main_N_fixed')==60 and p.get('independent_scenarios')==12 and p.get('expected_trajectories')==240 and not p.get('missing') and not p.get('nonterminal'),'Pilot precision cardinality/identity mismatch')
    require(p.get('frozen_model_sha256')==approval['model_sha256'],'Pilot model differs from approval')
    inputs=pilot_inputs(root,config,run_id);input_receipt=Path(pilot_report_path).with_suffix('.inputs.json')
    proof=read(input_receipt) if input_receipt.is_file() else {}
    require(proof.get('runtime_identity_sha256')==run_id and proof.get('report')==file_ref(root,pilot_report_path) and proof.get('inputs')==inputs,'Pilot report lacks same-run immutable input evidence')
    scenarios=read(resolve(root,inputs['scenarios']['path']));bank=read(resolve(root,inputs['reference_bank']['path']))
    from research.v63.pilot_precision import _hash_object
    require(p.get('input_fingerprint')==_hash_object([[s['scenario_id'] for s in scenarios],[s['r'] for s in scenarios],bank]),'Pilot reference/scenario fingerprint differs')
    require(p.get('runtime_metadata')==read(resolve(root,inputs['runtime_metadata']['path'])),'Pilot runtime metadata differs')
    require(p.get('provenance')=={n:digest(Path(root)/'research/v63'/n) for n in ['pilot_precision.py','evaluate.py','numerics.py','statistics.py']},'Pilot evaluator code differs')
    frozen=resolve(root,config['runtime_freeze_path']);f=read(frozen);require(freeze_hash(f)==approval['runtime_freeze_without_main_flag_sha256'],'Runtime changed before main promotion')
    receipt=Path(guardian_dir)/'main_freeze_transition.json'
    if f.get('main_model_frozen') is True:
        r=read(receipt) if receipt.is_file() else {};require(r.get('approval_sha256')==approval_sha and r.get('after_sha256')==digest(frozen) and r.get('pilot_report_sha256')==digest(pilot_report_path),'Main was frozen outside this validated guardian transition')
        review=read(verify_ref(root,r.get('resource_review')))
        require(review.get('approval_sha256')==approval_sha and set(review.get('phase_forecasts',{}))==set(PHASES[1:]),'Main resource review is missing or changed')
        return
    require(f.get('main_model_frozen') is False,'Initial main freeze must explicitly be false')
    costs=accounted_costs(root,approval,raw_costs(resolve(root,config['output_root'])/'runs'/run_id),f.get('request_timeout'))
    forecasts={phase:forecast_budget(phase,approval,measured,costs) for phase in PHASES[1:]}
    reserved_requests=sum(approval['phase_budgets'][phase]['max_generation_requests'] for phase in PHASES[1:])
    require(costs['generation_request_budget_count']+reserved_requests<=approval['resource_limits']['max_total_generation_requests'],'Total authority cannot reserve every remaining phase cap before main')
    projected_seconds=sum(row['request_seconds'] for row in forecasts.values())
    require(costs['request_seconds_budget_count']+projected_seconds<=approval['resource_limits']['max_total_request_seconds'],'All remaining phase time forecasts plus observed and reserved costs exceed total resource authority')
    resource_review=Path(guardian_dir)/'main_resource_review.json'
    write(resource_review,{'approval_sha256':approval_sha,'runtime_identity_sha256':run_id,'at_utc':now(),'development_measurements':measured['measurements'],'phase_forecasts':forecasts,'actual_costs_before_main':costs,'remaining_phase_request_caps_reserved':reserved_requests,'conditional_remaining_request_seconds':projected_seconds,'effect_or_pvalue_read_for_decision':False})
    before=digest(frozen);f['main_model_frozen']=True;write(frozen,f)
    write(receipt,{'at_utc':now(),'approval_sha256':approval_sha,'runtime_identity_sha256':run_id,
                   'before_sha256':before,'after_sha256':digest(frozen),'pilot_report_sha256':digest(pilot_report_path),
                   'development_measurements':measured['measurements'],'changed_fields':['main_model_frozen'],
                   'resource_review':file_ref(root,resource_review),
                   'effect_or_pvalue_read_for_decision':False})


class Guardian:
    def __init__(self,root,config_path,approval_path,approval_sha,*,heartbeat_seconds=10):
        self.root=Path(root).resolve();self.config_path=resolve(root,config_path);self.approval_path=resolve(root,approval_path);self.approval_sha=approval_sha
        self.approval=validate_approval(self.root,self.config_path,self.approval_path,approval_sha);self.config=read(self.config_path)
        self.run_id=self.approval['runtime_identity_sha256'];self.output=resolve(root,self.config['output_root']);self.directory=self.output/'guardian'/self.run_id
        self.phase_root=self.output/'phases'/self.run_id;self.run_root=self.output/'runs'/self.run_id
        require(1<=heartbeat_seconds<=60,'Heartbeat must be between 1 and 60 seconds');self.interval=heartbeat_seconds;self.process=None
        self.directory.mkdir(parents=True,exist_ok=True);self.state_path=self.directory/'checkpoint.json';self.state=read(self.state_path) if self.state_path.exists() else {'approval_sha256':approval_sha,'run_id':self.run_id,'started_at_utc':now(),'completed_phases':[],'elapsed_guardian_seconds':0.,'attempts':[]}
        require(self.state.get('approval_sha256')==approval_sha and self.state.get('run_id')==self.run_id,'Checkpoint belongs to a different approval/runtime');self.start=time.monotonic();self.prior_elapsed=self.state.get('elapsed_guardian_seconds',0.)
    def reload_checkpoint(self):
        # __init__ is read-only except for mkdir. A second process may finish
        # between construction and lock acquisition, so never reuse stale state.
        if self.state_path.exists():self.state=read(self.state_path)
        require(self.state.get('approval_sha256')==self.approval_sha and self.state.get('run_id')==self.run_id,'Checkpoint belongs to a different approval/runtime')
        completed=self.state.get('completed_phases',[])
        require(completed==list(PHASES[:len(completed)]),'Checkpoint phase order is not a valid completed prefix')
        self.prior_elapsed=self.state.get('elapsed_guardian_seconds',0.);self.start=time.monotonic()
    def heartbeat(self,status,phase=None,**extra):
        self.state.update(status=status,phase=phase,updated_at_utc=now(),pid=os.getpid(),child_pid=self.process.pid if self.process else None,
                          elapsed_guardian_seconds=self.prior_elapsed+time.monotonic()-self.start,**extra)
        write(self.state_path,self.state);write(self.directory/'heartbeat.json',{k:self.state[k] for k in ('status','phase','updated_at_utc','pid','child_pid','elapsed_guardian_seconds')})
    def unchanged(self):
        validate_approval(self.root,self.config_path,self.approval_path,self.approval_sha)
    def limits(self,phase=None):
        lim=self.approval['resource_limits']
        timeout=read(resolve(self.root,self.config['runtime_freeze_path'])).get('request_timeout',0)
        costs=accounted_costs(self.root,self.approval,raw_costs(self.run_root),timeout)
        require(costs['generation_request_budget_count']<=lim['max_total_generation_requests'],'Total generation request budget reached')
        require(costs['request_seconds_budget_count']<=lim['max_total_request_seconds'],'Total request-time budget including untimed request reservations reached')
        require(self.prior_elapsed+time.monotonic()-self.start<=lim['max_guardian_wall_seconds'],'Guardian cumulative active wall-time budget reached')
        return costs
    def phase_usage(self,phase):
        """Original campaign ledger includes downtime and survives restarts."""
        from research.v63.campaign_control import budget_elapsed,final_trace_path
        from research.v63.build_run import select_phase_schedule
        directory=self.phase_root/phase;budget_path=directory/'budget_state.json'
        used=0;elapsed=0.;remaining=COUNTS[phase]
        if budget_path.exists():
            state=read(budget_path);require(state['limits']==self.approval['phase_budgets'][phase],'Persisted phase budget changed')
            elapsed=budget_elapsed(state)
        # Technical/paired trajectories are reused in development even before
        # development has a prepared_inputs file. Count their original costs once.
        for entry in select_phase_schedule(phase,self.config['smoke_fund_id']):
            case_id=entry['scenario']+'__'+entry['fund_id']
            path=self.run_root/entry['block']/(case_id+'__'+entry['arm']+'__'+str(entry['replicate']))
            used+=raw_costs(path)['generation_request_budget_count']
            trace_path=final_trace_path(path)
            if trace_path is not None:
                trace=read(trace_path)
                require(trace.get('fund_id')==entry['fund_id'] and trace.get('arm')==entry['arm'],'Existing trace owner differs before resume')
                if trace.get('status') in TERMINAL and trace.get('calls'):remaining-=1
        return {'phase_used_requests':used,'phase_elapsed_seconds':elapsed,'remaining_trajectories':remaining}
    def subprocess(self,command,label,max_wall):
        self.unchanged();log=self.directory/'logs'/f'{len(self.state["attempts"])+1:03d}_{label}.log';log.parent.mkdir(exist_ok=True)
        self.state['attempts'].append({'label':label,'command':command,'log_path':str(log),'started_at_utc':now(),'elapsed_seconds':0.});started=time.monotonic();code=None
        self.heartbeat('launching',label)
        with log.open('ab',buffering=0) as handle:
            self.process=subprocess.Popen(command,cwd=self.root,stdout=handle,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0)
            try:
                while self.process.poll() is None:
                    self.state['attempts'][-1]['elapsed_seconds']=time.monotonic()-started
                    self.heartbeat('running',label,actual_costs=self.limits(label));require(time.monotonic()-started<=max_wall,'Subprocess wall-time cap reached: '+label)
                    # Fast binding checks every poll; full approval/trace validation
                    # is repeated before and after each phase.
                    for ref in self.approval['bound_files']:verify_ref(self.root,ref)
                    require(freeze_hash(read(resolve(self.root,self.config['runtime_freeze_path'])))==self.approval['runtime_freeze_without_main_flag_sha256'],'Runtime parameters changed while running')
                    try:self.process.wait(timeout=self.interval)
                    except subprocess.TimeoutExpired:pass
                code=self.process.returncode
            except BaseException:
                self.state['attempts'][-1]['interruption_cleanup']=stop_owned_process_tree(self.process)
                raise
            finally:
                self.state['attempts'][-1].update(returncode=self.process.returncode,ended_at_utc=now(),elapsed_seconds=time.monotonic()-started)
                self.process=None;self.heartbeat('subprocess_finished' if code==0 else 'subprocess_interrupted',label)
        self.heartbeat('subprocess_finished',label,actual_costs=self.limits(label))
        require(code==0,'Phase stopped/incomplete; restart uses campaign recovery without deleting prior artifacts: '+label)
        self.unchanged()
    def run(self):
        with ProcessLock(self.output/'.longrun_guardian.lock'),system_awake() as awake:
            try:
                self.reload_checkpoint();self.state['temporary_system_sleep_prevention']=awake
                self.unchanged();f=read(resolve(self.root,self.config['runtime_freeze_path']))
                precision=self.directory/'pilot_precision_report.json'
                if f.get('main_model_frozen') is True:
                    require((self.directory/'main_freeze_transition.json').is_file(),'Initial main auto-authorization is forbidden')
                    promote_main(self.root,self.config,self.approval,self.approval_sha,self.directory,precision)
                observed=check_phase_outputs(self.root,self.config,self.run_id,'paired-feasibility',self.approval['resource_limits'])
                for phase in PHASES:
                    self.unchanged();costs=self.limits(phase)
                    if phase in self.state['completed_phases']:
                        observed=check_phase_outputs(self.root,self.config,self.run_id,phase,self.approval['resource_limits']);continue
                    if phase=='B-main':
                        if not precision.is_file():
                            d=self.phase_root/'development-pilot'
                            command=[sys.executable,'-m','research.v63.pilot_precision','--records',str(d/'records.json'),'--reference-bank',str(d/'evaluator_only/reference_bank.json'),'--scenarios',str(d/'evaluator_only/frozen_scenarios.json'),'--model-sha256',self.approval['model_sha256'],'--runtime-metadata',str(d/'frozen_runtime.json'),'--output',str(precision)]
                            self.subprocess(command,'pilot-precision',self.approval['phase_budgets']['development-pilot']['max_wall_seconds'])
                            write(precision.with_suffix('.inputs.json'),{'runtime_identity_sha256':self.run_id,'report':file_ref(self.root,precision),'inputs':pilot_inputs(self.root,self.config,self.run_id)})
                        forecast=forecast_budget(phase,self.approval,observed,costs,**self.phase_usage(phase))
                        promote_main(self.root,self.config,self.approval,self.approval_sha,self.directory,precision)
                    else:forecast=forecast_budget(phase,self.approval,observed,costs,**self.phase_usage(phase))
                    self.heartbeat('phase_starting',phase,cost_forecast=forecast,actual_costs=costs)
                    self.subprocess([sys.executable,'-m','research.v63.campaign',str(self.config_path),'--phase',phase],phase,self.approval['phase_budgets'][phase]['max_wall_seconds']-forecast['persisted_phase_elapsed_seconds'])
                    observed=check_phase_outputs(self.root,self.config,self.run_id,phase,self.approval['resource_limits'])
                    self.state['completed_phases'].append(phase);self.state.setdefault('phase_evidence',{})[phase]=observed;self.heartbeat('phase_completed',phase)
                all_evidence={p:check_phase_outputs(self.root,self.config,self.run_id,p,self.approval['resource_limits']) for p in PHASES}
                self.unchanged();self.limits();promote_main(self.root,self.config,self.approval,self.approval_sha,self.directory,precision)
                remaining_wall=self.approval['resource_limits']['max_guardian_wall_seconds']-(self.prior_elapsed+time.monotonic()-self.start)
                self.subprocess([sys.executable,'-m','research.v63.finalize_experiment_report','--output-root',str(self.output),'--run-id',self.run_id,
                                 '--config',str(self.config_path),'--approval',str(self.approval_path),'--approval-sha256',self.approval_sha],'final-report',remaining_wall)
                final_path=self.root/'data/v63_20261027/final_results.json';final=read(final_path)
                require(final.get('status')=='completed_real_experiments' and final.get('run_id')==self.run_id and final.get('terminal_trajectories')==3272 and final.get('planned_logical_stages')==9816,'Final report does not certify the same complete run')
                receipt={'status':'all_required_phases_and_analyses_completed','completed_at_utc':now(),'approval':file_ref(self.root,self.approval_path),'runtime_identity_sha256':self.run_id,'main_N':60,'main_replicates':2,'phases':all_evidence,'pilot_precision':file_ref(self.root,precision),'actual_costs':self.limits(),'conclusions':'Read the preserved analysis artifacts; completion does not imply rejection, superiority or a recommendation.','effect_or_pvalue_used_for_selection':False,'missing_filled_with_zero_or_h':False}
                receipt['final_results']=file_ref(self.root,final_path)
                write(self.directory/'completion_receipt.json',receipt);self.heartbeat('completed');return receipt
            except BaseException as exc:
                self.heartbeat('stopped_requires_review_or_same_identity_resume',self.state.get('phase'),error_type=type(exc).__name__,error=str(exc));raise


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);p.add_argument('--config',type=Path,required=True);p.add_argument('--approval',type=Path,required=True);p.add_argument('--approval-sha256',required=True);p.add_argument('--heartbeat-seconds',type=float,default=10);a=p.parse_args()
    try:result=Guardian(a.root,a.config,a.approval,a.approval_sha256,heartbeat_seconds=a.heartbeat_seconds).run();print(json.dumps({'status':result['status']}));return 0
    except (GuardianStop,OSError,ValueError,KeyError) as exc:print(json.dumps({'status':'guardian_stopped','error_type':type(exc).__name__,'error':str(exc)}));return 2


if __name__=='__main__':raise SystemExit(main())
