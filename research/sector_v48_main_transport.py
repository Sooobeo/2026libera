"""One gate-bound main-study v4.8 transport call; no semantic scoring.

Only ``--worker`` or an explicit ``run_transport``/``supervise`` call reaches HTTP.
Metadata, render-only, generation and unload are counted separately. There are no
warmup generations, retries, model substitutions, repairs or authorization-record creation. The main coordinator and this worker both verify
the separate immutable main execution gate before any HTTP.
The coordinator owns case/stage/repair budgets and supplies the visible contract.
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
from sector_v48_main_gate import verify_main_gate
from sector_v48_contract import build_system, evaluate_proposal, repair_eligible
from compact_sector_prompt import compact_stage_content, restore_market
from sector_response_schema import SCHEMA_VERSION, response_schema, validate_response

remote, bench = base.remote, base.bench
MODEL, DIGEST, TEMPLATE, ENGINE = base.MODEL, base.DIGEST, base.TEMPLATE, base.ENGINE
OPTIONS = base.OPTIONS.copy()
canonical, assert_pin = base.canonical, base.assert_pin
RENDERER_POLICY_ID = base.RENDERER_POLICY_ID
ENDPOINTS = ('stage1', 'stage2', 'stage3', 'C0', 'C1', 'C2')


def auxiliary_payload(endpoint):
    return {'stage': 4, 'endpoint': endpoint,
        'task': 'Auxiliary arithmetic revision after the preserved primary C0. Reconsider the last submitted vector using its actual calculator feedback. Return all seven fields; retain source-grounded rationale and identify actual changes. No suggested target weights are supplied. Do not claim corrected arithmetic unless the submitted numbers support it.',
        'response_schema': response_schema(4, True), 'original_primary_retained': True,
        'maximum_additional_revisions': 2}


def validate_authored_history(spec, case, contract, registry, market):
    """Rebuild the request from frozen task previews and literal prior responses.

    This is input/sequence consistency, not a semantic verdict or identity check.
    No hidden annotation, target vector, normalization or new model call is used.
    """
    prepared = Path(spec['execution_context']['manifest_path']).resolve().parent
    target = Path(spec['target_path']).resolve(); current = target.name
    packet = remote.read(prepared / 'packets' / (case['source_id'] + '.json'))
    messages = [{'role': 'system', 'content': build_system(contract)}]
    visible_ids = {r['fact_id'] for r in registry['rows'] + registry['matrix_fact_references']}
    previous_weights = None; prior = None
    for endpoint in ENDPOINTS[:ENDPOINTS.index(current) + 1]:
        stage = int(endpoint[-1]) if endpoint.startswith('stage') else 4
        visible = case['arm'] == 'R1' or stage == 4
        if visible: visible_ids.update(row['evidence_id'] for row in packet['evidence_passages'])
        if endpoint in ('C1', 'C2'):
            if prior is None or not repair_eligible(prior)['eligible']:
                raise ValueError('Auxiliary request lacks eligible retained predecessor')
            payload = auxiliary_payload(endpoint)
        else:
            payload = remote.read(prepared / 'previews' / case['case_id'] / f'stage{stage}_payload.json')
        if not visible and 'institution_document' in payload:
            raise ValueError('Assigned institution must remain absent from pre-R4 authored task')
        current_text = compact_stage_content(canonical(payload)) if endpoint == 'stage1' else canonical(payload)
        if endpoint == 'stage1':
            restored = json.loads(current_text); restored['common_market'] = restore_market(restored['common_market'])
            if canonical(restored) != canonical(payload):
                raise ValueError('Compact market changed frozen preview values')
        messages.append({'role': 'user', 'content': current_text})
        if endpoint == current: break
        folder = target.parent / endpoint
        record = remote.read(folder / 'record.json')
        response = remote.read(folder / 'http_0001_generation/response.json')
        raw = response.get('message', {}).get('content')
        valid = validate_response(raw, stage, case['source_id'] if visible else None, visible)
        if (response.get('done_reason') != 'stop' or not isinstance(raw, str) or not valid['valid']
                or record.get('transport_status') != 'completed' or record.get('response_complete') is not True
                or record.get('raw_response_text') != raw or record.get('schema_validation') != valid):
            raise ValueError('Prior endpoint is incomplete or differs from retained raw response')
        prior = json.loads(raw); canonical(prior)
        feedback = evaluate_proposal(prior, stage, market, sorted(visible_ids), endpoint, previous_weights)
        if canonical(record.get('feedback')) != canonical(feedback):
            raise ValueError('Prior feedback differs from arithmetic of actual raw proposal')
        prior_request = remote.read(folder / 'http_0001_generation/request.json')
        expected_prior = request_header(spec['runtime'], stage, visible)
        expected_prior['messages'] = copy.deepcopy(messages)
        if canonical(prior_request.get('body')) != canonical(expected_prior):
            raise ValueError('Prior request differs from frozen task and literal response history')
        messages.extend([{'role': 'assistant', 'content': raw},
                         {'role': 'user', 'content': canonical({'calculator_feedback': feedback})}])
        visible_ids.update(row['fact_id'] for row in feedback.get('facts', []))
        previous_weights = copy.deepcopy(prior.get('weights'))
    if spec['body'].get('messages') != messages:
        raise ValueError('Worker messages differ from frozen tasks and full retained raw history')
    return {'status': 'frozen_tasks_and_literal_prior_history_match', 'endpoint': current,
            'message_count': len(messages), 'auxiliary_predecessor_checked': current in ('C1', 'C2')}


def runtime_v48():
    value = base.runtime_v44()
    value.pop('format')
    value.update(protocol_version='4.8', format_mode='per_stage_json_schema',
                 response_schema_version=SCHEMA_VERSION)
    return value


def validate_runtime(runtime):
    if canonical(runtime) != canonical(runtime_v48()):
        raise ValueError('Exact declared v4.8 runtime required; no fallback')


def request_header(runtime, stage, institution_visible):
    validate_runtime(runtime)
    if type(institution_visible) is not bool:
        raise ValueError('Institution visibility must be an explicit boolean')
    header = {k: copy.deepcopy(runtime[k]) for k in
              ('model', 'think', 'truncate', 'shift', 'stream', 'keep_alive', 'options')}
    header['format'] = response_schema(stage, institution_visible)
    return header


def validate_execution_context(spec):
    context = spec.get('execution_context')
    if not isinstance(context, dict) or set(context) != {'manifest_path', 'gate_path', 'run_root'}:
        raise ValueError('Explicit main execution gate context required')
    manifest, runtime, contract, registry, market, gate, human, authorization = verify_main_gate(
        Path(context['manifest_path']), Path(context['gate_path']))
    run_root = Path(context['run_root']).resolve()
    if run_root != Path(gate['authorized_run_root']).resolve():
        raise ValueError('Transport run root differs from explicit authorization')
    target = Path(spec['target_path']).resolve()
    try: parts = target.relative_to(run_root).parts
    except ValueError: raise ValueError('Transport target must stay within authorized run root')
    roster = {c['case_id']: c for c in manifest['roster']}
    if len(parts) != 2 or parts[0] not in roster or parts[1] not in ('stage1', 'stage2', 'stage3', 'C0', 'C1', 'C2'):
        raise ValueError('Transport target must be a fixed main case endpoint')
    stage = int(parts[1][-1]) if parts[1].startswith('stage') else 4
    case = roster[parts[0]]
    visible = case['arm'] == 'R1' or stage == 4
    if (spec['stage'] != stage or spec['institution_visible'] is not visible
            or spec['expected_source_id'] != (case['source_id'] if visible else None)):
        raise ValueError('Transport exposure/source differs from main case endpoint')
    if canonical(runtime) != canonical(spec['runtime']):
        raise ValueError('Transport runtime differs from frozen main inputs')
    if spec['expected_system'] != build_system(contract):
        raise ValueError('Transport system differs from frozen main contract')
    history = validate_authored_history(spec, case, contract, registry, market)
    return {'scope': 'main', 'gate_path': str(Path(context['gate_path']).resolve()),
            'case_id': parts[0], 'endpoint': parts[1], 'reviewer_identity_authenticated': False,
            'history_validation': history}


def validate_spec(spec):
    execution = validate_execution_context(spec)
    validate_runtime(spec['runtime'])
    remote.validate_origin(spec['origin'])
    if spec['deadline_seconds'] != spec['runtime']['deadline_seconds']:
        raise ValueError('Worker deadline differs from declared runtime')
    visible = spec['institution_visible']
    expected_source = spec['expected_source_id']
    if (type(visible) is not bool or (not visible and expected_source is not None)
            or (visible and (not isinstance(expected_source, str) or not expected_source))):
        raise ValueError('Expected source metadata must be absent before exposure')
    body = spec['body']
    if not isinstance(body, dict) or canonical({k: v for k, v in body.items() if k != 'messages'}) != canonical(
            request_header(spec['runtime'], spec['stage'], visible)):
        raise ValueError('Body differs from exact v4.8 API controls or visible schema')
    messages = body.get('messages')
    system = spec['expected_system']
    if not isinstance(system, str) or not system or not isinstance(messages, list) or len(messages) < 2:
        raise ValueError('Explicit nonempty system and message history required')
    if messages[0] != {'role': 'system', 'content': system}:
        raise ValueError('System differs from the coordinator-declared prompt')
    for index, msg in enumerate(messages):
        if (not isinstance(msg, dict) or set(msg) != {'role', 'content'}
                or not isinstance(msg['content'], str)
                or msg['role'] not in (('system',) if index == 0 else ('user', 'assistant'))):
            raise ValueError('Only explicit role/content history is allowed')
        if index and not isinstance(json.loads(msg['content']), dict):
            raise ValueError('Non-system history must contain complete JSON objects')
    if messages[-1]['role'] != 'user':
        raise ValueError('Current instruction must be a user JSON message')
    return {'status': 'validated', 'execution': execution, 'stage': spec['stage'], 'institution_visible': visible,
            'expected_source_id': expected_source, 'system_utf8_sha256': hashlib.sha256(system.encode()).hexdigest(),
            'body_value_sha256': base.value_sha(body), 'semantic_assessment': False}


def validate_render(response, messages, expected_system):
    """Inherited JSON-boundary renderer policy, generalized to a pinned system."""
    info = response.get('_debug_info')
    rendered = info.get('rendered_template') if isinstance(info, dict) else None
    if (response.get('model') != MODEL or not isinstance(rendered, str) or not rendered
            or info.get('image_count', 0) != 0 or response.get('eval_count', 0) != 0
            or response.get('prompt_eval_count', 0) != 0
            or response.get('message', {}).get('content')
            or response.get('message', {}).get('thinking')
            or response.get('message', {}).get('tool_calls')):
        raise ValueError('Render-only evidence missing or unexpected generation; no next generation')
    position, evidence = 0, []
    for index, msg in enumerate(messages):
        raw_content = msg['content']
        if index == 0:
            if raw_content != expected_system or msg['role'] != 'system':
                raise ValueError('Unexpected system content')
            expected, prefix, suffix, preserved = raw_content, '', '', None
        else:
            expected = raw_content.strip(' \t\r\n')
            left = len(raw_content) - len(raw_content.lstrip(' \t\r\n'))
            right = len(raw_content.rstrip(' \t\r\n'))
            prefix, suffix = raw_content[:left], raw_content[right:]
            raw_value, expected_value = json.loads(raw_content), json.loads(expected)
            preserved = isinstance(raw_value, dict) and canonical(raw_value) == canonical(expected_value)
            if not preserved:
                raise ValueError('Only exact JSON-object values and outer ASCII whitespace are allowed')
        start = rendered.find(expected, position)
        if start < 0:
            raise ValueError(f'Rendered history omitted or changed message {index}')
        position = start + len(expected)
        evidence.append({'message_index': index, 'role': msg['role'], 'start_character': start,
                         'end_character': position,
                         'raw_content_utf8_sha256': hashlib.sha256(raw_content.encode()).hexdigest(),
                         'expected_renderer_content_utf8_sha256': hashlib.sha256(expected.encode()).hexdigest(),
                         'removed_outer_prefix': prefix, 'removed_outer_suffix': suffix,
                         'strict_json_payload_value_preservation': preserved, 'http_content_modified': False})
    return {'status': 'all_expected_renderer_contents_present_in_order',
            'renderer_policy': RENDERER_POLICY_ID, 'renderer_policy_sha256': base.RENDERER_POLICY_SHA,
            'message_count': len(messages), 'message_spans': evidence,
            'rendered_utf8_sha256': hashlib.sha256(rendered.encode()).hexdigest(),
            'exact_token_count': None,
            'scope': 'Observed rendering with truncate=false/shift=false; not independent tokenization or proof of spare capacity.'}


def render_call(session, body, expected_system):
    target = session.target / 'render_only'
    target.mkdir()
    request = copy.deepcopy(body)
    request.update(stream=False, _debug_render_only=True)
    remote.save(target / 'request.json', {'path': '/api/chat', 'body': request,
                                        'purpose': 'render_only_not_generation'})
    payload = json.dumps(request, ensure_ascii=False, allow_nan=False).encode()
    (target / 'request_body.bin').write_bytes(payload)
    conn = remote.connect(session.origin, session.timeout_seconds)
    result = {'status': 'attempted', 'generation_requests': 0}
    started = time.monotonic()
    try:
        conn.request('POST', '/api/chat', payload, {'Content-Type': 'application/json'})
        response = conn.getresponse()
        result['http_status'] = response.status
        chunks = []
        with (target / 'response_body.bin').open('xb') as handle:
            while chunk := response.read1(65536):
                handle.write(chunk); handle.flush(); chunks.append(chunk)
        raw = json.loads(b''.join(chunks))
        remote.save(target / 'response.json', raw)
        result['unexpected_generation_evidence'] = bool(raw.get('eval_count', 0)
            or raw.get('message', {}).get('content') or raw.get('message', {}).get('thinking')
            or raw.get('message', {}).get('tool_calls'))
        if not 200 <= response.status < 300 or raw.get('error'):
            raise RuntimeError('Render-only request failed: ' + str(raw.get('error', response.status)))
        remote.save(target / 'validation.json', validate_render(raw, body['messages'], expected_system))
        (target / 'rendered_prompt.txt').write_bytes(raw['_debug_info']['rendered_template'].encode('utf-8'))
        result['status'] = 'validated'
    except BaseException as exc:
        result.update(status='failed', error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        conn.close()
        result['wall_seconds'] = time.monotonic() - started
        remote.save(target / 'result.json', result)


def call_accounting(target):
    """Read durable envelopes even if the supervised child was killed mid-stream."""
    target = Path(target)
    generation = target / 'http_0001_generation'
    result_path = generation / 'result.json'
    render_path = target / 'render_only/result.json'
    artifact_errors = {}
    def recorded(path):
        if not path.is_file(): return {}
        try:
            value = remote.read(path)
            if not isinstance(value, dict): raise ValueError('Expected artifact object')
            return value
        except (OSError, ValueError) as exc:
            artifact_errors[path.relative_to(target).as_posix()] = {'type': type(exc).__name__, 'message': str(exc)}
            return {}
    result, render = recorded(result_path), recorded(render_path)
    return {'render_requests_attempted': int((target / 'render_only/request.json').is_file()),
            'generation_requests_attempted': int((generation / 'request.json').is_file()),
            'main_model_calls': int((generation / 'request.json').is_file()),
            'execution_scope': 'main',
            'http_streams_completed': int(result.get('status') == 'completed'),
            'unexpected_generation_evidence_in_render': render.get('unexpected_generation_evidence', False),
            'request_count_scope': 'Durable request envelopes, including requests that may fail before provider inference.',
            'raw_stream_present': (generation / 'raw_stream.bin').is_file(),
            'accounting_artifact_errors': artifact_errors}


def worker(spec_path):
    spec = remote.read(spec_path)
    target = Path(spec_path).resolve().parent
    if target != Path(spec['target_path']).resolve():
        raise ValueError('Worker spec moved outside declared endpoint')
    session = bench.ProbeSession(target, spec['origin'], spec['deadline_seconds'], 2)
    started = time.monotonic()
    outcome = {'status': 'started', 'failure_class': None, 'main_model_calls': 0,
               'automatic_retries': 0, 'warmup_generation_calls': 0,
               'system_integrity_incident': False, 'execution_scope': 'main',
               'main_model_calls_scope': 'Durable main generation request envelopes; excludes metadata/render-only/unload.'}
    phase = 'preflight'
    def record_phase(value):
        with (target / 'worker_phases.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps({'phase': value, 'at_utc': remote.now()}) + '\n')
            handle.flush()
    try:
        record_phase(phase)
        remote.save(target / 'spec_validation.json', validate_spec(spec))
        session.start_monitor()
        for phase in ('before_render', 'before_generation'):
            record_phase(phase)
            if Path(spec['cancel_path']).exists():
                raise base.StageStopped('cancelled')
            pin = bench.observe(spec['origin'], MODEL)
            remote.save(target / ('pin_' + phase + '.json'), pin)
            assert_pin(pin)
            if phase == 'before_render':
                phase = 'render'
                record_phase(phase)
                render_call(session, spec['body'], spec['expected_system'])
        phase = 'generation'
        record_phase(phase)
        response = remote.stream_call(session, '/api/chat', spec['body'], 'generation')
        if (response.get('model') != MODEL or response.get('message', {}).get('thinking')
                or response.get('message', {}).get('tool_calls')):
            raise RuntimeError('Unexpected model/thinking/tool response; raw retained')
        if response.get('done_reason') not in ('stop', 'length'):
            raise RuntimeError('Unrecognized completion reason; raw retained')
        if response['done_reason'] == 'length':
            outcome.update(status='output_limit_reached', failure_class='model_output_truncation')
        else:
            phase = 'contract'
            record_phase(phase)
            validation = validate_response(response.get('message', {}).get('content'),
                spec['stage'], spec['expected_source_id'], spec['institution_visible'])
            remote.save(target / 'response_contract_validation.json', validation)
            outcome.update(status='completed' if validation['valid'] else 'model_contract_failure',
                           failure_class=None if validation['valid'] else 'model_contract_failure')
    except BaseException as exc:
        cancelled = isinstance(exc, (KeyboardInterrupt, remote.Cancelled)) or getattr(exc, 'status', None) == 'cancelled'
        remote_status = exc.result.get('status') if isinstance(exc, remote.RemoteCallError) else None
        cancelled = cancelled or remote_status == 'cancelled'
        case_timeout = phase == 'generation' and remote_status == 'timeout'
        outcome.update(status='cancelled' if cancelled else 'case_timeout' if case_timeout else 'failed',
                       failure_class='operator_cancelled' if cancelled else 'generation_timeout' if case_timeout else 'execution_or_instrument_failure',
                       system_integrity_incident=not (cancelled or case_timeout),
                       failure_phase=phase, error_type=type(exc).__name__, error=str(exc))
    finally:
        session.stop_monitor()
        outcome.update(elapsed_seconds=time.monotonic() - started, calls=session.calls,
                       **call_accounting(target))
        remote.save(target / 'worker_summary.json', outcome)
    return 0 if outcome['status'] == 'completed' else 1


def supervise(spec_path, deadline, cancel_path):
    spec_path = Path(spec_path)
    target = spec_path.parent
    spec = remote.read(spec_path)
    if target.resolve() != Path(spec['target_path']).resolve():
        raise ValueError('Supervisor spec moved outside declared endpoint')
    validate_spec(spec)
    if (deadline != spec['deadline_seconds'] or deadline != runtime_v48()['deadline_seconds']
            or Path(cancel_path).resolve() != Path(spec['cancel_path']).resolve()):
        raise ValueError('Supervisor deadline/cancellation must match declared worker spec')
    started = time.monotonic()
    stopped = None
    with (target / 'worker.console.log').open('xb') as log:
        process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--worker', str(spec_path)],
            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == 'win32' else 0)
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
    result = {'status': stopped or 'worker_exited', 'worker_exit_code': process.returncode,
              'elapsed_seconds': time.monotonic() - started, 'deadline_seconds': deadline,
              'deadline_scope': 'Child setup, metadata, rendering and generation combined; cleanup and OS kill/scheduling overhead are outside.',
              'automatic_retries': 0, **call_accounting(target)}
    if (target / 'worker_summary.json').is_file():
        try:
            worker_summary = remote.read(target / 'worker_summary.json')
            if not isinstance(worker_summary, dict):
                raise ValueError('Expected worker summary object')
            result['worker'] = worker_summary
        except (OSError, ValueError) as exc:
            # A kill can interrupt the final JSON write. Keep the supervisor's
            # cancellation/deadline decision authoritative and retain the bytes.
            # An un-interrupted exit with no usable summary remains an incident.
            result['worker_summary_read_error'] = {'type': type(exc).__name__, 'message': str(exc)}
    phases = target / 'worker_phases.jsonl'
    if phases.is_file():
        complete_phases = []
        for line in phases.read_text(encoding='utf-8').splitlines():
            try: complete_phases.append(json.loads(line))
            except ValueError: break
        result['failure_phase_last_observed'] = complete_phases[-1]['phase'] if complete_phases else None
    remote.save(target / 'supervisor_result.json', result)
    return result


def run_transport(*, body, target, runtime, stage, institution_visible, expected_source_id,
                  expected_system, origin, cancel_path, server_log, execution_context):
    """Return outcome plus saved raw response, including model-contract failures.

    ``target`` may already hold coordinator-only records, but transport artifact
    filenames must be new. The coordinator must inspect statuses;
    this helper does not authorize another stage, another case or a repair.
    """
    target, server_log = Path(target), Path(server_log)
    if not server_log.is_file():
        raise ValueError('Existing owned server log is required')
    spec = dict(execution_context=copy.deepcopy(execution_context), target_path=str(target.resolve()),
                origin=remote.validate_origin(origin), body=body, runtime=runtime, stage=stage,
                institution_visible=institution_visible, expected_source_id=expected_source_id,
                expected_system=expected_system, cancel_path=str(Path(cancel_path).resolve()),
                deadline_seconds=runtime['deadline_seconds'])
    validate_spec(spec)
    target.mkdir(exist_ok=True)
    remote.save(target / 'authoritative_body.json', body)
    (target / 'authoritative_body.bin').write_bytes(json.dumps(body, ensure_ascii=False, allow_nan=False).encode())
    remote.save(target / 'worker_spec.json', spec)
    before = server_log.read_bytes()
    remote.save(target / 'server_log_before.json', {'path': str(server_log.resolve()), 'bytes': len(before),
                                                  'sha256': hashlib.sha256(before).hexdigest()})
    result, clean, preservation_error = None, None, None
    try:
        result = supervise(target / 'worker_spec.json', runtime['deadline_seconds'], cancel_path)
    except BaseException as exc:
        result = {'status': 'cancelled' if isinstance(exc, KeyboardInterrupt) else 'supervisor_failed',
                  'failure_class': 'execution_or_instrument_failure',
                  'error_type': type(exc).__name__, 'error': str(exc), **call_accounting(target)}
    finally:
        try:
            clean = bench.unload_and_confirm(origin, MODEL)
        except Exception as exc:
            clean = {'status': 'idle_not_confirmed', 'error_type': type(exc).__name__, 'error': str(exc)}
        try:
            remote.save(target / 'unload_and_residency.json', clean)
            after = server_log.read_bytes()
            (target / 'server_log_after_snapshot.bin').write_bytes(after)
            remote.save(target / 'server_log_delta.json', {'original_prefix_retained': after.startswith(before),
                'prior_bytes': len(before), 'after_bytes': len(after), 'sha256': hashlib.sha256(after).hexdigest()})
        except Exception as exc:
            preservation_error = {'error_type': type(exc).__name__, 'error': str(exc)}
    response_path = target / 'http_0001_generation/response.json'
    status = result.get('worker', {}).get('status', 'worker_summary_missing') if result['status'] == 'worker_exited' else result['status']
    if clean['status'] != 'no_resident_models_observed':
        status = 'cleanup_not_confirmed'
    response = None
    interrupted_response_artifact = False
    if response_path.is_file():
        try:
            response = remote.read(response_path)
        except (OSError, ValueError) as exc:
            interrupted_response_artifact = preservation_error is None and status in ('cancelled', 'hard_deadline', 'case_timeout')
            error = {'error_type': type(exc).__name__, 'error': str(exc)}
            if preservation_error is not None:
                error['prior_preservation_error'] = preservation_error
            preservation_error = error
    if preservation_error is not None and not interrupted_response_artifact:
        status = 'artifact_preservation_failure'
    if status in ('completed', 'model_contract_failure', 'output_limit_reached', 'case_timeout', 'cancelled'):
        incident = bool(result.get('worker', {}).get('system_integrity_incident', False))
    elif status == 'hard_deadline':
        incident = result.get('failure_phase_last_observed') != 'generation'
    else:
        incident = True
    return {'status': status, 'response': response,
            'supervisor': result, 'cleanup': clean,
            'system_integrity_incident': incident,
            'artifact_preservation_error': preservation_error,
            'response_artifact_unreadable_after_interruption': interrupted_response_artifact,
            'response_path': str(response_path) if response_path.is_file() else None,
            'assembled_text_path': str(target / 'http_0001_generation/assembled_text.json')
                if (target / 'http_0001_generation/assembled_text.json').is_file() else None,
            **call_accounting(target)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, required=True)
    args = parser.parse_args()
    return worker(args.worker)


if __name__ == '__main__':
    raise SystemExit(main())
