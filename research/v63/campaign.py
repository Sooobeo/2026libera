"""Source-qualified v6.3 campaign orchestration; resumable, phase-gated real calls.

Usage: python -m research.v63.campaign CONFIG.json --phase technical-smoke
       python -m research.v63.campaign CONFIG.json --phase all
The same-hash development trajectories are reused across 15/60/720-stage phases.
No unattempted trajectory is converted to a hold-h result. Existing files and
the original v6.3 protocol are never overwritten by a different run identity.
"""
from __future__ import annotations
import os
# This process performs only small 12-dimensional numerical operations. Limit
# BLAS worker buffers before importing NumPy; the separate inference server's
# explicit num_thread option is unaffected. This is part of the code identity.
for _numeric_thread_variable in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[_numeric_thread_variable]='1'
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import importlib.metadata
from pathlib import Path
import time

from research.v63 import numerics,evaluate
from research.v63.build_run import (PHASES,read_json,save_json,file_ref,build_phase,b_input,make_numeric_callbacks)
from research.v63.exact_tokenizer import NativeTokenizer
from research.v63.ollama_transport import OllamaTransport,packed,digest_bytes
from research.v63.retrieval import TokenCounter,canonical,sha
from research.v63.runtime import run_trajectory,response_schema,evidence_for_stage,gate_errors
from research.v63.transport_errors import ProtocolViolation
from research.v63.campaign_control import campaign_lock,phase_budget,budget_elapsed,task_request_cost,final_trace_path,merged_history,immutable_json,verify_frozen_artifacts,TERMINAL_STATUSES,BLOCKED_STATUSES
from research.v63.recovery import RecoveryClient

TERMINAL=TERMINAL_STATUSES
CODE_FILES=('campaign.py','campaign_control.py','recovery.py','build_run.py','runtime.py','retrieval.py','numerics.py','evaluate.py','statistics.py','pilot_precision.py','ollama_transport.py','exact_tokenizer.py','transport_errors.py')

def now():return datetime.now(timezone.utc).isoformat()

def validate_phase_freeze(freeze,phase,config=None):
    if phase=='B-main' and (config or {}).get('direct_main_no_preliminary_validation') is True:
        return
    if phase not in PHASES[:3] and freeze.get('main_model_frozen') is not True:
        raise ValueError('Main execution requires main_model_frozen=true after development resource review.')

def verify_amendment(root,ref):
    path=root/ref['path']
    if numerics.sha256(path)!=ref['sha256']:raise ValueError('Execution amendment hash mismatch.')
    amendment=read_json(path)
    if amendment.get('human_review_mode')!='user_assumed_completed' or amendment.get('human_review_gate_satisfied_by_user_assumption') is not True:
        raise ValueError('This campaign requires the explicit user assumption amendment.')
    return amendment

def runtime_identity(root,freeze,tokenizer_ref,amendment_ref,config=None):
    fields=('model','model_sha256','engine_revision','chat_template_sha256','quantization_level','context_tokens',
            'temperature','seed_support','seed','output_tokens','request_timeout','think','fixed_options','execution_environment')
    identity={key:freeze.get(key) for key in fields}
    identity.update(tokenizer_sha256=tokenizer_ref['sha256'],amendment_sha256=amendment_ref['sha256'],
                    code={name:numerics.sha256(root/'research/v63'/name) for name in CODE_FILES},
                    response_schemas=[response_schema(i) for i in (1,2,3)])
    if (config or {}).get('direct_main_no_preliminary_validation') is True:
        identity['direct_main']={key:config.get(key) for key in (
            'main_direct_design','weight_policy','skip_duplicate_render_identity','allow_infrastructure_retries')}
        identity['direct_main']['design_manifest']=file_ref(root/config['design_manifest_path'],root)
        paths=('research/v64_reduced/design.py','research/v64_reduced/runtime.py',
               'research/v64_reduced/policy.py','research/v64_reduced/analysis.py',
               'research/v63/start_direct_main.py')
        identity['direct_main']['code']={path:numerics.sha256(root/path) for path in paths}
    return sha(canonical(identity)),identity

def normalized_input_hash(case,arm,identity):
    obj={'baseline':case['baseline'],'stage_evidence':[evidence_for_stage(case['retrieval'],arm,i) for i in (1,2,3)],
         'tool_access':'posterior(exposed IDs), check_portfolio(raw weights, exposed IDs)',
         'response_schemas':[response_schema(i) for i in (1,2,3)],'runtime':identity}
    # Hashes in packets encode the changing virtual label. Normalize text first,
    # then recompute hashes, rather than retaining label-specific hash strings.
    for view in obj['stage_evidence']:
        view.pop('sha256',None)
    text=canonical(obj)
    for label in ('N01','N02','N03','N04'):text=text.replace(label,'NXX')
    return sha(text)

def build_bank(package,tokenizer):
    """Compute evaluator-only references before the first request of the phase."""
    phase=package['phase']
    if phase in {'A','C'}:return {}
    cases=package['cases'];cal=package['calibration'];wanted={r['scenario'] for r in package['entries']}
    scenarios=[s for s in package['scenarios_evaluator_only'] if s['scenario_id'] in wanted]
    bank={}
    for s in scenarios:
        sid=s['scenario_id'];profiles=package['profiles'];scenario=deepcopy(s)
        if phase=='negative-control':
            index=int(sid.rsplit('-',1)[1])-1;source=f'F{index%4+1:02d}'
            profiles={f'N{i:02d}':{**deepcopy(package['profiles'][source]),'fund_id':f'N{i:02d}'} for i in range(1,5)}
            own=scenario['private_signals']['F01'];scenario['private_signals']={label:own.copy() for label in profiles}
        exposed={sid:{}}
        for fund,profile in profiles.items():
            key=sid+'__'+fund
            case=cases.get(key)
            if case is None:case=b_input(profile,cal,scenario,tokenizer,fund_id=fund,mandate_units=package.get('mandate_units_audit',{}))
            exposed[sid][fund]=[case['evidence_registry'][e] for e in case['retrieval']['packet']['exposed_evidence_ids'] if e in case['evidence_registry']]
        bank.update(evaluate.build_reference_bank(cal,[scenario],profiles,exposed))
    return bank

def scan_run_costs(run_root):
    cost=task_request_cost(run_root);prompt=0;generated=0;seconds=0
    paths={final_trace_path(p.parent) for p in Path(run_root).rglob('input_identity.json')}
    for path in paths-{None}:
        trace=read_json(path)
        for event in trace.get('calls',[]):
            seconds+=event.get('elapsed_seconds',0)
            usage=event.get('raw_response',{}).get('usage',{}) or {}
            prompt+=usage.get('prompt_eval_count',0) or 0;generated+=usage.get('eval_count',0) or 0
    return {**cost,'prompt_tokens':prompt,'generated_tokens':generated,'request_elapsed_seconds':seconds}

def phase_measurements(records,entries,started):
    traces=[read_json(r['trace_path']) for r in records]
    completed=sum(t.get('status') in TERMINAL for t in traces)
    full_history=any(r['arm']=='C-context' and any(e.get('stage')==3 and e.get('status')=='response' and
                     e.get('raw_response',{}).get('usage',{}).get('prompt_eval_count') is not None
                     for e in t.get('calls',[])) for r,t in zip(records,traces))
    prompts=[n for t in traces for s in t.get('stages',[]) for n in s.get('prompt_token_counts',[])]
    return {'recorded_at_utc':now(),'phase_trajectories':len(entries),'terminal_trajectories':completed,
            'status':'completed' if completed==len(entries) else 'incomplete','full_history_observed':full_history,
            'terminal_status_counts':{status:sum(t.get('status')==status for t in traces) for status in TERMINAL|BLOCKED_STATUSES},
            'max_observed_prompt_tokens':max(prompts,default=0),'wall_seconds_this_phase':time.monotonic()-started,
            'model_generation_requests_in_traces':sum(t.get('experimental_model_calls',0) for t in traces)}

def run_phase(root,config,phase,native):
    root=Path(root).resolve();freeze=read_json(root/config['runtime_freeze_path'])
    run_id,_=runtime_identity(root,freeze,file_ref(root/config['tokenizer_config_path'],root),config['execution_amendment'],config)
    with campaign_lock(root/config['output_root']/'runs'/run_id/'.campaign.lock'):
        return _run_phase_locked(root,config,phase,native,run_id)

def _run_phase_locked(root,config,phase,native,locked_run_id):
    root=Path(root).resolve();out=root/config['output_root'];out.mkdir(parents=True,exist_ok=True)
    if config.get('direct_main_no_preliminary_validation') is True:
        from research.v64_reduced.design import make_main_only_design,validate_design
        manifest=read_json(root/config['design_manifest_path'])
        expected={'precision_levels':[.5,2.],'samples_per_precision':5,'replicates':1,
                  'arms':['R0','R1','R2','R3']}
        if (phase!='B-main' or manifest.get('status')!='USER_SCOPE_CONFIRMED'
                or validate_design(manifest.get('design'))!=make_main_only_design()
                or config.get('main_direct_design')!=expected
                or config.get('weight_policy')!='normalize_nonnegative_then_recheck'
                or config.get('skip_duplicate_render_identity') is not True
                or config.get('allow_infrastructure_retries') is not False):
            raise ValueError('Direct-main configuration differs from the selected scope/call policy.')
    amendment=verify_amendment(root,config['execution_amendment'])
    freeze=read_json(root/config['runtime_freeze_path'])
    validate_phase_freeze(freeze,phase,config)
    tokenizer_ref=file_ref(root/config['tokenizer_config_path'],root)
    run_id,identity=runtime_identity(root,freeze,tokenizer_ref,config['execution_amendment'],config)
    if run_id!=locked_run_id:raise ValueError('Frozen source/config changed while acquiring the run lock.')
    run_root=out/'runs'/run_id;phase_dir=out/'phases'/run_id/phase;phase_dir.mkdir(parents=True,exist_ok=True)
    verify_frozen_artifacts(root,phase_dir/'frozen_runtime.json')
    source_paths=[config[k] for k in ('profiles_path','documents_path','mandate_atomic_units_path','source_catalog_path') if config.get(k)]
    if identity.get('direct_main'):
        source_paths+=list(identity['direct_main']['code'])
    french_manifest=read_json(root/'data/french/manifest.json')
    source_paths+=['data/french/manifest.json','data/french/monthly_returns.json',french_manifest['sources']['ff12_returns']['path']]
    source_refs=[file_ref(root/path,root) for path in sorted(set(source_paths))]
    immutable_json(run_root/'source_input_manifest.json',{'sources':source_refs,'smoke_fund_id':config['smoke_fund_id']})
    source_snapshot=phase_dir/'source_snapshot';source_snapshot.mkdir(exist_ok=True)
    for name,expected in identity['code'].items():
        content=(root/'research/v63'/name).read_bytes()
        if digest_bytes(content)!=expected:raise ValueError('Source changed before its immutable snapshot.')
        path=source_snapshot/name
        if path.exists() and path.read_bytes()!=content:raise ValueError('Frozen source snapshot changed.')
        path.write_bytes(content)
    save_json(source_snapshot/'manifest.json',identity['code'])
    for relative,expected in identity.get('direct_main',{}).get('code',{}).items():
        content=(root/relative).read_bytes()
        if digest_bytes(content)!=expected:raise ValueError('Selected direct-main source changed before snapshot.')
        path=source_snapshot/'prospective'/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists() and path.read_bytes()!=content:raise ValueError('Selected direct-main source snapshot changed.')
        path.write_bytes(content)
    if identity.get('direct_main'):
        immutable_json(source_snapshot/'prospective_manifest.json',identity['direct_main']['code'])
    environment_ref=None
    if config.get('execution_environment_path'):
        environment_ref=file_ref(root/config['execution_environment_path'],root)
        if read_json(root/config['execution_environment_path'])!=freeze.get('execution_environment'):
            raise ValueError('Execution environment differs from frozen candidate.')
        for item in freeze['execution_environment'].get('binary_artifacts',[]):
            if numerics.sha256(root/item['path'])!=item['sha256']:raise ValueError('Execution binary artifact changed.')
        for name,expected in freeze['execution_environment'].get('python_environment',{}).items():
            if os.environ.get(name)!=expected:raise ValueError('Frozen numeric environment differs: '+name)
        for name,expected in freeze['execution_environment'].get('python_packages',{}).items():
            if importlib.metadata.version(name)!=expected:raise ValueError('Frozen Python package version differs: '+name)
    counter=TokenCounter(native.identity,native.count,True)
    started=time.monotonic()
    direct_main = phase == 'B-main' and config.get('direct_main_no_preliminary_validation') is True
    if direct_main:
        from research.v64_reduced.design import build_phase as build_selected_phase
        package=build_selected_phase(root,config,phase,counter)
    else:
        package=build_phase(root,config,phase,counter)
    package_path=phase_dir/'prepared_inputs.json'
    serial=numerics.jsonable({k:v for k,v in package.items() if k not in {'scenarios_evaluator_only','hidden_evaluator_only'}})
    if package_path.exists() and read_json(package_path)!=serial:raise ValueError('Prepared inputs changed under an existing runtime identity; create a new frozen config/version.')
    immutable_json(package_path,serial)
    evaluation_dir=phase_dir/'evaluator_only';evaluation_dir.mkdir(exist_ok=True)
    bank_path=evaluation_dir/'reference_bank.json'
    bank_receipt=evaluation_dir/'reference_bank_receipt.json'
    if bank_path.exists():
        if not bank_receipt.is_file() or read_json(bank_receipt)!=file_ref(bank_path,root):
            raise ValueError('Existing reference bank lacks its original matching hash receipt.')
        bank=read_json(bank_path)
    else:
        bank=build_bank(package,counter);save_json(bank_path,bank)
        immutable_json(bank_receipt,file_ref(bank_path,root))
    immutable_json(evaluation_dir/'frozen_scenarios.json',numerics.jsonable(package['scenarios_evaluator_only']))
    immutable_json(evaluation_dir/'hidden_truth.json',numerics.jsonable(package['hidden_evaluator_only']))
    budget=config['phase_budgets'][phase]
    if budget.get('max_generation_requests',0)<=0 or budget.get('max_wall_seconds',0)<=0:raise ValueError('An executable phase budget is required.')
    previous=out/'phases'/run_id/'development-pilot'/'measurements.json'
    full_main=phase not in PHASES[:3]
    prior=read_json(previous) if previous.is_file() else {}
    direct_main = phase == 'B-main' and config.get('direct_main_no_preliminary_validation') is True
    if full_main and not direct_main and (prior.get('status')!='completed' or prior.get('full_history_observed') is not True):
        raise ValueError('Main/counterfactual/negative/A/C phases require the completed same-version 720-stage development pilot with full-history evidence.')
    if phase=='paired-feasibility':required_previous='technical-smoke'
    elif phase=='development-pilot':required_previous='paired-feasibility'
    else:required_previous=None
    if required_previous:
        previous_measure=out/'phases'/run_id/required_previous/'measurements.json'
        if not previous_measure.is_file() or read_json(previous_measure).get('status')!='completed':
            raise ValueError('Previous staged development phase is incomplete: '+required_previous)
    freeze.update(workspace_root=str(root),execution_phase=phase,human_review_mode='user_assumed_completed',
                  execution_amendment=config['execution_amendment'],tokenizer_sha256=tokenizer_ref['sha256'],
                  tool_schema_sha256=sha(canonical([response_schema(i) for i in (1,2,3)])),
                  allowed_response_schema_sha256=[digest_bytes(packed(response_schema(i))) for i in (1,2,3)],
                  artifacts=[file_ref(p,root) for p in (package_path,bank_path,bank_receipt,evaluation_dir/'frozen_scenarios.json',evaluation_dir/'hidden_truth.json',run_root/'source_input_manifest.json')]+source_refs+[tokenizer_ref,config['execution_amendment']]+([environment_ref] if environment_ref else []),
                  gates={name:True for name in ('complete_sources','holdings_and_constraints','human_audit','numerical_verification',
                         'retrieval_validation','information_boundary','model_snapshot','budget','sample_plan_and_analysis','input_manifest')})
    freeze['gates'].update(pilot_measurements=(prior.get('status')=='completed'),
                           full_history_capacity=(prior.get('full_history_observed') is True))
    if direct_main:
        freeze['direct_main_authorization']={
            'user_requested_no_preliminary_validation':True,
            'preliminary_phases_skipped':True,
            'results_are_main_experiment':True,
        }
        freeze.update(skip_duplicate_render_identity=config.get('skip_duplicate_render_identity',False),
                      allow_infrastructure_retries=config.get('allow_infrastructure_retries',True))
        freeze['artifacts'].append(file_ref(root/config['design_manifest_path'],root))
    if direct_main:
        from research.v64_reduced.runtime import execution_gate_errors
        errors=execution_gate_errors(freeze)
    else:
        errors=gate_errors(freeze)
    if errors:raise ValueError('Execution prerequisites: '+', '.join(errors))
    save_json(phase_dir/'frozen_runtime.json',freeze);save_json(phase_dir/'runtime_identity.json',identity)
    records=[];budget_state=phase_budget(phase_dir/'budget_state.json',budget)
    task_paths={run_root/e['block']/(e['case_id']+'__'+e['arm']+'__'+str(e['replicate'])) for e in package['entries']}
    run_costs=scan_run_costs(run_root)
    task_costs={path:scan_run_costs(path) for path in task_paths}
    def phase_requests():return sum(value['generation_requests'] for value in task_costs.values())
    def refresh_cost(path):
        old=task_costs[path];new=scan_run_costs(path)
        for key in run_costs:run_costs[key]+=new[key]-old[key]
        task_costs[path]=new
    progress_path=phase_dir/'progress.json'
    def progress(current_task,status):
        value={'phase':phase,'run_id':run_id,'current_task':current_task,'status':status,
               'updated_at_utc':now(),'planned_trajectories':len(package['entries']),
               'recorded_trajectories':len(records),'terminal_counts':{status:sum(r.get('trajectory_status')==status for r in records) for status in TERMINAL|BLOCKED_STATUSES},
               'cumulative_wall_seconds':budget_elapsed(budget_state),
               'phase_generation_requests':phase_requests(),'budget_limits':budget_state['limits'],
               'actual_costs':run_costs}
        save_json(progress_path,value)
        save_json(out/'progress.json',value)
    progress(None,'preflight_complete')
    for entry in package['entries']:
        case=package['cases'][entry['case_id']]
        task_id=entry['case_id']+'__'+entry['arm']+'__'+str(entry['replicate'])
        task_dir=run_root/entry['block']/task_id
        fingerprint=sha(canonical({'input':entry['input_sha256'],'arm':entry['arm'],'replicate':entry['replicate'],'identity':identity}))
        trace_path=final_trace_path(task_dir)
        identity_path=task_dir/'input_identity.json'
        if identity_path.exists() and read_json(identity_path).get('sha256')!=fingerprint:
            raise ValueError('Cannot reuse a trajectory with changed model/input/code.')
        if trace_path is not None:
            if not identity_path.is_file():
                raise ValueError('Cannot reuse a trajectory with changed model/input/code.')
            trace=read_json(trace_path)
        else:
            elapsed=budget_elapsed(budget_state);used=phase_requests()
            worst_case=9 if direct_main and not config.get('allow_infrastructure_retries',True) else 27
            reserve=max(0,worst_case-task_costs[task_dir]['generation_requests'])
            if elapsed>=budget['max_wall_seconds'] or used+reserve>budget['max_generation_requests']:
                save_json(phase_dir/'budget_stop.json',{'status':'not_attempted_budget_stop','elapsed':elapsed,'used_generation_requests':used,
                                                     'next_trajectory':task_id,'reason':'Reserve a complete worst-case trajectory before launch.'})
                progress(task_id,'budget_stop')
                break
            task_dir.mkdir(parents=True,exist_ok=True)
            save_json(task_dir/'input_identity.json',{'sha256':fingerprint,'entry':entry,'human_review_mode':'user_assumed_completed'})
            save_json(task_dir/'input_case.json',case)
            progress(task_id,'running')
            partial=(task_dir/'trajectory').exists() or (task_dir/'http').exists() or any(task_dir.glob('recovery_*'))
            if partial:
                index=1
                while (task_dir/f'recovery_{index:03d}').exists():index+=1
                recovery_dir=task_dir/f'recovery_{index:03d}'
                history_dir=merged_history(task_dir,phase_dir/'recovery_inputs'/task_id/f'history_{index:03d}')
                transport=OllamaTransport(config['origin'],freeze,recovery_dir/'http')
                client=RecoveryClient(history_dir,freeze,transport,history_quiescent=True)
                trajectory_dir=recovery_dir/'trajectory'
            else:
                transport=OllamaTransport(config['origin'],freeze,task_dir/'http');client=transport
                trajectory_dir=task_dir/'trajectory'
            tools,check=make_numeric_callbacks(case)
            trajectory_args=dict(output_dir=trajectory_dir,
                count_rendered_request=lambda request:transport.render_and_count(request,native),engineering=False)
            if direct_main:
                from research.v64_reduced.runtime import run_trajectory as run_selected_trajectory
                trace=run_selected_trajectory(case['baseline'],case['retrieval'],entry['arm'],client,tools,check,freeze,**trajectory_args)
            else:
                trace=run_trajectory(case['baseline'],case['retrieval'],entry['arm'],client,tools,check,freeze,
                    normalize_weights=config.get('weight_policy')=='normalize_nonnegative_then_recheck',**trajectory_args)
            trace_path=trajectory_dir/'trace.json'
            if isinstance(client,RecoveryClient):save_json(recovery_dir/'recovery_receipt.json',client.recovery_receipt())
            save_json(task_dir/'trace_pointer.json',{'relative_path':trace_path.relative_to(task_dir).as_posix(),'sha256':numerics.sha256(trace_path)})
        record={k:entry[k] for k in ('block','scenario','fund_id','arm','replicate')}
        record.update(trace_path=str(trace_path.resolve()),trace_sha256=numerics.sha256(trace_path),input_sha256=entry['input_sha256'],
                      normalized_input_sha256=normalized_input_hash(case,entry['arm'],identity),trajectory_status=trace.get('status'))
        records.append(record);save_json(phase_dir/'records.json',records)
        refresh_cost(task_dir)
        progress(task_id,trace.get('status','unknown'))
        if trace.get('status') not in TERMINAL:break
    measurements=phase_measurements(records,package['entries'],started)
    measurements.update(all_attempt_costs=run_costs,runtime_identity_sha256=run_id,
                        phase_generation_requests=phase_requests(),cumulative_wall_seconds=budget_elapsed(budget_state),
                        human_review_mode='user_assumed_completed',actual_independent_human_reviews_claimed=False)
    save_json(phase_dir/'measurements.json',measurements)
    progress(None,measurements['status'])
    if phase=='B-main':
        if direct_main:
            from research.v64_reduced.analysis import analyze_phase
            analyze_phase(root,config,phase_dir,package,records,bank,run_id,freeze)
        else:
            result=evaluate.evaluate_main(records,bank,package['scenarios_evaluator_only'],frozen_model_sha256=freeze['model_sha256'])
            save_json(phase_dir/'analysis.json',result)
    elif phase=='x-replacement':
        main_dir=out/'phases'/run_id/'B-main'
        if (main_dir/'records.json').is_file() and (main_dir/'evaluator_only/reference_bank.json').is_file():
            result=evaluate.evaluate_counterfactual(read_json(main_dir/'records.json'),records,
                read_json(main_dir/'evaluator_only/reference_bank.json'),bank,package['replacement_assignments'],
                frozen_model_sha256=freeze['model_sha256'])
            save_json(phase_dir/'analysis.json',result)
    elif phase=='negative-control':
        result=evaluate.evaluate_negative_control(records,bank,[s['scenario_id'] for s in package['scenarios_evaluator_only']],frozen_model_sha256=freeze['model_sha256'])
        save_json(phase_dir/'analysis.json',result)
    elif phase in {'A','C'}:
        all_records=[];actual_profiles={}
        for module in ('A','C'):
            directory=out/'phases'/run_id/module
            if (directory/'records.json').is_file():all_records+=read_json(directory/'records.json')
            if (directory/'prepared_inputs.json').is_file():
                ready=read_json(directory/'prepared_inputs.json');actual_profiles[module]={}
                for fund,p in ready['profiles'].items():
                    actual_profiles[module][fund]={'h':p['h'],'Sigma':ready['calibration']['Sigma'],'A':p['A'],'b':p['b']}
        if set(actual_profiles)=={'A','C'}:
            catalog=read_json(root/config['source_catalog_path']) if config.get('source_catalog_path') else None
            result=evaluate.evaluate_actual_documents(all_records,actual_profiles,frozen_model_sha256=freeze['model_sha256'],source_catalog=catalog)
            save_json(phase_dir/'analysis.json',result)
    return measurements

def main():
    parser=argparse.ArgumentParser();parser.add_argument('config',type=Path);parser.add_argument('--phase',choices=(*PHASES,'all'),required=True)
    args=parser.parse_args();config=read_json(args.config);root=Path(config.get('workspace_root',Path(__file__).resolve().parents[2])).resolve()
    native=NativeTokenizer(read_json(root/config['tokenizer_config_path']))
    phases=PHASES if args.phase=='all' else (args.phase,)
    try:
        for phase in phases:
            try:result=run_phase(root,config,phase,native)
            except Exception as exc:
                receipt={'phase':phase,'status':'preflight_or_protocol_block','error_type':type(exc).__name__,'error':str(exc),'recorded_at_utc':now()}
                save_json(root/config['output_root']/('blocked_'+phase+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json'),receipt)
                print(json.dumps(receipt,ensure_ascii=False));return 2
            print(json.dumps(result,ensure_ascii=False))
            if result['status']!='completed':return 2
    finally:native.close()
    return 0

if __name__=='__main__':raise SystemExit(main())
