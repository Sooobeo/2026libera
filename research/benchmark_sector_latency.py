"""Three serial synthetic latency probes; never pilot/main research responses.

This uses engineering settings, not paper conditions. Each configuration gets
one generation attempt, without retries. Existing installed manifests are pinned;
no model is pulled and no research runtime, evaluation or freeze file is changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import remote_sector_runtime as remote

ROOT = Path(__file__).resolve().parents[1]
ENGINE = '0.35.1'
MODELS = {
    'qwen3.5:4b-q4_K_M':'d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04',
    'qwen3:1.7b':'8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7',
}
PROBES = [('4b_threads2','qwen3.5:4b-q4_K_M',2),
          ('4b_threads4','qwen3.5:4b-q4_K_M',4),
          ('1p7b_threads2','qwen3:1.7b',2)]
PROMPT = (
    'This is a synthetic latency check, not an investment task. Read these fictional inventory records. '
    'Do not summarize or analyze them. After the records, return only the requested JSON.\n' +
    ''.join(f'item={i:02}; group=amber; units=07; note=synthetic fixture.\n' for i in range(1,16)) +
    '\nReturn exactly this JSON object, without commentary: {"ready":true}\n'
)


def selected_probes(names=None):
    """Repeated --probe options select distinct configurations, never retries."""
    if names is None:return list(PROBES)
    lookup={row[0]:row for row in PROBES}
    if not names or len(names)!=len(set(names)) or any(name not in lookup for name in names):
        raise ValueError('Select known probe IDs once each; duplicate generations are not permitted')
    return [lookup[name] for name in names]


def windows_memory_snapshot():
    """Reuse the existing read-only collector; unavailable memory is never zero."""
    try:
        from probe_ollama_runtime import memory_snapshot
        value=memory_snapshot()
        processes=value.get('ollama_process_memory',[])
        working_sets=[]
        for process in processes:
            info=process.get('memory_info',{})
            # psutil's rss is the Windows working set; native fallback names it explicitly.
            amount=info.get('working_set_bytes',info.get('rss'))
            if isinstance(amount,int) and not isinstance(amount,bool) and amount>=0:
                working_sets.append(amount)
        available=(value.get('global_memory_status_ex') or {}).get('available_physical_bytes')
        if not isinstance(available,int) or isinstance(available,bool) or available<0:available=None
        value.update(source='windows_existing_read_only_memory_collector',
                     working_set_sum_bytes=sum(working_sets) if working_sets else None,
                     working_set_observed_process_count=len(working_sets),
                     working_set_observation_status='observed_named_processes' if working_sets else 'not_observed',
                     available_physical_bytes=available,
                     available_physical_observation_status='observed' if available is not None else 'not_observed',
                     interpretation='Sum covers successfully observed named Ollama process working sets and can double-count shared pages. Missing values remain null. Available RAM is system-wide; private bytes are commit, not resident memory; process peaks are lifetime values. No cgroup equivalent or GPU-memory use is inferred.')
        return value
    except Exception as exc:
        return {'observed_at_utc':remote.now(),'source':'windows_existing_read_only_memory_collector',
                'memory_observation_status':'not_observed','working_set_sum_bytes':None,
                'available_physical_bytes':None,'error_type':type(exc).__name__,'error':str(exc),
                'interpretation':'Optional resource observation failed; this is not zero memory usage.'}


class ProbeSession(remote.Session):
    def start_monitor(self):
        if sys.platform!='win32':return super().start_monitor()
        def monitor():
            with (self.target/'monitor.jsonl').open('x',encoding='utf-8') as handle:
                while not self.monitor_stop.is_set():
                    start=time.monotonic()
                    sample={'elapsed_seconds':start-self.started,'memory':windows_memory_snapshot(),
                            'ollama_ps':remote.optional_api(self.origin,'/api/ps',timeout=1)}
                    handle.write(json.dumps(sample,allow_nan=False)+'\n');handle.flush()
                    self.monitor_stop.wait(max(0,self.monitor_seconds-(time.monotonic()-start)))
        self.monitor_thread=threading.Thread(target=monitor,name='windows-memory-monitor',daemon=True)
        self.monitor_thread.start()


def body_for(model, threads):
    return {'model':model,'messages':[{'role':'user','content':PROMPT}],
            'stream':True,'think':False,'format':'json','keep_alive':0,
            'options':{'temperature':0,'num_ctx':8192,'num_predict':32,'num_thread':threads,
                       'num_batch':512,'repeat_penalty':1.0,'presence_penalty':0.0,
                       'frequency_penalty':0.0,'seed':3407}}


def observe(origin, model, previous=None):
    version = remote.api_json(origin,'/api/version')
    tags = remote.api_json(origin,'/api/tags')
    selected = [m for m in tags.get('models',[]) if m.get('name')==model]
    if version.get('version')!=ENGINE or len(selected)!=1:
        raise RuntimeError('Exact installed model and engine pins are required; no substitution')
    if selected[0].get('digest','').removeprefix('sha256:')!=MODELS[model]:
        raise RuntimeError('Installed manifest differs from the approved existing digest')
    show = remote.api_json(origin,'/api/show',{'model':model})
    template = show.get('template')
    if not isinstance(template,str):raise RuntimeError('Model template was not observed')
    value = {'version':version,'selected_model':selected[0],'show':show,
             'template_sha256':hashlib.sha256(template.encode()).hexdigest()}
    if previous and value['template_sha256']!=previous['template_sha256']:
        raise RuntimeError('Model template changed between probes')
    return value


def unload_and_confirm(origin, model):
    # Use the explicitly selected model, never the coordinator's module MODEL.
    unloaded = remote.optional_api(origin,'/api/generate',{'model':model,'keep_alive':0},timeout=5)
    unload_confirmed = (unloaded.get('status')=='ok' and
                        isinstance(unloaded.get('value'),dict) and
                        unloaded['value'].get('done') is True)
    observations = []
    for _ in range(3):
        state = remote.optional_api(origin,'/api/ps',timeout=2)
        observations.append(state)
        models=state.get('value',{}).get('models') if isinstance(state.get('value'),dict) else None
        empty_residency=state.get('status')=='ok' and isinstance(models,list) and not models
        if unload_confirmed and empty_residency:
            return {'status':'no_resident_models_observed','unload':unloaded,'ps':observations}
        if not unload_confirmed:
            # /ps can be empty while a previous request is still loading. An
            # unsuccessful unload must never authorize a subsequent generation.
            return {'status':'idle_not_confirmed','reason':'unload_completion_not_confirmed',
                    'unload':unloaded,'ps':observations}
        time.sleep(0.2)
    return {'status':'idle_not_confirmed','unload':unloaded,'ps':observations}


def worker(spec_path):
    spec = remote.read(spec_path); target = Path(spec_path).parent
    session = ProbeSession(target,spec['origin'],timeout_seconds=spec['deadline_seconds'],monitor_seconds=2)
    started = time.monotonic(); outcome = {'status':'attempted','model_requests_attempted':1}
    try:
        session.start_monitor()
        response = remote.stream_call(session,'/api/chat',spec['body'],'latency_probe')
        content = response.get('message',{}).get('content','')
        try: parsed = json.loads(content); json_ok = isinstance(parsed,dict)
        except (ValueError,TypeError): parsed = None; json_ok = False
        matching_model=response.get('model')==spec['body']['model']
        thinking=bool(response.get('message',{}).get('thinking'))
        status=('output_limit_reached' if response.get('done_reason')=='length' else
                'response_protocol_anomaly' if thinking or not matching_model else 'completed')
        resource_only=spec.get('assessment_policy')=='resource_only'
        outcome.update(status=status,done_reason=response.get('done_reason'),
                       parseable_json_object=json_ok,unexpected_thinking=bool(response.get('message',{}).get('thinking')),
                       expected_synthetic_json=None if resource_only else parsed=={'ready':True},
                       assessment_scope='not_graded_engineering_feasibility' if resource_only else 'synthetic_ready_json_only',
                       response_model=response.get('model'))
    except remote.RemoteCallError as exc:
        outcome.update(status=exc.result.get('status','failed'),error=str(exc))
    except BaseException as exc:
        outcome.update(status='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed',
                       error_type=type(exc).__name__,error=str(exc))
    finally:
        session.stop_monitor()
        outcome.update(worker_wall_seconds=time.monotonic()-started,calls=session.calls,
                       model_requests_attempted=len(session.calls),
                       pilot_model_calls=0,main_model_calls=0,automatic_retries=0)
        remote.save(target/'worker_summary.json',outcome)
    return 0 if outcome['status']=='completed' else 1


def supervised_worker(spec_path, deadline, cancel_path):
    """A separate process bounds connect, headers and streaming, not only reads."""
    target = Path(spec_path).parent; started = time.monotonic()
    with (target/'worker.console.log').open('xb') as log:
        process = subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--worker',str(spec_path)],
                                   stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        stopped = None
        try:
            while process.poll() is None:
                remaining = deadline-(time.monotonic()-started)
                if Path(cancel_path).exists():stopped='cancelled';break
                if remaining<=0:stopped='hard_deadline';break
                time.sleep(min(0.05,remaining))
        except KeyboardInterrupt:
            stopped='cancelled'
        if stopped:
            # SIGKILL/TerminateProcess closes this client's sockets; do not kill Ollama.
            process.kill()
            process.wait(timeout=3)
        else:process.wait()
    result = {'supervisor_status':stopped or 'worker_exited','worker_exit_code':process.returncode,
              'elapsed_seconds':time.monotonic()-started,'deadline_seconds':deadline,
              'deadline_scope':'Child process lifetime includes setup, connect, headers and complete stream; OS scheduling/kill overhead is separately included in elapsed_seconds.',
              'automatic_retries':0}
    if (target/'worker_summary.json').is_file():result['worker']=remote.read(target/'worker_summary.json')
    else:result['worker_summary_missing']=True
    remote.save(target/'supervisor_result.json',result)
    return result


def run(args):
    origin = remote.validate_origin(args.base_url)
    if not 1<=args.deadline_seconds<=120:raise ValueError('Each probe deadline must be 1..120 seconds')
    chosen=selected_probes(getattr(args,'probe',None))
    target = remote.new_output(args.output_root,'latency',args.run_id)
    planned = [{'probe_id':label,'model':model,'threads':threads,'status':'not_started'} for label,model,threads in chosen]
    memory_collector=Path(__file__).with_name('probe_ollama_runtime.py')
    remote.save(target/'invocation.json',{
        'scope':'Synthetic engineering latency diagnosis; excluded from research pilot/main and evaluation.',
        'started_at_utc':remote.now(),'origin':origin,'deadline_seconds':args.deadline_seconds,
        'script_sha256':remote.sha(Path(__file__)),'coordinator_sha256':remote.sha(Path(remote.__file__)),
        'platform':sys.platform,'selected_probe_ids':[row[0] for row in chosen],
        'windows_memory_collector_sha256':remote.sha(memory_collector) if sys.platform=='win32' and memory_collector.is_file() else None,
        'resource_observation_policy':'On Windows, reuse the existing native/optional-psutil read-only collector and retain Ollama /api/ps samples. Missing memory is null, not zero; observation failures do not trigger generation retries.',
        'prompt_characters':len(PROMPT),'prompt_utf8_bytes':len(PROMPT.encode()),
        'prompt_sha256':hashlib.sha256(PROMPT.encode()).hexdigest(),'planned_probes':planned,
        'condition_basis':'8192 context, output cap32, T0, disabled thinking, batch512, neutral repeat/presence/frequency penalties, seed3407, thread counts and deadline are engineering controls for these latency probes; this is not a paper-derived experiment even where a number also appears in a paper.',
        'comparison_limits':'One fixed-order attempt per configuration; unload does not evict OS file cache. Model/template/tokenizer differ. No statistical speed ranking or four-stage feasibility verdict.',
        'pilot_model_calls':0,'main_model_calls':0})
    (target/'prompt.txt').write_text(PROMPT,encoding='utf-8')
    pinned = {}; attempted = 0; overall = 'completed'
    try:
        # Existing other workloads must be stopped by the operator before this diagnostic.
        state = remote.api_json(origin,'/api/ps')
        remote.save(target/'residency_before.json',state)
        if state.get('models'):raise RuntimeError('Ollama is already resident/busy; stop the earlier run before these serial probes')
        for row in planned:
            if (target/'CANCEL').exists():overall='cancelled';break
            folder = target/row['probe_id'];folder.mkdir()
            observed = observe(origin,row['model'],pinned.get(row['model']))
            pinned.setdefault(row['model'],observed)
            remote.save(folder/'model_observation.json',observed)
            spec = {'origin':origin,'deadline_seconds':args.deadline_seconds,'body':body_for(row['model'],row['threads'])}
            remote.save(folder/'worker_spec.json',spec)
            row['status']='attempted';attempted+=1
            result = supervised_worker(folder/'worker_spec.json',args.deadline_seconds,target/'CANCEL')
            row.update(status=result.get('worker',{}).get('status',result['supervisor_status']),
                       supervisor_status=result['supervisor_status'],elapsed_seconds=result['elapsed_seconds'])
            http_folder=folder/'http_0001_latency_probe'
            row['generation_request_recorded']=(http_folder/'request.json').is_file()
            call_result=remote.read(http_folder/'result.json') if (http_folder/'result.json').is_file() else {}
            row['provider_metrics']=call_result.get('metrics')
            row['prompt_eval_count']=(row['provider_metrics'] or {}).get('prompt_eval_count')
            row['eval_count']=(row['provider_metrics'] or {}).get('eval_count')
            row['response_assessment']=({key:result['worker'].get(key) for key in
                ('parseable_json_object','expected_synthetic_json','assessment_scope','unexpected_thinking','response_model','done_reason')}
                if result.get('worker') else None)
            cleanup = unload_and_confirm(origin,row['model'])
            remote.save(folder/'unload_and_residency.json',cleanup)
            if cleanup['status']!='no_resident_models_observed':
                overall='stopped_idle_not_confirmed';break
            if result['supervisor_status']=='cancelled':overall='cancelled';break
        if overall=='completed' and any(row['status']!='completed' for row in planned):overall='completed_with_probe_failures'
    except BaseException as exc:
        overall='cancelled' if isinstance(exc,KeyboardInterrupt) else 'stopped_before_or_between_probes'
        remote.save(target/'failure.json',{'type':type(exc).__name__,'message':str(exc)})
    result = {'status':overall,'finished_at_utc':remote.now(),'probe_invocations_attempted':attempted,
              'completed_probes':sum(row['status']=='completed' for row in planned),
              'generation_request_envelopes_recorded':sum(row.get('generation_request_recorded',False) for row in planned),
              'not_started_probes':sum(row['status']=='not_started' for row in planned),
              'records':planned,'pilot_model_calls':0,'main_model_calls':0,
              'scope':'Engineering latency probes only; never merged into research responses.',
              'output':str(target)}
    remote.save(target/'summary.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    return 0 if overall in ('completed','completed_with_probe_failures') else 1


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:11434')
    parser.add_argument('--output-root',type=Path,default=ROOT/'data/sector_runtime')
    parser.add_argument('--run-id')
    parser.add_argument('--deadline-seconds',type=float,default=120)
    parser.add_argument('--probe',action='append',choices=[row[0] for row in PROBES],
                        help='Run only this probe; repeat for distinct probes in the specified order. Omit to run all three.')
    parser.add_argument('--worker',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    return worker(args.worker) if args.worker else run(args)


if __name__=='__main__':raise SystemExit(main())
