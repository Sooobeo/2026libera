"""Gate-bound main v4.8 coordinator: four fixed cases, raw C0, bounded C1/C2.

No registration, freeze, approval creation, hidden gold reads, normalization or
automatic retry. Every real request requires a separately recorded main gate.
This module does not authenticate reviewer identities or certify model semantics.
"""
from __future__ import annotations
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import remote_sector_runtime as remote
import sector_v48_main_transport as transport
import sector_v48_main_awake as awake
from sector_v48_main_gate import verify_main_gate
from sector_v48_contract import (build_system, stage_payload, evaluate_proposal,
                                 complete_vector, repair_eligible)
from sector_response_schema import response_schema, validate_response
from sector_engine import parse_response
from compact_sector_prompt import compact_stage_content, restore_market

ROOT=Path(__file__).resolve().parents[1]
SOURCES=('fidelity_q3_2026','ubs_july_2026')
ROSTER=tuple({'case_id':s+'__'+a,'source_id':s,'arm':a,'split':'main'} for s in SOURCES for a in ('R1','R4'))
DESIGN='data/sector_protocol/v48_design_20261018'



def now(): return datetime.now(timezone.utc).isoformat()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def value_sha(value): return hashlib.sha256(canonical(value).encode()).hexdigest()
def save(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def ref(path):
    p=Path(path).resolve()
    try: name=p.relative_to(ROOT).as_posix()
    except ValueError: name=str(p)
    return {'path':name,'sha256':sha(p)}


def request_body(messages,runtime,stage,visible):
    if any(set(x)!={'role','content'} or not isinstance(x['content'],str) for x in messages):
        raise ValueError('Only explicit role/content strings allowed')
    body=transport.request_header(runtime,stage,visible)
    body['messages']=copy.deepcopy(messages)
    return body


def public_ids(registry):
    return {r['fact_id'] for r in registry['rows']+registry['matrix_fact_references']}


def get_raw(stage_dir,result):
    response_path=stage_dir/'http_0001_generation/response.json'
    if response_path.is_file():
        try:
            response=read(response_path)
            if not isinstance(response,dict): raise ValueError('Invalid response envelope')
            message=response.get('message')
            if not isinstance(message,dict) or not isinstance(message.get('content'),str):
                raise ValueError('Invalid response message envelope')
            return message['content'],response
        except (OSError,ValueError): pass
    partial=stage_dir/'http_0001_generation/assembled_text.json'
    if partial.is_file():
        try:
            assembled=read(partial)
            if not isinstance(assembled,dict) or not isinstance(assembled.get('content'),str):
                raise ValueError('Invalid partial envelope')
            return assembled['content'],None
        except (OSError,ValueError): pass
    # A hard-killed worker may not have assembled its already flushed stream.
    events=stage_dir/'http_0001_generation/events.jsonl'
    content=[]
    if events.is_file():
        for line in events.read_bytes().splitlines():
            try:
                e=json.loads(line.decode('utf-8'))['event'];part=e.get('message',{}).get('content','')
                if not isinstance(part,str): break
                content.append(part)
            except (ValueError,KeyError,TypeError,AttributeError): break
    return ''.join(content) or None,None


def emit(event,**kw): print(json.dumps({'event':event,'at_utc':now(),**kw},ensure_ascii=False),flush=True)


def run_case(case,prepared,target,runtime,contract,registry,market,origin,cancel_path,server_log,check_pins,execution_context):
    target.mkdir()
    packet=read(prepared/'packets'/f'{case["source_id"]}.json')
    save(target/'case_manifest.json',case|{'packet':ref(prepared/'packets'/f'{case["source_id"]}.json'),
        'primary_endpoint':'C0','main_model_calls_at_case_creation':0,'purpose':'main_fixed_case_under_separately_verified_gate'})
    messages=[{'role':'system','content':build_system(contract)}]
    visible_ids=public_ids(registry);visible_facts=[];previous_weights=None;records=[]
    summary=case|{'status':'not_started','primary_endpoint':'C0','endpoints':[],
        'core_calls_attempted':0,'auxiliary_calls_attempted':0,'main_model_calls':0,'automatic_retries':0,
        'completed_core_stages':0,'final_allocation_valid':None,'human_semantic_review_completed':False,
        'system_integrity_incident':False,'started_at_utc':now()}
    started=time.monotonic()
    def endpoint(endpoint_id,stage,visible,payload):
        nonlocal previous_weights
        if cancel_path.exists(): raise RuntimeError('cancelled')
        check_pins()
        # Only newly authored task messages are serialized; all previous strings stay unchanged.
        text=compact_stage_content(canonical(payload)) if endpoint_id=='stage1' else canonical(payload)
        if endpoint_id=='stage1':
            restored=json.loads(text);restored['common_market']=restore_market(restored['common_market'])
            if canonical(restored)!=canonical(payload): raise ValueError('Market projection changed an input value')
        messages.append({'role':'user','content':text})
        body=request_body(messages,runtime,stage,visible)
        stage_dir=target/endpoint_id;stage_dir.mkdir()
        save(stage_dir/'logical_payload.json',payload)
        save(stage_dir/'visible_evidence_before_generation.json',{'ids':sorted(visible_ids),'calculator_facts':visible_facts})
        emit('endpoint_started',case_id=case['case_id'],endpoint=endpoint_id)
        result=transport.run_transport(body=body,target=stage_dir,runtime=runtime,stage=stage,
            institution_visible=visible,expected_source_id=packet['source_id'] if visible else None,
            expected_system=messages[0]['content'],origin=origin,cancel_path=cancel_path,server_log=server_log,execution_context=execution_context)
        raw,response=get_raw(stage_dir,result)
        parsed=parse_response(raw)
        if parsed['ok']:
            try: canonical(parsed['value'])
            except (ValueError,OverflowError,TypeError,RecursionError):
                parsed={'ok':False,'value':None,'error':'nonfinite_or_unserializable_JSON_value'}
        validation=validate_response(raw,stage,packet['source_id'] if visible else None,visible)
        feedback=None
        if parsed['ok']:
            feedback=evaluate_proposal(parsed['value'],stage,market,sorted(visible_ids),endpoint_id,previous_weights)
        record={'endpoint':endpoint_id,'stage':stage,'institution_visible':visible,
            'recorded_at_utc':now(),'raw_response_text':raw,'response_artifact_present':response is not None,
            'response_complete':response is not None and response.get('done_reason')=='stop',
            'parsed_response':parsed['value'] if parsed['ok'] else None,'parse_error':parsed['error'],
            'schema_validation':validation,'feedback':feedback,'transport_status':result['status'],
            'transport_result':result,'request_body_sha256':value_sha(body),
            'visible_evidence_ids_before_generation':sorted(visible_ids),
            'visible_calculator_facts_before_generation':copy.deepcopy(visible_facts),
            'semantic_review':'pending; never inferred from structure or arithmetic'}
        save(stage_dir/'record.json',record);records.append(record)
        if endpoint_id=='C0' and feedback is not None:
            # Arithmetic validity of a complete captured vector is separate from
            # the seven-field contract. A missing rationale must stay visible,
            # but does not retroactively alter the submitted numbers.
            summary['final_allocation_valid']=bool(feedback['allocation']['valid']) if response is not None and response.get('done_reason')=='stop' else None
            summary['C0_contract_valid']=validation['valid']
        attempted=int((stage_dir/'http_0001_generation/request.json').is_file())
        key='auxiliary_calls_attempted' if endpoint_id in ('C1','C2') else 'core_calls_attempted'
        summary[key]+=attempted
        summary['main_model_calls']=summary['core_calls_attempted']+summary['auxiliary_calls_attempted']
        summary['endpoints'].append({'endpoint':endpoint_id,'status':result['status'],
            'generation_attempted':bool(attempted),'record':ref(stage_dir/'record.json')})
        if result['status']!='completed':
            summary['status']='stopped_'+result['status']
            summary['system_integrity_incident']=result.get('system_integrity_incident',False)
            return False,record
        if not validation['valid']:
            summary['status']='stopped_model_contract_failure';return False,record
        if not endpoint_id.startswith('C') or endpoint_id=='C0': summary['completed_core_stages']+=1
        messages.append({'role':'assistant','content':raw})
        messages.append({'role':'user','content':canonical({'calculator_feedback':feedback})})
        newfacts=feedback.get('facts',[]) if feedback else []
        visible_facts.extend(copy.deepcopy(newfacts));visible_ids.update(f['fact_id'] for f in newfacts)
        previous_weights=copy.deepcopy(parsed['value'].get('weights'))
        return True,record
    try:
        summary['status']='running'
        for stage in range(1,5):
            visible=case['arm']=='R1' or stage==4
            if visible: visible_ids.update(x['evidence_id'] for x in packet['evidence_passages'])
            endpoint_id=f'stage{stage}' if stage<4 else 'C0'
            okay,record=endpoint(endpoint_id,stage,visible,stage_payload(stage,case['arm'],packet,market,registry))
            save(target/'case_summary.json',summary)
            if not okay: break
        else:
            summary['status']='completed_core'
            c0=records[-1]
            eligible=repair_eligible(c0['parsed_response'])
            summary['C0_repair_eligibility']=eligible
            summary['final_allocation_valid']=bool(eligible['allocation']['valid'])
            if eligible['eligible']:
                for n in (1,2):
                    payload={'stage':4,'endpoint':f'C{n}',
                        'task':'Auxiliary arithmetic revision after the preserved primary C0. Reconsider the last submitted vector using its actual calculator feedback. Return all seven fields; retain source-grounded rationale and identify actual changes. No suggested target weights are supplied. Do not claim corrected arithmetic unless the submitted numbers support it.',
                        'response_schema':response_schema(4,True),
                        'original_primary_retained':True,'maximum_additional_revisions':2}
                    okay,record=endpoint(f'C{n}',4,True,payload)
                    if not okay: break
                    candidate=repair_eligible(record['parsed_response'])
                    if not candidate['eligible']:
                        summary['auxiliary_stop_reason']='arithmetic_valid' if candidate['allocation']['valid'] else 'incomplete_or_nonfinite_vector'
                        break
                else: summary['auxiliary_stop_reason']='cap_C2_reached'
                if summary['status']=='completed_core': summary['status']='completed_core_and_auxiliary_policy'
            else: summary['auxiliary_stop_reason']='C0_not_eligible'
    except BaseException as exc:
        cancelled=isinstance(exc,KeyboardInterrupt) or str(exc)=='cancelled'
        summary.update(status='cancelled' if cancelled else 'system_exception',
            error_type=type(exc).__name__,error=str(exc),system_integrity_incident=not cancelled)
        save(target/'case_exception.json',{'type':type(exc).__name__,'message':str(exc)})
    finally:
        # Count durable request artifacts even if parsing/calculation/record
        # writing failed after the model call. Such a call must not disappear.
        attempted_endpoints={p.parent.parent.name for p in target.glob('*/http_0001_generation/request.json')}
        summary['core_calls_attempted']=len(attempted_endpoints & {'stage1','stage2','stage3','C0'})
        summary['auxiliary_calls_attempted']=len(attempted_endpoints & {'C1','C2'})
        summary['main_model_calls']=summary['core_calls_attempted']+summary['auxiliary_calls_attempted']
        summary['model_call_count_scope']='Durable generation request envelopes; includes failed/interrupted requests.'
        summary['core_stage_states']={x:('completed' if any(r['endpoint']==x and r['transport_status']=='completed' and r['schema_validation']['valid'] for r in records)
            else 'attempted_failed' if x in attempted_endpoints else 'not_started') for x in ('stage1','stage2','stage3','C0')}
        summary.update(finished_at_utc=now(),wall_seconds=time.monotonic()-started,
            planned_core_stages_not_completed=[x for x in ('stage1','stage2','stage3','C0') if not any(r['endpoint']==x and r['transport_status']=='completed' and r['schema_validation']['valid'] for r in records)],
            primary_record=ref(target/'C0/record.json') if (target/'C0/record.json').exists() else None,
            auxiliary_terminal_record=ref(target/records[-1]['endpoint']/'record.json') if records and records[-1]['endpoint'] in ('C1','C2') else None,
            primary_never_replaced=True)
        save(target/'case_summary.json',summary)
    emit('case_finished',case_id=case['case_id'],status=summary['status'],core_calls=summary['core_calls_attempted'],auxiliary_calls=summary['auxiliary_calls_attempted'])
    return summary


def durable_counts(target):
    """Count saved attempted request envelopes even if no case summary survived."""
    core, auxiliary, unexpected = [], [], []
    allowed_cases = {c['case_id'] for c in ROSTER}
    for path in Path(target).glob('*/**/http_*_generation/request.json'):
        parts=path.relative_to(target).parts
        if len(parts)!=4 or parts[0] not in allowed_cases or parts[2]!='http_0001_generation':
            unexpected.append(path.relative_to(target).as_posix())
        elif parts[1] in ('stage1','stage2','stage3','C0'): core.append(path.relative_to(target).as_posix())
        elif parts[1] in ('C1','C2'): auxiliary.append(path.relative_to(target).as_posix())
        else: unexpected.append(path.relative_to(target).as_posix())
    return {'core_generation_calls':len(core),'auxiliary_generation_calls':len(auxiliary),
        'main_model_calls':len(core)+len(auxiliary)+len(unexpected),
        'unexpected_generation_request_paths':sorted(unexpected),
        'model_call_count_scope':'Durable main request envelopes, including failure or interruption; excludes metadata/render-only/unload.'}


def run(args):
    manifest_path=Path(args.manifest).resolve();gate_path=Path(args.gate).resolve()
    manifest,runtime,contract,registry,market,gate,human,authorization=verify_main_gate(manifest_path,gate_path)
    if manifest['roster']!=list(ROSTER): raise ValueError('Only fixed main roster is executable')
    target=Path(args.output).resolve()
    if target!=Path(gate['authorized_run_root']).resolve(): raise ValueError('Output differs from explicitly authorized main run root')
    origin=remote.validate_origin(args.base_url)
    if origin!='http://127.0.0.1:11434': raise ValueError('Only locally observed pinned endpoint is selected')
    server_log=Path(args.server_log).resolve()
    if not server_log.is_file(): raise ValueError('Owned running service log required')
    target.mkdir(parents=True,exist_ok=False)
    cancel_path=target/'CANCEL';start=time.monotonic()
    save(target/'manifest_snapshot.json',manifest)
    save(target/'main_execution_gate_snapshot.json',gate)
    save(target/'main_execution_authorization_snapshot.json',authorization)
    save(target/'human_source_review_snapshot.json',human)
    save(target/'invocation.json',{'at_utc':now(),'manifest':ref(manifest_path),'main_execution_gate':ref(gate_path),
        'main_execution_authorization':gate['main_execution_authorization'],
        'human_source_review':gate['human_source_review'], 'origin':origin,'server_log':str(server_log),
        'scope':'four fixed main cases under separately recorded source review, freeze and explicit approval',
        'main_model_calls_at_invocation':0,'reviewer_identity_authenticated':False})
    summary={'protocol_version':'4.8','scope':'four_fixed_main_cases','status':'not_started','planned_cases':list(ROSTER),'cases':[],
        'main_model_calls':0,'core_generation_calls':0,'auxiliary_generation_calls':0,
        'main_frozen':True,'human_review_completed':True,
        'human_review_scope':'Recorded pre-generation independent source review; no identity authentication.',
        'human_semantic_review_completed':False,'automatic_retries':0,'system_integrity_incident':False}
    context={'manifest_path':str(manifest_path),'gate_path':str(gate_path),'run_root':str(target)}
    def check_pins():
        verified=verify_main_gate(manifest_path,gate_path)
        if canonical(verified[0])!=canonical(manifest) or canonical(verified[5])!=canonical(gate):
            raise ValueError('Authorized main input or gate changed after invocation')
    awake_token=None
    try:
        awake_token=awake.acquire()
        save(target/'awake_acquire.json',awake_token)
        if awake_token.get('status')!='active':
            raise RuntimeError('Temporary idle-sleep request was not acquired; main not started')
        check_pins()
        state=remote.api_json(origin,'/api/ps');save(target/'residency_before.json',state)
        if state.get('models')!=[]: raise ValueError('Existing workload left unchanged; cannot start serial main study')
        summary['status']='running'
        for case in ROSTER:
            if cancel_path.exists(): summary['status']='cancelled';break
            result=run_case(case,manifest_path.parent,target/case['case_id'],runtime,contract,registry,market,
                origin,cancel_path,server_log,check_pins,context)
            summary['cases'].append(result);summary.update(durable_counts(target));save(target/'summary.json',summary)
            if result['status'] in ('cancelled','stopped_cancelled'):
                summary['status']='cancelled';break
            if result['system_integrity_incident']:
                summary.update(status='stopped_system_integrity_incident',system_integrity_incident=True);break
        else: summary['status']='all_planned_cases_accounted'
    except BaseException as exc:
        cancelled=isinstance(exc,KeyboardInterrupt)
        summary.update(status='cancelled' if cancelled else 'stopped_before_or_between_cases',
            error_type=type(exc).__name__,error=str(exc),system_integrity_incident=not cancelled)
    finally:
        if isinstance(awake_token,dict) and awake_token.get('status')=='active':
            released=awake.release(awake_token)
            save(target/'awake_release.json',released)
            summary['awake_release_status']=released.get('status')
            if released.get('status')!='released':
                summary.update(status='awake_restoration_failed',system_integrity_incident=True)
        summary['operating_protection']='Temporary thread-scoped idle-sleep request; no guarantee against explicit sleep, lid actions, power loss or suspend-related deadline delay.'
        summary.update(durable_counts(target))
        if summary['unexpected_generation_request_paths'] or summary['core_generation_calls']>16 or summary['auxiliary_generation_calls']>8:
            summary.update(status='request_budget_integrity_incident',system_integrity_incident=True)
        summary.update(finished_at_utc=now(),wall_seconds=time.monotonic()-start,
            cases_not_started=[c['case_id'] for c in ROSTER if not any(x['case_id']==c['case_id'] for x in summary['cases'])],
            completed_core_cases=sum(x['completed_core_stages']==4 for x in summary['cases']))
        save(target/'summary.json',summary)
    emit('main_finished',output=str(target),status=summary['status'],main_model_calls=summary['main_model_calls'],
        core_calls=summary['core_generation_calls'],auxiliary_calls=summary['auxiliary_generation_calls'])
    return 0 if summary['status']=='all_planned_cases_accounted' else 1


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True);parser.add_argument('--gate',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--server-log',required=True)
    parser.add_argument('--base-url',default='http://127.0.0.1:11434')
    return run(parser.parse_args(argv))


if __name__=='__main__': raise SystemExit(main())
