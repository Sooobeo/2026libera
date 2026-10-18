"""One bounded real-input feasibility probe, excluded from research pilot/main.

The exact Fidelity Q2/R1 first-stage SYSTEM and public document are used, with a
reversible duplicate-only market projection. Only the compact request is sent.
The 32-token output cap, model-specific context, threads, batch and deadline are
engineering controls. No response quality is scored and truncation is expected.
No model pull, protocol/freeze update, automatic retry, or main run is performed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import time

import benchmark_sector_latency as bench
import remote_sector_runtime as remote
import run_sector_workflow as workflow
from compact_sector_prompt import PROJECTION_VERSION, compact_stage_content, restore_market


ROOT = Path(__file__).resolve().parents[1]
CONTEXTS = {'qwen3:1.7b': 32768, 'qwen3.5:4b-q4_K_M': 65536}
SOURCE = 'fidelity_q2_2026'
OUTPUT_CAP = 32


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(',', ':'))


def value_sha(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def prepare_requests(model, threads, packet, market):
    """Pure construction and exact-value round trip; neither input is mutated."""
    if model not in CONTEXTS or model not in bench.MODELS:
        raise ValueError('Only explicitly pinned installed model candidates are allowed')
    if type(threads) is not int or threads not in (2, 4):
        raise ValueError('Threads must be the explicit engineering candidate 2 or 4')
    if packet.get('source_id') != SOURCE or packet.get('split') != 'pilot':
        raise ValueError('This feasibility probe uses Fidelity Q2/R1 stage 1 only')
    if 'evidence_passages' not in packet or any(k in packet for k in ('sector_ratings', 'evidence_index')):
        raise ValueError('Public source packet required, never reference annotations')
    before_market, before_packet = canonical(market), canonical(packet)
    original = bench.body_for(model, threads)
    original['options']['num_ctx'] = CONTEXTS[model]
    original['messages'] = [{'role': 'system', 'content': workflow.SYSTEM},
                            workflow.stage_message(1, 'R1', packet, market)]
    compact = copy.deepcopy(original)
    compact['messages'][1]['content'] = compact_stage_content(original['messages'][1]['content'])
    restored = json.loads(compact['messages'][1]['content'])
    restored['common_market'] = restore_market(restored['common_market'])
    original_payload = json.loads(original['messages'][1]['content'])
    if canonical(restored) != canonical(original_payload):
        raise ValueError('Exact original first-stage field values did not round-trip')
    if canonical(market) != before_market or canonical(packet) != before_packet:
        raise ValueError('Input mutation detected')
    if compact['messages'][0] != original['messages'][0]:
        raise ValueError('SYSTEM changed')
    counts = {}
    for label, body in (('original', original), ('compact', compact)):
        messages = body['messages']
        bound = workflow.conservative_context_bound(messages)
        counts[label] = {
            'content_characters': sum(len(m['content']) for m in messages),
            'content_utf8_bytes': sum(len(m['content'].encode('utf-8')) for m in messages),
            'messages_serialized_utf8_bytes': len(json.dumps(messages, ensure_ascii=False).encode('utf-8')),
            'request_serialized_utf8_bytes': len(json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')),
            'request_value_sha256': value_sha(body), 'conservative_screening_bound': bound,
            'screening_plus_output_allowance': bound + OUTPUT_CAP,
        }
    if counts['compact']['screening_plus_output_allowance'] > CONTEXTS[model]:
        raise ValueError('Compact prompt exceeds the conservative context screen; no truncation')
    validation = {'exact_original_field_value_roundtrip': True, 'input_mutation': False,
                  'system_unchanged': True, 'institution_document_unchanged': True,
                  'projection_version': PROJECTION_VERSION, 'sizes': counts,
                  'interpretation': 'Bytes and conservative screen are not actual tokenizer counts or speed predictions.'}
    return original, compact, validation


def run(args):
    origin = remote.validate_origin(args.base_url)
    if not math.isfinite(args.deadline_seconds) or not 0 < args.deadline_seconds <= 180:
        raise ValueError('Engineering child-process deadline must be greater than zero and at most 180 seconds')
    target = remote.new_output(args.output_root, 'real_input_feasibility', args.run_id)
    started = time.monotonic()
    result = {'status': 'not_started', 'output': str(target), 'scope': 'real_input_engineering_feasibility_only',
              'model': args.model, 'case_input': SOURCE + '__R1__stage1',
              'probe_invocations_attempted': 0, 'generation_request_envelopes_recorded': 0,
              'pilot_model_calls': 0, 'main_model_calls': 0, 'automatic_retries': 0,
              'response_quality_scored': False, 'four_stage_feasibility_established': False}
    try:
        corpus, market = remote.load_pilot_inputs(args.packets, args.market)
        packet = next(p for p in corpus if p['source_id'] == SOURCE)
        original, compact, validation = prepare_requests(args.model, args.threads, packet, market)
        remote.save(target / 'original_request_not_sent.json', original)
        remote.save(target / 'compact_request_to_send.json', compact)
        remote.save(target / 'roundtrip_and_sizes.json', validation)
        hashes = {str(path.relative_to(ROOT)): remote.sha(path) for path in (
            Path(__file__), Path(bench.__file__), Path(remote.__file__), Path(workflow.__file__),
            Path(__file__).with_name('compact_sector_prompt.py'))}
        hashes.update(market_file_sha256=remote.sha(args.market), packet_file_sha256=remote.sha(args.packets),
                      selected_packet_value_sha256=value_sha(packet))
        remote.save(target / 'invocation.json', {
            'started_at_utc': remote.now(), 'scope': result['scope'], 'model': args.model,
            'approved_manifest_digest': bench.MODELS[args.model], 'approved_engine': bench.ENGINE,
            'origin': origin, 'deadline_seconds': args.deadline_seconds, 'file_hashes': hashes,
            'projection_version': PROJECTION_VERSION, 'request_options': compact['options'],
            'only_compact_request_sent': True, 'planned_generation_attempts': 1,
            'pilot_model_calls': 0, 'main_model_calls': 0,
            'condition_basis': 'Output cap32, context32768/65536, thread/batch settings, decoding overrides and timeout are engineering probe controls, not a claimed paper-condition replication.',
            'interpretation_limits': 'One first-stage request. No allocation/rating scoring, no full workflow verdict, no original-versus-compact latency comparison; OS file cache is not evicted.'})
        state = remote.api_json(origin, '/api/ps')
        remote.save(target / 'residency_before.json', state)
        if not isinstance(state.get('models'), list) or state['models']:
            raise RuntimeError('Require an explicit empty residency observation; operator must stop earlier workloads first')
        observed = bench.observe(origin, args.model)
        remote.save(target / 'model_observation.json', observed)
        idle = bench.unload_and_confirm(origin, args.model)
        remote.save(target / 'idle_confirmation_before.json', idle)
        if idle['status'] != 'no_resident_models_observed':
            raise RuntimeError('Idle not confirmed; no generation permitted')
        observed_again = bench.observe(origin, args.model, observed)
        remote.save(target / 'model_observation_before_request.json', observed_again)
        if (target / 'CANCEL').exists():
            result['status'] = 'cancelled_before_probe'
        else:
            folder = target / 'compact_probe'
            folder.mkdir()
            spec = {'origin': origin, 'deadline_seconds': args.deadline_seconds,
                    'assessment_policy': 'resource_only', 'body': compact}
            remote.save(folder / 'worker_spec.json', spec)
            result['probe_invocations_attempted'] = 1
            supervised = bench.supervised_worker(folder / 'worker_spec.json', args.deadline_seconds, target / 'CANCEL')
            result['supervisor'] = supervised
            child = supervised.get('worker', {})
            status = child.get('status', supervised['supervisor_status'])
            if child.get('unexpected_thinking') or (child.get('response_model') is not None
                                                    and child['response_model'] != args.model):
                status = 'response_protocol_anomaly'
            result.update(status=status, output_limit_reached=child.get('done_reason') == 'length',
                          output_limit_is_expected_engineering_ceiling=True)
    except BaseException as exc:
        result.update(status='cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed',
                      error_type=type(exc).__name__, error=str(exc))
        remote.save(target / 'failure.json', {'type': type(exc).__name__, 'message': str(exc)})
    finally:
        if result['probe_invocations_attempted']:
            cleanup = bench.unload_and_confirm(origin, args.model)
            remote.save(target / 'unload_and_residency_after.json', cleanup)
            result['cleanup_status'] = cleanup['status']
            if cleanup['status'] != 'no_resident_models_observed':
                result['probe_outcome_before_cleanup'] = result['status']
                result['status'] = 'stopped_idle_not_confirmed'
        http = target / 'compact_probe' / 'http_0001_latency_probe'
        result['generation_request_envelopes_recorded'] = int((http / 'request.json').is_file())
        if (http / 'result.json').is_file():
            call = remote.read(http / 'result.json')
            result['provider_metrics'] = call.get('metrics')
        result.update(finished_at_utc=remote.now(), script_wall_seconds=time.monotonic() - started,
                      deadline_scope=f'{args.deadline_seconds:g}-second maximum applies to the supervised child lifetime; metadata checks and cleanup are outside that bound.')
        remote.save(target / 'summary.json', result)
    print(json.dumps({k: result[k] for k in ('status', 'output', 'model', 'probe_invocations_attempted',
          'generation_request_envelopes_recorded', 'pilot_model_calls', 'main_model_calls', 'script_wall_seconds')},
          ensure_ascii=False), flush=True)
    return 0 if result['status'] in ('completed', 'output_limit_reached') else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, choices=tuple(CONTEXTS))
    parser.add_argument('--threads', type=int, choices=(2, 4), default=2)
    parser.add_argument('--base-url', default='http://127.0.0.1:11434')
    parser.add_argument('--output-root', type=Path, default=ROOT / 'data/sector_runtime')
    parser.add_argument('--run-id')
    parser.add_argument('--deadline-seconds', type=float, default=180)
    parser.add_argument('--packets', type=Path, default=ROOT / 'data/sector_documents/model_packets.jsonl')
    parser.add_argument('--market', type=Path, default=ROOT / 'data/sector_market/market_input.json')
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    raise SystemExit(main())
