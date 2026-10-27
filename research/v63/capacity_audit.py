"""Read-only model-capacity measurements; render/tokenize only, no generation.

Representative actual cases are fixed at development-001/main-001. Future
stage-output lengths are explicit arithmetic assumptions, never model results.
Writes only a separate audit directory, never campaign/code/freeze artifacts.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path

from research.v63 import build_run,numerics,runtime
from research.v63.exact_tokenizer import NativeTokenizer
from research.v63.ollama_transport import OllamaTransport,packed,digest_bytes
from research.v63.retrieval import TokenCounter,canonical


class Captured(BaseException):
    def __init__(self,request):self.request=deepcopy(request)


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def initial_request(case,freeze,directory):
    """Capture the unmodified production prompt before any transport call."""
    _,check=build_run.make_numeric_callbacks(case)
    def capture(request):raise Captured(request)
    def forbid(*args,**kwargs):raise AssertionError('Generation is forbidden in capacity audit')
    try:
        runtime.run_trajectory(case['baseline'],case['retrieval'],'C-context',forbid,forbid,check,
            freeze,output_dir=directory,count_rendered_request=capture,engineering=True)
    except Captured as result:return result.request
    raise AssertionError('Production prompt was not captured')


def run(root,config_path,output):
    root=Path(root).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError('Refuse to overwrite an earlier capacity audit')
    output.mkdir(parents=True)
    config=build_run.read_json(config_path)
    # These are the candidate2 source additions, not edits to the live config.
    config.setdefault('mandate_atomic_units_path','data/v63_20261027/continuation_sources/mandate_atomic_units_v2.json')
    config.setdefault('source_catalog_path','data/v63_20261027/numerical/evaluator_only/source_catalog_v2.json')
    frozen=build_run.read_json(root/config['runtime_freeze_path']);freeze=deepcopy(frozen)
    files=['runtime.py','build_run.py','numerics.py','retrieval.py','ollama_transport.py','exact_tokenizer.py','capacity_audit.py']
    refs=[root/'research/v63'/n for n in files]+[root/config['tokenizer_config_path'],Path(config_path).resolve()]
    refs.extend(root/config[k] for k in ('profiles_path','documents_path','mandate_atomic_units_path','source_catalog_path','runtime_freeze_path'))
    initial_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in refs}
    freeze.update(context_tokens=32768,output_tokens=4096,main_model_frozen=False,
        allowed_response_schema_sha256=[digest_bytes(packed(runtime.response_schema(i))) for i in (1,2,3)])
    tokenizer_path=root/config['tokenizer_config_path']
    native=NativeTokenizer(build_run.read_json(tokenizer_path))
    counter=TokenCounter(native.identity,native.count,True)
    transport=OllamaTransport(config['origin'],freeze,output/'render_http')
    calibration=numerics.calibrate(root)
    dev=numerics.generate_scenarios(calibration,'development')[0][0]
    main=numerics.generate_scenarios(calibration,'main')[0][0]
    atomic=build_run.load_mandate_units(root/config['mandate_atomic_units_path'])
    contexts=[16384,24576,32768,40960];lengths=[512,1024,2048];rows=[]
    try:
        for module,period in [('B-development','development'),('B-main','A_B'),('A','A_B'),('C','C')]:
            profiles=build_run.load_profiles(root/config['profiles_path'],period)
            for fund,profile in sorted(profiles.items()):
                if module.startswith('B'):
                    scenario=dev if module=='B-development' else main
                    case=build_run.b_input(profile,calibration,scenario,counter,mandate_units=atomic)
                else:case=build_run.actual_document_input(profile,calibration,module,root/config['documents_path'],counter)
                label=module+'__'+fund
                request=initial_request(case,freeze,output/'captured_engineering_only'/label)
                baseline=deepcopy(request);baseline['messages'][-1]['content']='STAGE 1\nADDITIONAL EVIDENCE\n'
                baseline_count=transport.render_and_count(baseline,native)
                full_count=transport.render_and_count(request,native)
                tools,check=build_run.make_numeric_callbacks(case)
                all_visible=runtime.disclosed_baseline_ids(case['baseline'])|set(case['retrieval']['full']['exposed_evidence_ids'])
                if module.startswith('B'):
                    name='posterior';ids=sorted(set(case['evidence_registry'])&all_visible)
                    if len(ids)!=12:raise ValueError('FULL must expose all twelve private numeric observations')
                    args={'exposed_evidence_ids':ids}
                else:
                    name='check_portfolio';args={'raw_weights':case['baseline']['h'],'exposed_evidence_ids':[]}
                response=tools(name,args,frozenset(all_visible))
                if 'error' in response:raise ValueError('Capacity calculator returned an error')
                tool_call=canonical({'kind':'tools','calls':[{'name':name,'arguments':args}]})
                tool_result='CALCULATOR RESULTS\n'+canonical([{'name':name,'result':response}])
                raw_check=check(case['baseline']['h'])
                raw_message='RAW WEIGHT CHECK (no normalization)\n'+canonical(raw_check)
                placeholder='x';placeholder_tokens=len(native.tokens(placeholder,add_special=False))
                history=deepcopy(request);history['response_schema']=runtime.response_schema(3)
                history['messages'].extend([
                    {'role':'assistant','content':tool_call},
                    {'role':'user','content':tool_result},
                    {'role':'assistant','content':placeholder},
                    {'role':'user','content':'STAGE 2\nADDITIONAL EVIDENCE\nUse the same evidence already in this full history.'},
                    {'role':'assistant','content':placeholder},
                    {'role':'user','content':raw_message},
                    {'role':'user','content':'STAGE 3\nADDITIONAL EVIDENCE\nUse the same evidence already in this full history.'},
                ])
                skeleton_render_count=transport.render_and_count(history,native)
                skeleton_count=skeleton_render_count-2*placeholder_tokens
                row={'module':module,'period':period,'fund_id':fund,
                    'scenario_id':scenario['scenario_id'] if module.startswith('B') else 'actual-documents-'+module,
                    'case_sha256':digest_bytes(canonical(case).encode()),
                    'baseline_render_tokens':baseline_count,'baseline_plus_FULL_render_tokens':full_count,
                    'stage1_headroom_with_4096_output_reserve':{str(c):c-full_count-4096 for c in contexts},
                    'calculator':name,'calculator_numeric_observation_ids':args.get('exposed_evidence_ids'),
                    'calculator_response_body_tokens':native.count(canonical(response)),
                    'calculator_user_message_tokens':native.count(tool_result),
                    'calculator_request_assistant_tokens':native.count(tool_call),
                    'automatic_stage2_raw_check_tokens':native.count(raw_message),
                    'stage3_fixed_history_render_tokens':skeleton_count,
                    'stage3_skeleton_render_tokens_with_placeholders':skeleton_render_count,
                    'each_placeholder_content_tokens':placeholder_tokens,
                    'history_assumption':'One stage1 calculator roundtrip; h used only to measure the check response. Stage1/2 final output contents are x placeholders in the exact fixed-history render, their measured content tokens subtracted and each replaced arithmetically by the stated token length.',
                    'headroom_assumptions':[{'each_prior_stage_output_tokens':length,
                        'projected_stage3_prompt_tokens':skeleton_count+2*length,
                        'reserve_for_stage3_output':4096,
                        'headroom_by_context':{str(c):c-skeleton_count-2*length-4096 for c in contexts}}
                        for length in lengths]}
                save(output/'tool_outputs'/f'{label}.json',{'calculator_call':json.loads(tool_call),
                    'calculator_response':response,'automatic_stage2_raw_check_at_h':raw_check,'row':row})
                rows.append(row)
                print(label,full_count,skeleton_count,flush=True)
        if initial_hashes!={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in refs}:
            raise ValueError('An input/code/freeze file changed during the capacity audit')
        report={'status':'render_and_native_capacity_measurements_complete','engineering_only':True,
            'generation_requests':0,'inference_calls':0,'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
            'model_sha256':freeze['model_sha256'],'chat_template_sha256':freeze['chat_template_sha256'],
            'tokenizer_identity':native.identity,'contexts':contexts,'output_reserve_tokens':4096,
            'effective_audit_config':config,'audit_transport_freeze':freeze,
            'candidate_runtime_unmodified':frozen,'files':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in refs],
            'limitations':['This is capacity-only, not model output quality, speed or outcome selection.',
                'B uses development-001/main-001; other scenarios vary in numeric token length.',
                'One calculator roundtrip is assumed; the protocol can allow more. Every extra retained response reduces headroom.',
                'Posterior uses all twelve visible numeric X IDs. Mandatory document IDs are not numeric observations.',
                'Check responses use the actual h vector, which is valid; invalid portfolios can yield longer diagnostics.',
                'Future assistant lengths are arithmetic assumptions, not predictions; exact fixed-history templates contain measured x placeholders, removed arithmetically before adding each assumed length.',
                'Context sizes do not certify RAM feasibility, execution speed or all future full histories. Actual per-call render gates remain required.'],
            'rows':rows}
        save(output/'capacity_report.json',report)
        import csv
        with (output/'capacity_headroom.csv').open('w',encoding='utf-8-sig',newline='') as handle:
            fields=['module','fund_id','baseline_render','baseline_FULL_render','tool_response','stage3_fixed','prior_each',*[str(c) for c in contexts]]
            writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader()
            for row in rows:
                for assumption in row['headroom_assumptions']:
                    writer.writerow({'module':row['module'],'fund_id':row['fund_id'],
                        'baseline_render':row['baseline_render_tokens'],'baseline_FULL_render':row['baseline_plus_FULL_render_tokens'],
                        'tool_response':row['calculator_response_body_tokens'],'stage3_fixed':row['stage3_fixed_history_render_tokens'],
                        'prior_each':assumption['each_prior_stage_output_tokens'],**assumption['headroom_by_context']})
        return report
    finally:native.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--config',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.root,args.config,args.output)
