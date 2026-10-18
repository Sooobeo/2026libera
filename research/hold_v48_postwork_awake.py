"""Temporary awake lease for active offline review AFTER the guarded pilot ends.

This does not run a model or alter study controls. A STOP file or the one-hour
operating lease ends the request. The cap is housekeeping, not a research value.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import sector_v48_main_awake as awake


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def reference(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-summary', required=True, type=Path)
    parser.add_argument('--operating-summary', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    run, operating = read(args.run_summary), read(args.operating_summary)
    if run.get('status') in (None, 'running', 'not_started') or run.get('main_model_calls') != 0:
        raise ValueError('Only after the pilot has terminated')
    if operating.get('awake_release', {}).get('status') != 'released':
        raise ValueError('Resolve prior operating restoration first')
    target = args.output.resolve()
    target.mkdir(parents=True, exist_ok=False)
    save(target / 'invocation.json', {
        'at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Active offline post-pilot audits and document preparation; no model calls.',
        'run_summary': reference(args.run_summary), 'prior_operating_summary': reference(args.operating_summary),
        'maximum_lease_seconds': 3600, 'lease_role': 'Engineering housekeeping; not an experiment parameter.',
        'stop_file': str(target / 'STOP'), 'helper': reference(Path(awake.__file__)),
        'model_calls': 0, 'permanent_power_configuration_changed': False})
    token = None
    status = 'not_started'
    started = time.monotonic()
    try:
        token = awake.acquire()
        save(target / 'acquire.json', token)
        if token.get('status') != 'active':
            raise RuntimeError('Temporary awake lease not acquired')
        print(json.dumps({'status': 'active', 'scope': 'offline_postwork', 'output': str(target)}), flush=True)
        while not (target / 'STOP').exists() and time.monotonic() - started < 3600:
            time.sleep(1)
        status = 'stopped_by_work_owner' if (target / 'STOP').exists() else 'lease_expired'
    finally:
        release = awake.release(token) if isinstance(token, dict) and token.get('status') == 'active' else {'status': 'no_active_request'}
        save(target / 'release.json', release)
        save(target / 'summary.json', {'at_utc': datetime.now(timezone.utc).isoformat(), 'status': status,
             'release': release, 'elapsed_seconds': time.monotonic() - started, 'model_calls': 0})
        if release.get('status') not in ('released', 'no_active_request'):
            raise RuntimeError('Temporary postwork awake restoration failed; inspect release.json')


if __name__ == '__main__':
    main()
