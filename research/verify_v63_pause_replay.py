"""Offline-only reconstruction of the paused response; live transport forbidden."""
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,sys
from research.v63.build_run import read_json,save_json,make_numeric_callbacks,file_ref
from research.v63.campaign import runtime_identity
from research.v63.campaign_control import verify_frozen_artifacts
from research.v63.recovery import RecoveryClient
from research.v63.runtime import run_trajectory
from research.v63.retrieval import canonical

ROOT=Path(__file__).resolve().parents[1]
RUN_ID='de1b479b54d5b4429211059df1496be588c3c5af81ec21f4d4c355e3004f76ec'
BASE=ROOT/'data/v63_20261027/local_campaign_results'
PHASE=BASE/'phases'/RUN_ID/'technical-smoke'
TASK=BASE/'runs'/RUN_ID/'B-development/development-001__F03__R2__1'
OUT=ROOT/'data/v63_20261027/continuation/pause_20261027'
class OfflineBoundary(BaseException):pass
def streamed_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def verify_all_raw(frozen,*,seal=False):
    manifest_path=OUT/'raw_http_manifest.json';receipt_path=OUT/'offline_raw_history_verification.json'
    run=BASE/'runs'/RUN_ID
    folders=sorted(run.glob('B-development/*/http'))
    manifest={p.relative_to(ROOT).as_posix():streamed_sha(p) for folder in folders for p in folder.rglob('*') if p.is_file()}
    if seal:
        if manifest_path.exists() or receipt_path.exists():raise ValueError('Raw HTTP checkpoint already sealed.')
    else:
        if read_json(manifest_path)!=manifest:raise ValueError('Paused raw HTTP artifacts changed.')
        if read_json(receipt_path)['raw_http_manifest_sha256']!=streamed_sha(manifest_path):raise ValueError('Raw checkpoint manifest changed.')
    replayed=0;receipts=[]
    def forbidden(request):raise AssertionError('Offline revalidation must never invoke live transport.')
    for folder in folders:
        client=RecoveryClient(folder,frozen,forbidden,history_quiescent=False)
        for attempt in sorted(folder.glob('attempt_*')):
            result=client((attempt/'runner_request.bin').read_bytes())
            if result.get('new_generation_requests')!=0:raise AssertionError('Unexpected new generation.')
            replayed+=1
        receipts.append(client.recovery_receipt())
    if replayed!=7:raise ValueError('Expected exactly seven closed requests at this user pause.')
    if seal:
        save_json(manifest_path,manifest)
        save_json(receipt_path,{'status':'seven_original_requests_replayed_offline','verified_at_utc':datetime.now(timezone.utc).isoformat(),
            'http_calls':0,'new_generation_requests':0,'original_responses_replayed':replayed,
            'raw_http_manifest_sha256':streamed_sha(manifest_path),'recovery_receipts':receipts})
    return replayed
def main():
    if (OUT/'offline_replay_verification.json').exists() and not {'--identity-only','--seal-raw'} & set(sys.argv):raise ValueError('Offline receipt already exists.')
    config=read_json(ROOT/'data/v63_20261027/continuation/deployment/local_windows/candidate_002/campaign_config.json')
    frozen=read_json(PHASE/'frozen_runtime.json');case=read_json(TASK/'input_case.json')
    verify_frozen_artifacts(ROOT,PHASE/'frozen_runtime.json')
    candidate=read_json(ROOT/config['runtime_freeze_path'])
    if candidate.get('main_model_frozen') is not False:raise ValueError('This paused development helper must not promote or resume main execution.')
    actual,_=runtime_identity(ROOT,candidate,file_ref(ROOT/config['tokenizer_config_path'],ROOT),config['execution_amendment'])
    if actual!=RUN_ID:raise ValueError('Frozen source/model/config identity changed.')
    if '--seal-raw' in sys.argv:
        print(json.dumps({'status':'raw_checkpoint_sealed','original_responses_replayed':verify_all_raw(frozen,seal=True),'new_generation_requests':0,'http_calls':0}))
        return
    if '--identity-only' in sys.argv:
        replayed=verify_all_raw(frozen)
        tokenizer=read_json(ROOT/config['tokenizer_config_path'])
        targets=[(Path(tokenizer['gguf_path']),tokenizer['gguf_sha256'])]
        targets.extend((ROOT/item['path'],item['sha256']) for item in frozen['execution_environment']['binary_artifacts'])
        targets.append((ROOT/'tmp/v63_local_ollama/models/manifests/registry.ollama.ai/library/qwen3/1.7b',frozen['model_sha256']))
        for path,expected in targets:
            if not path.is_file() or streamed_sha(path)!=expected:raise ValueError('Pinned local cache/binary missing or changed: '+str(path))
        print(json.dumps({'status':'unchanged_frozen_identity_artifacts_and_raw_replay','run_id':actual,'original_responses_replayed':replayed,'http_calls':0,'model_generation_requests':0}))
        return
    raw=(TASK/'http/attempt_000001/runner_request.bin').read_bytes();prior=json.loads(raw)
    denied_calls=[]
    def deny_live(request):denied_calls.append(True);raise AssertionError('No live transport is permitted in offline validation.')
    client=RecoveryClient(TASK/'http',frozen,deny_live,history_quiescent=False)
    calls=[]
    def replay(request):
        if request!=raw:raise AssertionError('Reconstructed stage1 request differs from the original bytes.')
        value=client(request);calls.append(value);return value
    def offline_count(request):
        if calls:raise OfflineBoundary('Stop before stage2 preflight or any new request.')
        expected={k:v for k,v in prior.items() if k!='expected_prompt_tokens'}
        if canonical(request)!=canonical(expected):raise AssertionError('Model-visible request reconstruction differs.')
        return prior['expected_prompt_tokens']
    tools,check=make_numeric_callbacks(case)
    try:run_trajectory(case['baseline'],case['retrieval'],'R2',replay,tools,check,frozen,
                      output_dir=OUT/'offline_reconstruction',count_rendered_request=offline_count,engineering=False)
    except OfflineBoundary:pass
    trace=read_json(OUT/'offline_reconstruction/trace.json')
    if denied_calls or len(calls)!=1 or calls[0]['new_generation_requests']!=0 or trace['stages'][0]['status']!='completed':
        raise AssertionError('Offline reconstruction did not validate the same completed first stage.')
    state=read_json(PHASE/'budget_state.json')
    from datetime import timedelta
    deadline=datetime.fromisoformat(state['first_started_at_utc'])+timedelta(seconds=state['limits']['max_wall_seconds'])
    result={'status':'passed_offline_replay_no_network','verified_at_utc':datetime.now(timezone.utc).isoformat(),
        'runtime_identity_sha256':actual,'original_recorded_generation_requests_replayed':1,'new_generation_requests':0,'http_calls':0,
        'same_runner_request_bytes':True,'stage1_schema_status':trace['stages'][0]['status'],
        'subsequent_stage_execution_stopped_before_preflight':True,'recovery_receipt':client.recovery_receipt(),
        'pause_reconstruction_trace_is_not_a_new_experimental_trajectory':True,
        'phase_budget':state,'phase_budget_expires_at_utc':deadline.isoformat(),
        'budget_note':'UTC wall budget includes downtime. Do not delete/reset budget_state. After expiry, an explicit recorded budget amendment is required.',
        'resume_config':'data/v63_20261027/continuation/deployment/local_windows/candidate_002/campaign_config.json',
        'runtime_freeze_path':config['runtime_freeze_path'],'resume_phase':'technical-smoke','main_model_frozen':False,
        'future_action':'On explicit resume, reuse R0/R1 terminal traces, replay this R2 stage1 response with zero new generation, then allow stage2 onward under the unchanged identity.'}
    save_json(OUT/'offline_replay_verification.json',result)
    print(json.dumps({k:result[k] for k in ('status','new_generation_requests','http_calls','stage1_schema_status','phase_budget_expires_at_utc')}))
if __name__=='__main__':main()
