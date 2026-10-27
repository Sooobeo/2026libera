"""Two prospective CPU timing probes; no experiment slots or response selection."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import json,time
from research.v63 import numerics
from research.v63.build_run import read_json,save_json,build_phase,make_numeric_callbacks
from research.v63.exact_tokenizer import NativeTokenizer
from research.v63.retrieval import TokenCounter
from research.v63.runtime import run_trajectory,response_schema
from research.v63.ollama_transport import OllamaTransport,packed,digest_bytes

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/v63_20261027/runtime/local_windows/q8_timing_probe_002'
class CapturedRequest(Exception):pass

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    base=ROOT/'data/v63_20261027/continuation/deployment/local_windows'
    config=read_json(base/'campaign_config.json')
    config['mandate_atomic_units_path']='data/v63_20261027/continuation_sources/mandate_atomic_units_v2.json'
    native=NativeTokenizer(read_json(ROOT/config['tokenizer_config_path']))
    freeze=read_json(base/'runtime_candidate.json');freeze.update(context_tokens=32768,output_tokens=64,request_timeout=900)
    freeze['allowed_response_schema_sha256']=[digest_bytes(packed(response_schema(i))) for i in (1,2,3)]
    captured=[];rows=[]
    try:
        package=build_phase(ROOT,config,'technical-smoke',TokenCounter(native.identity,native.count,True))
        case=next(iter(package['cases'].values()));tools,check=make_numeric_callbacks(case)
        def capture(raw):captured.append(json.loads(raw));raise CapturedRequest()
        try:run_trajectory(case['baseline'],case['retrieval'],'R0',capture,tools,check,freeze,
                output_dir=OUT/'prompt_capture_only',count_rendered_request=lambda r:0,engineering=True)
        except CapturedRequest:pass
        request=captured[0]
        for threads in (4,8):
            directory=OUT/f'threads_{threads}';settings=deepcopy(freeze);settings['fixed_options']['num_thread']=threads
            client=OllamaTransport(config['origin'],settings,directory/'http')
            # Each comparison starts from a fully unloaded model. Administrative calls do not generate.
            admin=directory/'administration';admin.mkdir()
            raw=client._http(admin,'unload_before','/api/generate',packed({'model':settings['model'],'keep_alive':0}))
            if json.loads(raw).get('done_reason')!='unload':raise ValueError('Cold-load baseline not confirmed.')
            tokens=client.render_and_count(request,native);frozen_request={**request,'expected_prompt_tokens':tokens}
            save_json(directory/'probe_intent.json',{'engineering_only':True,'actual_experimental_requests':0,'planned_engineering_requests':1,
                'threads':threads,'kv_cache_type':'q8_0','context_tokens':32768,'output_limit':64,'prompt_sha256':digest_bytes(packed(request['messages']))})
            start=time.monotonic()
            response=client(packed(frozen_request));elapsed=time.monotonic()-start
            save_json(directory/'response.json',response)
            row={'threads':threads,'elapsed_seconds':elapsed,'usage':response.get('usage'),
                 'finish_reason':response.get('finish_reason'),'prompt_tokens':tokens,'engineering_generation_requests':1,'experimental_generation_requests':0}
            rows.append(row);save_json(OUT/'progress.json',{'status':'running','measurements':rows})
            client._http(admin,'unload_after','/api/generate',packed({'model':settings['model'],'keep_alive':0}))
        save_json(OUT/'summary.json',{'status':'completed','engineering_only':True,'actual_experimental_requests':0,
            'live_engineering_generation_requests':len(rows),'retries':0,'measurements':rows,
            'comparison_scope':'Identical DODGX development stage1 prompt, 64 generated tokens, cold model load, sequential thread4 then8. Select only capacity/latency; response content is not analyzed. Not a full-history capacity test.',
            'finished_at_utc':datetime.now(timezone.utc).isoformat()})
        print(json.dumps(rows))
    finally:native.close()

if __name__=='__main__':main()
