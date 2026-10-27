"""Read only operational metadata; never inspect allocations or calculate effects."""
import json,hashlib
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
RUN_ID='de1b479b54d5b4429211059df1496be588c3c5af81ec21f4d4c355e3004f76ec'
OUT=ROOT/'data/v63_20261027/local_campaign_results'
PHASE=OUT/'phases'/RUN_ID/'technical-smoke'
RUN=OUT/'runs'/RUN_ID
WATCH=ROOT/'data/v63_20261027/runtime/local_windows/development_smoke_candidate_002_20261027T043408869Z'

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
    requests=[]
    for p in sorted(RUN.rglob('generation.response.bin')):
        try:r=read(p)
        except (ValueError,OSError):continue
        requests.append({'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
            'done':r.get('done'),'finish_reason':r.get('done_reason'),'prompt_tokens':r.get('prompt_eval_count'),
            'generated_tokens':r.get('eval_count'),'prompt_seconds':r.get('prompt_eval_duration',0)/1e9,
            'decode_seconds':r.get('eval_duration',0)/1e9,'load_seconds':r.get('load_duration',0)/1e9,
            'total_seconds':r.get('total_duration',0)/1e9})
    stages=[];traces=[]
    for p in sorted(RUN.rglob('trace.json')):
        try:r=read(p)
        except (ValueError,OSError):continue
        traces.append({'arm':r.get('arm'),'status':r.get('status'),'requests':r.get('experimental_model_calls'),
                       'new_requests':r.get('new_model_requests_this_execution')})
        stages.extend({'arm':r.get('arm'),'stage':s['stage'],'status':s.get('status'),'reason':s.get('reason'),
                       'prompt_token_counts':s.get('prompt_token_counts',[]),
                       'contract_failure_categories':s.get('raw_weight_check',{}).get('failures',[]),
                       'unexposed_citation_count':len(s.get('unexposed_citation_ids',[]))} for s in r.get('stages',[]))
    planned=[{'file':p.name,'expected_prompt_tokens':read(p).get('expected_prompt_tokens')} for p in sorted(RUN.rglob('stage*_request.json'))]
    progress=read(PHASE/'progress.json') if (PHASE/'progress.json').exists() else {}
    result={'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'run_id':RUN_ID,
       'scope':'Only format/capacity/cost metadata. No weights, utilities, effects, significance or p-values inspected.',
       'progress':progress,'received_responses':len(requests),'request_metadata':requests,
       'trace_metadata':traces,'stage_metadata':stages,'prepared_requests':planned,
       'output_cap_failures':[r for r in requests if r['finish_reason']=='length'],'model_generated_tokens':sum(r['generated_tokens'] or 0 for r in requests)}
    (WATCH/'metadata_watch.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:result[k] for k in ('recorded_at_utc','received_responses','trace_metadata','stage_metadata','prepared_requests','output_cap_failures','model_generated_tokens')}))

if __name__=='__main__':main()
