"""Record stopped-state resource accounting only; no model/HTTP/analysis calls."""
import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/v63_20261027/continuation/pause_20261027'
RUN_ID='de1b479b54d5b4429211059df1496be588c3c5af81ec21f4d4c355e3004f76ec'
RUN=ROOT/'data/v63_20261027/local_campaign_results/runs'/RUN_ID
MON=ROOT/'data/v63_20261027/runtime/local_windows/development_smoke_candidate_002_20261027T043408869Z/memory_observations.jsonl'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,value):p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def main():
    # Correct only a resume-path metadata label; all original experiment bytes remain untouched.
    verification=OUT/'offline_replay_verification.json';value=read(verification)
    if value['resume_config'].endswith('/runtime_candidate.json'):
        prior_hash=hashlib.sha256(verification.read_bytes()).hexdigest()
        value['runtime_freeze_path']=value['resume_config']
        value['resume_config']='data/v63_20261027/continuation/deployment/local_windows/candidate_002/campaign_config.json'
        value['metadata_correction']={'original_receipt_sha256':prior_hash,'reason':'resume_config denotes campaign CLI configuration, not the nested runtime freeze. Offline verification result unchanged.'}
        save(verification,value)
    responses=[]
    for p in sorted(RUN.rglob('generation.response.bin')):
        row=read(p);http=read(p.with_name('generation.receipt.json'))
        responses.append({'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
            'prompt_tokens':row['prompt_eval_count'],'output_tokens':row['eval_count'],'finish_reason':row.get('done_reason'),
            'generation_http_seconds':http['elapsed_seconds'],'provider_prompt_seconds':row['prompt_eval_duration']/1e9,
            'provider_decode_seconds':row['eval_duration']/1e9})
    observations=[];bad=0
    for line in MON.read_text(encoding='utf-8-sig').splitlines():
        try:observations.append(json.loads(line))
        except ValueError:bad+=1
    memory={'observations':len(observations),'unparseable_lines':bad,
        'minimum_available_physical_memory_KiB':min(o['memory']['FreePhysicalMemory'] for o in observations),
        'minimum_available_virtual_memory_KiB':min(o['memory']['FreeVirtualMemory'] for o in observations),
        'peak_combined_working_set_bytes':max(o['combined_working_set_bytes'] for o in observations),
        'peak_campaign_child_private_bytes':max(p['PrivateMemorySize64'] for o in observations for p in o['processes'] if p['Id']==20340)}
    summary={'status':'paused_by_explicit_user_instruction','recorded_at_utc':datetime.now(timezone.utc).isoformat(),'run_id':RUN_ID,
        'phase':'technical-smoke','planned_logical_stages':15,'actual_completed_response_count':len(responses),
        'terminal_trajectories':2,'terminal_status_counts':{'model_output_failure':2},'partial_trajectory':'R2 stage1 completed response, offline schema/replay verified; stage2 not sent',
        'new_dispatches_after_pause_instruction':0,'full_history_C_context_verified':False,'main_model_frozen':False,'paired_60_started':False,
        'prompt_tokens':sum(r['prompt_tokens'] for r in responses),'output_tokens':sum(r['output_tokens'] for r in responses),
        'generation_http_seconds':sum(r['generation_http_seconds'] for r in responses),
        'output_length_failures':sum(r['finish_reason']=='length' for r in responses),'responses':responses,'memory':memory,
        'pause_boundary':read(OUT/'pause_boundary.json'),'process_stop_verified':read(OUT/'local_service_stop_verification.json'),
        'offline_replay_status':value['status'],'offline_new_generation_requests':0,'offline_http_calls':0,
        'resume_helper':'research/resume_v63_candidate_002.ps1','resume_helper_executed':False,
        'phase_budget_expires_at_utc':value['phase_budget_expires_at_utc'],'phase_budget_expires_at_KST':'2026-10-27 19:34:12 KST',
        'budget_note':'The original 6h wall clock includes this user-requested downtime. Never reset the start. An explicit recorded amendment is required after expiry.',
        'selection_not_complete':True,'analysis_scope':'Only protocol, token, timing and memory metadata. No allocation effect, regret, utility or p-value evaluated.',
        'download_overlap':{'start_utc':'2026-10-27T04:46:51.018344+00:00','end_utc':'2026-10-27T04:50:45.872894+00:00','model_generation_requests':0}}
    save(OUT/'pause_summary.json',summary)
    print(json.dumps({k:summary[k] for k in ('status','actual_completed_response_count','prompt_tokens','output_tokens','generation_http_seconds','memory','phase_budget_expires_at_utc')}))
if __name__=='__main__':main()
