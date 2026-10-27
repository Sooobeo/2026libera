"""One bounded f16/32K alternative probe; memory gate precedes generation."""
import ctypes,json,time
from pathlib import Path
from research.v63.build_run import read_json,save_json
from research.v63.exact_tokenizer import NativeTokenizer
from research.v63.ollama_transport import OllamaTransport,packed,digest_bytes
from research.v63.runtime import response_schema

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/v63_20261027/runtime/local_windows/f16_timing_probe_003'

class MEMORYSTATUSEX(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('memory_load_percent',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in
        ('total_physical','available_physical','total_pagefile','available_pagefile','total_virtual','available_virtual','available_extended_virtual')]

def memory():
    state=MEMORYSTATUSEX();state.length=ctypes.sizeof(state)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):raise OSError('Memory measurement unavailable.')
    return {name:getattr(state,name) for name,_ in state._fields_}

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    base=ROOT/'data/v63_20261027/continuation/deployment/local_windows'
    freeze=read_json(base/'runtime_candidate.json')
    freeze.update(context_tokens=32768,output_tokens=64,request_timeout=900,fixed_options={'num_thread':8,'num_gpu':0,'use_mmap':True,'num_batch':256})
    freeze['allowed_response_schema_sha256']=[digest_bytes(packed(response_schema(i))) for i in (1,2,3)]
    native=NativeTokenizer(read_json(base/'tokenizer_config.json'));client=OllamaTransport('http://127.0.0.1:11435',freeze,OUT/'http')
    request=read_json(ROOT/'data/v63_20261027/runtime/local_windows/q8_timing_probe_002/prompt_capture_only/stage1_round0_request.json')
    admin=OUT/'administration';admin.mkdir();attempted=0;summary={}
    try:
        client._http(admin,'unload_before','/api/generate',packed({'model':freeze['model'],'keep_alive':0}))
        before=memory();render_start=time.monotonic();tokens=client.render_and_count(request,native);render_seconds=time.monotonic()-render_start
        after=memory()
        intent={'engineering_only':True,'actual_experimental_requests':0,'planned_max_engineering_requests':1,'memory_gate_min_available_bytes':512*1024**2,
                'before':before,'after_render':after,'render_seconds':render_seconds,'settings':freeze,
                'prompt_sha256':digest_bytes(packed(request['messages'])),'prompt_tokens':tokens}
        save_json(OUT/'probe_intent.json',intent)
        if after['available_physical']<512*1024**2:
            summary={'status':'memory_gate_blocked_without_generation','live_engineering_generation_requests':0,
                     'actual_experimental_requests':0,'after_render':after,'render_seconds':render_seconds}
            return
        start=time.monotonic();attempted=1
        response=client(packed({**request,'expected_prompt_tokens':tokens}));elapsed=time.monotonic()-start
        save_json(OUT/'response.json',response)
        summary={'status':'completed','engineering_only':True,'live_engineering_generation_requests':1,'actual_experimental_requests':0,
                 'retries':0,'elapsed_seconds':elapsed,'render_seconds':render_seconds,'usage':response.get('usage'),
                 'finish_reason':response.get('finish_reason'),'after_generation':memory(),
                 'comparison_scope':'Same 9570-token development prompt,64 output tokens. f16 32K,8 threads,use_mmap=true,num_batch=256 as a combined resource configuration; not an isolated cache-effect estimate. Prefix cold after unload; exact-render preflight may load engine before generation; OS file cache uncontrolled.'}
    except Exception as exc:
        summary={'status':'failed','error':str(exc),'error_type':type(exc).__name__,
                 'live_engineering_generation_requests':attempted,'actual_experimental_requests':0}
        raise
    finally:
        save_json(OUT/'summary.json',summary)
        try:client._http(admin,'unload_after','/api/generate',packed({'model':freeze['model'],'keep_alive':0}))
        finally:native.close()
        print(json.dumps(summary))

if __name__=='__main__':main()
