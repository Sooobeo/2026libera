"""One source-free CPU smoke request; never a pilot, a speed ranking or a main run.

120 seconds/32 output tokens are diagnostic resource ceilings, not paper-derived
experimental conditions. The full research output allowance remains 8192.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

import benchmark_sector_latency as bench
import local_sector_single_case as base
import remote_sector_runtime as remote
import sector_v48_main_awake as awake


def run(service_directory: Path):
    service_directory = service_directory.resolve()
    service = json.loads((service_directory / 'service_receipt.json').read_text(encoding='utf-8-sig'))
    if (service['origin'] != 'http://127.0.0.1:11435' or service['status'] != 'ready'
            or service['child_environment']['OLLAMA_VULKAN'] != '0'):
        raise ValueError('Owned isolated CPU service receipt required')
    target = service_directory / 'synthetic_smoke'
    target.mkdir(exist_ok=False)
    body = {'model': base.MODEL, 'messages': [
        {'role': 'user', 'content': 'Synthetic infrastructure check only. Return exactly {"ready":true}.'}],
        'stream': True, 'think': False, 'truncate': False, 'shift': False, 'keep_alive': 0,
        'format': {'type': 'object', 'properties': {'ready': {'const': True}},
                   'required': ['ready'], 'additionalProperties': False},
        'options': base.OPTIONS | {'num_gpu': 0, 'num_predict': 32}}
    pin = bench.observe(service['origin'], base.MODEL)
    base.assert_pin(pin)
    remote.save(target / 'pin.json', pin)
    remote.save(target / 'spec.json', {'origin': service['origin'], 'body': body,
        'deadline_seconds': 120, 'assessment_policy': 'resource_only',
        'purpose': 'One source-free CPU smoke test. No institution, market, evaluation, or pilot input.',
        'research_calls': 0, 'num_ctx': 65536,
        'limits': 'Short prompt/output do not establish full-history task latency or reliability.'})
    token = awake.acquire()
    remote.save(target / 'awake_acquire.json', token)
    try:
        if token['status'] != 'active':
            raise RuntimeError('Temporary awake request not active')
        result = bench.supervised_worker(target / 'spec.json', 120, target / 'CANCEL')
    finally:
        remote.save(target / 'awake_release.json', awake.release(token))
        remote.save(target / 'cleanup.json', bench.unload_and_confirm(service['origin'], base.MODEL))
        log = service_directory / 'server.stderr.log'
        (target / 'server_log_snapshot.txt').write_bytes(log.read_bytes())
    # supervised_worker already writes the authoritative exclusive-create receipt.
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service-directory', type=Path, required=True)
    args = parser.parse_args()
    sys.exit(run(args.service_directory))
