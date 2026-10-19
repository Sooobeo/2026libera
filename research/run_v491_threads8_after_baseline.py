"""Wait for the predeclared CPU baseline, then launch its one 8-thread diagnostic.

No research input is sent. The original2-thread outcome is preserved regardless
of success. A confirmed idle service is mandatory; no overlapping generations.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

import remote_sector_runtime as remote

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/local_sector_runtime/v491_cpu_preflight_20261019'


def main():
    registration = json.loads((BASE / 'thread_comparison_plan.json').read_text(encoding='utf-8'))
    if registration['order'] != [2, 8] or not registration['no_retries']:
        raise ValueError('Predeclared engineering sequence differs')
    target = BASE / 'synthetic_large_input_threads8'
    if target.exists():
        raise ValueError('Existing8-thread diagnostic cannot be repeated')
    started = time.monotonic()
    # Waiting is only a coordinator activity, never an extension of baseline's
    # own900-second supervised request limit.
    while not (BASE / 'synthetic_large_input/cleanup.json').is_file():
        if time.monotonic() - started > 1000:
            raise TimeoutError('Baseline cleanup receipt did not appear; no next request')
        time.sleep(1)
    time.sleep(1)  # Permit the exclusive receipt writer to finish before parsing.
    cleanup = json.loads((BASE / 'synthetic_large_input/cleanup.json').read_text(encoding='utf-8'))
    if cleanup['status'] != 'no_resident_models_observed':
        raise RuntimeError('Baseline cleanup not confirmed; no next request')
    state = remote.api_json('http://127.0.0.1:11435', '/api/ps')
    if state.get('models') != []:
        raise RuntimeError('Isolated server is not idle; no next request')
    remote.save(BASE / 'threads8_launch_receipt.json', {'at_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Second prespecified source-free engineering configuration',
        'baseline_cleanup': cleanup['status'], 'idle_before_launch': True,
        'pilot_calls': 0, 'main_calls': 0})
    command = [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'research/probe_sector_v491_long_cpu.py'),
               '--service-directory', str(BASE), '--target-tokens', '13225', '--threads', '8']
    with (BASE / 'threads8_coordinator.console.log').open('xb') as log:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    print(json.dumps({'threads8_coordinator_exit_code': result.returncode, 'pilot_calls': 0, 'main_calls': 0}))
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
