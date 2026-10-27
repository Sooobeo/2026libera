"""Explicitly bounded remote engineering probe: one generation POST, no retry.
Run only inside the already authorized container 150 against its existing
Ollama PID2704/11434. Not an experiment or a model-output quality comparison.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,threading,time,urllib.request,urllib.error,zipfile

BASE=Path('/root/libera_v63_20261027')
OUT=BASE/'runtime/remote_qwen35_4b_resource_probe_001'
MODEL='qwen3.5:4b-q4_K_M'
DIGEST='d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04'
ORIGIN='http://127.0.0.1:11434'
SOURCE=BASE/'package_001/data/v63_20261027/campaign_results/runs/2bacd49c8a4888a6811c8ba32ad56be6ab55c28704986ae3b55c1034dbb34cc0/B-development/development-001__F03__R0__1/http/attempt_000001/generation.request.bin'

def sha(raw):return hashlib.sha256(raw).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def write(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=True,allow_nan=False)+'\n')
def get(path,name):
    with urllib.request.urlopen(ORIGIN+path,timeout=10) as response:raw=response.read()
    (OUT/name).write_bytes(raw);return json.loads(raw)
def memory():
    m={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if len(line.split())>=2 and line.split()[1].isdigit()}
    row={'utc':now(),'meminfo_kB':m,'loadavg':Path('/proc/loadavg').read_text().strip()}
    for name in ('memory.current','memory.max','memory.events'):
        p=Path('/sys/fs/cgroup')/name
        if p.exists():row['cgroup_'+name]=p.read_text().strip()
    return row

def main():
    OUT.mkdir(parents=True,exist_ok=False) # a second invocation cannot resend
    assert Path('/proc/2704/cmdline').read_bytes().replace(b'\x00',b' ').strip()==b'/usr/local/bin/ollama serve'
    version=get('/api/version','before_version.json');assert version['version']=='0.35.1'
    tags=get('/api/tags','before_tags.json')
    matches=[m for m in tags['models'] if m['name']==MODEL];assert len(matches)==1 and matches[0]['digest']==DIGEST
    ps=get('/api/ps','before_ps.json');assert not ps.get('models'),'Existing active model: stop without generation'
    original=SOURCE.read_bytes();(OUT/'source_generation.request.bin').write_bytes(original)
    body=json.loads(original);assert isinstance(body['messages'],list) and body['messages']
    assert '_debug_render_only' not in body
    options={'num_predict':64,'num_ctx':32768,'temperature':0,'seed':1001,'num_thread':4,'num_gpu':0,'use_mmap':True,'num_batch':256}
    body.update(model=MODEL,think=False,stream=False,options=options,keep_alive='0s')
    request=json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
    (OUT/'generation.request.bin').write_bytes(request)
    (OUT/'probe_script.py').write_bytes(Path(__file__).read_bytes())
    write('preflight.json',{'engineering_only':True,'model':MODEL,'model_digest':DIGEST,'options':options,'timeout_seconds':900,
        'max_generation_posts':1,'retries':0,'keep_alive':'0s','source_request':str(SOURCE),'source_sha256':sha(original),
        'request_sha256':sha(request),'request_bytes':len(request),'memory':memory(),'existing_ollama_pid':2704,
        'quality_or_effect_selection':False,'native_tokenizer_verified':False,'old_schema_and_different_hardware_not_directly_comparable':True})
    samples=[];stop=threading.Event()
    def monitor():
        while not stop.is_set():
            samples.append(memory());stop.wait(2)
    worker=threading.Thread(target=monitor,daemon=True);worker.start()
    started=time.perf_counter();receipt={'started_at_utc':now(),'generation_dispatches':1,'retries':0,'model_digest_before':DIGEST}
    write('generation_dispatch.json',receipt);raw=b'';result={}
    try:
        req=urllib.request.Request(ORIGIN+'/api/chat',data=request,headers={'Content-Type':'application/json'},method='POST')
        with urllib.request.urlopen(req,timeout=900) as response:
            receipt['http_status']=response.status;raw=response.read()
        result=json.loads(raw);receipt['status']='complete_http_response'
    except urllib.error.HTTPError as exc:
        receipt.update(status='http_error',http_status=exc.code,error=str(exc));raw=exc.read()
    except Exception as exc:receipt.update(status='transport_or_parse_error_no_retry',error_type=type(exc).__name__,error=str(exc))
    finally:
        receipt.update(ended_at_utc=now(),http_seconds=time.perf_counter()-started,response_bytes=len(raw),response_sha256=sha(raw))
        (OUT/'generation.response.bin').write_bytes(raw);stop.set();worker.join(timeout=3)
        write('generation.receipt.json',receipt);write('memory_samples.json',samples)
    after=get('/api/tags','after_tags.json');assert next(m['digest'] for m in after['models'] if m['name']==MODEL)==DIGEST
    after_ps=get('/api/ps','after_ps.json')
    summary={**receipt,'engineering_only':True,'model':MODEL,'model_digest':DIGEST,'model_response_content_read_for_selection':False,
        'native_tokenizer_verified':False,'experimental_eligibility':False,'comparison_scope':'Resource-only; original older schema/input, different hardware and no exact native tokenizer validation.',
        'provider_metrics':{k:result.get(k) for k in ('done','done_reason','prompt_eval_count','eval_count','total_duration','load_duration','prompt_eval_duration','eval_duration')},
        'available_memory_kB_min':min(x['meminfo_kB']['MemAvailable'] for x in samples),
        'memory_after':memory(),'model_present_after_keep_alive_zero':any(m['name']==MODEL for m in after_ps.get('models',[])),
        'existing_service_pid_still_present':Path('/proc/2704').exists(),'options':options}
    for key,tokens,duration in [('prefill_tokens_per_second','prompt_eval_count','prompt_eval_duration'),('decode_tokens_per_second','eval_count','eval_duration')]:
        summary[key]=result[tokens]/(result[duration]/1e9) if result.get(duration) and result.get(tokens) is not None else None
    write('summary.json',summary)
    write('manifest.json',{'files':[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in sorted(OUT.iterdir()) if p.is_file()]})
    archive=OUT/'probe_bundle.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.iterdir()):
            if p.is_file() and p!=archive:z.write(p,p.name)
    print(json.dumps({'status':receipt['status'],'generation_dispatches':1,'http_seconds':receipt['http_seconds'],
        'provider_metrics':summary['provider_metrics'],'minimum_available_kB':summary['available_memory_kB_min'],
        'unloaded':not summary['model_present_after_keep_alive_zero'],'archive':str(archive),'archive_bytes':archive.stat().st_size,'archive_sha256':sha(archive.read_bytes())}),flush=True)

if __name__=='__main__':main()
