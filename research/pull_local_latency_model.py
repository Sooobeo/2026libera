"""Download one approved public model locally; no inference or research calls."""
import argparse
import http.client
import json
import time
from pathlib import Path
import benchmark_sector_latency as bench
import remote_sector_runtime as remote


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, choices=tuple(bench.MODELS))
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    origin = 'http://127.0.0.1:11434'
    version = remote.api_json(origin, '/api/version')
    if version.get('version') != bench.ENGINE:
        raise RuntimeError('Installed engine differs from benchmark pin')
    remote.save(args.output/'invocation.json', {
        'started_at_utc':remote.now(), 'model':args.model, 'origin':origin,
        'expected_manifest':bench.MODELS[args.model], 'version':version,
        'research_pilot_calls':0, 'research_main_calls':0,
        'scope':'Public model download only; download duration is not inference latency.'})
    conn = http.client.HTTPConnection('127.0.0.1',11434,timeout=60)
    started = time.monotonic()
    try:
        conn.request('POST','/api/pull', json.dumps({'model':args.model,'stream':True}),
                     {'Content-Type':'application/json'})
        response = conn.getresponse()
        if response.status != 200: raise RuntimeError(f'HTTP {response.status}')
        previous_status = None; previous_bytes = 0; terminal = None
        with (args.output/'progress.jsonl').open('xb') as log:
            for line in response:
                log.write(line); log.flush()
                event = json.loads(line)
                if 'error' in event: raise RuntimeError(event['error'])
                status = event.get('status'); completed = event.get('completed',0)
                if status != previous_status or completed-previous_bytes >= 128*1024**2:
                    print(json.dumps(event),flush=True)
                    previous_status = status; previous_bytes = completed
                if status == 'success': terminal = event
        if terminal is None: raise RuntimeError('No successful terminal download event')
        observed = bench.observe(origin,args.model)
        remote.save(args.output/'model_observation.json',observed)
        remote.save(args.output/'summary.json', {'status':'downloaded_and_pinned',
            'model':args.model,'elapsed_seconds':time.monotonic()-started,
            'finished_at_utc':remote.now(),'research_pilot_calls':0,'research_main_calls':0})
    except BaseException as exc:
        remote.save(args.output/'failure.json',{'error_type':type(exc).__name__,'error':str(exc)})
        raise
    finally: conn.close()


if __name__ == '__main__': main()
