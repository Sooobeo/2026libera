"""Explicit v4.4: one predetermined Fidelity Q2/R1 four-stage pilot case.

`prepare` is offline. Only `run` makes requests; no gold, evaluator or main packet
is opened. Each stage has one generation attempt and no retry. Render-only calls
are recorded separately. Old protocol files and prior artifacts are untouched.
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

import benchmark_sector_latency as bench
import remote_sector_runtime as remote
import run_sector_workflow as workflow
from compact_sector_prompt import PROJECTION_VERSION, compact_stage_content, restore_market

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'qwen3.5:4b-q4_K_M'
DIGEST = 'd8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04'
TEMPLATE = 'b507b9c2f6ca642bffcd06665ea7c91f235fd32daeefdf875a0f938db05fb315'
ENGINE = '0.35.1'
SOURCE = 'fidelity_q2_2026'
CASE = SOURCE + '__R1'
SOURCE_REQUEST = ROOT / 'data/local_sector_runtime/laptop_realinput_4b_20261018/original_request_not_sent.json'
SOURCE_REQUEST_SHA = 'b9368d3d27c7208de9b5c89f836c28ed72bc4ca96837b86c537caa82a16dd163'
PACKET_VALUE_SHA = 'dd55b6d197d1732e3051d9361566c7db3a175a6a90e720c0053659c2f9124a46'
MARKET_SHA = 'e0017731851f7d93a7c1e3d56e7674b28fc945a9a33b8bf89d33b429e96cdf0f'
PRIMARY_MANIFEST = ROOT / 'research/evidence/v44_primary_sources_20261018/manifest.json'
CONDITIONS_SHA = 'a403d4c37d1581f9af21af8ba7a6333614d890ff15277e83181c1204549a9c5b'
RENDERER_POLICY = ROOT / 'research/v44_renderer_policy_20261018.json'
RENDERER_POLICY_SHA = '4135e7f2d0000e4f51ca3414af803805c823f681468807d3ab19f9fd116488a4'
RENDERER_POLICY_ID = 'http_verbatim_json_outer_ascii_whitespace_only_v1'
SOFTWARE = ('local_sector_single_case.py', 'run_sector_workflow.py', 'sector_engine.py',
            'compact_sector_prompt.py', 'benchmark_sector_latency.py',
            'remote_sector_runtime.py', 'probe_ollama_runtime.py')
OPTIONS = dict(temperature=0, num_ctx=65536, num_predict=8192, num_thread=2,
               num_batch=512, repeat_penalty=1.0, presence_penalty=0.0,
               frequency_penalty=0.0, seed=3407, top_p=0.95, top_k=20, min_p=0.0)


class StageStopped(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__('Stage stopped: ' + status)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(',', ':'))


def value_sha(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def runtime_v44():
    return dict(protocol_version='4.4', backend='ollama', model=MODEL, digest=DIGEST,
                template_sha256=TEMPLATE, engine_version=ENGINE, options=OPTIONS.copy(),
                think=False, truncate=False, shift=False, stream=True, format='json',
                keep_alive=0, deadline_seconds=900,
                history_policy=workflow.EXPLICIT_HISTORY,
                renderer_policy=RENDERER_POLICY_ID,
                projection_version=PROJECTION_VERSION)


def validate_runtime(runtime):
    if canonical(runtime) != canonical(runtime_v44()):
        raise ValueError('The explicit v4.4 runtime differs; no fallback or unrecorded revision')


def validate_packet(packet):
    if (packet.get('source_id') != SOURCE or packet.get('split') != 'pilot'
            or value_sha(packet) != PACKET_VALUE_SHA):
        raise ValueError('Only the predetermined exact public Fidelity Q2 pilot packet is allowed')


def validate_conditions(path):
    if remote.sha(path) != CONDITIONS_SHA:
        raise ValueError('Conditions evidence differs from the reviewed immutable snapshot')
    evidence = remote.read(path)
    runtime = runtime_v44()
    expected = {key: runtime[key] for key in
                ('model', 'think', 'format', 'keep_alive', 'truncate', 'shift', 'options')}
    if canonical(evidence['recommended_request']) != canonical(expected):
        raise ValueError('Runtime request differs from the full prespecified conditions')
    execution = evidence['recommended_execution']
    if (execution['engine'] != ENGINE or execution['model_digest'] != DIGEST
            or execution['request_timeout_seconds'] != runtime['deadline_seconds']
            or execution['serial_requests'] != 1 or execution['authorized_pilot_cases'] != 1
            or execution['stages_per_case'] != 4 or execution['automatic_retry'] is not False
            or execution['main_frozen'] is not False):
        raise ValueError('Execution settings differ from the prespecified conditions')


def renderer_source_records():
    if remote.sha(RENDERER_POLICY) != RENDERER_POLICY_SHA:
        raise ValueError('Predeclared renderer policy changed')
    policy = remote.read(RENDERER_POLICY)
    if policy['policy_id'] != RENDERER_POLICY_ID:
        raise ValueError('Unexpected renderer policy')
    records = [{'path': str(RENDERER_POLICY), 'sha256': RENDERER_POLICY_SHA}]
    for row in policy['primary_sources']:
        if 'path' in row:
            source = ROOT / row['path']
            if remote.sha(source) != row['sha256']:
                raise ValueError('Renderer primary source changed')
            records.append({'path': str(source), 'sha256': row['sha256'], 'url': row['url']})
    return records


def prepare(args):
    source, market_path = SOURCE_REQUEST, workflow.MARKET
    if remote.sha(source) != SOURCE_REQUEST_SHA or remote.sha(market_path) != MARKET_SHA:
        raise ValueError('Original request or market file differs from the measured public input')
    prior = remote.read(source)
    packet = json.loads(prior['messages'][1]['content'])['institution_document']
    validate_packet(packet)
    evidence = Path(args.conditions_evidence).resolve()
    if not evidence.is_file() or 'evaluator_only' in evidence.parts:
        raise ValueError('A separate conditions evidence file is required; never evaluator material')
    validate_conditions(evidence)
    renderer_records = renderer_source_records()
    primary = remote.read(PRIMARY_MANIFEST)
    source_evidence = [{'path': str(PRIMARY_MANIFEST), 'sha256': remote.sha(PRIMARY_MANIFEST)}]
    for row in primary['records']:
        p = ROOT / row['path']
        if remote.sha(p) != row['sha256']:
            raise ValueError('Archived primary source changed: ' + row['path'])
        source_evidence.append({'path': str(p), 'sha256': row['sha256'], 'url': row['url']})
    target = Path(args.output).resolve()
    target.mkdir(parents=True, exist_ok=False)
    remote.save(target / 'runtime.json', runtime_v44())
    remote.save(target / 'model_packet.json', packet)
    (target / 'market_input.json').write_bytes(market_path.read_bytes())
    manifest = dict(protocol_version='4.4', scope='one_predetermined_pilot_case',
        created_at_utc=remote.now(), case_id=CASE, arm='R1', planned_cases=1,
        planned_stages=[1, 2, 3, 4], selection='Predetermined same first case; no selection by outcome.',
        main_freeze=False, human_semantic_pass=False,
        inputs={name: remote.sha(target / name) for name in
                ('runtime.json', 'model_packet.json', 'market_input.json')},
        source_request={'path': str(source), 'sha256': SOURCE_REQUEST_SHA},
        selected_packet_value_sha256=PACKET_VALUE_SHA,
        software={name: remote.sha(ROOT / 'research' / name) for name in SOFTWARE},
        conditions_evidence={'path': str(evidence), 'sha256': remote.sha(evidence)},
        renderer_policy_evidence=renderer_records,
        primary_source_evidence=source_evidence,
        controls={'decoding': 'Explicit T0, thinking disabled, neutral penalties and seed. Attribution is in the separately pinned conditions evidence.',
                  'engineering': '65536 context, 8192 output allowance, thread2, batch512, keep_alive0 and 900-second stage deadline are recorded controls; do not label all as paper-derived.',
                  'deadline': 'One supervised child per stage: setup, metadata, render-only and generation combined cannot exceed 900 seconds apart from OS kill/scheduling overhead. Cleanup is outside this bound.',
                  'context': 'No UTF-8 token estimate. Pinned render-only output must include every expected content in order under the separately pinned JSON-boundary whitespace policy; HTTP strings stay unchanged. truncate=false and shift=false are sent on both requests. Overflow or missing evidence stops subsequent stages. This does not prove spare token capacity.',
                  'history': 'Assistant final content and calculator message strings are retained verbatim. Only stage1 user JSON has the recorded reversible duplicate-field projection. No prior thinking is forwarded.',
                  'assessment': 'Completion is workflow execution, not human semantic PASS or a main-study result.'})
    remote.save(target / 'manifest.json', manifest)
    print(json.dumps({'prepared_manifest': str(target / 'manifest.json'),
                      'model_calls': 0, 'main_freeze': False}), flush=True)
    return 0


def verify_manifest(path):
    path = Path(path).resolve()
    m = remote.read(path)
    if (m.get('protocol_version') != '4.4' or m.get('case_id') != CASE
            or m.get('planned_cases') != 1 or m.get('arm') != 'R1'
            or m.get('planned_stages') != [1, 2, 3, 4]):
        raise ValueError('Manifest must describe exactly the predetermined one-case pilot')
    if set(m['inputs']) != {'runtime.json', 'model_packet.json', 'market_input.json'}:
        raise ValueError('Unexpected input manifest')
    for name, expected in m['inputs'].items():
        if remote.sha(path.parent / name) != expected:
            raise ValueError('Prepared input changed: ' + name)
    if set(m['software']) != set(SOFTWARE):
        raise ValueError('Software hash inventory is incomplete')
    for name, expected in m['software'].items():
        if remote.sha(ROOT / 'research' / name) != expected:
            raise ValueError('Prepared software changed: ' + name)
    if m['renderer_policy_evidence'] != renderer_source_records():
        raise ValueError('Prepared renderer evidence inventory changed')
    for item in [m['source_request'], m['conditions_evidence'], *m['primary_source_evidence'],
                 *m['renderer_policy_evidence']]:
        if remote.sha(Path(item['path'])) != item['sha256']:
            raise ValueError('Pinned provenance changed: ' + item['path'])
    if m['source_request']['sha256'] != SOURCE_REQUEST_SHA:
        raise ValueError('Unapproved source request')
    runtime = remote.read(path.parent / 'runtime.json')
    validate_runtime(runtime)
    validate_conditions(Path(m['conditions_evidence']['path']))
    packet = remote.read(path.parent / 'model_packet.json')
    validate_packet(packet)
    if remote.sha(path.parent / 'market_input.json') != MARKET_SHA:
        raise ValueError('Unapproved market input')
    return m, runtime, packet, remote.read(path.parent / 'market_input.json')


def prepare_body(messages, runtime):
    validate_runtime(runtime)
    sent = copy.deepcopy(messages)
    if len(sent) < 2 or sent[0] != {'role': 'system', 'content': workflow.SYSTEM}:
        raise ValueError('Unexpected system/history structure')
    for msg in sent:
        if set(msg) != {'role', 'content'} or not isinstance(msg['content'], str):
            raise ValueError('Only complete explicit role/content messages are permitted')
    original = json.loads(sent[1]['content'])
    if original.get('stage') != 1 or 'institution_document' not in original:
        raise ValueError('Predetermined R1 document must be present at stage 1')
    validate_packet(original['institution_document'])
    sent[1]['content'] = compact_stage_content(sent[1]['content'])
    restored = json.loads(sent[1]['content'])
    restored['common_market'] = restore_market(restored['common_market'])
    if canonical(restored) != canonical(original) or sent[2:] != messages[2:]:
        raise ValueError('Lossless stage1 projection or verbatim later history failed')
    return {k: copy.deepcopy(runtime[k]) for k in
            ('model', 'think', 'truncate', 'shift', 'stream', 'format', 'keep_alive', 'options')} | {'messages': sent}


def validate_render(response, messages):
    info = response.get('_debug_info')
    rendered = info.get('rendered_template') if isinstance(info, dict) else None
    if (response.get('model') != MODEL or not isinstance(rendered, str) or not rendered
            or info.get('image_count', 0) != 0 or response.get('eval_count', 0) != 0
            or response.get('prompt_eval_count', 0) != 0
            or response.get('message', {}).get('content')
            or response.get('message', {}).get('thinking')
            or response.get('message', {}).get('tool_calls')):
        raise ValueError('Render-only evidence missing or unexpected generation response; stop before generation')
    position, evidence = 0, []
    for index, msg in enumerate(messages):
        raw_content = msg['content']
        if index == 0:
            if raw_content != workflow.SYSTEM:
                raise ValueError('Unexpected SYSTEM content')
            expected = raw_content
            removed_prefix = removed_suffix = ''
            value_preserved = None
        else:
            # Match the documented Go renderer boundary behavior only for JSON
            # whitespace. Never apply broad Python strip or edit HTTP content.
            expected = raw_content.strip(' \t\r\n')
            left = len(raw_content) - len(raw_content.lstrip(' \t\r\n'))
            right = len(raw_content.rstrip(' \t\r\n'))
            removed_prefix, removed_suffix = raw_content[:left], raw_content[right:]
            raw_value, expected_value = json.loads(raw_content), json.loads(expected)
            value_preserved = (isinstance(raw_value, dict)
                               and canonical(raw_value) == canonical(expected_value))
            if not value_preserved:
                raise ValueError('Renderer boundary policy requires exact JSON object values')
        start = rendered.find(expected, position)
        if start < 0:
            raise ValueError(f'Rendered prompt omitted or changed explicit message {index}')
        position = start + len(expected)
        evidence.append({'message_index': index, 'role': msg['role'], 'start_character': start,
                         'end_character': position,
                         'raw_content_utf8_sha256': hashlib.sha256(raw_content.encode()).hexdigest(),
                         'expected_renderer_content_utf8_sha256': hashlib.sha256(expected.encode()).hexdigest(),
                         'removed_outer_prefix': removed_prefix, 'removed_outer_suffix': removed_suffix,
                         'strict_json_payload_value_preservation': value_preserved,
                         'http_content_modified': False})
    return {'status': 'all_expected_renderer_contents_present_in_order',
            'renderer_policy': RENDERER_POLICY_ID, 'renderer_policy_sha256': RENDERER_POLICY_SHA,
            'message_count': len(messages), 'message_spans': evidence,
            'rendered_utf8_sha256': hashlib.sha256(rendered.encode()).hexdigest(),
            'exact_token_count': None,
            'basis': 'Observed pinned server rendering, predeclared JSON-boundary whitespace policy, and explicit truncate=false/shift=false. HTTP message strings are unchanged. This is not independent tokenization or a proof of spare context capacity.'}


def render_call(session, body):
    target = session.target / 'render_only'
    target.mkdir()
    request = copy.deepcopy(body)
    request.update(stream=False, _debug_render_only=True)
    remote.save(target / 'request.json', {'path': '/api/chat', 'body': request,
                                        'purpose': 'render_only_not_generation'})
    raw_request = json.dumps(request, ensure_ascii=False, allow_nan=False).encode()
    (target / 'request_body.bin').write_bytes(raw_request)
    connection = remote.connect(session.origin, session.timeout_seconds)
    result = {'status': 'attempted', 'generation_requests': 0}
    started = time.monotonic()
    try:
        connection.request('POST', '/api/chat', raw_request, {'Content-Type': 'application/json'})
        response = connection.getresponse()
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
            raise RuntimeError('Render-only request failed; no generation: ' + str(raw.get('error', response.status)))
        validation = validate_render(raw, body['messages'])
        remote.save(target / 'validation.json', validation)
        (target / 'rendered_prompt.txt').write_bytes(raw['_debug_info']['rendered_template'].encode('utf-8'))
        result['status'] = 'validated'
    except BaseException as exc:
        result.update(status='failed', error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        connection.close()
        result['wall_seconds'] = time.monotonic() - started
        remote.save(target / 'result.json', result)


def assert_pin(observation):
    if (observation['version'].get('version') != ENGINE
            or observation['selected_model'].get('digest') != DIGEST
            or observation.get('template_sha256') != TEMPLATE):
        raise ValueError('Pinned model, engine or template mismatch; no fallback')


def worker(spec_path):
    spec = remote.read(spec_path); target = Path(spec_path).parent
    session = bench.ProbeSession(target, spec['origin'], spec['deadline_seconds'], 2)
    outcome = {'status': 'started', 'main_model_calls': 0, 'automatic_retries': 0}
    started = time.monotonic()
    try:
        expected_header = {key: value for key, value in runtime_v44().items() if key in
                           ('model', 'think', 'truncate', 'shift', 'stream', 'format', 'keep_alive', 'options')}
        actual_header = {key: value for key, value in spec['body'].items() if key != 'messages'}
        if canonical(actual_header) != canonical(expected_header):
            raise ValueError('Worker body differs from exact v4.4 request controls')
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
    target = remote.new_output(args.output_root, 'single_case_v44', args.run_id)
    frozen_manifest_sha = remote.sha(manifest_path)
    started = time.monotonic(); stages = []
    summary = dict(status='not_started', protocol_version='4.4', case_id=CASE, planned_cases=1,
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
        remote.save(stage_dir / 'authoritative_body.json', body)
        (stage_dir / 'authoritative_body.bin').write_bytes(json.dumps(body, ensure_ascii=False, allow_nan=False).encode())
        remote.save(stage_dir / 'projection_validation.json', dict(status='exact_original_field_values',
            projection=PROJECTION_VERSION, later_message_strings_verbatim=True,
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
