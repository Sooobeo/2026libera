"""Offline round 1: audit available pilot evidence, preserving partial outcomes.

Missing or unfinished records are not PASS. No model calls, response repair,
arithmetic grading, semantic scoring or runtime-file mutation is performed.
"""
from __future__ import annotations
import argparse
import ast
import html
import math
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = 'fidelity_q2_2026__R1'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def floats(value, prefix=''):
    if type(value) is float:
        return {prefix: value.hex()}
    if type(value) is dict:
        return {k: v for name, child in value.items() for k, v in floats(child, prefix+'/'+name).items()}
    if type(value) is list:
        return {k: v for i, child in enumerate(value) for k, v in floats(child, prefix+'/'+str(i)).items()}
    return {}


REGISTRATION = ROOT / 'data/sector_protocol/v45_single_case_registration_20261018.json'
REGISTRATION_SHA = '8cf54a9aaaad2ad89e595174a6bfda85b0a307b99f932ca1e0ae5274081b34da'
POLICY_SHA = '4135e7f2d0000e4f51ca3414af803805c823f681468807d3ab19f9fd116488a4'
V44_REVIEW = ROOT / 'research/v44_single_case_round1_20261018.json'
V44_REVIEW_SHA = 'b28abd8840bb94431b950971a924e8d680fdd3a72df8517889bacd0384d2aa42'
IMMUTABLE_BASE = {
    'local_sector_single_case.py': '0b2596a223167136bb37578e86469d50c26e7883305d4db31f43b9ddd10d28d0',
    'run_sector_workflow.py': '5625450a4dcbe1aa717c9809bf4955c1ef6b10aab4f0c83ef05dc2eb2c123cfd',
    'sector_engine.py': '507eb352fc3b8b61ad92be31e4697e48deb0e8cc233fae5e230aecb7a0c9649c',
}
CODES = ['10','15','20','25','30','35','40','45','50','55','60']
KEYS = {'source_id','interpretations','weights','alternatives','risk_discussion','unresolved','submitted_constraints'}


def literal_assignment(source, name):
    # Read a literal from hash-pinned source; never import or execute the runner.
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('Missing literal '+name)


def strict_object(text):
    def pairs(rows):
        out={}
        for key,value in rows:
            if key in out: raise ValueError('Duplicate JSON key')
            out[key]=value
        return out
    def reject(value): raise ValueError('Nonfinite JSON constant')
    value=json.loads(text,object_pairs_hook=pairs,parse_constant=reject)
    if not isinstance(value,dict): raise ValueError('Not a JSON object')
    return value


def structure_errors(value, stage):
    # Independent explicit contract, not a call to the online schema validator.
    errors=[]
    def object_keys(v,keys,path):
        if not isinstance(v,dict) or set(v)!=set(keys):errors.append(path+': object keys');return False
        return True
    def text(v,path):
        if not isinstance(v,str) or len(v)<1:errors.append(path+': required text')
    def ids(v,path):
        if not isinstance(v,list) or any(not isinstance(x,str) or len(x)<1 for x in v):errors.append(path+': string array')
    def number(v,path):
        try:ok=not isinstance(v,bool) and isinstance(v,(int,float)) and math.isfinite(float(v))
        except (OverflowError,ValueError):ok=False
        if not ok:errors.append(path+': finite number')
    if not object_keys(value,KEYS,'$'):return errors
    if value['source_id'] is not None and not isinstance(value['source_id'],str):errors.append('source_id: type')
    for key in ('alternatives','risk_discussion'):text(value[key],key)
    ids(value['unresolved'],'unresolved')
    for field,required in [('interpretations',{'sector_code','rating','evidence_ids','reason'}),
                           ('weights',{'sector_code','weight','rationale','evidence_ids'}),
                           ('submitted_constraints',{'constraint_id','sector_code','kind','bound','evidence_ids'})]:
        rows=value[field]
        if not isinstance(rows,list):errors.append(field+': array');continue
        allowed=(11,) if field=='interpretations' or (field=='weights' and stage>=3) else (0,11) if field=='weights' else None
        if allowed is not None and len(rows) not in allowed:errors.append(field+': row count')
        for i,row in enumerate(rows):
            p=field+'['+str(i)+']'
            if not object_keys(row,required,p):continue
            if row['sector_code'] not in CODES:errors.append(p+': public sector identifier')
            ids(row['evidence_ids'],p+'.evidence_ids')
            if field=='interpretations':text(row['rating'],p+'.rating');text(row['reason'],p+'.reason')
            elif field=='weights':number(row['weight'],p+'.weight');text(row['rationale'],p+'.rationale')
            else:
                text(row['constraint_id'],p+'.constraint_id');number(row['bound'],p+'.bound')
                if row['kind'] not in ('sector_min_weight','sector_max_weight'):errors.append(p+': constraint kind')
    return errors


def audit(run, manifest_path, registration_path, registration_sha):
    from datetime import datetime
    run, manifest_path = Path(run).resolve(), Path(manifest_path).resolve()
    checks, facts, evidence, cache = [], [], {}, {}
    def label(path):
        path = Path(path).resolve()
        try: return path.relative_to(ROOT).as_posix()
        except ValueError: return str(path)
    def resolve(path):
        p = Path(path)
        return p if p.is_absolute() else ROOT/p
    def check(name, condition, detail=None):
        checks.append({'check': name, 'status': 'not_observed' if condition is None else 'pass' if condition else 'fail',
                       'pass': None if condition is None else bool(condition), 'detail': detail})
    def test(name, fn, *required):
        if any(x is None for x in required):
            check(name, None, 'Required evidence missing; not PASS.'); return
        try: check(name, fn())
        except Exception as exc: check(name, False, {'error_type':type(exc).__name__,'error':str(exc)})
    def derive(name, fn, *required):
        if any(x is None for x in required): return None
        try: return fn()
        except Exception as exc:
            check(name, False, {'error_type':type(exc).__name__,'error':str(exc)}); return None
    def data(path):
        path=Path(path).resolve()
        if path in cache: return cache[path]
        if not path.is_file():
            check('available:'+label(path),None,'File absent at audit time.');cache[path]=None;return None
        try: value=path.read_bytes()
        except OSError as exc:
            check('readable:'+label(path),False,str(exc));cache[path]=None;return None
        evidence[label(path)]=hashlib.sha256(value).hexdigest();cache[path]=value;return value
    def load(path):
        raw=data(path)
        return derive('json:'+label(path),lambda:json.loads(raw.decode('utf-8-sig')),raw)
    def pin(name,path,expected):
        raw=data(path);test(name,lambda:hashlib.sha256(raw).hexdigest()==expected,raw)
    def lines(path):
        raw=data(path)
        if raw is None:return None,None
        out=[];partial=False;parts=raw.splitlines()
        for i,line in enumerate(parts):
            if not line.strip():continue
            try:out.append(json.loads(line))
            except (ValueError,UnicodeError) as exc:
                if i==len(parts)-1 and not raw.endswith(b'\n'):
                    partial=True;check('partial_line:'+label(path),None,'Preserved incomplete trailing bytes.')
                else:check('json_lines:'+label(path),False,str(exc))
        return out,partial
    manifest=load(manifest_path);runtime=load(manifest_path.parent/'runtime.json')
    packet=load(manifest_path.parent/'model_packet.json');market=load(manifest_path.parent/'market_input.json')
    summary=load(run/'summary.json');invocation=load(run/'invocation.json')
    snap=load(run/'manifest_snapshot.json');rsnap=load(run/'runtime.json')
    test('manifest_snapshot_identical',lambda:snap==manifest,snap,manifest)
    test('runtime_snapshot_identical',lambda:rsnap==runtime,rsnap,runtime)
    test('manifest_hash_at_launch',lambda:invocation['manifest_sha256']==hashlib.sha256(data(manifest_path)).hexdigest(),invocation,manifest)
    condition=policy=None
    if manifest is not None:
        for name,expected in manifest.get('inputs',{}).items():pin('prepared_'+name,manifest_path.parent/name,expected)
        for name,expected in manifest.get('software',{}).items():pin('software_'+name,ROOT/'research'/name,expected)
        refs=[manifest.get('inherited_conditions_evidence'),manifest.get('source_request')]
        for group in ('primary_source_evidence','renderer_policy_evidence','schema_evidence'):
            check('manifest_'+group+'_present',bool(manifest.get(group)));refs.extend(manifest.get(group,[]))
        for item in refs:
            if item:pin('reference_'+label(resolve(item['path'])),resolve(item['path']),item['sha256'])
        if manifest.get('inherited_conditions_evidence'):condition=load(resolve(manifest['inherited_conditions_evidence']['path']))
        policies=[x for x in manifest.get('renderer_policy_evidence',[]) if x['sha256']==POLICY_SHA]
        check('fixed_renderer_policy_manifest',len(policies)==1)
        if len(policies)==1:policy=load(resolve(policies[0]['path']))
    test('case_fixed_before_outcomes',lambda:manifest['case_id']==CASE and manifest['arm']=='R1' and manifest['planned_cases']==1 and manifest['planned_stages']==[1,2,3,4],manifest)
    test('selected_packet_value_hash',lambda:hashlib.sha256(canonical(packet).encode()).hexdigest()==manifest['selected_packet_value_sha256'],packet,manifest)
    test('runtime_renderer_policy_id',lambda:runtime['renderer_policy']==policy['policy_id'],runtime,policy)
    for name,digest in IMMUTABLE_BASE.items():pin('immutable_v44_'+name,ROOT/'research'/name,digest)
    pin('immutable_v44_round1_record',V44_REVIEW,V44_REVIEW_SHA)
    prior_review=load(V44_REVIEW)
    if prior_review is not None:
        for row in prior_review['sources']:
            if row['path'].startswith(('data/local_sector_runtime/single_case_v44_20261018/',
                                       'data/sector_protocol/v44_single_case_20261018/')):
                pin('immutable_v44_artifact_'+row['path'],resolve(row['path']),row['sha256'])
    pin('immutable_v44_conditions', ROOT/'research/v44_conditions_reference_20261018.json',
        'a403d4c37d1581f9af21af8ba7a6333614d890ff15277e83181c1204549a9c5b')
    pin('reviewed_v45_reference', ROOT/'research/v45_revision_reference_20261018.json',
        '57a9c86c2bbc08a1006d6339bcd3303194ae8975cab14d6c5603a3191122dd79')
    test('v45_protocol_revision',lambda:manifest['protocol_version']==runtime['protocol_version']=='4.5',manifest,runtime)
    source_text=data(ROOT/'research/run_sector_workflow.py')
    schema_text=data(ROOT/'research/sector_response_schema.py')
    system=derive('pinned_system_literal',lambda:literal_assignment(source_text.decode('utf-8'),'SYSTEM'),source_text)
    tasks=derive('pinned_tasks_literal',lambda:literal_assignment(source_text.decode('utf-8'),'STAGES'),source_text)
    instruction=derive('pinned_grounding_literal',lambda:literal_assignment(schema_text.decode('utf-8'),'CONTRACT_INSTRUCTION'),schema_text)
    schemas={n:load(manifest_path.parent/f'response_schema_stage{n}.json') for n in range(1,5)}
    for n,schema in schemas.items():
        def schema_has_no_answers(schema=schema):
            props=schema['properties']
            if set(schema['required'])!=KEYS or set(props)!=KEYS or schema['additionalProperties'] is not False:return False
            if props['source_id']!={'type':['string','null']}:return False
            if props['interpretations']['items']['properties']['rating']!={'type':'string','minLength':1}:return False
            def visit(node,path=''):
                if isinstance(node,dict):
                    if any(k in node for k in ('const','default','prefixItems','uniqueItems','contains')):return False
                    if 'enum' in node and node['enum'] not in (CODES,['sector_min_weight','sector_max_weight']):return False
                    return all(visit(v,path+'/'+k) for k,v in node.items())
                if isinstance(node,list):return all(visit(v,path) for v in node)
                return True
            return visit(schema)
        test('schema_'+str(n)+'_structure_without_answer_values',schema_has_no_answers,schema)
    reg=load(registration_path)
    pin('pre_run_registration_fixed_hash',registration_path,registration_sha)
    if reg is not None:
        for item in reg.get('reference_files',reg.get('references',[])):
            # Offline opaque-byte integrity check only, no evaluator parsing.
            pin('registration_reference_'+item['path'],resolve(item['path']),item['sha256'])
    test('registration_recorded_before_launch',lambda:datetime.fromisoformat(reg['registered_at_utc'])<=datetime.fromisoformat(invocation['started_at_utc']),reg,invocation)
    test('registration_same_case_no_main',lambda:reg['case_id']==CASE and reg['planned_cases']==1 and reg['planned_stages']==[1,2,3,4] and reg['execution_policy']['main_calls']==0 and reg['main_frozen'] is False,reg)
    test('registration_no_repair_or_retry',lambda:reg['execution_policy']['automatic_retries']==0 and reg['execution_policy']['raw_repair'] is False and reg['execution_policy']['retain_failed_attempts'] is True,reg)
    test('no_retry_main_or_human_pass',lambda:summary['automatic_retries']==0 and summary['main_model_calls']==0 and summary['main_freeze'] is False and summary['human_semantic_pass'] is False,summary)
    test('case_completed_four_stages',lambda:summary['status']=='completed_four_stages' and summary['completed_workflow_stages']==4 and summary['completed_cases']==1,summary)
    previous_logical=previous_sent=previous_content=previous_feedback=None
    counts=dict(generation_requests_attempted=0,render_requests_attempted=0,completed_workflow_stages=0,http_streams_completed=0,unexpected_generation_evidence_in_render=0)
    for n in range(1,5):
        tag=f's{n}_';folder=run/f'stage{n}_transport';case=run/CASE;http=folder/'http_0001_generation'
        if not folder.exists() and not (case/f'stage{n}_request.json').exists():
            check(tag+'stage_evidence',None,'Stage absent: not started or not observed, never PASS.')
            facts.append({'stage':n,'status':'not_started_or_not_observed','generation_request_recorded':False})
            previous_logical=previous_sent=previous_content=previous_feedback=None;continue
        logical=load(case/f'stage{n}_request.json');logical_copy=load(folder/'logical_messages.json')
        grounded=load(folder/'grounded_messages.json')
        stage_schema=load(folder/'response_schema.json')
        stored=load(folder/'authoritative_body.json');spec=load(folder/'worker_spec.json');request=load(http/'request.json')
        body=derive(tag+'generation_body',lambda:request['body'],request)
        sent=derive(tag+'sent_messages',lambda:(body if body is not None else stored)['messages'],body if body is not None else stored)
        number=len(list(folder.glob('http_*_generation/request.json')));counts['generation_requests_attempted']+=number
        check(tag+'no_duplicate_generation_requests',number<=1,{'recorded_request_envelopes':number})
        test(tag+'authoritative_request',lambda:body==stored==spec['body'] and request['path']=='/api/chat',body,stored,spec)
        wire=data(folder/'authoritative_body.bin')
        test(tag+'authoritative_serialization',lambda:wire==json.dumps(stored,ensure_ascii=False,allow_nan=False).encode(),wire,stored)
        expected=derive(tag+'condition_schema',lambda:copy.deepcopy(condition['recommended_request'])|{'stream':True,'format':schemas[n]},condition,schemas[n])
        test(tag+'planned_conditions_exact',lambda:{k:v for k,v in stored.items() if k!='messages'}==expected,stored,expected)
        test(tag+'sent_conditions_exact',lambda:{k:v for k,v in body.items() if k!='messages'}==expected,body,expected)
        test(tag+'logical_history_record',lambda:logical==logical_copy,logical,logical_copy)
        test(tag+'schema_api_and_saved_match',lambda:stage_schema==schemas[n]==stored['format'],stage_schema,schemas[n],stored)
        test(tag+'system_unchanged',lambda:logical[0]=={'role':'system','content':system},logical,system)
        test(tag+'expected_message_count',lambda:len(logical)==2+3*(n-1),logical)
        if n>1:
            test(tag+'previous_messages_verbatim',lambda:logical[:len(previous_logical)]==previous_logical,logical,previous_logical)
            test(tag+'previous_sent_verbatim',lambda:sent[:len(previous_sent)]==previous_sent,sent,previous_sent)
            test(tag+'previous_assistant_verbatim',lambda:logical[-3]=={'role':'assistant','content':previous_content},logical,previous_content)
            test(tag+'feedback_verbatim',lambda:logical[-2]=={'role':'user','content':previous_feedback},logical,previous_feedback)
        def reconstruct_grounding():
            result=copy.deepcopy(logical);seen=[]
            for i,message in enumerate(logical):
                if message['role']!='user':continue
                value=strict_object(message['content'])
                if 'stage' not in value:
                    if set(value)!={'calculator_feedback'}:raise ValueError('Unknown user message')
                    continue
                stage=value['stage']
                if type(stage) is not int or stage!=len(seen)+1 or stage>n:raise ValueError('Stage order')
                expected_keys={'stage','task','common_market','institution_document'} if stage==1 else {'stage','task'}
                if set(value)!=expected_keys or value['task']!=tasks[stage]:raise ValueError('Original task changed')
                value['response_schema']=copy.deepcopy(schemas[stage]);value['response_contract_instruction']=instruction
                result[i]['content']=json.dumps(value,ensure_ascii=False,allow_nan=False);seen.append(stage)
            if seen!=list(range(1,n+1)):raise ValueError('Missing stage message')
            return result
        expected_grounded=derive(tag+'independent_grounding',reconstruct_grounding,logical,tasks,instruction,*schemas.values())
        test(tag+'grounding_exact',lambda:grounded==expected_grounded,grounded,expected_grounded)
        test(tag+'schema_in_current_prompt',lambda:strict_object(grounded[-1]['content'])['response_schema']==schemas[n],grounded,schemas[n])
        original=derive(tag+'stage1_payload',lambda:json.loads(logical[1]['content']),logical)
        test(tag+'ordered_stage',lambda:json.loads(logical[-1]['content'])['stage']==n,logical)
        test(tag+'public_packet_market_exact',lambda:canonical(original['institution_document'])==canonical(packet) and canonical(original['common_market'])==canonical(market),original,packet,market)
        def restore():
            result=json.loads(sent[1]['content']);small=result['common_market']
            if type(small.get('covariance_ddof')) is not int or small['covariance_ddof']!=1:raise ValueError('Exact ddof=1 absent')
            if 'sample_covariance_ddof_1' in small or 'baseline_weights_array' in small:raise ValueError('Duplicate fields unexpectedly present')
            del small['covariance_ddof'];small['sample_covariance_ddof_1']=copy.deepcopy(small['covariance'])
            small['baseline_weights_array']=[small['baseline_weights'][c] for c in small['sector_codes']];return result
        restored=derive(tag+'projection_structure',restore,sent)
        grounded_first=derive(tag+'grounded_first',lambda:strict_object(grounded[1]['content']),grounded)
        test(tag+'exact_projection_roundtrip',lambda:canonical(restored)==canonical(grounded_first) and floats(restored)==floats(grounded_first),restored,grounded_first)
        test(tag+'remaining_strings_unchanged',lambda:sent[0]==grounded[0] and sent[2:]==grounded[2:],sent,grounded)
        rq=load(folder/'render_only/request.json');rr=load(folder/'render_only/response.json')
        rv=load(folder/'render_only/validation.json');ro=load(folder/'render_only/result.json')
        counts['render_requests_attempted']+=int((folder/'render_only/request.json').is_file())
        if ro is not None:counts['unexpected_generation_evidence_in_render']+=int(bool(ro.get('unexpected_generation_evidence')))
        expected_render=derive(tag+'expected_render',lambda:copy.deepcopy(stored)|{'stream':False,'_debug_render_only':True},stored)
        test(tag+'render_request_matches',lambda:rq['path']=='/api/chat' and rq['body']==expected_render,rq,expected_render)
        rqb=data(folder/'render_only/request_body.bin');rrb=data(folder/'render_only/response_body.bin')
        test(tag+'render_request_bytes',lambda:rqb==json.dumps(rq['body'],ensure_ascii=False,allow_nan=False).encode(),rq,rqb)
        test(tag+'render_response_bytes',lambda:json.loads(rrb)==rr,rr,rrb)
        rendered=derive(tag+'rendered_template',lambda:rr['_debug_info']['rendered_template'],rr)
        rendered_bytes=data(folder/'render_only/rendered_prompt.txt')
        test(tag+'rendered_prompt_file_bytes',lambda:rendered_bytes==rendered.encode('utf-8'),rendered_bytes,rendered)
        def spans():
            cursor=0;out=[]
            for i,message in enumerate(sent):
                raw=message['content'];text=raw if i==0 else raw.strip(' \t\r\n');prefix=suffix='';preserved=None
                if i:
                    prefix=raw[:len(raw)-len(raw.lstrip(' \t\r\n'))];suffix=raw[len(raw.rstrip(' \t\r\n')):]
                    parsed=json.loads(raw);preserved=isinstance(parsed,dict) and canonical(parsed)==canonical(json.loads(text))
                    if not preserved:raise ValueError('JSON value changed')
                found=rendered.find(text,cursor)
                if found<0:raise ValueError('Rendered content missing or changed at '+str(i))
                cursor=found+len(text)
                out.append(dict(message_index=i,role=message['role'],start_character=found,end_character=cursor,raw_content_utf8_sha256=hashlib.sha256(raw.encode()).hexdigest(),expected_renderer_content_utf8_sha256=hashlib.sha256(text.encode()).hexdigest(),removed_outer_prefix=prefix,removed_outer_suffix=suffix,strict_json_payload_value_preservation=preserved,http_content_modified=False))
            return out
        expected_spans=derive(tag+'render_order_and_values',spans,sent,rendered)
        test(tag+'render_validation_recomputed',lambda:rv['message_spans']==expected_spans and rv['renderer_policy']==policy['policy_id'] and rv['renderer_policy_sha256']==POLICY_SHA and rv['rendered_utf8_sha256']==hashlib.sha256(rendered.encode()).hexdigest(),rv,expected_spans,policy,rendered)
        test(tag+'no_render_generation',lambda:rr.get('eval_count',0)==0 and rr.get('prompt_eval_count',0)==0 and not any(rr.get('message',{}).get(k) for k in ('content','thinking','tool_calls')),rr)
        for phase in ('before_render','before_generation'):
            observed=load(folder/f'pin_{phase}.json')
            test(tag+phase+'_pins',lambda observed=observed:observed['version']['version']==runtime['engine_version'] and observed['selected_model']['digest']==runtime['digest'] and observed['template_sha256']==runtime['template_sha256'],observed,runtime)
        events,partial=lines(http/'raw_stream.bin');logged,logged_partial=lines(http/'events.jsonl')
        response=load(http/'response.json');result=load(http/'result.json');assembled=load(http/'assembled_text.json')
        if result is not None:counts['http_streams_completed']+=int(result.get('status')=='completed')
        test(tag+'raw_decoded_prefix_matches_events',lambda:events==[x['event'] for x in logged],events,logged)
        terminal=events[-1] if events and isinstance(events[-1],dict) and events[-1].get('done') is True else None
        content=derive(tag+'raw_content',lambda:''.join(x.get('message',{}).get('content','') for x in events),events)
        test(tag+'terminal_stop_without_cap',lambda:terminal.get('done_reason')=='stop' and response.get('done_reason')=='stop' and not partial and not logged_partial,terminal,response)
        test(tag+'response_metadata_matches_raw_terminal',lambda:all(response.get(k)==v for k,v in terminal.items() if k!='message'),terminal,response)
        test(tag+'raw_content_identical',lambda:content==response['message']['content']==assembled['content'],content,response,assembled)
        test(tag+'no_thinking_toolcalls',lambda:not any(x.get('message',{}).get('thinking') or x.get('message',{}).get('tool_calls') for x in events),events if events else None)
        contract=load(folder/'response_contract_validation.json')
        proposal=derive(tag+'strict_response_JSON',lambda:strict_object(content),content if response is not None else None)
        schema_errors=derive(tag+'independent_contract',lambda:structure_errors(proposal,n),proposal)
        test(tag+'response_satisfies_independent_contract',lambda:schema_errors==[],schema_errors)
        test(tag+'online_contract_agrees',lambda:contract['valid']==(not schema_errors) and contract['response_repaired'] is False and contract['human_semantic_pass'] is False and contract['content_utf8_sha256']==hashlib.sha256(content.encode()).hexdigest(),contract,schema_errors,content)
        test(tag+'request_after_registration',lambda:datetime.fromisoformat(result['started_at_utc'])>=datetime.fromisoformat(reg['registered_at_utc']),result,reg)
        test(tag+'response_model_pin',lambda:response['model']==runtime['model'],response,runtime)
        wr=load(case/f'stage{n}_response.json');record=load(case/f'stage{n}_record.json')
        counts['completed_workflow_stages']+=int(record is not None)
        test(tag+'workflow_response_identical',lambda:wr==response,wr,response)
        test(tag+'no_output_repair',lambda:record['repair_applied'] is False and canonical(record['raw_proposal'])==canonical(json.loads(content)),record,content)
        test(tag+'calculator_receives_raw_values',lambda:record['calculator_arguments']=={'weights':record['raw_proposal']['weights'],'submitted_constraints':record['raw_proposal']['submitted_constraints']},record)
        test(tag+'visible_evidence_ids',lambda:record['visible_evidence_ids']==[x['evidence_id'] for x in packet['evidence_passages']],record,packet)
        supervisor=load(folder/'supervisor_result.json');worker=load(folder/'worker_summary.json');unload=load(folder/'unload_and_residency.json')
        test(tag+'supervised_success',lambda:supervisor['status']=='worker_exited' and supervisor['worker_exit_code']==0 and supervisor['deadline_seconds']==900,supervisor)
        test(tag+'worker_counts',lambda:worker['generation_requests_attempted']==number and worker['pilot_model_calls']==number and worker['render_requests_attempted']==int(rq is not None) and worker['main_model_calls']==0 and worker['automatic_retries']==0,worker)
        test(tag+'unload_confirmed',lambda:unload['status']=='no_resident_models_observed' and unload['unload']['status']=='ok' and unload['unload']['value']['done'] is True and unload['ps'][-1].get('status')=='ok' and unload['ps'][-1].get('value',{}).get('models')==[],unload)
        before=load(folder/'server_log_before.json');delta=load(folder/'server_log_delta.json');after=data(folder/'server_log_after_snapshot.bin')
        test(tag+'server_log_hash_and_prefix',lambda:delta['original_prefix_retained'] is True and delta['prior_bytes']==before['bytes'] and delta['after_bytes']==len(after) and delta['sha256']==hashlib.sha256(after).hexdigest() and before['sha256']==hashlib.sha256(after[:before['bytes']]).hexdigest(),before,delta,after)
        stage_log=derive(tag+'stage_log_delta',lambda:after[before['bytes']:].decode('utf-8',errors='replace'),after,before)
        monitor,monitor_partial=lines(folder/'monitor.jsonl')
        memory=[x.get('memory',{}) for x in monitor if isinstance(x,dict)] if monitor is not None else []
        working=[x['working_set_sum_bytes'] for x in memory if type(x.get('working_set_sum_bytes')) is int]
        available=[x['available_physical_bytes'] for x in memory if type(x.get('available_physical_bytes')) is int]
        facts.append(dict(stage=n,status='workflow_recorded' if record is not None else 'partial_or_failed',generation_request_recorded=body is not None,render_request_recorded=rq is not None,supervisor_status=supervisor.get('status') if supervisor else None,worker_status=worker.get('status') if worker else None,stream_status=result.get('status') if result else None,http_status=result.get('http_status') if result else None,observed_prompt_tokens=response.get('prompt_eval_count') if response else None,observed_output_tokens=response.get('eval_count') if response else None,metrics=result.get('metrics') if result else None,done_reason=response.get('done_reason') if response else terminal.get('done_reason') if terminal else None,decoded_raw_events=len(events) if events is not None else None,partial_raw_line=partial,independent_tokenization=False,explicit_no_truncation=(body.get('truncate') is False and body.get('shift') is False) if body else None,stage_delta_contains_truncated_zero=('truncated = 0' in stage_log) if stage_log is not None else None,memory_samples=len(monitor) if monitor is not None else None,sampled_max_working_set_sum_bytes=max(working) if working else None,sampled_min_available_physical_bytes=min(available) if available else None,memory_partial_line=monitor_partial))
        previous_logical,previous_sent,previous_content=logical,sent,content if response is not None else None
        previous_feedback=derive(tag+'feedback',lambda:json.dumps({'calculator_feedback':record['calculator_result']},ensure_ascii=False,allow_nan=False),record)
    final=load(run/CASE/'final.json');fourth=load(run/CASE/'stage4_record.json')
    test('final_is_fourth_raw_proposal',lambda:canonical(final)==canonical(fourth['raw_proposal']),final,fourth)
    trace=load(run/CASE/'trace.json')
    records=[load(run/CASE/f'stage{n}_record.json') for n in range(1,5)]
    test('trace_equals_ordered_raw_records',lambda:trace==records,trace,*records)
    test('final_financial_validity_reported_separately',lambda:summary['final_allocation_valid']==fourth['calculator_result']['allocation']['valid'] and summary['semantic_validity_assessed'] is False and summary['replaces_prior_v44_failure'] is False,summary,fourth)
    counts['generation_stages_not_started']=[n for n in range(1,5) if not (run/f'stage{n}_transport/http_0001_generation/request.json').is_file()]
    test('summary_counts_match_artifacts',lambda:all(summary[k]==v for k,v in counts.items()) and summary['pilot_model_calls']==counts['generation_requests_attempted'],summary)
    test('four_generation_four_render_requests',lambda:counts['generation_requests_attempted']==4 and counts['render_requests_attempted']==4,summary)
    failed=[x['check'] for x in checks if x['status']=='fail'];missing=[x['check'] for x in checks if x['status']=='not_observed']
    complete=bool(summary and summary.get('status')=='completed_four_stages' and counts['completed_workflow_stages']==4)
    all_passed=complete and not failed and not missing
    return dict(round=1,scope='v4.5 execution/schema/grounding/history/transport audit, not financial arithmetic or semantic quality',case_id=CASE,run_dir=label(run),run_summary_status=summary.get('status') if summary else None,audit_status='complete_pass' if all_passed else 'complete_with_issues' if complete else 'partial_or_failed_run_audit',checks=checks,check_count=len(checks),failed_checks=failed,not_observed_checks=missing,all_passed=all_passed,complete_case_observed=complete,stage_facts=facts,observed_counts=counts,sources=[{'path':p,'sha256':h} for p,h in evidence.items()],auditor_source_sha256=sha(Path(__file__)),limits=['Missing evidence or unstarted stages are not PASS; incomplete streams support only a decoded-prefix audit.','Rendered text uses the predeclared JSON-boundary policy; HTTP strings remain unchanged.','Provider counters and stage-local log strings are observations, not independent tokenization or context-capacity proof.','Only the stage log delta is searched; earlier entries in the full server log are excluded.','Memory extrema are sampled observations, not host-wide peaks or dedicated physical GPU capacity.','Registration times are local records, not externally timestamped preregistration. Evaluator references are hashed as opaque bytes only.','Arithmetic and claim-to-source interpretation belong to rounds 2 and 3.','Files are read once each; re-audit a settled archive before final completion claims if the process was still writing.'],model_calls_by_auditor=0,response_repairs_by_auditor=0,human_semantic_pass=False)



def render_report(result):
    esc=lambda v:html.escape(str(v))
    rows=''.join('<tr><td>'+esc(x['check'])+'</td><td>'+esc(x['status'])+'</td><td>'+esc(x['detail'])+'</td></tr>' for x in result['checks'])
    facts=''.join('<li>'+esc(json.dumps(x,ensure_ascii=False))+'</li>' for x in result['stage_facts'])
    return '<!doctype html><html lang="en"><meta charset="utf-8"><title>v4.5 independent round 1</title><style>body{font:15px/1.6 system-ui;max-width:1200px;margin:32px auto;padding:0 24px}td,th{border:1px solid #ddd;padding:6px;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%}li{overflow-wrap:anywhere}</style><h1>v4.5 independent execution audit</h1><p>'+esc(result['audit_status'])+'; complete case: '+esc(result['complete_case_observed'])+'. This is not financial, semantic or human-review approval.</p><p>Model calls: 0; output repairs: 0. Missing or partial evidence is not PASS.</p><h2>Observed stages</h2><ul>'+facts+'</ul><h2>Checks</h2><table><tr><th>Check</th><th>Status</th><th>Detail</th></tr>'+rows+'</table><h2>Limits</h2><ul>'+''.join('<li>'+esc(x)+'</li>' for x in result['limits'])+'</ul></html>'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',type=Path,default=ROOT/'data/local_sector_runtime/single_case_v45_20261018')
    p.add_argument('--manifest',type=Path,default=ROOT/'data/sector_protocol/v45_single_case_20261018/manifest.json')
    p.add_argument('--registration',type=Path,default=REGISTRATION)
    p.add_argument('--registration-sha256',default=REGISTRATION_SHA)
    p.add_argument('--output',type=Path,default=ROOT/'research/v45_single_case_round1_20261018.json')
    p.add_argument('--html-output',type=Path,default=ROOT/'research/v45_single_case_round1_20261018.html')
    a=p.parse_args()
    if len(a.registration_sha256)!=64 or any(x not in '0123456789abcdef' for x in a.registration_sha256.lower()):
        p.error('An independently recorded registration SHA256 is required')
    if a.output.exists() or a.html_output.exists():raise FileExistsError('Preserve earlier audits; choose new output paths')
    result=audit(a.run_dir,a.manifest,a.registration,a.registration_sha256.lower())
    with a.output.open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    with a.html_output.open('x',encoding='utf-8') as f:f.write(render_report(result))
    print(json.dumps({'audit_status':result['audit_status'],'check_count':result['check_count'],'failed_checks':result['failed_checks'],
        'not_observed_check_count':len(result['not_observed_checks']),'output':str(a.output),'html_output':str(a.html_output),'model_calls':0},ensure_ascii=False))
    return 0 if result['all_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
