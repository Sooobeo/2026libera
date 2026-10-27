"""One isolated local engineering generation, excluded from v6.3 slots.

The fixed connectivity prompt matches the remote probe. num_thread=8 and
num_gpu=0 make local hardware use explicit. No generation retries are made.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,time,urllib.request
from research.v63.exact_tokenizer import NativeTokenizer

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/v63_20261027/runtime/local_windows/connectivity_probe_001'
ORIGIN='http://127.0.0.1:11435'
MODEL_HASH='8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7'
TEMPLATE_HASH='ae370d884f108d16e7cc8fd5259ebc5773a0afa6e078b11f4ed7e39a27e0dfc4'
def now():return datetime.now(timezone.utc).isoformat()
def packed(value):return json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
def save(name,value):(OUT/name).write_bytes(packed(value))
def http(name,path,body=None):
    request=urllib.request.Request(ORIGIN+path,data=packed(body) if body is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=120) as response:raw=response.read()
    (OUT/name).write_bytes(raw);return json.loads(raw)

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    version=http('version.json','/api/version');tags=http('tags.json','/api/tags')
    show=http('show.json','/api/show',{'model':'qwen3:1.7b'})
    if version['version']!='0.35.1':raise ValueError('Version drift.')
    if next(m['digest'] for m in tags['models'] if m['name']=='qwen3:1.7b')!=MODEL_HASH:raise ValueError('Model digest drift.')
    if hashlib.sha256(show['template'].encode()).hexdigest()!=TEMPLATE_HASH:raise ValueError('Template drift.')
    native=NativeTokenizer(json.loads((ROOT/'data/v63_20261027/continuation/deployment/local_windows/tokenizer_config.json').read_text()))
    request={'model':'qwen3:1.7b','messages':[{'role':'user','content':'Return exactly the JSON object {"ok":true}.'}],
             'stream':False,'think':False,'format':'json','options':{'temperature':0,'seed':1001,'num_predict':32,'num_ctx':2048,'num_thread':8,'num_gpu':0},'keep_alive':'0s'}
    save('request.json',request)
    rendered=http('render_only_response.json','/api/chat',{**request,'_debug_render_only':True})
    if rendered.get('eval_count') or rendered.get('message',{}).get('content'):raise ValueError('Unexpected render-only generation.')
    text=rendered['_debug_info']['rendered_template'];receipt=native.receipt(text);save('tokenizer_receipt.json',receipt);native.close()
    (OUT/'rendered_prompt.txt').write_text(text,encoding='utf8',newline='')
    start=time.monotonic();save('generation_attempt.json',{'status':'attempt_started','started_at_utc':now(),'live_engineering_generation_requests':1,'actual_experimental_requests':0})
    try:
        response=http('response.json','/api/chat',request);wall=time.monotonic()-start
    except Exception as exc:
        save('summary.json',{'status':'failed','error_type':type(exc).__name__,'error':str(exc),'wall_seconds':time.monotonic()-start,
             'live_engineering_generation_requests':1,'actual_experimental_requests':0,'retries':0});raise
    count_match=response.get('prompt_eval_count')==receipt['token_count']
    result={'status':'completed' if count_match and response.get('done') else 'verification_failed','completed_at_utc':now(),
            'role':'Engineering latency/connectivity only; excluded from all v6.3 stages, pilots and results.',
            'origin':ORIGIN,'model_sha256':MODEL_HASH,'engine':'0.35.1','chat_template_sha256':TEMPLATE_HASH,
            'live_engineering_generation_requests':1,'actual_experimental_requests':0,'retries':0,
            'native_prompt_count':receipt['token_count'],'provider_prompt_count':response.get('prompt_eval_count'),'exact_count_match':count_match,
            'wall_seconds':wall,'response_content':response.get('message',{}).get('content'),'done_reason':response.get('done_reason'),
            'load_seconds':response.get('load_duration',0)/1e9,'prompt_eval_seconds':response.get('prompt_eval_duration',0)/1e9,
            'eval_seconds':response.get('eval_duration',0)/1e9,'eval_count':response.get('eval_count'),
            'generated_tokens_per_second':response.get('eval_count',0)/(response.get('eval_duration',0)/1e9) if response.get('eval_duration') else None,
            'hardware_options':request['options'],'comparison_limit':'Same short prompt/model; local thread count explicit 8 versus remote default. Not evidence of full-task capacity.'}
    save('summary.json',result);print(json.dumps(result))

if __name__=='__main__':main()
