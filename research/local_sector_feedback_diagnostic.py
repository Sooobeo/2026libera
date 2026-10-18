"""One registered development correction of the preserved v4.5 invalid answer.

``prepare`` is offline. Only explicit ``run`` contacts a model service. The
unchanged v4.5 supervised worker supplies pins, rendering, raw transport and the
deadline. Its stage=4 selects the existing schema; this is NOT a four-stage run.
No automatic retry, normalization, hidden reference or main execution exists.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import local_sector_structured_case as transport
from sector_engine import calculate_portfolio, parse_response

base, remote, bench, workflow = transport.base, transport.remote, transport.bench, transport.workflow
ROOT = transport.ROOT
PROTOCOL = '4.6'
DIAGNOSTIC_ID = 'fidelity_q2_2026__v45_final_feedback_revision'
V45_MANIFEST = ROOT / 'data/sector_protocol/v45_single_case_20261018/manifest.json'
V45_MANIFEST_SHA = '6465406eddaa2bab5136d15a0aee1487e9501066f20f421e4c1237ec01b13ff8'
V45_RUN = ROOT / 'data/local_sector_runtime/single_case_v45_20261018'
REVISION_SHA = 'a871bea800e7199b726706e8c064803021735a7bbc99f80f5736014e7790a0d9'
SOURCE_PINS = {
    'fidelity_q2_2026__R1/stage1_request.json': '021aa18ec6b495a6c6323f4b7fae66279340cd1f8ba18f6109b98f768abb5c70',
    'fidelity_q2_2026__R1/stage4_response.json': 'd8218ee743275ab6d9d77151969048e39c0988ac848bdf48a19f872ab7777304',
    'fidelity_q2_2026__R1/stage4_record.json': '7b20d31a9e70f1cdd21aa0abb02c30c5ea7d6c1cd2b5ecdf5c3db11585188731',
    'summary.json': 'e06b9877d288b7a124769528a1a0d475723501477465a515dec9de406e1c9e58',
}
SOFTWARE = transport.SOFTWARE + ('local_sector_feedback_diagnostic.py',)
INPUTS = ('runtime.json', 'model_packet.json', 'market_input.json', 'logical_messages.json',
          'authoritative_body.json', 'response_schema.json', 'prior_calculator_result.json',
          'prior_feedback_message.json', 'prior_response.json', 'prior_record.json')
TASK = (
    'This is one separate development diagnostic, not a continuation of the original four-stage case. '
    'The earlier user message supplies the original public task, institution document and market data. '
    'The preceding assistant message is the complete preserved final candidate from that case. '
    'Intermediate stage-1, stage-2 and stage-3 assistant responses are not included. '
    'Reconsider that candidate using the actual deterministic calculator_feedback embedded here '
    'and repeated unchanged in the preceding user message. This feedback concerns the preserved '
    'candidate, not a new candidate. Treat its reported allocation validity, sum and residual as '
    'the authoritative arithmetic result for that candidate. Determine and submit your own revised '
    '11-sector allocation under the existing nonnegative, sum-to-one conditions. No corrected '
    'sector weights or allocation rule are supplied. Do not normalize or edit the calculator report. '
    'Use risk_discussion to explain which reported violation you addressed and what you changed; '
    'use unresolved to disclose any remaining problem. Do not claim the prior invalid candidate '
    'satisfied a condition that the calculator marked violated. Your declaration of validity is '
    'not acceptance: the new raw weights will be calculated again after this response. '
    'market_diagnostics.status describes the market-input check; a null risk or baseline result '
    'is not a completed portfolio-risk or benchmark check. Focus this diagnostic on allocation '
    'and calculator-feedback reconciliation; no separate source-rationale improvement or '
    'market-number verification program is introduced. Those aspects remain independently '
    'unassessed. Return the existing seven-field response object only.'
)


def sha_record(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': remote.sha(path)}


def revision_records(path):
    path = Path(path).resolve()
    if 'evaluator_only' in path.parts or remote.sha(path) != REVISION_SHA:
        raise ValueError('Require the immutable reviewed diagnostic evidence addendum')
    value = remote.read(path)
    if (value['protocol_version'] != PROTOCOL or value['change_scope'] !=
            'one_call_feedback_grounded_revision_of_preserved_invalid_final_candidate'):
        raise ValueError('Unexpected diagnostic evidence scope')
    rows = [sha_record(path)]
    for row in [value[k] for k in ('prior_basis', 'inherited_conditions', 'renderer_policy', 'schema_evidence')] + value['primary_sources']:
        p = (ROOT / row['path']).resolve()
        if 'evaluator_only' in p.parts or remote.sha(p) != row['sha256']:
            raise ValueError('Diagnostic evidence source changed: ' + str(p))
        rows.append(sha_record(p))
    return rows


def original_inputs():
    if remote.sha(V45_MANIFEST) != V45_MANIFEST_SHA:
        raise ValueError('The prior prepared manifest changed')
    _, runtime, packet, market = transport.verify_manifest(V45_MANIFEST)
    records = []
    for name, expected in SOURCE_PINS.items():
        path = V45_RUN / name
        if remote.sha(path) != expected:
            raise ValueError('Preserved v4.5 artifact changed: ' + name)
        records.append(sha_record(path))
    case = V45_RUN / transport.CASE
    original = remote.read(case / 'stage1_request.json')
    response = remote.read(case / 'stage4_response.json')
    record = remote.read(case / 'stage4_record.json')
    if original != [{'role': 'system', 'content': workflow.SYSTEM},
                    workflow.stage_message(1, 'R1', packet, market)]:
        raise ValueError('Original public task differs from pinned supplied values')
    parsed = parse_response(response['message']['content'])
    if (not parsed['ok'] or parsed['value'] != record['raw_proposal'] or
            response.get('done_reason') != 'stop' or record['repair_applied'] is not False):
        raise ValueError('The preserved final candidate is not the complete original answer')
    recomputed = calculate_portfolio(record['raw_proposal']['weights'], market=market,
        visible_evidence_ids=workflow.evidence_ids(packet),
        submitted_constraints=record['raw_proposal']['submitted_constraints'])
    if recomputed != record['calculator_result'] or recomputed['allocation']['valid'] is not False:
        raise ValueError('The selected candidate must retain its actual invalid calculation')
    return runtime, packet, market, original, response, record, records


def diagnostic_messages(original, response, record):
    feedback = record['calculator_result']
    # No final calculator user message was sent in the old case. This is a new
    # serialization of the original result, using the unchanged workflow format.
    feedback_message = {'role': 'user', 'content': json.dumps(
        {'calculator_feedback': feedback}, ensure_ascii=False, allow_nan=False)}
    task = {'stage': 4, 'diagnostic_id': DIAGNOSTIC_ID,
            'stage_field_role': 'existing_final_response_schema_selector_not_a_workflow_stage',
            'task': TASK, 'calculator_feedback': copy.deepcopy(feedback),
            'response_schema': transport.response_schema(4),
            'response_contract_instruction': transport.CONTRACT_INSTRUCTION}
    messages = copy.deepcopy(original) + [
        {'role': 'assistant', 'content': response['message']['content']}, feedback_message,
        {'role': 'user', 'content': json.dumps(task, ensure_ascii=False, allow_nan=False)}]
    if len(messages) != 5 or json.loads(messages[3]['content'])['calculator_feedback'] != task['calculator_feedback']:
        raise ValueError('Diagnostic feedback duplication differs')
    return messages


def request_body(messages):
    body = base.prepare_body(messages, base.runtime_v44())
    body['format'] = transport.response_schema(4)
    if body['messages'][2:] != messages[2:]:
        raise ValueError('Diagnostic assistant, feedback or task content changed')
    if {k: v for k, v in body.items() if k != 'messages'} != transport.request_header(transport.runtime_v45(), 4):
        raise ValueError('Inherited numerical request controls changed')
    return body


def prepare(args):
    runtime, packet, market, original, response, record, sources = original_inputs()
    evidence = revision_records(args.revision_evidence)
    messages = diagnostic_messages(original, response, record)
    target = Path(args.output).resolve(); target.mkdir(parents=True, exist_ok=False)
    values = {'runtime.json': runtime, 'model_packet.json': packet, 'market_input.json': market,
        'logical_messages.json': messages, 'authoritative_body.json': request_body(messages),
        'response_schema.json': transport.response_schema(4),
        'prior_calculator_result.json': record['calculator_result'],
        'prior_feedback_message.json': messages[3], 'prior_response.json': response, 'prior_record.json': record}
    for name, value in values.items(): remote.save(target / name, value)
    manifest = dict(protocol_version=PROTOCOL, diagnostic_id=DIAGNOSTIC_ID,
        created_at_utc=remote.now(), planned_generation_attempts=1, automatic_retries=0,
        main_model_calls=0, main_freeze=False, human_semantic_pass=False,
        scope='one_prespecified_development_revision_of_a_known_invalid_candidate',
        selection='The failed v4.5 final answer is deliberately selected for development; not an independent sample.',
        call_count_basis='One generation is the registered development scope, not a paper-derived optimum or statistical sample size.',
        parent_preparation=sha_record(V45_MANIFEST), original_sources=sources,
        revision_evidence=evidence, inputs={n: remote.sha(target / n) for n in INPUTS},
        software={n: remote.sha(ROOT / 'research' / n) for n in SOFTWARE},
        controls={'input_messages': 5, 'intermediate_assistant_stages_included': [],
          'feedback_serialization': 'Original stage4 calculator_result newly serialized with the old workflow formatter; it was not sent after the previous final answer.',
          'feedback_embedding': 'The same full original calculator value is duplicated in the current task; no target weights or correction coefficient.',
          'transport': 'Unchanged v4.5 supervised child/worker, response schema, pins, renderer, model and all request options.',
          'stage_selector': 'stage=4 selects the old final-response schema only; this run has one diagnostic call, not four workflow stages.',
          'deadline': '900 seconds for child setup, metadata, render-only and generation combined, apart from OS scheduling/kill overhead. Cleanup is outside.',
          'legacy_worker_counts': 'The reused worker names its call pilot_model_calls; this diagnostic parent counts it only as diagnostic_generation_calls, never a new four-stage pilot or main call.',
          'acceptance': 'Recalculate raw output without normalization, clipping, cash insertion or retry. Numeric acceptance does not grant the three independent reviews or semantic success.',
          'excluded_scope': 'No separate market-number correction or source-rationale improvement program; no R1/R4 inference.'})
    remote.save(target / 'manifest.json', manifest)
    print(json.dumps({'manifest': str(target / 'manifest.json'), 'sha256': remote.sha(target / 'manifest.json'),
                      'model_calls': 0}), flush=True)
    return 0


def verify_manifest(path):
    path = Path(path).resolve(); m = remote.read(path)
    if (m.get('protocol_version') != PROTOCOL or m.get('diagnostic_id') != DIAGNOSTIC_ID or
            m.get('planned_generation_attempts') != 1 or m.get('automatic_retries') != 0 or
            m.get('main_model_calls') != 0 or m.get('main_freeze') is not False or
            m.get('human_semantic_pass') is not False):
        raise ValueError('Unexpected one-call diagnostic scope')
    if set(m['inputs']) != set(INPUTS) or set(m['software']) != set(SOFTWARE):
        raise ValueError('Incomplete prepared artifact inventory')
    for n, digest in m['inputs'].items():
        if remote.sha(path.parent / n) != digest: raise ValueError('Prepared input changed: ' + n)
    for n, digest in m['software'].items():
        if remote.sha(ROOT / 'research' / n) != digest: raise ValueError('Prepared software changed: ' + n)
    runtime, packet, market, original, response, record, sources = original_inputs()
    if m['original_sources'] != sources or m['parent_preparation'] != sha_record(V45_MANIFEST):
        raise ValueError('Prior artifact provenance changed')
    if m['revision_evidence'] != revision_records(m['revision_evidence'][0]['path']):
        raise ValueError('Revision evidence inventory changed')
    messages = diagnostic_messages(original, response, record)
    expected = {'runtime.json': runtime, 'model_packet.json': packet, 'market_input.json': market,
        'logical_messages.json': messages, 'authoritative_body.json': request_body(messages),
        'response_schema.json': transport.response_schema(4), 'prior_calculator_result.json': record['calculator_result'],
        'prior_feedback_message.json': messages[3], 'prior_response.json': response, 'prior_record.json': record}
    for name, value in expected.items():
        if remote.read(path.parent / name) != value: raise ValueError('Prepared value differs: ' + name)
    return m, runtime, packet, market, messages


def verify_registration(path, manifest_path):
    path = Path(path).resolve(); r = remote.read(path)
    if (r.get('protocol_version') != PROTOCOL or r.get('diagnostic_id') != DIAGNOSTIC_ID or
            r.get('manifest') != sha_record(manifest_path) or r.get('planned_generation_attempts') != 1 or
            r.get('automatic_retries') != 0 or r.get('main_model_calls') != 0 or r.get('main_freeze') is not False):
        raise ValueError('A separate registration must pin this exact one-call manifest')
    stamp = datetime.fromisoformat(r['registered_at_utc'].replace('Z', '+00:00'))
    created = datetime.fromisoformat(remote.read(manifest_path)['created_at_utc'].replace('Z', '+00:00'))
    if stamp.tzinfo is None or created.tzinfo is None or not created <= stamp <= datetime.now(timezone.utc):
        raise ValueError('Registration must follow preparation and precede execution')
    return r


def numeric_assessment(calc, old_proposal, new_proposal):
    constraints = calc['submitted_constraint_checks']
    checks = constraints['checks']
    all_constraints = constraints['valid_request'] and all(
        c['evaluable'] is True and c['violation'] == 0 for c in checks)
    accepted = (calc['allocation']['valid'] is True and all_constraints and
                calc['market_diagnostics']['status'] != 'invalid_market')
    def vector(proposal):
        rows = proposal['weights']; codes = [r['sector_code'] for r in rows]
        if len(codes) != 11 or len(set(codes)) != 11 or set(codes) != set(market_codes()): return None
        return {r['sector_code']: r['weight'] for r in rows}
    old, new = vector(old_proposal), vector(new_proposal)
    return {'allocation_valid': calc['allocation']['valid'], 'raw_sum': calc['allocation']['raw_sum'],
        'raw_budget_residual': calc['allocation']['raw_budget_residual'],
        'submitted_constraints_evaluable_and_satisfied': all_constraints,
        'numeric_acceptance': bool(accepted), 'weight_vector_changed': new != old if new is not None else None,
        'changed_sector_codes': [c for c in market_codes() if old[c] != new[c]] if old is not None and new is not None else None,
        'automatic_repair': False, 'semantic_feedback_claim_review': 'pending_offline_review',
        'priority1_solved': False, 'scope': 'raw_numeric_constraints_only_not_strategy_or_feedback_claim_truth'}


def market_codes():
    # Public taxonomy only; no file I/O or evaluator lookup.
    return ('10','15','20','25','30','35','40','45','50','55','60')


def append_event(target, event, **details):
    path = Path(target) / 'events.jsonl'
    prior = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
    previous = json.loads(prior[-1])['event_sha256'] if prior else None
    value = dict(sequence=len(prior) + 1, time_utc=remote.now(), event=event,
                 previous_event_sha256=previous, **details)
    value['event_sha256'] = base.value_sha(value)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')


def run(args):
    path = Path(args.manifest).resolve()
    manifest, runtime, packet, market, messages = verify_manifest(path)
    registration_path = Path(args.registration).resolve()
    registration = verify_registration(registration_path, path)
    origin = remote.validate_origin(args.base_url)
    server_log = Path(args.server_log).resolve()
    if not server_log.is_file(): raise ValueError('Existing owned service log is required')
    target = remote.new_output(args.output_root, 'feedback_diagnostic_v46', args.run_id)
    started = time.monotonic(); stage = target / 'revision_transport'
    summary = dict(status='not_started', protocol_version=PROTOCOL, diagnostic_id=DIAGNOSTIC_ID,
        planned_generation_attempts=1, automatic_retries=0, four_stage_pilot_calls=0, main_model_calls=0,
        main_freeze=False, human_semantic_pass=False, priority1_solved=False, numeric_acceptance=None)
    frozen = {'manifest': sha_record(path), 'registration': sha_record(registration_path)}
    remote.save(target / 'manifest_snapshot.json', manifest)
    remote.save(target / 'registration_snapshot.json', registration)
    remote.save(target / 'runtime.json', runtime)
    remote.save(target / 'invocation.json', dict(started_at_utc=remote.now(), origin=origin,
        server_log=str(server_log), **frozen, controls=manifest['controls'], purpose=manifest['scope']))
    append_event(target, 'registered_diagnostic_started', **frozen)
    try:
        state = remote.api_json(origin, '/api/ps'); remote.save(target / 'residency_before.json', state)
        if state.get('models') != []: raise ValueError('Existing model workload must be resolved by the operator')
        observed = bench.observe(origin, base.MODEL)
        remote.save(target / 'initial_pin.json', observed); base.assert_pin(observed)
        if (target / 'CANCEL').exists(): raise base.StageStopped('cancelled')
        verify_manifest(path); verify_registration(registration_path, path)
        if frozen != {'manifest': sha_record(path), 'registration': sha_record(registration_path)}:
            raise ValueError('Manifest or registration changed before generation')
        stage.mkdir(); body = request_body(messages)
        remote.save(stage / 'logical_messages.json', messages)
        remote.save(stage / 'authoritative_body.json', body)
        (stage / 'authoritative_body.bin').write_bytes(json.dumps(body, ensure_ascii=False, allow_nan=False).encode())
        remote.save(stage / 'response_schema.json', transport.response_schema(4))
        remote.save(stage / 'prior_feedback_message.json', messages[3])
        before = server_log.read_bytes()
        remote.save(stage / 'server_log_before.json', dict(path=str(server_log), bytes=len(before), sha256=hashlib.sha256(before).hexdigest()))
        spec = stage / 'worker_spec.json'
        remote.save(spec, dict(origin=origin, body=body, deadline_seconds=runtime['deadline_seconds'], cancel_path=str(target / 'CANCEL')))
        append_event(target, 'single_supervised_attempt_dispatched', body=sha_record(stage / 'authoritative_body.bin'))
        try:
            result = transport.supervise(spec, runtime['deadline_seconds'], target / 'CANCEL')
        finally:
            clean = bench.unload_and_confirm(origin, base.MODEL)
            remote.save(stage / 'unload_and_residency.json', clean)
            after = server_log.read_bytes(); (stage / 'server_log_after_snapshot.bin').write_bytes(after)
            remote.save(stage / 'server_log_delta.json', dict(original_prefix_retained=after.startswith(before),
                prior_bytes=len(before), after_bytes=len(after), sha256=hashlib.sha256(after).hexdigest()))
            append_event(target, 'cleanup_recorded', cleanup=sha_record(stage / 'unload_and_residency.json'))
        if clean['status'] != 'no_resident_models_observed': raise RuntimeError('Model unload/idle was not confirmed')
        if result['status'] != 'worker_exited': raise base.StageStopped(result['status'])
        status = result.get('worker', {}).get('status')
        if status != 'completed': raise base.StageStopped(status or 'worker_result_missing')
        response_path = stage / 'http_0001_generation/response.json'
        response = remote.read(response_path)
        parsed = parse_response(response['message']['content'])
        if not parsed['ok']: raise ValueError('Invalid response retained; no correction by the host')
        proposal = parsed['value']
        calc = calculate_portfolio(proposal['weights'], market=market,
            visible_evidence_ids=workflow.evidence_ids(packet), submitted_constraints=proposal['submitted_constraints'])
        prior = remote.read(path.parent / 'prior_record.json')
        assessment = numeric_assessment(calc, prior['raw_proposal'], proposal)
        remote.save(target / 'revision_record.json', dict(raw_proposal=proposal,
            calculator_arguments={'weights': proposal['weights'], 'submitted_constraints': proposal['submitted_constraints']},
            calculator_result=calc, prior_calculator_result=prior['calculator_result'],
            assessment=assessment, response_source=sha_record(response_path), repair_applied=False))
        append_event(target, 'raw_revision_recalculated', record=sha_record(target / 'revision_record.json'))
        summary.update(status='completed_one_diagnostic', numeric_acceptance=assessment['numeric_acceptance'],
            weight_vector_changed=assessment['weight_vector_changed'], raw_sum=assessment['raw_sum'],
            raw_budget_residual=assessment['raw_budget_residual'])
    except BaseException as exc:
        summary.update(status='cancelled' if isinstance(exc, KeyboardInterrupt) else getattr(exc, 'status', 'failed'),
                       error_type=type(exc).__name__, error=str(exc))
        remote.save(target / 'failure.json', dict(type=type(exc).__name__, message=str(exc),
            handling='Retain this attempt; no automatic retry, replacement candidate or continuation.'))
        append_event(target, 'diagnostic_stopped', status=summary['status'])
    finally:
        generated = (stage / 'http_0001_generation/request.json').is_file()
        rendered = (stage / 'render_only/request.json').is_file()
        result_path = stage / 'http_0001_generation/result.json'
        render_path = stage / 'render_only/result.json'
        summary.update(finished_at_utc=remote.now(), wall_seconds=time.monotonic() - started,
            generation_requests_attempted=int(generated), diagnostic_generation_calls=int(generated),
            render_requests_attempted=int(rendered),
            http_streams_completed=int(result_path.is_file() and remote.read(result_path).get('status') == 'completed'),
            unexpected_generation_evidence_in_render=bool(render_path.is_file() and remote.read(render_path).get('unexpected_generation_evidence')),
            complete_revision_record=(target / 'revision_record.json').is_file(),
            semantic_validity_assessed=False, independent_reviews_completed=0,
            replaces_previous_failed_attempt=False,
            completion_scope='One registered diagnostic attempt; observed transport completion, structural validity, arithmetic acceptance and the three independent reviews are separate.',
            reused_worker_count_scope=manifest['controls']['legacy_worker_counts'])
        remote.save(target / 'summary.json', summary)
        append_event(target, 'diagnostic_finished', summary=sha_record(target / 'summary.json'))
    print(json.dumps({'output': str(target), **summary}, ensure_ascii=False), flush=True)
    return 0 if summary['status'] == 'completed_one_diagnostic' else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare'); prep.add_argument('--output', type=Path, required=True)
    prep.add_argument('--revision-evidence', type=Path, required=True)
    runner = sub.add_parser('run'); runner.add_argument('--manifest', type=Path, required=True)
    runner.add_argument('--registration', type=Path, required=True)
    runner.add_argument('--base-url', default='http://127.0.0.1:11434')
    runner.add_argument('--server-log', type=Path, required=True)
    runner.add_argument('--output-root', type=Path, default=ROOT / 'data/local_sector_runtime')
    runner.add_argument('--run-id', required=True)
    args = parser.parse_args(argv)
    return prepare(args) if args.command == 'prepare' else run(args)


if __name__ == '__main__':
    raise SystemExit(main())
