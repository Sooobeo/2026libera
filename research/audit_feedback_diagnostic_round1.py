"""Offline provenance audit of a settled feedback diagnostic, with no model calls."""
from __future__ import annotations
import argparse
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
from audit_v45_single_case_round1 import strict_object, structure_errors, canonical, floats

ROOT = Path(__file__).resolve().parents[1]


def audit(run, preparation, registration):
    checks, refs = [], {}
    def read(path, raw=False):
        path = Path(path).resolve()
        value = path.read_bytes()
        refs[path.relative_to(ROOT).as_posix()] = hashlib.sha256(value).hexdigest()
        return value if raw else json.loads(value.decode('utf-8-sig'))
    def check(name, condition, detail=None):
        checks.append({'check': name, 'status': 'pass' if condition else 'fail', 'detail': detail})
    def pin(ref):
        p = Path(ref['path'])
        p = p if p.is_absolute() else ROOT / p
        value = read(p, raw=True)
        check('hash:' + p.name, hashlib.sha256(value).hexdigest() == ref['sha256'])
    manifest = read(preparation)
    reg = read(registration)
    summary = read(run / 'summary.json')
    invocation = read(run / 'invocation.json')
    check('manifest_snapshot', read(run / 'manifest_snapshot.json') == manifest)
    check('registration_snapshot', read(run / 'registration_snapshot.json') == reg)
    for name, expected in manifest['inputs'].items():
        pin({'path': str(preparation.parent / name), 'sha256': expected})
    for name, expected in manifest['software'].items():
        pin({'path': str(ROOT / 'research' / name), 'sha256': expected})
    for row in [manifest['parent_preparation'], *manifest['original_sources'], *manifest['revision_evidence']]:
        pin(row)
    for key in ('manifest', 'registration'):
        pin(invocation[key])
    for row in reg.get('reference_files', []):
        pin(row)
    check('registered_before_launch', datetime.fromisoformat(reg['registered_at_utc']) <= datetime.fromisoformat(invocation['started_at_utc']))
    check('one_attempt_scope', manifest['planned_generation_attempts'] == reg['planned_generation_attempts'] == 1)
    check('completed_one_diagnostic', summary['status'] == 'completed_one_diagnostic')
    check('no_main_retry_or_full_pilot', summary['main_model_calls'] == summary['automatic_retries'] == summary['four_stage_pilot_calls'] == 0)
    check('no_unearned_approval', summary['main_freeze'] is False and summary['human_semantic_pass'] is False and summary['priority1_solved'] is False)
    folder = run / 'revision_transport'
    http = folder / 'http_0001_generation'
    logical = read(folder / 'logical_messages.json')
    prepared = read(preparation.parent / 'logical_messages.json')
    body = read(folder / 'authoritative_body.json')
    request = read(http / 'request.json')
    spec = read(folder / 'worker_spec.json')
    check('logical_matches_preparation', logical == prepared)
    check('body_matches_preparation_and_wire', body == read(preparation.parent / 'authoritative_body.json') == request['body'] == spec['body'])
    check('serialized_authority', read(folder / 'authoritative_body.bin', raw=True) == json.dumps(body, ensure_ascii=False, allow_nan=False).encode())
    check('one_generation_record', len(list(run.rglob('http_*_generation/request.json'))) == 1)
    check('five_messages', len(logical) == 5 and [m['role'] for m in logical] == ['system','user','assistant','user','user'])
    prior_response = read(preparation.parent / 'prior_response.json')
    prior_record = read(preparation.parent / 'prior_record.json')
    original_refs = {Path(row['path']).name: row for row in manifest['original_sources']}
    check('original_public_messages', logical[:2] == read(original_refs['stage1_request.json']['path']))
    check('original_assistant_verbatim', logical[2] == {'role':'assistant','content':prior_response['message']['content']})
    check('original_raw_proposal', strict_object(logical[2]['content']) == prior_record['raw_proposal'])
    original_calc = prior_record['calculator_result']
    check('negative_feedback_observed', original_calc['allocation']['valid'] is False)
    check('feedback_values_identical', strict_object(logical[3]['content']) == {'calculator_feedback':original_calc}
          and strict_object(logical[4]['content'])['calculator_feedback'] == original_calc)
    check('feedback_serialization_declared', logical[3]['content'] == json.dumps({'calculator_feedback':original_calc},ensure_ascii=False,allow_nan=False))
    task = strict_object(logical[4]['content'])
    schema = read(preparation.parent / 'response_schema.json')
    check('same_schema_in_prompt_and_api', task['response_schema'] == schema == body['format'])
    check('schema_only_selector', task['stage'] == 4 and task['stage_field_role'] == 'existing_final_response_schema_selector_not_a_workflow_stage')
    # Independently reconstruct the reversible duplicate-field representation.
    projected = strict_object(body['messages'][1]['content'])
    small = projected['common_market']
    check('projection_ddof', type(small['covariance_ddof']) is int and small['covariance_ddof'] == 1)
    del small['covariance_ddof']
    small['sample_covariance_ddof_1'] = copy.deepcopy(small['covariance'])
    small['baseline_weights_array'] = [small['baseline_weights'][code] for code in small['sector_codes']]
    original_public = strict_object(logical[1]['content'])
    check('public_input_values_preserved', canonical(projected) == canonical(original_public) and floats(projected) == floats(original_public))
    check('other_message_strings_verbatim', body['messages'][0] == logical[0] and body['messages'][2:] == logical[2:])
    runtime = read(run / 'runtime.json')
    check('runtime_matches_prepared', runtime == read(preparation.parent / 'runtime.json'))
    expected = {k: runtime[k] for k in ('model','think','truncate','shift','stream','keep_alive','options')}
    expected['format'] = schema
    check('all_runtime_controls', {k:v for k,v in body.items() if k != 'messages'} == expected)
    for phase in ('before_render','before_generation'):
        observed = read(folder / ('pin_' + phase + '.json'))
        check('runtime_pins_' + phase, observed['version']['version'] == runtime['engine_version']
              and observed['selected_model']['digest'] == runtime['digest'] and observed['template_sha256'] == runtime['template_sha256'])
    render_req = read(folder / 'render_only/request.json')
    render = read(folder / 'render_only/response.json')
    check('render_exact_request', render_req['body'] == (body | {'stream':False,'_debug_render_only':True}))
    check('render_no_generation', render.get('eval_count',0) == render.get('prompt_eval_count',0) == 0
          and not any(render.get('message',{}).get(k) for k in ('content','thinking','tool_calls')))
    rendered = render['_debug_info']['rendered_template']
    check('rendered_file', read(folder / 'render_only/rendered_prompt.txt', raw=True) == rendered.encode())
    cursor = 0
    for i, msg in enumerate(body['messages']):
        content = msg['content'] if i == 0 else msg['content'].strip(' \t\r\n')
        position = rendered.find(content, cursor)
        check('rendered_message_' + str(i), position >= cursor)
        if position >= 0:
            cursor = position + len(content)
    raw = read(http / 'raw_stream.bin', raw=True)
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    logged = [json.loads(line) for line in read(http / 'events.jsonl', raw=True).splitlines() if line.strip()]
    check('raw_events_preserved', events == [item['event'] for item in logged] and raw.endswith(b'\n'))
    response = read(http / 'response.json')
    check('response_model_pin', response.get('model') == runtime['model'])
    content = ''.join(event.get('message',{}).get('content','') for event in events)
    check('stopped_without_cap', events[-1]['done'] is True and events[-1]['done_reason'] == response['done_reason'] == 'stop')
    check('response_from_raw_stream', response['message']['content'] == content == read(http / 'assembled_text.json')['content'])
    check('no_hidden_thinking_or_tools', not any(event.get('message',{}).get('thinking') or event.get('message',{}).get('tool_calls') for event in events))
    parsed = strict_object(content)
    check('independent_structure', not structure_errors(parsed, 4))
    record = read(run / 'revision_record.json')
    check('raw_response_is_calculator_input', parsed == record['raw_proposal'] and record['calculator_arguments'] ==
          {'weights':parsed['weights'],'submitted_constraints':parsed['submitted_constraints']} and record['repair_applied'] is False)
    check('numeric_result_separate', summary['numeric_acceptance'] == record['assessment']['numeric_acceptance'] and summary['semantic_validity_assessed'] is False)
    result = read(http / 'result.json')
    check('http_completed', result.get('status') == 'completed' and result.get('http_status') == 200)
    check('request_after_registration', datetime.fromisoformat(result['started_at_utc']) >= datetime.fromisoformat(reg['registered_at_utc']))
    supervisor = read(folder / 'supervisor_result.json')
    check('supervised_completion', supervisor['status'] == 'worker_exited' and supervisor['worker_exit_code'] == 0 and supervisor['deadline_seconds'] == 900)
    unload = read(folder / 'unload_and_residency.json')
    check('idle_after_cleanup', unload['status'] == 'no_resident_models_observed' and unload['ps'][-1]['value']['models'] == [])
    check('unload_acknowledged', unload['unload']['status'] == 'ok' and unload['unload']['value']['done'] is True)
    before = read(folder / 'server_log_before.json')
    after = read(folder / 'server_log_after_snapshot.bin', raw=True)
    delta = read(folder / 'server_log_delta.json')
    check('server_log_immutable_snapshot', hashlib.sha256(after[:before['bytes']]).hexdigest() == before['sha256']
          and hashlib.sha256(after).hexdigest() == delta['sha256'] and delta['original_prefix_retained'] is True)
    ledger = [json.loads(line) for line in read(run / 'events.jsonl', raw=True).splitlines()]
    check('required_run_events', [x.get('event') for x in ledger] == [
        'registered_diagnostic_started','single_supervised_attempt_dispatched',
        'cleanup_recorded','raw_revision_recalculated','diagnostic_finished'])
    summary_ref = ledger[-1].get('summary', {}) if ledger else {}
    check('ledger_terminal_summary', Path(summary_ref.get('path','')).resolve() == (run / 'summary.json').resolve()
          and summary_ref.get('sha256') == hashlib.sha256((run / 'summary.json').read_bytes()).hexdigest())
    for i, event in enumerate(ledger):
        payload = {k:v for k,v in event.items() if k != 'event_sha256'}
        check('run_ledger_' + str(i + 1), event['sequence'] == i + 1
              and event['previous_event_sha256'] == (ledger[i-1]['event_sha256'] if i else None)
              and event['event_sha256'] == hashlib.sha256(canonical(payload).encode()).hexdigest())
    check('summary_call_counts', summary['generation_requests_attempted'] == summary['diagnostic_generation_calls'] == summary['http_streams_completed'] == 1
          and summary['render_requests_attempted'] == 1 and summary['unexpected_generation_evidence_in_render'] is False)
    read(Path(__file__), raw=True)
    read(ROOT / 'research/audit_v45_single_case_round1.py', raw=True)
    failed = [x['check'] for x in checks if x['status'] == 'fail']
    return {'phase':'priority1','round':1,'run_dir':run.relative_to(ROOT).as_posix(),
            'scope':'Input/provenance/transport/record preservation for one development correction; no arithmetic or semantic approval.',
            'all_passed':not failed,'audit_completed':True,'failed_checks':failed,'not_observed_checks':[],'checks':checks,
            'source_files':[{'path':p,'sha256':h} for p,h in refs.items()],
            'model_calls_by_auditor':0,'main_freeze':False,'human_semantic_pass':False,
            'limits':['Local registration timestamps are not an external timestamp authority.',
                      'This is not a four-stage pilot; intermediate old assistant history is intentionally absent.',
                      'Rendering inspection does not independently count model tokens.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--registration',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): raise FileExistsError('Keep earlier audits')
    try:
        result=audit(args.run_dir.resolve(),args.manifest.resolve(),args.registration.resolve())
    except Exception as exc:
        # A settled failed attempt can lack a response/record. Preserve the audit
        # failure itself and available evidence rather than emitting a PASS or
        # silently leaving no review artifact. This is not a complete trace audit.
        run=args.run_dir.resolve()
        paths=[args.manifest,args.registration,run/'summary.json',run/'failure.json',Path(__file__)]
        paths += list(run.glob('revision_transport/http_*/raw_stream.bin'))
        paths += list(run.glob('revision_transport/worker_summary.json'))
        refs=[{'path':p.resolve().relative_to(ROOT).as_posix(),
               'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths if p.is_file()]
        result={'phase':'priority1','round':1,'run_dir':run.relative_to(ROOT).as_posix(),
                'scope':'Incomplete execution audit; missing evidence or audit error is never PASS.',
                'all_passed':False,'audit_completed':False,'failed_checks':['audit_not_completed'],
                'not_observed_checks':['full_execution_review'], 'checks':[],
                'error_type':type(exc).__name__,'error':str(exc),'source_files':refs,
                'model_calls_by_auditor':0,'main_freeze':False,'human_semantic_pass':False}
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write('\n')
    print(json.dumps({'all_passed':result['all_passed'],'checks':len(result['checks']),
                      'failed_checks':result['failed_checks'],'output':str(args.output)}))
    return 0 if result['all_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
