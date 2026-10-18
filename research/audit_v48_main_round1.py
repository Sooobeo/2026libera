"""Offline audit of a gate-bound v4.8 main bundle; never invokes a model.

Audit PASS concerns the instrument, retained records and prescribed case policy.
It does not require correct arithmetic or reasoning, and never supplies a human
semantic pass or authorizes main execution. Every scheduled case stays visible.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import run_sector_v48_main as runner
from sector_v48_contract import build_system, stage_payload, evaluate_proposal, repair_eligible
from sector_response_schema import response_schema, validate_response
from sector_engine import parse_response
from compact_sector_prompt import compact_stage_content

ROOT = Path(__file__).resolve().parents[1]
ENDPOINTS = ('stage1', 'stage2', 'stage3', 'C0', 'C1', 'C2')
CORE = ENDPOINTS[:4]
EVALUATOR_MATERIAL_KEYS = {'reference_annotations', 'source_verification', 'design_handoff',
                         'evaluation_protocol', 'review_template', 'source_comparison'}


def sha_bytes(value): return hashlib.sha256(value).hexdigest()
def canonical(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
def same(left, right):
    try: return canonical(left) == canonical(right)
    except (ValueError, TypeError, OverflowError): return False
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def label(path):
    path = Path(path).resolve()
    try: return path.relative_to(ROOT).as_posix()
    except ValueError: return str(path)
def reference(path):
    path = Path(path)
    return {'path': label(path), 'sha256': sha_bytes(path.read_bytes()), 'size_bytes': path.stat().st_size}
def inventory(folder):
    return [reference(p) for p in sorted(Path(folder).rglob('*')) if p.is_file()]


class Checks:
    def __init__(self): self.rows = []
    def check(self, name, passed, evidence=None):
        self.rows.append({'id': name, 'passed': bool(passed), 'evidence': evidence})
        return bool(passed)
    def attempt(self, name, function):
        try:
            value = function()
            self.check(name, True)
            return value
        except Exception as exc:
            self.check(name, False, {'error_type': type(exc).__name__, 'error': str(exc)})
            return None
    def json(self, path, name): return self.attempt(name, lambda: read(path))


def complete_lines(path, *, event_wrapper=False):
    """Return captured complete JSON lines and an explicit partial-tail flag."""
    if not Path(path).is_file(): return [], False
    values, partial = [], False
    lines = Path(path).read_bytes().splitlines()
    for index, line in enumerate(lines):
        if not line.strip(): continue
        try:
            value = json.loads(line)
            if event_wrapper: value = value['event']
            if not isinstance(value, dict): raise ValueError('Expected event object')
            values.append(value)
        except (ValueError, TypeError, KeyError, UnicodeError):
            if index != len(lines) - 1: raise ValueError('Malformed event before final line')
            partial = True
    return values, partial


def captured_text(folder):
    """Independently recover literal captured content; no output repair."""
    folder = Path(folder)
    for name in ('response.json', 'assembled_text.json'):
        path = folder / name
        if path.is_file():
            try:
                value = read(path)
                message = value.get('message') if name == 'response.json' else value
                if isinstance(message, dict) and isinstance(message.get('content'), str):
                    return message['content'], value if name == 'response.json' else None
            except (ValueError, AttributeError, OSError): pass
    events, _ = complete_lines(folder / 'events.jsonl', event_wrapper=True)
    parts = []
    for event in events:
        message = event.get('message', {})
        if not isinstance(message, dict): break
        part = message.get('content', '')
        if not isinstance(part, str): break
        parts.append(part)
    return ''.join(parts) or None, None


def audit_render(checks, folder, body, prefix):
    request = checks.json(folder / 'request.json', prefix + ':render_request')
    raw_body = checks.attempt(prefix + ':render_request_bytes', lambda: json.loads((folder / 'request_body.bin').read_bytes()))
    expected = copy.deepcopy(body); expected.update(stream=False, _debug_render_only=True)
    checks.check(prefix + ':render_exact_body', isinstance(request, dict) and request.get('path') == '/api/chat'
                 and same(request.get('body'), expected) and same(raw_body, expected))
    response = checks.json(folder / 'response.json', prefix + ':render_response')
    saved = checks.json(folder / 'validation.json', prefix + ':render_validation_record')
    result = checks.json(folder / 'result.json', prefix + ':render_result')
    if not isinstance(response, dict): return
    debug = response.get('_debug_info', {})
    rendered = debug.get('rendered_template') if isinstance(debug, dict) else None
    message = response.get('message') or {}
    checks.check(prefix + ':render_no_generation', response.get('model') == runner.transport.MODEL
                 and response.get('eval_count', 0) == 0 and response.get('prompt_eval_count', 0) == 0
                 and isinstance(debug, dict) and debug.get('image_count', 0) == 0
                 and isinstance(message, dict) and not any(message.get(k) for k in ('content', 'thinking', 'tool_calls')))
    checks.check(prefix + ':render_validated', isinstance(result, dict) and result.get('status') == 'validated'
                 and result.get('unexpected_generation_evidence') is False)
    if not checks.check(prefix + ':render_text_available', isinstance(rendered, str) and bool(rendered)): return
    position, spans = 0, []
    for index, msg in enumerate(body['messages']):
        raw = msg['content']; expected_content = raw if index == 0 else raw.strip(' \t\r\n')
        if index:
            checks.check(prefix + f':render_json_value_{index}', same(json.loads(raw), json.loads(expected_content)))
        start = rendered.find(expected_content, position)
        checks.check(prefix + f':render_message_{index}', start >= 0)
        if start < 0: continue
        position = start + len(expected_content)
        spans.append((start, position, sha_bytes(raw.encode()), sha_bytes(expected_content.encode())))
    checks.check(prefix + ':render_saved_text', (folder / 'rendered_prompt.txt').is_file()
                 and (folder / 'rendered_prompt.txt').read_bytes() == rendered.encode())
    checks.check(prefix + ':render_hash_matches', isinstance(saved, dict)
                 and saved.get('rendered_utf8_sha256') == sha_bytes(rendered.encode())
                 and saved.get('message_count') == len(body['messages']))
    if isinstance(saved, dict):
        observed = [(x.get('start_character'), x.get('end_character'), x.get('raw_content_utf8_sha256'),
                     x.get('expected_renderer_content_utf8_sha256')) for x in saved.get('message_spans', [])]
        checks.check(prefix + ':render_spans_match', observed == spans)


def audit_generation(checks, endpoint, body, runtime, prefix):
    call = endpoint / 'http_0001_generation'
    request = checks.json(call / 'request.json', prefix + ':generation_request')
    checks.check(prefix + ':exact_generation_request', isinstance(request, dict)
                 and request.get('path') == '/api/chat' and request.get('kind') == 'generation'
                 and same(request.get('body'), body))
    for phase in ('before_render', 'before_generation'):
        pin = checks.json(endpoint / ('pin_' + phase + '.json'), prefix + ':pin_' + phase)
        checks.check(prefix + ':exact_pin_' + phase, isinstance(pin, dict)
                     and pin.get('version', {}).get('version') == runtime['engine_version']
                     and pin.get('selected_model', {}).get('digest') == runtime['digest']
                     and pin.get('selected_model', {}).get('name') == runtime['model']
                     and pin.get('template_sha256') == runtime['template_sha256']
                     and isinstance(pin.get('show', {}).get('template'), str)
                     and sha_bytes(pin['show']['template'].encode()) == runtime['template_sha256'])
    audit_render(checks, endpoint / 'render_only', body, prefix)
    checks.check(prefix + ':raw_stream_preserved', (call / 'raw_stream.bin').is_file())
    events = checks.attempt(prefix + ':event_log_parse', lambda: complete_lines(call / 'events.jsonl', event_wrapper=True))
    wire = checks.attempt(prefix + ':wire_log_parse', lambda: complete_lines(call / 'raw_stream.bin'))
    call_result = None
    if (call / 'result.json').is_file():
        try: call_result = read(call / 'result.json')
        except (OSError, ValueError): pass  # A killed final write is retained, not silently repaired.
    if events is not None and wire is not None:
        e, ep = events; w, wp = wire
        completed = isinstance(call_result, dict) and call_result.get('status') == 'completed'
        checks.check(prefix + ':events_match_wire', same(e, w) if completed else same(e, w[:len(e)]),
                     {'http_completed': completed, 'event_tail_partial': ep, 'wire_tail_partial': wp})
        if completed:
            checks.check(prefix + ':complete_stream_terminal', bool(e) and e[-1].get('done') is True and not ep and not wp)
    text, response = captured_text(call)
    if response is not None:
        checks.check(prefix + ':response_model_and_mode', response.get('model') == runtime['model']
                     and not response.get('message', {}).get('thinking') and not response.get('message', {}).get('tool_calls'))
        if events is not None:
            assembled = ''.join(e.get('message', {}).get('content', '') for e in events[0])
            checks.check(prefix + ':response_matches_stream', text == assembled)
    return text, response


def auxiliary_payload(endpoint):
    return {'stage': 4, 'endpoint': endpoint,
        'task': 'Auxiliary arithmetic revision after the preserved primary C0. Reconsider the last submitted vector using its actual calculator feedback. Return all seven fields; retain source-grounded rationale and identify actual changes. No suggested target weights are supplied. Do not claim corrected arithmetic unless the submitted numbers support it.',
        'response_schema': response_schema(4, True), 'original_primary_retained': True,
        'maximum_additional_revisions': 2}


def audit_case(checks, root, case, prepared, runtime, contract, registry, market):
    folder = root / case['case_id']; prefix = case['case_id']
    if not folder.is_dir(): return {'case_id': case['case_id'], 'status': 'not_started', 'core_calls': 0, 'auxiliary_calls': 0}
    summary = checks.json(folder / 'case_summary.json', prefix + ':case_summary') or {}
    packet = read(prepared / 'packets' / (case['source_id'] + '.json'))
    case_manifest = checks.json(folder / 'case_manifest.json', prefix + ':case_manifest') or {}
    checks.check(prefix + ':case_identity', all(case_manifest.get(k) == v for k, v in case.items())
                 and case_manifest.get('primary_endpoint') == 'C0' and case_manifest.get('main_model_calls_at_case_creation') == 0)
    packet_path = prepared / 'packets' / (case['source_id'] + '.json')
    checks.check(prefix + ':public_packet_reference', case_manifest.get('packet') ==
                 {'path': label(packet_path), 'sha256': sha_bytes(packet_path.read_bytes())}
                 and 'sector_ratings' not in packet and 'evidence_index' not in packet)
    checks.check(prefix + ':case_instrument_integrity', summary.get('system_integrity_incident') is False,
                 {'observed_status': summary.get('status'), 'model_failure_is_not_check_failure': True})
    checks.check(prefix + ':case_primary_not_replaced', summary.get('primary_never_replaced') is True
                 and summary.get('automatic_retries') == 0)
    messages = [{'role': 'system', 'content': build_system(contract)}]
    visible_ids = set(runner.public_ids(registry)); facts = []; previous_weights = None
    observed_records = {}; call_counts = {'core': 0, 'auxiliary': 0}; may_continue = True
    for endpoint_id in ENDPOINTS:
        endpoint = folder / endpoint_id
        if not endpoint.is_dir(): continue
        stage = int(endpoint_id[-1]) if endpoint_id.startswith('stage') else 4
        visible = case['arm'] == 'R1' or stage == 4
        if visible: visible_ids.update(x['evidence_id'] for x in packet['evidence_passages'])
        name = prefix + '/' + endpoint_id
        checks.check(name + ':no_stage_after_failure', may_continue)
        predecessor = ENDPOINTS[ENDPOINTS.index(endpoint_id) - 1] if endpoint_id != 'stage1' else None
        checks.check(name + ':stage_order', predecessor is None or predecessor in observed_records)
        if endpoint_id in ('C1', 'C2'):
            prior = observed_records.get(predecessor, {})
            eligible = repair_eligible(prior.get('parsed_response'))
            checks.check(name + ':bounded_arithmetic_eligibility', eligible['eligible']
                         and prior.get('transport_status') == 'completed' and prior.get('schema_validation', {}).get('valid') is True)
        payload = auxiliary_payload(endpoint_id) if endpoint_id in ('C1', 'C2') else stage_payload(stage, case['arm'], packet, market, registry)
        logical = checks.json(endpoint / 'logical_payload.json', name + ':logical_payload')
        checks.check(name + ':exact_declared_task', same(logical, payload))
        current_text = compact_stage_content(canonical(payload)) if endpoint_id == 'stage1' else canonical(payload)
        messages.append({'role': 'user', 'content': current_text})
        body = checks.json(endpoint / 'authoritative_body.json', name + ':authoritative_body')
        expected = runner.transport.request_header(runtime, stage, visible); expected['messages'] = copy.deepcopy(messages)
        checks.check(name + ':full_history_and_current_task_exact', same(body, expected))
        checks.check(name + ':context_flags', isinstance(body, dict) and body.get('truncate') is False and body.get('shift') is False)
        if isinstance(body, dict):
            exact_bytes = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
            checks.check(name + ':authoritative_request_bytes', (endpoint / 'authoritative_body.bin').is_file()
                         and (endpoint / 'authoritative_body.bin').read_bytes() == exact_bytes)
        spec = checks.json(endpoint / 'worker_spec.json', name + ':worker_spec')
        checks.check(name + ':worker_visibility_and_options', isinstance(spec, dict) and same(spec.get('body'), expected)
                     and same(spec.get('runtime'), runtime) and spec.get('stage') == stage
                     and spec.get('institution_visible') is visible
                     and spec.get('expected_source_id') == (case['source_id'] if visible else None)
                     and spec.get('expected_system') == build_system(contract)
                     and spec.get('deadline_seconds') == runtime['deadline_seconds'])
        visibility = checks.json(endpoint / 'visible_evidence_before_generation.json', name + ':visibility_record')
        checks.check(name + ':only_actual_visible_ids_and_facts', isinstance(visibility, dict)
                     and visibility.get('ids') == sorted(visible_ids) and same(visibility.get('calculator_facts'), facts))
        # Inspect authored task/feedback, not model-generated guesses, for source injection.
        if not visible:
            authored = canonical(payload)
            checks.check(name + ':R4_source_not_injected', 'institution_document' not in payload
                         and not any(x['evidence_id'] in visible_ids for x in packet['evidence_passages']))
        request_path = endpoint / 'http_0001_generation/request.json'
        attempted = request_path.is_file()
        call_counts['auxiliary' if endpoint_id in ('C1', 'C2') else 'core'] += int(attempted)
        checks.check(name + ':one_generation_envelope', len(list(endpoint.glob('http_*/request.json'))) <= 1)
        raw, response = (None, None)
        if attempted and isinstance(body, dict): raw, response = audit_generation(checks, endpoint, body, runtime, name)
        cleanup = checks.json(endpoint / 'unload_and_residency.json', name + ':cleanup')
        checks.check(name + ':idle_confirmed', isinstance(cleanup, dict) and cleanup.get('status') == 'no_resident_models_observed')
        before = checks.json(endpoint / 'server_log_before.json', name + ':server_log_before')
        delta = checks.json(endpoint / 'server_log_delta.json', name + ':server_log_delta')
        log_path = endpoint / 'server_log_after_snapshot.bin'
        if isinstance(before, dict) and isinstance(delta, dict) and log_path.is_file():
            raw_log = log_path.read_bytes()
            checks.check(name + ':server_log_prefix_and_hash', delta.get('original_prefix_retained') is True
                         and delta.get('prior_bytes') == before.get('bytes') and delta.get('after_bytes') == len(raw_log)
                         and delta.get('sha256') == sha_bytes(raw_log)
                         and sha_bytes(raw_log[:before['bytes']]) == before.get('sha256'))
        else: checks.check(name + ':server_log_preserved', False)
        record = checks.json(endpoint / 'record.json', name + ':endpoint_record')
        if not isinstance(record, dict): may_continue = False; continue
        observed_records[endpoint_id] = record
        checks.check(name + ':literal_response_preserved', record.get('raw_response_text') == raw
                     and record.get('response_artifact_present') is (response is not None)
                     and record.get('response_complete') is bool(response is not None and response.get('done_reason') == 'stop'))
        returned = record.get('transport_result', {})
        checks.check(name + ':returned_transport_record_consistent', isinstance(returned, dict)
                     and returned.get('status') == record.get('transport_status')
                     and same(returned.get('response'), response)
                     and same(returned.get('cleanup'), cleanup))
        audit_transport_accounting(checks, returned, int(attempted), name)
        checks.check(name + ':request_value_hash', record.get('request_body_sha256') == sha_bytes(canonical(expected).encode()))
        checks.check(name + ':record_visibility_exact', record.get('visible_evidence_ids_before_generation') == sorted(visible_ids)
                     and same(record.get('visible_calculator_facts_before_generation'), facts)
                     and record.get('institution_visible') is visible)
        parsed = parse_response(raw)
        if parsed['ok']:
            try: canonical(parsed['value'])
            except (ValueError, OverflowError, TypeError, RecursionError): parsed = {'ok': False, 'value': None}
        value = parsed['value'] if parsed['ok'] else None
        checks.check(name + ':parsed_value_unrepaired', same(record.get('parsed_response'), value))
        validation = validate_response(raw, stage, case['source_id'] if visible else None, visible)
        checks.check(name + ':schema_observation_exact_not_required_pass', same(record.get('schema_validation'), validation),
                     {'model_contract_valid': validation['valid']})
        expected_feedback = evaluate_proposal(value, stage, market, sorted(visible_ids), endpoint_id, previous_weights) if value is not None else None
        checks.check(name + ':actual_feedback_without_repair', same(record.get('feedback'), expected_feedback))
        may_continue = record.get('transport_status') == 'completed' and validation['valid']
        if may_continue:
            messages.extend([{'role': 'assistant', 'content': raw},
                             {'role': 'user', 'content': canonical({'calculator_feedback': expected_feedback})}])
            newfacts = expected_feedback.get('facts', [])
            facts.extend(copy.deepcopy(newfacts)); visible_ids.update(f['fact_id'] for f in newfacts)
            previous_weights = copy.deepcopy(value.get('weights'))
    checks.check(prefix + ':case_attempt_counts', summary.get('core_calls_attempted') == call_counts['core']
                 and summary.get('auxiliary_calls_attempted') == call_counts['auxiliary']
                 and summary.get('main_model_calls') == call_counts['core'] + call_counts['auxiliary']
                 and call_counts['core'] <= 4 and call_counts['auxiliary'] <= 2)
    completed_core = sum(observed_records.get(e, {}).get('transport_status') == 'completed'
                         and observed_records.get(e, {}).get('schema_validation', {}).get('valid') is True for e in CORE)
    checks.check(prefix + ':completed_stage_count', summary.get('completed_core_stages') == completed_core)
    c0 = observed_records.get('C0')
    expected_c0_arithmetic = (bool(c0['feedback']['allocation']['valid'])
        if c0 and c0.get('response_complete') is True and c0.get('feedback') is not None else None)
    checks.check(prefix + ':C0_raw_arithmetic_separate_from_contract',
        summary.get('final_allocation_valid') == expected_c0_arithmetic,
        'A complete captured vector is assessed without requiring unrelated rationale/schema success; incomplete capture stays unavailable.')
    for candidate, next_candidate in (('C0', 'C1'), ('C1', 'C2')):
        observed = observed_records.get(candidate)
        if not observed: continue
        candidate_completed = observed.get('transport_status') == 'completed' and observed.get('schema_validation', {}).get('valid') is True
        next_required = candidate_completed and repair_eligible(observed.get('parsed_response'))['eligible']
        interrupted = summary.get('status') in ('cancelled', 'stopped_cancelled', 'system_exception')
        checks.check(prefix + ':prespecified_auxiliary_transition:' + candidate,
                     ((next_candidate in observed_records) == next_required) or (interrupted and next_candidate not in observed_records),
                     {'eligible_predecessor': next_required, 'next_record_present': next_candidate in observed_records,
                      'cancellation_does_not_authorize_resampling': True})
    primary = folder / 'C0/record.json'
    expected_ref = {'path': label(primary), 'sha256': sha_bytes(primary.read_bytes())} if primary.is_file() else None
    checks.check(prefix + ':C0_reference_not_replaced', summary.get('primary_record') == expected_ref)
    auxiliary_records = [e for e in ('C1', 'C2') if e in observed_records]
    auxiliary_path = folder / auxiliary_records[-1] / 'record.json' if auxiliary_records else None
    terminal_ref = {'path': label(auxiliary_path), 'sha256': sha_bytes(auxiliary_path.read_bytes())} if auxiliary_path else None
    checks.check(prefix + ':auxiliary_is_last_attempt_not_best', summary.get('auxiliary_terminal_record') == terminal_ref)
    for endpoint_record in summary.get('endpoints', []):
        rid = endpoint_record.get('endpoint'); path = folder / str(rid) / 'record.json'
        checks.check(prefix + ':summary_record_hash:' + str(rid), path.is_file()
                     and endpoint_record.get('record') == {'path': label(path), 'sha256': sha_bytes(path.read_bytes())})
    return {'case_id': case['case_id'], 'status': summary.get('status'), 'core_calls': call_counts['core'],
            'auxiliary_calls': call_counts['auxiliary'], 'completed_core_stages': summary.get('completed_core_stages'),
            'C0_present': 'C0' in observed_records, 'C0_raw_arithmetic_valid': summary.get('final_allocation_valid'),
            'system_integrity_incident': summary.get('system_integrity_incident'),
            'semantic_verdict': None, 'model_failure_excluded': False}


def audit_transport_accounting(checks, returned, attempted, name):
    for label_, value in (('transport', returned), ('supervisor', returned.get('supervisor', {}))):
        checks.check(name + ':' + label_ + '_main_request_count', isinstance(value, dict)
                     and value.get('main_model_calls') == attempted
                     and value.get('generation_requests_attempted') == attempted
                     and value.get('execution_scope') == 'main')
    worker = returned.get('supervisor', {}).get('worker')
    if worker is not None:
        checks.check(name + ':worker_main_request_count', isinstance(worker, dict)
                     and worker.get('main_model_calls') == attempted
                     and worker.get('generation_requests_attempted') == attempted
                     and worker.get('execution_scope') == 'main')


def timing_observations(checks, run_root, runtime):
    rows = []
    for path in sorted(run_root.glob('*/*/supervisor_result.json')):
        value = checks.json(path, label(path) + ':timing_supervisor') or {}
        configured, actual = value.get('deadline_seconds'), value.get('elapsed_seconds')
        valid = type(actual) in (int, float) and actual >= 0 and actual < float('inf')
        checks.check(label(path) + ':timing_metadata', configured == runtime['deadline_seconds'] and valid)
        rows.append({'endpoint': path.parent.relative_to(run_root).as_posix(),
            'configured_deadline_seconds': configured, 'observed_supervisor_elapsed_seconds': actual,
            'elapsed_minus_configured_seconds': actual-configured if valid and type(configured) in (int,float) else None,
            'status': value.get('status'), 'last_observed_phase': value.get('failure_phase_last_observed'),
            'generation_requests_attempted': value.get('generation_requests_attempted'), 'reference': reference(path)})
    return {'endpoint_observations': rows, 'strict_wall_clock_bound_certified': False,
        'interpretation': 'The configured polling threshold and observed termination are distinct. Report actual elapsed values without clipping, inferring CPU time or applying a new timing tolerance. OS sleep and scheduler evidence require separate review.',
        'environmental_interruption_review': 'pending unless independently supplied and reviewed outside this byte/contract audit'}


def audit_awake(checks, root):
    acquired = checks.json(root / 'awake_acquire.json', 'awake_acquire') or {}
    released = checks.json(root / 'awake_release.json', 'awake_release') or {}
    checks.check('temporary_awake_request_recorded', acquired.get('status') == 'active'
        and acquired.get('flags') == runner.awake.FLAGS and acquired.get('platform') == 'win32'
        and acquired.get('permanent_power_configuration_changed') is False)
    checks.check('awake_prior_state_restored_same_thread', released.get('status') == 'released'
        and released.get('owner_thread_id') == acquired.get('owner_thread_id')
        and type(acquired.get('previous_state')) is int
        and released.get('restore_flags') == (acquired.get('previous_state', 0) | runner.awake.ES_CONTINUOUS)
        and released.get('permanent_power_configuration_changed') is False)
    return {'acquisition': acquired, 'release': released,
            'uninterrupted_operation_proven': False, 'permanent_power_configuration_changed': False}


def audit_evaluator_materials(checks, manifest):
    """Offline verification of the candidate-pinned criteria, never an online input."""
    refs = manifest.get('evaluator_material_refs')
    if not checks.check('evaluator_material_inventory', isinstance(refs, dict)
                        and set(refs) == EVALUATOR_MATERIAL_KEYS):
        return refs
    available = {}
    for key, value in refs.items():
        valid = (isinstance(value, dict) and isinstance(value.get('path'), str)
                 and Path(value['path']).is_absolute() and isinstance(value.get('sha256'), str)
                 and len(value['sha256']) == 64 and all(c in '0123456789abcdef' for c in value['sha256']))
        if not checks.check('evaluator_material_reference:' + key, valid):
            continue
        actual = checks.attempt('evaluator_material_read:' + key, lambda v=value: sha_bytes(Path(v['path']).read_bytes()))
        if checks.check('evaluator_material_bytes:' + key, actual == value['sha256']):
            available[key] = value
    if 'source_verification' in available and 'reference_annotations' in available:
        verification = checks.json(Path(available['source_verification']['path']), 'evaluator_source_verification') or {}
        checks.check('annotation_hash_matches_original_verification',
                     verification.get('artifact_sha256', {}).get('evaluator_only/reference_annotations.jsonl')
                     == available['reference_annotations']['sha256'])
    if 'design_handoff' in available:
        handoff = checks.json(Path(available['design_handoff']['path']), 'evaluator_design_handoff') or {}
        delivered = handoff.get('delivered_artifacts', [])
        for key in ('evaluation_protocol', 'review_template', 'source_comparison'):
            if key not in available:
                continue
            expected = available[key]
            matches = [item for item in delivered if isinstance(item, dict) and isinstance(item.get('path'), str)
                       and (ROOT / item['path']).resolve() == Path(expected['path']).resolve()
                       and item.get('sha256') == expected['sha256']]
            checks.check('evaluation_criterion_matches_design_handoff:' + key, len(matches) == 1)
    return refs


def audit(manifest_path, gate_path, run_root):
    manifest_path, gate_path, run_root = map(lambda p: Path(p).resolve(), (manifest_path, gate_path, run_root))
    before = inventory(run_root); checks = Checks(); cases = []; prepared = manifest_path.parent
    verified = checks.attempt('frozen_main_gate_inputs_code_reviews_and_authorization',
                              lambda: runner.verify_main_gate(manifest_path, gate_path))
    manifest = read(manifest_path); gate = read(gate_path)
    evaluator_material_refs = audit_evaluator_materials(checks, manifest)
    runtime, contract, registry, market = tuple(read(prepared / name) for name in
        ('runtime.json', 'prompt_contract.json', 'public_numeric_registry.json', 'market_input.json'))
    checks.check('exact_runtime_controls', same(runtime, runner.transport.runtime_v48()))
    summary = checks.json(run_root / 'summary.json', 'main_summary') or {}
    checks.check('fixed_scheduled_roster_retained', summary.get('planned_cases') == list(runner.ROSTER)
                 and manifest.get('roster') == list(runner.ROSTER))
    checks.check('source_review_freeze_recorded_not_model_semantic_pass', summary.get('main_frozen') is True
                 and summary.get('human_review_completed') is True
                 and summary.get('human_semantic_review_completed') is False and summary.get('automatic_retries') == 0)
    checks.check('exact_authorized_run_root', Path(gate.get('authorized_run_root', '')).resolve() == run_root)
    snapshots = [('manifest_snapshot.json', manifest), ('main_execution_gate_snapshot.json', gate)]
    if verified is not None:
        snapshots.extend([('human_source_review_snapshot.json', verified[6]),
                          ('main_execution_authorization_snapshot.json', verified[7])])
    for name, expected in snapshots:
        saved = checks.json(run_root / name, name + ':read')
        checks.check(name + ':exact_snapshot', same(saved, expected))
    invocation = checks.json(run_root / 'invocation.json', 'invocation') or {}
    checks.check('invocation_exact_provenance', invocation.get('manifest') == {'path': label(manifest_path), 'sha256': sha_bytes(manifest_path.read_bytes())}
        and invocation.get('main_execution_gate') == {'path': label(gate_path), 'sha256': sha_bytes(gate_path.read_bytes())}
        and invocation.get('human_source_review') == gate.get('human_source_review')
        and invocation.get('main_execution_authorization') == gate.get('main_execution_authorization')
        and invocation.get('main_model_calls_at_invocation') == 0
        and invocation.get('reviewer_identity_authenticated') is False)
    awake = audit_awake(checks, run_root)
    for case in runner.ROSTER:
        result = checks.attempt(case['case_id'] + ':audit_completed', lambda c=case:
            audit_case(checks, run_root, c, prepared, runtime, contract, registry, market))
        cases.append(result or {'case_id': case['case_id'], 'status': 'audit_error', 'core_calls': None, 'auxiliary_calls': None})
    for row in summary.get('cases', []):
        cid = row.get('case_id'); path = run_root / str(cid) / 'case_summary.json'
        checks.check('case_summary_matches_bundle:' + str(cid), path.is_file() and same(read(path), row))
    requests = [p for p in run_root.rglob('request.json') if p.parent.name.endswith('_generation')]
    expected_cases = {c['case_id'] for c in runner.ROSTER}
    checks.check('no_unregistered_generation_paths', all(len(p.relative_to(run_root).parts) == 4
        and p.parents[2].name in expected_cases and p.parents[1].name in ENDPOINTS
        and p.parent.name == 'http_0001_generation' for p in requests))
    core_calls = sum(p.parents[1].name in CORE for p in requests)
    auxiliary_calls = sum(p.parents[1].name in ('C1', 'C2') for p in requests)
    checks.check('fixed_core_auxiliary_budget', core_calls <= 16 and auxiliary_calls <= 8 and len(requests) <= 24)
    checks.check('main_counts_match_durable_requests', summary.get('core_generation_calls') == core_calls
        and summary.get('auxiliary_generation_calls') == auxiliary_calls and summary.get('main_model_calls') == len(requests))
    for spec_path in sorted(run_root.glob('*/*/worker_spec.json')):
        spec = checks.json(spec_path, label(spec_path) + ':worker_gate_context') or {}
        checks.check(label(spec_path) + ':exact_gate_context', spec.get('execution_context') == {
            'manifest_path': str(manifest_path), 'gate_path': str(gate_path), 'run_root': str(run_root)}
            and Path(spec.get('target_path', '')).resolve() == spec_path.parent.resolve())
    not_started = [c['case_id'] for c in cases if c['status'] == 'not_started']
    checks.check('not_started_cases_not_deleted', summary.get('cases_not_started') == not_started)
    summary_cases = summary.get('cases', [])
    checks.check('case_summary_inventory_complete', {c.get('case_id') for c in summary_cases} == expected_cases - set(not_started)
        and len(summary_cases) == len({c.get('case_id') for c in summary_cases}))
    checks.check('four_case_policy_terminal_accounting', summary.get('status') == 'all_planned_cases_accounted'
        and not not_started and summary.get('system_integrity_incident') is False,
        'All planned cases remain, including model failures. Stopped or incomplete execution is not ready for a full comparison.')
    timing = timing_observations(checks, run_root, runtime)
    after = inventory(run_root)
    checks.check('run_artifacts_stable_during_offline_audit', before == after)
    checks.check('topic_judgment_rationale_choice_retained', all(x in build_system(contract) for x in
        ('published judgments', 'reasoned departure', 'C0', 'rationale')),
        'Interpretation, source evidence, rationale and raw proposal remain visible; label copying or arithmetic is not strategy quality.')
    passed = sum(row['passed'] for row in checks.rows)
    return {'audit_version': 'v48_main_round1_1', 'round': 1, 'status': 'PASS' if passed == len(checks.rows) else 'FAIL',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Offline main captured-byte, execution-contract and fixed-case audit. Does not authorize a run, authenticate people, certify uninterrupted power, or judge strategy.',
        'check_count': len(checks.rows), 'pass_count': passed, 'checks': checks.rows,
        'case_outcomes': cases, 'planned_cases': 4, 'expected_sector_slots': 44,
        'observed_main_generation_requests': len(requests), 'observed_core_generation_requests': core_calls,
        'observed_auxiliary_generation_requests': auxiliary_calls,
        'manifest': reference(manifest_path), 'main_execution_gate': reference(gate_path),
        'evaluator_material_refs': evaluator_material_refs,
        'audit_software': reference(Path(__file__)), 'run_root': label(run_root), 'artifact_inventory': after,
        'model_calls_by_audit': 0, 'execution_gate_binding_valid': verified is not None,
        'human_source_review_completed_as_recorded': summary.get('human_review_completed'),
        'human_identity_authenticated': False, 'new_execution_authorized_by_audit': False,
        'semantic_or_strategic_verdict': None, 'weight_comparison_verdict': None,
        'operating_awake_receipts': awake, 'timing_and_environment': timing,
        'limitations': ['Recorded request/render controls are not independent tokenization or proof of spare context.',
            'Hashes are local provenance, not external timestamp notarization or human identity verification.',
            'Raw output completeness, arithmetic validity and semantic strategy preservation remain separate.',
            'System/host interruptions remain recorded; unavailable pairs are not zero differences or pure model inability.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest', 'gate', 'run-root', 'output'): parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args(argv)
    output, run_root = args.output.resolve(), args.run_root.resolve()
    if output == run_root or run_root in output.parents:
        raise ValueError('Audit output must be outside the immutable run directory')
    report = audit(args.manifest, args.gate, run_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False); handle.write('\n')
    print(json.dumps({'output': str(output), 'status': report['status'], 'checks': report['check_count'],
                      'passed': report['pass_count'], 'model_calls': 0}, ensure_ascii=False))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
