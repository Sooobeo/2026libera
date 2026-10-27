"""Replace obsolete preparation-only counters with an explicit observed snapshot."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from research.v63.campaign_control import task_request_cost, final_trace_path
from research.v63.build_continuation_report import verify_completion_commit

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/v63_20261027'
def read(path,default=None):
    try:return json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else default
    except (OSError,ValueError):return default
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()
def write(path,value):
    tmp=path.with_suffix(path.suffix+'.writing')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(path)

def run_observation(directory,run,progress):
    """Count original attempts and only the selected trace per task, never replay copies."""
    traces=[];issues=[]
    for identity in sorted(run.rglob('input_identity.json')):
        try:
            selected=final_trace_path(identity.parent)
            value=read(selected) if selected else None
            if value is not None:traces.append(value)
            else:issues.append(str(identity.parent.relative_to(ROOT)).replace('\\','/')+': no selected terminal trace yet')
        except (OSError,ValueError,KeyError) as exc:
            issues.append(str(identity.parent.relative_to(ROOT)).replace('\\','/')+': '+str(exc))
    costs=task_request_cost(run)
    phases={p.parent.name:read(p,{}) for p in sorted((directory/'phases'/run.name).glob('*/progress.json'))}
    return dict(output_root=str(directory.relative_to(ROOT)).replace('\\','/'),run_id=run.name,
        latest_progress=progress if progress.get('run_id')==run.name else None,
        generation_requests_started=costs['generation_requests'],request_accounting=costs,
        saved_terminal_traces=len(traces),selected_trace_issues=issues,
        trace_status_counts={key:sum(t.get('status')==key for t in traces) for key in ('completed','model_output_failure','operational_failure','protocol_violation','recovery_interrupted')},
        phases=phases,main_generation_requests=task_request_cost(run/'B-main')['generation_requests'],
        provenance='Original HTTP attempt receipts count actual requests. Missing attempt receipts reserve one uncertain dispatch. Each task contributes only its selected trace; preserved partial and superseded traces are not double counted.')

def main(status_override=None):
    now=datetime.now(timezone.utc).isoformat()
    previous=read(DATA/'execution_status.json',{})
    if not status_override and previous.get('all_experiments_completed') is True:
        raise ValueError('A completed record can only be refreshed through final-result revalidation.')
    live=read(DATA/'continuation/live_status.json',{})
    abort=read(DATA/'continuation/deployment/remote_capacity_abort.json',{})
    readiness=read(DATA/'continuation_sources/readiness_v2.json',{})
    pause=read(DATA/'continuation/user_pause_20261027.json',{})
    candidates=[]
    requests=abort.get('generation_requests_started',0)
    confirmed_requests=requests
    uncertain_requests=0
    for directory in sorted(DATA.glob('*campaign_results*')):
        if not directory.is_dir():continue
        progress=read(directory/'progress.json',{})
        for run in sorted((directory/'runs').glob('*')):
            if not run.is_dir():continue
            candidate=run_observation(directory,run,progress)
            candidates.append(candidate)
            requests+=candidate['generation_requests_started']
            confirmed_requests+=candidate['request_accounting']['confirmed_attempt_records']
            uncertain_requests+=candidate['request_accounting']['uncertain_dispatch_requests']
    main_started=any(c['main_generation_requests']>0 for c in candidates)
    selected=live.get('selected_run_id') or live.get('model_execution',{}).get('local_windows',{}).get('runtime_identity_sha256')
    chosen=next((c for c in candidates if c['run_id']==selected),{})
    main_valid=chosen.get('phases',{}).get('B-main',{}).get('terminal_counts',{}).get('completed',0)
    status=dict(schema='libera_v63_execution_status_v2',recorded_at_utc=now,
        protocol_version='6.3-design',protocol_sha256='a884b1242217cfed37a52444a541968eb680739c649e85c2b8d3bf9b0de383dc',
        status='main_or_followup_in_progress' if main_started else 'development_in_progress',all_experiments_completed=False,
        actual_experimental_model_requests=confirmed_requests,
        possibly_sent_requests_without_final_receipt=uncertain_requests,generation_request_budget_count=requests,
        count_scope='Lifetime candidate attempts as of this snapshot. Confirmed requests require original attempt receipts; in-flight or uncertain dispatches are separate. Superseded attempts do not fill slots of a new frozen pilot.',
        planned_trajectories=3272,planned_logical_stages=9816,
        successful_main_trajectories=main_valid,main_started=main_started,selected_run_id=selected,
        human_review_mode='user_assumed_completed',actual_independent_human_signatures=None,
        execution_amendment='continuation/execution_amendment.json',
        data_readiness=readiness.get('summary',{}),
        data_validation=live.get('data_validation',{}),
        local_candidates=candidates,remote_candidate_abort=abort,
        engineering_calls_excluded=True,engineering_receipt_locations=['runtime/local_windows','runtime/remote_runtime_inventory.json'],
        prior_preparation_snapshot='continuation/previous_delivery/execution_status.json',
        current_report='../../실험참고자료_20261027/02_계속실행기록_20261027.html',
        remaining=['Qualify the revised development runtime, preserving all superseded attempts.',
                   'Complete the same-version 720 planned development stages and precision/resource report.',
                   'Freeze the runtime, inputs and budgets; complete B, x-replacement, negative controls and A/C.',
                   'Validate complete raw-to-statistics accounting and write final experimental conclusions.'],
        source_limitations=['Issuer SIC fallback uses current official information for retrospective classification.',
                            'C currently has a new common FOMC outlook; fund-private new outlooks were not verified.',
                            'Security-level, source-industry, country, currency and transaction rules cannot be certified from FF12 weights alone.'])
    if status_override:status.update(status_override)
    elif pause.get('active') is True:
        status.update(status='paused_by_user',user_pause='continuation/user_pause_20261027.json',
            current_report='../../실험참고자료_20261027/04_중지와재개_20261027.html',
            remaining=['Resume only after an explicit user instruction; preserve the exact recorded model/code/data identity.']+status['remaining'])
    if status['all_experiments_completed']:verify_completion_commit(status)
    write(DATA/'execution_status.json',status)
    # A dated manifest is an observation, not a promise that active files are frozen.
    files=[];unstable=[]
    for path in sorted(DATA.rglob('*')):
        if not path.is_file() or path.name=='artifact_manifest.json' or path.suffix in {'.writing','.lock'}:continue
        before=path.stat();sha=digest(path);after=path.stat()
        item=dict(path=str(path.relative_to(ROOT)).replace('\\','/'),bytes=after.st_size,sha256=sha)
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):unstable.append(item['path']);continue
        files.append(item)
    for path in [*sorted((ROOT/'research/v63').glob('*.py')),*sorted((ROOT/'실험참고자료_20261027').glob('*.html'))]:
        files.append(dict(path=str(path.relative_to(ROOT)).replace('\\','/'),bytes=path.stat().st_size,sha256=digest(path)))
    manifest=dict(schema='v63_continuation_manifest_v2',recorded_at_utc=now,status='completed_snapshot' if status['all_experiments_completed'] else 'in_progress_snapshot',
                  confirmed_experimental_model_requests=confirmed_requests,possibly_sent_requests_without_final_receipt=uncertain_requests,generation_request_budget_count=requests,all_experiments_completed=status['all_experiments_completed'],
                  interpretation='Exact file hashes observed during capture. Running outputs may subsequently change; frozen phase manifests and closed raw receipts are the reproducibility authority.',
                  unstable_files_not_hashed=unstable,files=files)
    write(DATA/'artifact_manifest.json',manifest)
    print(json.dumps(dict(confirmed_experimental_requests=confirmed_requests,uncertain_requests=uncertain_requests,files=len(files),unstable=len(unstable))))

if __name__=='__main__':main()
