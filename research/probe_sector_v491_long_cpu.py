"""One source-free large-input CPU diagnostic, separate from all research cases.

Select synthetic input length by exact installed-tokenizer counts to cover the
largest measured D0. No institution or market content enters the generation.
One attempt, 900-second engineering deadline and 32-token diagnostic output cap.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import benchmark_sector_latency as bench
import local_sector_single_case as base
import remote_sector_runtime as remote
import sector_v48_transport as transport
import sector_v48_main_awake as awake
from sector_v491_tokenizer import NativeTokenizer


def run(service_directory, target_tokens, threads=2):
    service_directory = service_directory.resolve()
    service = json.loads((service_directory / 'service_receipt.json').read_text(encoding='utf-8-sig'))
    if service['origin'] != 'http://127.0.0.1:11435' or service['child_environment']['OLLAMA_VULKAN'] != '0':
        raise ValueError('Owned isolated CPU service required')
    if not 1000 < target_tokens < 65536 - 8192:
        raise ValueError('Explicit measured D0 size required')
    if threads not in (2, 8):
        raise ValueError('Only the two predeclared engineering thread settings are allowed')
    target = service_directory / ('synthetic_large_input' if threads == 2 else 'synthetic_large_input_threads8')
    target.mkdir(exist_ok=False)
    system = 'This is a source-free infrastructure check. Return exactly {"ready":true}.'
    with NativeTokenizer() as tokenizer:
        records = []
        while True:
            records.extend({'slot': i, 'units': 7, 'group': 'amber'} for i in range(len(records), len(records) + 32))
            content = json.dumps({'synthetic_inventory': records, 'instruction': 'Return only {"ready":true}.'}, separators=(',', ':'))
            count = len(tokenizer.tokens(content))
            if count >= target_tokens:
                break
        body = {'model': base.MODEL, 'messages': [{'role': 'system', 'content': system},
            {'role': 'user', 'content': content}], 'stream': True, 'think': False,
            'truncate': False, 'shift': False, 'keep_alive': 0, 'format': 'json',
            'options': base.OPTIONS | {'num_gpu': 0, 'num_predict': 32, 'num_thread': threads}}
        pin = bench.observe(service['origin'], base.MODEL)
        base.assert_pin(pin)
        remote.save(target / 'pin.json', pin)
        session = bench.ProbeSession(target, service['origin'], 60, 2)
        transport.render_call(session, body, system)
        rendered = (target / 'render_only/rendered_prompt.txt').read_bytes().decode('utf-8')
        token_receipt = tokenizer.count(rendered)
    if not target_tokens <= token_receipt['token_count'] < 65536 - 8192:
        raise ValueError('Actual rendered synthetic input fails declared capacity bound')
    remote.save(target / 'tokenizer_receipt.json', token_receipt)
    remote.save(target / 'spec.json', {'origin': service['origin'], 'body': body,
        'deadline_seconds': 900, 'assessment_policy': 'resource_only',
        'purpose': 'Source-free large-input engineering diagnostic; no model research case or output.',
        'sizing_rule': 'Add32fictional inventory rows until exact user-content tokens cover largest measured D0; count full actual rendering again.',
        'target_D0_tokens': target_tokens, 'actual_prompt_tokens': token_receipt['token_count'],
        'research_calls': 0, 'automatic_retries': 0,
        'limits': 'Synthetic content differs from the task. Short output cannot establish full F0/history latency or scientific validity.',
        'ceilings_basis': '900s inherited runtime engineering ceiling,32outputtokens inherited synthetic diagnostic cap; neither is a paper-derived experimental optimum.'})
    guard = awake.acquire()
    remote.save(target / 'awake_acquire.json', guard)
    try:
        if guard['status'] != 'active':
            raise RuntimeError('Awake request failed')
        result = bench.supervised_worker(target / 'spec.json', 900, target / 'CANCEL')
    finally:
        remote.save(target / 'awake_release.json', awake.release(guard))
        remote.save(target / 'cleanup.json', bench.unload_and_confirm(service['origin'], base.MODEL))
        (target / 'server_log_snapshot.txt').write_bytes((service_directory / 'server.stderr.log').read_bytes())
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service-directory', type=Path, required=True)
    parser.add_argument('--target-tokens', type=int, required=True)
    parser.add_argument('--threads', type=int, choices=[2, 8], default=2)
    args = parser.parse_args()
    run(args.service_directory, args.target_tokens, args.threads)
