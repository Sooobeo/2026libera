"""Execution audit v2: add full executor task comparison before observed output.

The original audit is preserved. This verifies the already declared task;
it introduces no new model outcome or financial acceptance criterion.
"""
from __future__ import annotations
import argparse
import ast
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
from audit_v45_single_case_round1 import canonical, floats, strict_object, structure_errors

ROOT = Path(__file__).resolve().parents[1]


def audit(run, manifest_path, registration_path):
    checks, refs = [], {}
    def read(path, raw=False):
        path = Path(path).resolve()
        value = path.read_bytes()
        refs[path.relative_to(ROOT).as_posix()] = hashlib.sha256(value).hexdigest()
        return value if raw else json.loads(value.decode('utf-8-sig'))
    def check(name, okay, detail=None):
        checks.append({'check':name,'status':'pass' if okay else 'fail','detail':detail})
    def pin(row):
        path = Path(row['path'])
        path = path if path.is_absolute() else ROOT/path
        check('hash:'+path.name, hashlib.sha256(read(path,raw=True)).hexdigest() == row['sha256'])
    manifest=read(manifest_path); reg=read(registration_path)
    summary=read(run/'summary.json'); invocation=read(run/'invocation.json')
    check('manifest_snapshot', read(run/'manifest_snapshot.json') == manifest)
    check('registration_snapshot', read(run/'registration_snapshot.json') == reg)
    for name,digest in manifest['inputs'].items():
        pin({'path':str(manifest_path.parent/name),'sha256':digest})
    for name,digest in manifest['software'].items():
        pin({'path':str(ROOT/'research'/name),'sha256':digest})
    pin(manifest['parent_preparation'])
    for key in ('original_sources','v45_sources','revision_evidence'):
        for row in manifest.get(key,[]): pin(row)
    for row in reg.get('reference_files',[]): pin(row)
    for key in ('manifest','registration'): pin(invocation[key])
    check('registered_before_launch', datetime.fromisoformat(reg['registered_at_utc']) <= datetime.fromisoformat(invocation['started_at_utc']))
    check('budget_two_not_two_retries', manifest['planned_generation_attempts'] == reg['planned_generation_attempts'] == 2)
    runtime=read(run/'runtime.json')
    check('runtime_snapshot', runtime == read(manifest_path.parent/'runtime.json'))
    prior=read(manifest_path.parent/'prior_response.json')
    prior_record=read(manifest_path.parent/'prior_record.json')
    runner_source=read(ROOT/'research/local_sector_plan_execute_diagnostic.py',raw=True).decode('utf-8')
    literals={node.targets[0].id:ast.literal_eval(node.value) for node in ast.parse(runner_source).body
              if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name)
              and node.targets[0].id in ('PLANNER_TASK','EXECUTOR_TASK','DIAGNOSTIC_ID')}
    check('prior_complete_and_invalid', prior['done_reason'] == 'stop' and prior_record['calculator_result']['allocation']['valid'] is False)
    check('prior_raw_record', strict_object(prior['message']['content']) == prior_record['raw_proposal'])
    planner_messages=None; planner_response=None; final_response=None
    for role,stage in [('planner',1),('executor',4)]:
        folder=run/(role+'_transport'); http=folder/'http_0001_generation'
        logical=read(folder/'logical_messages.json'); body=read(folder/'authoritative_body.json')
        request=read(http/'request.json'); spec=read(folder/'worker_spec.json')
        tag=role+':'
        check(tag+'request_and_spec', request['path']=='/api/chat' and request['body']==body==spec['body'])
        check(tag+'authoritative_bytes', read(folder/'authoritative_body.bin',raw=True)==json.dumps(body,ensure_ascii=False,allow_nan=False).encode())
        schema=read(folder/'response_schema.json')
        current=strict_object(logical[-1]['content'])
        check(tag+'schema_and_selector', body['format']==schema==current['response_schema'] and current['stage']==stage)
        check(tag+'prepared_schema',schema==read(manifest_path.parent/('schema_'+role+'.json')))
        check(tag+'declared_task',current['task']==literals[role.upper()+'_TASK']
              and current['diagnostic_id']==literals['DIAGNOSTIC_ID'] and current['role_in_diagnostic']==role)
        expected={k:runtime[k] for k in ('model','think','truncate','shift','stream','keep_alive','options')}
        expected['format']=schema
        check(tag+'unchanged_controls',{k:v for k,v in body.items() if k!='messages'}==expected)
        check(tag+'one_generation_record',len(list(folder.glob('http_*_generation/request.json')))==1)
        if role=='planner':
            check('planner_five_messages',len(logical)==5 and [m['role'] for m in logical]==['system','user','assistant','user','user'])
            check('planner_frozen_input',logical==read(manifest_path.parent/'planner_logical_messages.json')
                  and body==read(manifest_path.parent/'planner_authoritative_body.json'))
            original=read(ROOT/'data/local_sector_runtime/single_case_v45_20261018/fidelity_q2_2026__R1/stage1_request.json')
            check('original_public_task',logical[:2]==original)
            check('original_previous_assistant',logical[2]=={'role':'assistant','content':prior['message']['content']})
            check('original_previous_feedback',strict_object(logical[3]['content'])=={'calculator_feedback':prior_record['calculator_result']})
            check('task_feedback_values',current['calculator_feedback']==prior_record['calculator_result']
                  and current['delta_feedback']==read(manifest_path.parent/'prior_delta_feedback.json'))
            planner_messages=copy.deepcopy(logical)
        else:
            check('executor_seven_messages',len(logical)==7)
            check('planner_history_preserved',logical[:5]==planner_messages)
            check('planner_raw_forwarded',logical[5]=={'role':'assistant','content':planner_response['message']['content']})
            planner_task=strict_object(planner_messages[-1]['content'])
            expected_task={'stage':4,'diagnostic_id':literals['DIAGNOSTIC_ID'],
                'role_in_diagnostic':'executor','stage_field_role':'existing_schema_selector_not_a_workflow_stage',
                'task':literals['EXECUTOR_TASK'],'response_schema':read(manifest_path.parent/'schema_executor.json'),
                'response_contract_instruction':planner_task['response_contract_instruction']}
            check('executor_full_declared_task',logical[-1]['role']=='user' and current==expected_task)
        # Restore only the two redundant public market fields independently.
        restored=strict_object(body['messages'][1]['content'])
        market=restored['common_market']
        check(tag+'ddof',type(market.get('covariance_ddof')) is int and market['covariance_ddof']==1)
        del market['covariance_ddof']
        market['sample_covariance_ddof_1']=copy.deepcopy(market['covariance'])
        market['baseline_weights_array']=[market['baseline_weights'][code] for code in market['sector_codes']]
        public=strict_object(logical[1]['content'])
        check(tag+'lossless_public_values',canonical(restored)==canonical(public) and floats(restored)==floats(public))
        check(tag+'remaining_http_strings',body['messages'][0]==logical[0] and body['messages'][2:]==logical[2:])
        for phase in ('before_render','before_generation'):
            observed=read(folder/('pin_'+phase+'.json'))
            check(tag+phase,observed['version']['version']==runtime['engine_version']
                  and observed['selected_model']['digest']==runtime['digest'] and observed['template_sha256']==runtime['template_sha256'])
        render=read(folder/'render_only/response.json'); rq=read(folder/'render_only/request.json')
        check(tag+'render_request',rq['body']==(body|{'stream':False,'_debug_render_only':True}))
        check(tag+'render_no_generation',render.get('eval_count',0)==render.get('prompt_eval_count',0)==0
              and not any(render.get('message',{}).get(k) for k in ('content','thinking','tool_calls')))
        text=render['_debug_info']['rendered_template']
        check(tag+'rendered_file',read(folder/'render_only/rendered_prompt.txt',raw=True)==text.encode())
        cursor=0
        for i,message in enumerate(body['messages']):
            content=message['content'] if i==0 else message['content'].strip(' \t\r\n')
            at=text.find(content,cursor); check(tag+'render_message_'+str(i),at>=cursor)
            if at>=0:cursor=at+len(content)
        raw=read(http/'raw_stream.bin',raw=True)
        events=[json.loads(x) for x in raw.splitlines() if x.strip()]
        logged=[json.loads(x)['event'] for x in read(http/'events.jsonl',raw=True).splitlines() if x.strip()]
        response=read(http/'response.json'); assembled=read(http/'assembled_text.json')
        content=''.join(x.get('message',{}).get('content','') for x in events)
        check(tag+'raw_events',events==logged and raw.endswith(b'\n'))
        check(tag+'complete_stop',events[-1]['done'] is True and events[-1]['done_reason']==response['done_reason']=='stop')
        check(tag+'raw_content',content==response['message']['content']==assembled['content'])
        check(tag+'model_response',response['model']==runtime['model'])
        check(tag+'no_hidden_thinking',not any(x.get('message',{}).get('thinking') or x.get('message',{}).get('tool_calls') for x in events))
        parsed=strict_object(content)
        check(tag+'independent_structure',not structure_errors(parsed,stage))
        result=read(http/'result.json')
        check(tag+'http_completed',result.get('status')=='completed' and result.get('http_status')==200)
        check(tag+'after_registration',datetime.fromisoformat(result['started_at_utc'])>=datetime.fromisoformat(reg['registered_at_utc']))
        sup=read(folder/'supervisor_result.json')
        check(tag+'supervisor',sup['status']=='worker_exited' and sup['worker_exit_code']==0 and sup['deadline_seconds']==900)
        clean=read(folder/'unload_and_residency.json')
        check(tag+'cleanup',clean['status']=='no_resident_models_observed' and clean['ps'][-1]['value']['models']==[]
              and clean['unload']['status']=='ok' and clean['unload']['value']['done'] is True)
        before=read(folder/'server_log_before.json'); after=read(folder/'server_log_after_snapshot.bin',raw=True)
        delta=read(folder/'server_log_delta.json')
        check(tag+'service_log_snapshot',delta['original_prefix_retained'] is True and hashlib.sha256(after[:before['bytes']]).hexdigest()==before['sha256']
              and hashlib.sha256(after).hexdigest()==delta['sha256'])
        if role=='planner':
            planner_response=response
            plan=read(run/'plan_record.json')
            check('planner_unmodified',plan['raw_proposal']==parsed)
            check('planner_not_allocation',parsed['weights']==[] and plan['planner_contract_satisfied'] is True)
            check('planner_not_calculated_as_portfolio','calculator_result' not in plan or plan['calculator_result'] is None)
        else:
            final_response=response
            record=read(run/'revision_record.json')
            check('executor_unmodified',record['raw_proposal']==parsed and record['repair_applied'] is False)
            check('raw_calculator_arguments',record['calculator_arguments']=={'weights':parsed['weights'],'submitted_constraints':parsed['submitted_constraints']})
            check('numeric_result_separate',summary['numeric_acceptance']==record['assessment']['numeric_acceptance'])
    ledger=[json.loads(x) for x in read(run/'events.jsonl',raw=True).splitlines() if x.strip()]
    check('nonempty_event_ledger',len(ledger)>0)
    check('event_order',[row['event'] for row in ledger]==['registered_diagnostic_started',
          'supervised_attempt_dispatched','cleanup_recorded','plan_recorded',
          'supervised_attempt_dispatched','cleanup_recorded','raw_revision_recalculated','diagnostic_finished'])
    check('event_role_order',[row.get('role') for row in ledger if row['event'] in
          ('supervised_attempt_dispatched','cleanup_recorded')]==['planner','planner','executor','executor'])
    for i,event in enumerate(ledger):
        payload={k:v for k,v in event.items() if k!='event_sha256'}
        check('ledger_'+str(i),event['sequence']==i+1 and event['previous_event_sha256']==(ledger[i-1]['event_sha256'] if i else None)
              and event['event_sha256']==hashlib.sha256(canonical(payload).encode()).hexdigest())
    terminal=ledger[-1].get('summary',{}) if ledger else {}
    check('ledger_terminal_summary',Path(terminal.get('path','')).resolve()==(run/'summary.json').resolve()
          and terminal.get('sha256')==hashlib.sha256((run/'summary.json').read_bytes()).hexdigest())
    check('two_complete_calls',summary['status']=='completed_plan_execute_diagnostic'
          and summary['generation_requests_attempted']==summary['http_streams_completed']==summary['render_requests_attempted']==2)
    check('two_generation_records_total',len(list(run.glob('**/http_*_generation/request.json')))==2)
    check('planner_executor_completed',summary['planner_completed'] is True and summary['executor_completed'] is True and summary['planner_contract_satisfied'] is True)
    check('no_main_retry_or_four_stage_claim',summary['automatic_retries']==summary['main_model_calls']==summary['four_stage_pilot_calls']==0)
    check('no_unearned_approval',summary['main_freeze'] is False and summary['human_semantic_pass'] is False and summary['priority1_solved'] is False)
    read(Path(__file__),raw=True);read(ROOT/'research/audit_v45_single_case_round1.py',raw=True)
    failed=[row['check'] for row in checks if row['status']=='fail']
    return {'phase':'priority1','round':1,'run_dir':run.relative_to(ROOT).as_posix(),
        'scope':'Two-call plan/execute diagnostic execution, provenance and verbatim records; no arithmetic or semantic approval.',
        'audit_completed':True,'all_passed':not failed,'failed_checks':failed,'not_observed_checks':[],
        'checks':checks,'source_files':[{'path':p,'sha256':h} for p,h in refs.items()],
        'model_calls_by_auditor':0,'main_freeze':False,'human_semantic_pass':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--registration',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run=args.run_dir.resolve()
    if args.output.exists(): raise FileExistsError('Preserve earlier audit')
    try: result=audit(run,args.manifest.resolve(),args.registration.resolve())
    except Exception as exc:
        paths=[args.manifest,args.registration,run/'summary.json',run/'failure.json',Path(__file__)]
        paths+=list(run.glob('*_transport/http_*/raw_stream.bin'))
        result={'phase':'priority1','round':1,'run_dir':run.relative_to(ROOT).as_posix(),
            'scope':'Incomplete execution audit; no PASS from absent evidence or audit error.',
            'audit_completed':False,'all_passed':False,'failed_checks':['audit_not_completed'],
            'not_observed_checks':['full_execution_review'],'checks':[],
            'error_type':type(exc).__name__,'error':str(exc),
            'source_files':[{'path':x.resolve().relative_to(ROOT).as_posix(),
                'sha256':hashlib.sha256(x.read_bytes()).hexdigest()} for x in paths if x.is_file()]}
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'all_passed':result['all_passed'],'check_count':len(result['checks']),
                      'failed_checks':result['failed_checks'],'output':str(args.output)}))
    return 0 if result['all_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
