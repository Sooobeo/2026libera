"""Separate v4.5 one-case pilot: JSON-schema decoding plus prompt grounding.

Only explicit ``run`` performs HTTP requests. ``prepare`` is offline. Existing
v4.4 code, conditions and artifacts remain immutable. No retry, answer repair,
gold access, hidden lookup, main run or automatic semantic approval is allowed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import local_sector_single_case as base
from sector_response_schema import (SCHEMA_VERSION, GROUNDING_VERSION,
    CONTRACT_INSTRUCTION, response_schema, validate_response)

ROOT, MODEL, DIGEST, TEMPLATE, ENGINE = base.ROOT, base.MODEL, base.DIGEST, base.TEMPLATE, base.ENGINE
SOURCE, CASE = base.SOURCE, base.CASE
remote, bench, workflow = base.remote, base.bench, base.workflow
canonical, value_sha, StageStopped = base.canonical, base.value_sha, base.StageStopped
assert_pin, render_call, validate_render = base.assert_pin, base.render_call, base.validate_render
OPTIONS = base.OPTIONS.copy()
PROJECTION_VERSION = base.PROJECTION_VERSION
SOFTWARE = base.SOFTWARE + ('local_sector_structured_case.py', 'sector_response_schema.py')
SCHEMA_EVIDENCE_SHA = '57a9c86c2bbc08a1006d6339bcd3303194ae8975cab14d6c5603a3191122dd79'
LOCKED_BASE = {
    'local_sector_single_case.py': '0b2596a223167136bb37578e86469d50c26e7883305d4db31f43b9ddd10d28d0',
    'run_sector_workflow.py': '5625450a4dcbe1aa717c9809bf4955c1ef6b10aab4f0c83ef05dc2eb2c123cfd',
    'sector_engine.py': '507eb352fc3b8b61ad92be31e4697e48deb0e8cc233fae5e230aecb7a0c9649c',
}


def runtime_v45():
    value = base.runtime_v44()
    value.pop('format')
    value.update(protocol_version='4.5', format_mode='per_stage_json_schema',
                 response_schema_version=SCHEMA_VERSION, prompt_grounding_version=GROUNDING_VERSION)
    return value


def validate_runtime(runtime):
    if canonical(runtime) != canonical(runtime_v45()):
        raise ValueError('Runtime differs from the explicit v4.5 protocol; no fallback')


def verify_base_sources():
    for name, digest in LOCKED_BASE.items():
        if remote.sha(ROOT / 'research' / name) != digest:
            raise ValueError('Immutable v4.4 dependency changed: ' + name)


def current_stage(messages):
    if not messages or messages[-1].get('role') != 'user':
        raise ValueError('Expected the current stage user message')
    stage = json.loads(messages[-1]['content']).get('stage')
    if type(stage) is not int or stage not in (1, 2, 3, 4):
        raise ValueError('Unexpected stage number')
    return stage


def ground_messages(messages):
    """Add declared output guidance only to stage tasks, never assistant/calc text."""
    grounded = copy.deepcopy(messages)
    seen = []
    for index, original in enumerate(messages):
        if original.get('role') != 'user':
            continue
        payload = json.loads(original['content'])
        if 'stage' not in payload:
            if set(payload) != {'calculator_feedback'}:
                raise ValueError('Unexpected non-stage user message')
            continue
        stage = payload['stage']
        if type(stage) is not int or stage != len(seen) + 1 or stage not in (1, 2, 3, 4):
            raise ValueError('Stage messages must appear once in order')
        expected_keys = {'stage', 'task', 'common_market', 'institution_document'} if stage == 1 else {'stage', 'task'}
        if set(payload) != expected_keys or payload['task'] != workflow.STAGES[stage]:
            raise ValueError('Original R1 stage task changed')
        revised = copy.deepcopy(payload)
        revised['response_schema'] = response_schema(stage, institution_visible=True)
        revised['response_contract_instruction'] = CONTRACT_INSTRUCTION
        restored = copy.deepcopy(revised)
        restored.pop('response_schema'); restored.pop('response_contract_instruction')
        if canonical(restored) != canonical(payload):
            raise ValueError('Grounding modified an original task value')
        grounded[index]['content'] = json.dumps(revised, ensure_ascii=False, allow_nan=False)
        seen.append(stage)
    if seen != list(range(1, current_stage(messages) + 1)):
        raise ValueError('Incomplete stage history')
    return grounded


def request_header(runtime, stage):
    validate_runtime(runtime)
    header = {key: copy.deepcopy(runtime[key]) for key in
              ('model', 'think', 'truncate', 'shift', 'stream', 'keep_alive', 'options')}
    header['format'] = response_schema(stage, institution_visible=True)
    return header


def prepare_body(messages, runtime):
    validate_runtime(runtime)
    grounded = ground_messages(messages)
    # Explicit delegation, not mutation of the old module's constants or globals.
    body = base.prepare_body(grounded, base.runtime_v44())
    body['format'] = response_schema(current_stage(messages), institution_visible=True)
    expected_header = request_header(runtime, current_stage(messages))
    if canonical({k: v for k, v in body.items() if k != 'messages'}) != canonical(expected_header):
        raise ValueError('Transport options changed outside the declared schema revision')
    return body


def schema_evidence_records(path):
    path = Path(path).resolve()
    if 'evaluator_only' in path.parts or remote.sha(path) != SCHEMA_EVIDENCE_SHA:
        raise ValueError('Require the reviewed, separately pinned schema evidence package')
    value = remote.read(path)
    if (value.get('protocol_version') != '4.5'
            or value.get('change_scope') != 'response_schema_and_prompt_grounding'):
        raise ValueError('Unexpected schema amendment scope')
    inherited = value['inherited_conditions']
    if inherited['sha256'] != base.CONDITIONS_SHA:
        raise ValueError('Schema amendment changed inherited numerical conditions')
    if remote.sha(ROOT / inherited['path']) != base.CONDITIONS_SHA:
        raise ValueError('Inherited conditions file changed')
    records = [{'path': str(path), 'sha256': SCHEMA_EVIDENCE_SHA}]
    source_manifest = value['source_manifest']
    source_manifest_path = ROOT / source_manifest['path']
    if remote.sha(source_manifest_path) != source_manifest['sha256']:
        raise ValueError('Schema primary-source manifest changed')
    records.append({'path': str(source_manifest_path), 'sha256': source_manifest['sha256']})
    for row in value['primary_sources']:
        if 'path' not in row:
            continue
        source = ROOT / row['path']
        if 'evaluator_only' in source.parts or remote.sha(source) != row['sha256']:
            raise ValueError('Schema primary evidence changed: ' + row['path'])
        records.append({'path': str(source), 'sha256': row['sha256'], 'url': row['url']})
    if len(records) < 2:
        raise ValueError('Archived primary implementation evidence is required')
    return records


def prepare(args):
    verify_base_sources()
    source, market_path = base.SOURCE_REQUEST, workflow.MARKET
    if remote.sha(source) != base.SOURCE_REQUEST_SHA or remote.sha(market_path) != base.MARKET_SHA:
        raise ValueError('Pinned original public inputs changed')
    prior = remote.read(source)
    packet = json.loads(prior['messages'][1]['content'])['institution_document']
    base.validate_packet(packet)
    conditions = Path(args.conditions_evidence).resolve()
    if 'evaluator_only' in conditions.parts:
        raise ValueError('Conditions must not be evaluator material')
    base.validate_conditions(conditions)
    schema_records = schema_evidence_records(args.schema_evidence)
    renderer_records = base.renderer_source_records()
    primary = remote.read(base.PRIMARY_MANIFEST)
    source_evidence = [{'path': str(base.PRIMARY_MANIFEST), 'sha256': remote.sha(base.PRIMARY_MANIFEST)}]
    for row in primary['records']:
        p = ROOT / row['path']
        if remote.sha(p) != row['sha256']:
            raise ValueError('Archived inherited primary source changed: ' + row['path'])
        source_evidence.append({'path': str(p), 'sha256': row['sha256'], 'url': row['url']})
    target = Path(args.output).resolve()
    target.mkdir(parents=True, exist_ok=False)
    remote.save(target / 'runtime.json', runtime_v45())
    remote.save(target / 'model_packet.json', packet)
    (target / 'market_input.json').write_bytes(market_path.read_bytes())
    names = ['runtime.json', 'model_packet.json', 'market_input.json']
    for stage in range(1, 5):
        name = f'response_schema_stage{stage}.json'
        remote.save(target / name, response_schema(stage))
        names.append(name)
    manifest = dict(protocol_version='4.5', scope='one_predetermined_pilot_case',
        created_at_utc=remote.now(), case_id=CASE, arm='R1', planned_cases=1,
        planned_stages=[1, 2, 3, 4], selection='Same predetermined first case after recorded v4.4 failure; no outcome-based case substitution.',
        main_freeze=False, human_semantic_pass=False,
        inputs={name: remote.sha(target / name) for name in names},
        source_request={'path': str(source), 'sha256': base.SOURCE_REQUEST_SHA},
        selected_packet_value_sha256=base.PACKET_VALUE_SHA,
        software={name: remote.sha(ROOT / 'research' / name) for name in SOFTWARE},
        inherited_conditions_evidence={'path': str(conditions), 'sha256': remote.sha(conditions)},
        schema_evidence=schema_records, renderer_policy_evidence=renderer_records,
        primary_source_evidence=source_evidence,
        controls={'revision': 'JSON-schema API grammar and schema-in-prompt grounding change together; no separate causal effect identified.',
                  'decoding': 'v4.4 model/engine/template, T0, seed3407, neutral penalties, output8192, context65536 and all remaining request options retained.',
                  'deadline': 'One supervised child per stage: setup, metadata, render-only and generation combined are limited to 900 seconds, apart from OS scheduling/kill overhead. Cleanup is outside.',
                  'history': 'Logical requests saved unchanged; deterministic schema guidance added only to stage user JSON. Original task, common market and public document values retained. Assistant/calculator strings are verbatim.',
                  'projection': 'The unchanged reversible duplicate-market-field projection follows grounding. Grounded and authoritative messages are both saved.',
                  'context': 'Inherited render-only visible-message validation plus truncate=false/shift=false; no independent tokenization or capacity proof.',
                  'validation': 'Required fields, JSON types and array lengths only; no gold values. Public sector duplication/missing rows are recorded diagnostically. Portfolio sum/sign/coverage errors remain with the unchanged calculator. No semantic pass from structural validity.',
                  'failure': 'Preserve raw response and attempt count, stop on schema/cap/deadline/transport/pin failure; no repair, automatic retry or alternate model.',
                  'assessment': 'Four-stage completion is workflow execution, not investment validity, human review or main-study readiness.'})
    remote.save(target / 'manifest.json', manifest)
    print(json.dumps({'prepared_manifest': str(target / 'manifest.json'), 'model_calls': 0,
                      'main_freeze': False}), flush=True)
    return 0


def verify_manifest(path):
    verify_base_sources()
    path = Path(path).resolve(); m = remote.read(path)
    if (m.get('protocol_version') != '4.5' or m.get('case_id') != CASE or m.get('arm') != 'R1'
            or m.get('planned_cases') != 1 or m.get('planned_stages') != [1, 2, 3, 4]
            or m.get('main_freeze') is not False or m.get('human_semantic_pass') is not False):
        raise ValueError('Manifest must describe exactly the v4.5 single pilot')
    expected_inputs = {'runtime.json', 'model_packet.json', 'market_input.json'} | {
        f'response_schema_stage{n}.json' for n in range(1, 5)}
    if set(m['inputs']) != expected_inputs or set(m['software']) != set(SOFTWARE):
        raise ValueError('Manifest input/software inventory differs')
    for name, digest in m['inputs'].items():
        if remote.sha(path.parent / name) != digest: raise ValueError('Prepared input changed: ' + name)
    for name, digest in m['software'].items():
        if remote.sha(ROOT / 'research' / name) != digest: raise ValueError('Prepared software changed: ' + name)
    if m['renderer_policy_evidence'] != base.renderer_source_records():
        raise ValueError('Renderer policy inventory changed')
    if m['schema_evidence'] != schema_evidence_records(m['schema_evidence'][0]['path']):
        raise ValueError('Schema evidence inventory changed')
    for item in [m['source_request'], m['inherited_conditions_evidence'], *m['primary_source_evidence'],
                 *m['renderer_policy_evidence'], *m['schema_evidence']]:
        if remote.sha(Path(item['path'])) != item['sha256']:
            raise ValueError('Pinned provenance changed: ' + item['path'])
    if m['source_request']['sha256'] != base.SOURCE_REQUEST_SHA:
        raise ValueError('Unapproved original public request')
    base.validate_conditions(Path(m['inherited_conditions_evidence']['path']))
    runtime = remote.read(path.parent / 'runtime.json'); validate_runtime(runtime)
    packet = remote.read(path.parent / 'model_packet.json'); base.validate_packet(packet)
    if remote.sha(path.parent / 'market_input.json') != base.MARKET_SHA:
        raise ValueError('Unapproved market snapshot')
    for stage in range(1, 5):
        if remote.read(path.parent / f'response_schema_stage{stage}.json') != response_schema(stage):
            raise ValueError('Prepared output schema differs')
    return m, runtime, packet, remote.read(path.parent / 'market_input.json')


def worker(spec_path):
    spec = remote.read(spec_path); target = Path(spec_path).parent
    session = bench.ProbeSession(target, spec['origin'], spec['deadline_seconds'], 2)
    outcome = {'status': 'started', 'main_model_calls': 0, 'automatic_retries': 0}
    started = time.monotonic()
    try:
        stage = current_stage(spec['body']['messages'])
        expected_header = request_header(runtime_v45(), stage)
        actual_header = {key: value for key, value in spec['body'].items() if key != 'messages'}
        if canonical(actual_header) != canonical(expected_header):
            raise ValueError('Worker body differs from exact v4.5 request controls')
        session.start_monitor()
        for phase in ('before_render', 'before_generation'):
            if Path(spec['cancel_path']).exists():
                raise StageStopped('cancelled')
            pin = bench.observe(spec['origin'], MODEL)
            remote.save(target / ('pin_' + phase + '.json'), pin)
            assert_pin(pin)
            if phase == 'before_render':
                render_call(session, spec['body'])
        response = remote.stream_call(session, '/api/chat', spec['body'], 'generation')
        if (response.get('model') != MODEL or response.get('message', {}).get('thinking')
                or response.get('message', {}).get('tool_calls')):
            raise RuntimeError('Unexpected model/thinking/tool response; raw retained')
        if response.get('done_reason') not in ('stop', 'length'):
            raise RuntimeError('Unrecognized completion reason; raw retained')
        if response['done_reason'] == 'stop':
            validation = validate_response(response.get('message', {}).get('content'), stage, SOURCE)
            remote.save(target / 'response_contract_validation.json', validation)
            if not validation['valid']:
                raise ValueError('Response violates the declared structural contract; raw retained, no retry')
        outcome['status'] = 'output_limit_reached' if response['done_reason'] == 'length' else 'completed'
    except BaseException as exc:
        outcome.update(status='cancelled' if isinstance(exc, KeyboardInterrupt) else getattr(exc, 'status', 'failed'),
                       error_type=type(exc).__name__, error=str(exc))
    finally:
        session.stop_monitor()
        render_result = remote.read(target / 'render_only/result.json') if (target / 'render_only/result.json').is_file() else {}
        outcome.update(elapsed_seconds=time.monotonic() - started, calls=session.calls,
                       render_requests_attempted=int((target / 'render_only/request.json').is_file()),
                       generation_requests_attempted=len(session.calls),
                       pilot_model_calls=len(session.calls),
                       unexpected_generation_evidence_in_render=render_result.get('unexpected_generation_evidence', False),
                       http_streams_completed=sum(x['status'] == 'completed' for x in session.calls))
        remote.save(target / 'worker_summary.json', outcome)
    return 0 if outcome['status'] == 'completed' else 1


def supervise(spec_path, deadline, cancel_path):
    target = Path(spec_path).parent; started = time.monotonic(); stopped = None
    with (target / 'worker.console.log').open('xb') as log:
        process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()),
                                    '--worker', str(spec_path)], stdout=log, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL)
        try:
            while process.poll() is None:
                remaining = deadline - (time.monotonic() - started)
                if Path(cancel_path).exists(): stopped = 'cancelled'; break
                if remaining <= 0: stopped = 'hard_deadline'; break
                time.sleep(min(.05, remaining))
        except KeyboardInterrupt:
            stopped = 'cancelled'
        if stopped:
            process.kill(); process.wait(timeout=3)
        else:
            process.wait()
    result = dict(status=stopped or 'worker_exited', worker_exit_code=process.returncode,
                  elapsed_seconds=time.monotonic() - started, deadline_seconds=deadline,
                  deadline_scope='Child setup, metadata, render-only and generation combined. Cleanup is outside; OS scheduling/kill overhead may add to elapsed time.',
                  automatic_retries=0)
    if (target / 'worker_summary.json').is_file():
        result['worker'] = remote.read(target / 'worker_summary.json')
    remote.save(target / 'supervisor_result.json', result)
    return result


def run(args):
    manifest_path = Path(args.manifest).resolve()
    manifest, runtime, packet, market = verify_manifest(manifest_path)
    origin = remote.validate_origin(args.base_url)
    server_log = Path(args.server_log).resolve()
    if not server_log.is_file():
        raise ValueError('Existing owned service log required for contemporaneous archival')
    target = remote.new_output(args.output_root, 'single_case_v45', args.run_id)
    frozen_manifest_sha = remote.sha(manifest_path)
    started = time.monotonic(); stages = []
    summary = dict(status='not_started', protocol_version='4.5', case_id=CASE, planned_cases=1,
                   planned_stages=4, main_model_calls=0, automatic_retries=0,
                   human_semantic_pass=False, main_freeze=False)
    remote.save(target / 'manifest_snapshot.json', manifest)
    remote.save(target / 'runtime.json', runtime)
    remote.save(target / 'invocation.json', dict(started_at_utc=remote.now(), origin=origin,
        manifest_path=str(manifest_path), manifest_sha256=remote.sha(manifest_path),
        case_id=CASE, source_id=SOURCE, arm='R1', conditions=manifest['controls'],
        server_log=str(server_log), purpose='one_predetermined_four_stage_pilot_not_main'))
    previous = []

    def adapter(messages):
        stage = len(stages) + 1
        if (target / 'CANCEL').exists():
            raise StageStopped('cancelled')
        if remote.sha(manifest_path) != frozen_manifest_sha:
            raise ValueError('Preparation manifest changed during the case')
        verify_manifest(manifest_path)
        body = prepare_body(messages, runtime)
        if previous and body['messages'][:len(previous)] != previous:
            raise ValueError('Previously transmitted history changed')
        previous[:] = copy.deepcopy(body['messages'])
        stage_dir = target / ('stage%d_transport' % stage); stage_dir.mkdir()
        stages.append(stage_dir)
        remote.save(stage_dir / 'logical_messages.json', messages)
        remote.save(stage_dir / 'grounded_messages.json', ground_messages(messages))
        remote.save(stage_dir / 'response_schema.json', response_schema(stage))
        remote.save(stage_dir / 'authoritative_body.json', body)
        (stage_dir / 'authoritative_body.bin').write_bytes(json.dumps(body, ensure_ascii=False, allow_nan=False).encode())
        remote.save(stage_dir / 'projection_validation.json', dict(status='original_values_preserved_plus_declared_schema_grounding',
            projection=PROJECTION_VERSION, grounding_version=GROUNDING_VERSION,
            original_task_market_document_values_preserved=True,
            grounded_sha256=value_sha(ground_messages(messages)), later_message_strings_verbatim=True,
            logical_sha256=value_sha(messages), transmitted_sha256=value_sha(body['messages'])))
        before = server_log.read_bytes()
        remote.save(stage_dir / 'server_log_before.json', {'path': str(server_log), 'bytes': len(before),
                                                        'sha256': hashlib.sha256(before).hexdigest()})
        spec_path = stage_dir / 'worker_spec.json'
        remote.save(spec_path, dict(origin=origin, body=body, deadline_seconds=runtime['deadline_seconds'],
                                   cancel_path=str(target / 'CANCEL')))
        try:
            result = supervise(spec_path, runtime['deadline_seconds'], target / 'CANCEL')
        finally:
            clean = bench.unload_and_confirm(origin, MODEL)
            remote.save(stage_dir / 'unload_and_residency.json', clean)
            after = server_log.read_bytes()
            (stage_dir / 'server_log_after_snapshot.bin').write_bytes(after)
            remote.save(stage_dir / 'server_log_delta.json', dict(original_prefix_retained=after.startswith(before),
                         prior_bytes=len(before), after_bytes=len(after), sha256=hashlib.sha256(after).hexdigest()))
        if clean['status'] != 'no_resident_models_observed':
            raise RuntimeError('Model unload/idle was not confirmed; no subsequent stage')
        if result['status'] != 'worker_exited':
            raise StageStopped(result['status'])
        if result.get('worker', {}).get('status') == 'cancelled':
            raise StageStopped('cancelled')
        if result.get('worker', {}).get('status') not in ('completed', 'output_limit_reached'):
            raise RuntimeError('Stage failed: ' + str(result.get('worker', {})))
        return remote.read(stage_dir / 'http_0001_generation/response.json')

    try:
        state = remote.api_json(origin, '/api/ps')
        remote.save(target / 'residency_before.json', state)
        if state.get('models') != []:
            raise ValueError('Existing model residency/workload must be resolved by the operator')
        observed = bench.observe(origin, MODEL)
        remote.save(target / 'initial_pin.json', observed); assert_pin(observed)
        summary['status'] = 'attempted'
        workflow.run_case(packet, 'R1', market, adapter, target / CASE,
                          history_policy=workflow.EXPLICIT_HISTORY)
        summary['status'] = 'completed_four_stages'
    except BaseException as exc:
        summary.update(status='cancelled' if isinstance(exc, KeyboardInterrupt) else getattr(exc, 'status', 'failed'),
                       error_type=type(exc).__name__, error=str(exc))
        remote.save(target / 'run_failure.json', {'type': type(exc).__name__, 'message': str(exc),
                    'handling': 'Retained attempted case; no retry and no substitute case.'})
    finally:
        summary.update(finished_at_utc=remote.now(), wall_seconds=time.monotonic() - started,
            render_requests_attempted=sum((p / 'render_only/request.json').is_file() for p in stages),
            generation_requests_attempted=sum((p / 'http_0001_generation/request.json').is_file() for p in stages),
            pilot_model_calls=sum((p / 'http_0001_generation/request.json').is_file() for p in stages),
            http_streams_completed=sum(remote.read(p / 'http_0001_generation/result.json').get('status') == 'completed'
                for p in stages if (p / 'http_0001_generation/result.json').is_file()),
            unexpected_generation_evidence_in_render=sum(bool(remote.read(p / 'render_only/result.json').get('unexpected_generation_evidence'))
                for p in stages if (p / 'render_only/result.json').is_file()),
            stage_transports_entered=len(stages),
            completed_workflow_stages=sum((target / CASE / f'stage{n}_record.json').is_file() for n in range(1, 5)),
            generation_stages_not_started=[n for n in range(1, 5) if not
                (target / f'stage{n}_transport/http_0001_generation/request.json').is_file()],
            stage_records=[{'stage': n, 'workflow_record_present': (target / CASE / f'stage{n}_record.json').is_file(),
                'generation_request_recorded': (target / f'stage{n}_transport/http_0001_generation/request.json').is_file()}
                for n in range(1, 5)])
        summary['cases_with_generation_attempt'] = int(summary['generation_requests_attempted'] > 0
                                                       or summary['unexpected_generation_evidence_in_render'] > 0)
        summary['completed_cases'] = int(summary['status'] == 'completed_four_stages')
        summary['structure_validated_stages'] = [n for n in range(1, 5) if
            (target / f'stage{n}_transport/response_contract_validation.json').is_file()
            and remote.read(target / f'stage{n}_transport/response_contract_validation.json').get('valid') is True]
        final_record = target / CASE / 'stage4_record.json'
        summary['final_allocation_valid'] = (remote.read(final_record)['calculator_result']['allocation']['valid']
            if final_record.is_file() else None)
        summary['completion_scope'] = 'Four stopped responses satisfying the structural contract; financial feasibility and semantic accuracy are separate.'
        summary['semantic_validity_assessed'] = False
        summary['replaces_prior_v44_failure'] = False
        remote.save(target / 'summary.json', summary)
    print(json.dumps({'output': str(target), **summary}, ensure_ascii=False), flush=True)
    return 0 if summary['status'] == 'completed_four_stages' else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest='command')
    prep = sub.add_parser('prepare')
    prep.add_argument('--output', type=Path, required=True)
    prep.add_argument('--conditions-evidence', type=Path, required=True)
    prep.add_argument('--schema-evidence', type=Path, required=True)
    run_parser = sub.add_parser('run')
    run_parser.add_argument('--manifest', type=Path, required=True)
    run_parser.add_argument('--base-url', default='http://127.0.0.1:11434')
    run_parser.add_argument('--server-log', type=Path, required=True)
    run_parser.add_argument('--output-root', type=Path, default=ROOT / 'data/local_sector_runtime')
    run_parser.add_argument('--run-id', required=True)
    args = parser.parse_args(argv)
    if args.worker is not None:
        return worker(args.worker)
    if args.command == 'prepare': return prepare(args)
    if args.command == 'run': return run(args)
    parser.error('Choose prepare or explicit run')


if __name__ == '__main__':
    raise SystemExit(main())
