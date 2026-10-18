"""Versioned v4.8 pilot coordinator: 4 fixed cases, raw C0, bounded auxiliary C1/C2.

No main-study command, hidden gold reads, output normalization, automatic retry,
or semantic acceptance exists here. Preparation and registration are offline.
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
import sector_v48_transport as transport
from sector_v48_contract import (build_system, stage_payload, evaluate_proposal,
                                 complete_vector, repair_eligible)
from sector_response_schema import response_schema, validate_response
from sector_engine import parse_response
from compact_sector_prompt import compact_stage_content, restore_market

ROOT=Path(__file__).resolve().parents[1]
SOURCES=('fidelity_q2_2026','ubs_june_2026')
ROSTER=tuple({'case_id':s+'__'+a,'source_id':s,'arm':a,'split':'pilot'} for s in SOURCES for a in ('R1','R4'))
DESIGN='data/sector_protocol/v48_design_20261018'
SOFTWARE=('run_sector_v48.py','sector_v48_transport.py','sector_v48_contract.py',
          'sector_response_schema.py','sector_engine.py','compact_sector_prompt.py',
          'local_sector_single_case.py','remote_sector_runtime.py','benchmark_sector_latency.py',
          'probe_ollama_runtime.py','run_sector_workflow.py')


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
    return {'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)}


def expected_input_names():
    return {'runtime.json','prompt_contract.json','public_numeric_registry.json','market_input.json'} | {
        'packets/'+s+'.json' for s in SOURCES} | {
        f'schemas/{arm}_stage{stage}.json' for arm in ('R1','R4') for stage in range(1,5)}


def prepare(output):
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    save(output/'runtime.json',transport.runtime_v48())
    for name in ('prompt_contract.json','public_numeric_registry.json'):
        (output/name).write_bytes((ROOT/DESIGN/name).read_bytes())
    (output/'market_input.json').write_bytes((ROOT/'data/sector_market/market_input.json').read_bytes())
    (output/'packets').mkdir();(output/'schemas').mkdir()
    for source in SOURCES:
        path=ROOT/'data/sector_documents/packets/pilot'/f'{source}.json'
        packet=read(path)
        if packet['source_id']!=source or packet['split']!='pilot': raise ValueError('Pilot packet identity mismatch')
        (output/'packets'/path.name).write_bytes(path.read_bytes())
    for arm in ('R1','R4'):
        for stage in range(1,5): save(output/f'schemas/{arm}_stage{stage}.json',response_schema(stage,arm=='R1' or stage==4))
    manifest={'protocol_version':'4.8','scope':'all_four_fixed_pilot_cases_only',
        'prepared_at_utc':now(),'roster':list(ROSTER),'main_authorized':False,'main_frozen':False,
        'input_hashes':{name:sha(output/name) for name in sorted(expected_input_names())},
        'software_hashes':{name:sha(ROOT/'research'/name) for name in SOFTWARE},
        'design_references':[ref(ROOT/'plan/LIBERA_실험설정_v4.8_20261018.json'),
                             ref(ROOT/'research/v48_handoff_20261018.json')],
        'planned_core_calls':16,'maximum_auxiliary_calls':8,'maximum_total_generation_calls':24,
        'controls':{'first_final_C0_is_primary':True,'automatic_retries':0,'maximum_auxiliary_per_case':2,
            'no_projection_or_target_weights':True,'no_hidden_gold_or_evaluator_read':True,
            'prior_historical_failures_preserved':True,'same_fixed_case_order':True,
            'fixed_order_limit':'Order is operational, not randomized or counterbalanced. Model unload does not flush OS cache.',
            'runtime_limit':'900 seconds per worker including setup/render/generation; cleanup separately recorded.',
            'systematic_failure':'Protocol/pin/render/context integrity incidents stop bundle; model output failure stops affected case, stays in denominator.',
            'three_review_gate':'Three offline implementation review rounds before this pilot; three post-pilot review rounds before any next phase.',
            'topic':'Source judgment -> rationale -> actual allocation under R1/R4; arithmetic is a separate outcome, never a strategy-quality surrogate.'},
        'model_calls_by_preparation':0}
    save(output/'manifest.json',manifest)
    # Save all first-stage requests for offline leakage review; never sent here.
    runtime,contract,registry,market=load_inputs(output)
    for case in ROSTER:
        packet=read(output/'packets'/f'{case["source_id"]}.json')
        messages=[{'role':'system','content':build_system(contract)}]
        payload=stage_payload(1,case['arm'],packet,market,registry)
        messages.append({'role':'user','content':compact_stage_content(canonical(payload))})
        save(output/f'preview/{case["case_id"]}_stage1_body.json',request_body(messages,runtime,1,case['arm']=='R1'))
    print(json.dumps({'prepared':str(output/'manifest.json'),'model_calls':0},ensure_ascii=False))


def load_inputs(folder):
    return tuple(read(folder/n) for n in ('runtime.json','prompt_contract.json','public_numeric_registry.json','market_input.json'))


def verify_manifest(path):
    path=Path(path).resolve();m=read(path)
    if (m['protocol_version']!='4.8' or m['scope']!='all_four_fixed_pilot_cases_only'
            or m['roster']!=list(ROSTER) or m['main_authorized'] is not False or m['main_frozen'] is not False):
        raise ValueError('Only the exact four-case pilot is executable')
    if set(m['input_hashes'])!=expected_input_names() or set(m['software_hashes'])!=set(SOFTWARE):
        raise ValueError('Unexpected prepared input/software inventory')
    for name,h in m['input_hashes'].items():
        if sha(path.parent/name)!=h: raise ValueError('Prepared input changed: '+name)
    for name,h in m['software_hashes'].items():
        if sha(ROOT/'research'/name)!=h: raise ValueError('Prepared software changed: '+name)
    expected_designs={'plan/LIBERA_실험설정_v4.8_20261018.json','research/v48_handoff_20261018.json'}
    if {r['path'] for r in m['design_references']}!=expected_designs:
        raise ValueError('Unexpected design reference inventory')
    for item in m['design_references']:
        if ref(ROOT/item['path'])!=item: raise ValueError('Registered design reference changed')
    runtime,contract,registry,market=load_inputs(path.parent)
    if canonical(runtime)!=canonical(transport.runtime_v48()): raise ValueError('Runtime revision not registered')
    if registry['source']['sha256']!=sha(path.parent/'market_input.json'): raise ValueError('Registry market mismatch')
    if contract['auxiliary_repair']['maximum_additional_calls']!=2: raise ValueError('Repair policy changed')
    for case in ROSTER:
        packet=read(path.parent/'packets'/f'{case["source_id"]}.json')
        if packet.get('source_id')!=case['source_id'] or packet.get('split')!='pilot': raise ValueError('Wrong packet')
        for stage in range(1,5):
            if read(path.parent/f'schemas/{case["arm"]}_stage{stage}.json')!=response_schema(stage,case['arm']=='R1' or stage==4):
                raise ValueError('Prepared schema differs')
    return m,runtime,contract,registry,market


def register(manifest_path,review_paths,output):
    manifest_path=Path(manifest_path).resolve();manifest,*_=verify_manifest(manifest_path)
    if len(review_paths)!=3: raise ValueError('Exactly three review rounds required')
    reviewed=[]
    for n,path in enumerate(review_paths,1):
        r=read(path)
        if r.get('status')!='PASS' or r.get('round')!=n or r.get('manifest_sha256')!=sha(manifest_path):
            raise ValueError('Review missing PASS/round/manifest hash: '+str(path))
        if {x['path'] for x in r.get('reviewed_files',[])}!={'research/'+x for x in SOFTWARE}:
            raise ValueError('Review must bind the complete executable software inventory')
        for item in r.get('reviewed_files',[]):
            if ref(ROOT/item['path'])!=item: raise ValueError('Reviewed implementation changed')
        reviewed.append(ref(path))
    registration={'protocol_version':'4.8','registered_at_utc':now(),'manifest':ref(manifest_path),
        'roster':manifest['roster'],'planned_core_calls':16,'maximum_auxiliary_calls':8,
        'maximum_total_generation_calls':24,'reviews':reviewed,'automatic_retries':0,
        'model_failure_not_exclusion':True,'main_authorized':False,'human_review_completed':False,
        'scope':'Local prerecord of an authorized development pilot, not independent confirmation or a public timestamp authority.',
        'comparison_scope':'Different exposure/use workflows under one shared model; not pure memory mechanism or market-wide homogenization.',
        'model_calls_by_registration':0}
    p=Path(output);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as handle: json.dump(registration,handle,ensure_ascii=False,indent=2);handle.write('\n')
    print(json.dumps({'registration':str(p),'sha256':sha(p),'model_calls':0}))


def verify_registration(registration_path,manifest_path):
    r=read(registration_path)
    if r.get('protocol_version')!='4.8' or r.get('manifest')!=ref(manifest_path) or r.get('roster')!=list(ROSTER) or r.get('main_authorized') is not False:
        raise ValueError('Registration mismatch')
    if len(r['reviews'])!=3: raise ValueError('Three review records missing')
    for item in r['reviews']:
        if ref(ROOT/item['path'])!=item: raise ValueError('Registered review changed')
    return r


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


def run_case(case,prepared,target,runtime,contract,registry,market,origin,cancel_path,server_log,check_pins):
    target.mkdir()
    packet=read(prepared/'packets'/f'{case["source_id"]}.json')
    save(target/'case_manifest.json',case|{'packet':ref(prepared/'packets'/f'{case["source_id"]}.json'),
        'primary_endpoint':'C0','main_model_calls':0,'purpose':'development_pilot_not_independent_confirmatory_sample'})
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
            expected_system=messages[0]['content'],origin=origin,cancel_path=cancel_path,server_log=server_log)
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
        summary.update(status='cancelled' if isinstance(exc,KeyboardInterrupt) or str(exc)=='cancelled' else 'system_exception',
            error_type=type(exc).__name__,error=str(exc),system_integrity_incident=True)
        save(target/'case_exception.json',{'type':type(exc).__name__,'message':str(exc)})
    finally:
        # Count durable request artifacts even if parsing/calculation/record
        # writing failed after the model call. Such a call must not disappear.
        attempted_endpoints={p.parent.parent.name for p in target.glob('*/http_0001_generation/request.json')}
        summary['core_calls_attempted']=len(attempted_endpoints & {'stage1','stage2','stage3','C0'})
        summary['auxiliary_calls_attempted']=len(attempted_endpoints & {'C1','C2'})
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


def run(args):
    manifest_path=Path(args.manifest).resolve();registration_path=Path(args.registration).resolve()
    manifest,runtime,contract,registry,market=verify_manifest(manifest_path)
    registration=verify_registration(registration_path,manifest_path)
    origin=remote.validate_origin(args.base_url)
    if origin!='http://127.0.0.1:11434': raise ValueError('Only the locally observed pinned endpoint is selected')
    server_log=Path(args.server_log).resolve()
    if not server_log.is_file(): raise ValueError('Owned running service log required')
    target=Path(args.output).resolve();target.mkdir(parents=True,exist_ok=False)
    cancel_path=target/'CANCEL';start=time.monotonic()
    save(target/'manifest_snapshot.json',manifest);save(target/'registration_snapshot.json',registration)
    save(target/'invocation.json',{'at_utc':now(),'manifest':ref(manifest_path),'registration':ref(registration_path),
        'origin':origin,'server_log':str(server_log),'scope':'four-case pilot only','main_model_calls':0})
    summary={'protocol_version':'4.8','status':'not_started','planned_cases':list(ROSTER),'cases':[],
        'main_model_calls':0,'main_frozen':False,'human_review_completed':False,'automatic_retries':0}
    def check_pins():
        verify_manifest(manifest_path);verify_registration(registration_path,manifest_path)
    try:
        state=remote.api_json(origin,'/api/ps');save(target/'residency_before.json',state)
        if state.get('models')!=[]: raise ValueError('Existing model workload left unchanged; cannot start serial pilot')
        summary['status']='running'
        for case in ROSTER:
            if cancel_path.exists(): summary['status']='cancelled';break
            result=run_case(case,manifest_path.parent,target/case['case_id'],runtime,contract,registry,market,
                            origin,cancel_path,server_log,check_pins)
            summary['cases'].append(result);save(target/'summary.json',summary)
            if result['status'] in ('cancelled','stopped_cancelled'):
                summary['status']='cancelled';break
            if result['system_integrity_incident']:
                summary['status']='stopped_system_integrity_incident';break
        else: summary['status']='all_planned_cases_accounted'
    except BaseException as exc:
        summary.update(status='cancelled' if isinstance(exc,KeyboardInterrupt) else 'stopped_before_or_between_cases',
            error_type=type(exc).__name__,error=str(exc))
    finally:
        summary.update(finished_at_utc=now(),wall_seconds=time.monotonic()-start,
            cases_not_started=[c['case_id'] for c in ROSTER if not any(x['case_id']==c['case_id'] for x in summary['cases'])],
            core_generation_calls=sum(x['core_calls_attempted'] for x in summary['cases']),
            auxiliary_generation_calls=sum(x['auxiliary_calls_attempted'] for x in summary['cases']),
            completed_core_cases=sum(x['completed_core_stages']==4 for x in summary['cases']))
        save(target/'summary.json',summary)
    emit('pilot_finished',output=str(target),status=summary['status'],core_calls=summary['core_generation_calls'],auxiliary_calls=summary['auxiliary_generation_calls'])
    return 0 if summary['status']=='all_planned_cases_accounted' else 1


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--output',required=True)
    p=sub.add_parser('register');p.add_argument('--manifest',required=True);p.add_argument('--review',action='append',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('run');p.add_argument('--manifest',required=True);p.add_argument('--registration',required=True)
    p.add_argument('--output',required=True);p.add_argument('--server-log',required=True);p.add_argument('--base-url',default='http://127.0.0.1:11434')
    args=parser.parse_args(argv)
    if args.command=='prepare': prepare(args.output);return 0
    if args.command=='register': register(args.manifest,args.review,args.output);return 0
    return run(args)


if __name__=='__main__': raise SystemExit(main())
