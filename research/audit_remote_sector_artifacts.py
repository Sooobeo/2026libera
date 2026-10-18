"""Reconcile saved v4.3 remote artifacts without network, inference or scoring.

Only the audit JSON is written. Deployment/runtime/run/evaluation files are read
unchanged. Missing pilot artifacts remain pending, not successful or failed AI
observations. A mechanical PASS never constitutes a semantic or human review.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import tarfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
MODEL = 'qwen3.5:4b-q4_K_M'
DIGEST = 'd8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04'
ENGINE = '0.35.1'
SOURCES = ('fidelity_q2_2026', 'ubs_june_2026')
DEPLOYED = ('research/remote_sector_runtime.py', 'research/run_sector_workflow.py',
            'research/sector_engine.py', 'data/sector_market/market_input.json',
            'data/sector_documents/model_packets.jsonl')
PINS = ('model', 'digest', 'engine_version', 'template_sha256', 'protocol_version',
        'temperature', 'thinking', 'max_output_tokens', 'context_tokens', 'history_policy',
        'base_url', 'timeout_seconds')
CALC_REL_TOL = 1e-10
CALC_ABS_TOL = 1e-12


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def calculator_equal(left, right):
    """Allow only tiny cross-platform floating-point differences, never repairs."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(left, right, rel_tol=CALC_REL_TOL, abs_tol=CALC_ABS_TOL)
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(calculator_equal(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(calculator_equal(x, y) for x, y in zip(left, right))
    return type(left) is type(right) and left == right


class Audit:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.evidence = {}
        self.checks = []
        self.limitations = []
        self.cache = {}

    def path(self, path):
        path = Path(path).resolve()
        return path.relative_to(self.root).as_posix() if path.is_relative_to(self.root) else str(path)

    def check(self, name, ok, paths=(), detail=None):
        item = {'check':name, 'status':'pass' if ok else 'fail',
                'evidence_paths':[self.path(p) for p in paths]}
        if detail is not None:item['detail'] = detail
        self.checks.append(item)
        return ok

    def pending(self, name, paths=(), detail=None):
        self.checks.append({'check':name, 'status':'not_observed',
                            'evidence_paths':[self.path(p) for p in paths], 'detail':detail})

    def raw(self, path, required=True):
        path = Path(path).resolve(); key = self.path(path)
        if key in self.cache:return self.cache[key]
        if not path.is_file():
            self.evidence[key] = {'exists':False}
            if required:self.pending('artifact_available', [path])
            return None
        value = path.read_bytes(); self.cache[key] = value
        self.evidence[key] = {'exists':True, 'size_bytes':len(value), 'sha256':sha(value)}
        return value

    def json(self, path, required=True):
        value = self.raw(path, required)
        if value is None:return None
        try:return json.loads(value.decode('utf-8-sig'))
        except (ValueError, UnicodeError) as exc:
            self.check('readable_JSON', False, [path], str(exc));return None

    def lines(self, path, required=True):
        value = self.raw(path, required)
        if value is None:return None
        try:return [json.loads(line) for line in value.decode('utf-8-sig').splitlines() if line.strip()]
        except (ValueError, UnicodeError) as exc:
            self.check('readable_JSONL', False, [path], str(exc));return None

    def stable(self):
        changed = [p for p, raw in self.cache.items()
                   if not (self.root / p).is_file() or (self.root / p).read_bytes() != raw]
        self.check('read_evidence_unchanged_during_audit', not changed, detail=changed)


def deployment(a, received, archive):
    path = received/'bundle_manifest.json'; manifest = a.json(path)
    packets_path = a.root/DEPLOYED[-1]; raw = a.raw(packets_path)
    packets = []
    filtered = None
    if raw is not None:
        lines = [line for line in raw.splitlines() if line.strip()]
        try:
            values = [json.loads(line) for line in lines]
        except (ValueError, UnicodeError) as exc:
            a.check('public_packets_readable_JSONL', False, [packets_path], str(exc))
            values = []
        selected = [(line, value) for line, value in zip(lines, values) if value.get('split') == 'pilot']
        packets = [value for _, value in selected]
        filtered = b'\n'.join(line for line, _ in selected) + b'\n'
        a.check('exact_two_public_pilot_packets', len(packets) == 2 and
                [p.get('source_id') for p in packets] == list(SOURCES) and
                all('evidence_passages' in p and not any(k in p for k in ('sector_ratings','evidence_index')) for p in packets),
                [packets_path])
    expected = {}
    for relative in DEPLOYED:
        value = filtered if relative == DEPLOYED[-1] else a.raw(a.root/relative)
        if value is not None:expected[relative] = sha(value)
    if manifest is not None:
        a.check('deployment_allowlist_excludes_gold_and_main_packet_files', set(manifest.get('files', {})) == set(DEPLOYED), [path])
        a.check('source_packet_hash_matches_current_local_source', raw is not None and manifest.get('source_packets_sha256') == sha(raw), [path,packets_path])
        for relative in DEPLOYED:
            a.check('deployment_hash:' + relative, manifest.get('files',{}).get(relative) == expected.get(relative) and relative in expected,
                    [path,a.root/relative], {'recorded':manifest.get('files',{}).get(relative),'current_or_filtered':expected.get(relative)})
    if archive and archive.is_file():
        a.raw(archive)
        with tarfile.open(archive, 'r:gz') as bundle:
            members = bundle.getmembers(); names = [x.name for x in members]
            a.check('bundle_members_exact_allowlist', len(names) == len(set(names)) and set(names) == set(DEPLOYED) | {'bundle_manifest.json'}, [archive])
            for member in members:
                if member.name not in set(DEPLOYED) | {'bundle_manifest.json'}:continue
                if not a.check('bundle_member_regular_file:' + member.name, member.isfile(), [archive]):continue
                stream = bundle.extractfile(member)
                data = stream.read() if stream else b''
                target = expected.get(member.name) if member.name != 'bundle_manifest.json' else sha(a.raw(path) or b'')
                a.check('bundle_member_hash:' + member.name, sha(data) == target, [archive,path])
    else:
        a.limitations.append('Deployment archive unavailable: manifest/current-file agreement does not independently prove the uploaded bytes.')
    market = a.json(a.root/'data/sector_market/market_input.json')
    return packets, market, expected


def pin_check(a, runtime, metadata, paths):
    from run_sector_workflow import validate_runtime
    if runtime is None:return
    try:validate_runtime(runtime); valid = True
    except (ValueError, TypeError, KeyError):valid = False
    a.check('v43_runtime_contract', valid and runtime.get('protocol_version') == '4.3' and
            runtime.get('context_tokens') == 65536 and runtime.get('model') == MODEL and
            runtime.get('digest') == DIGEST and runtime.get('engine_version') == ENGINE and
            runtime.get('intended_split') == 'pilot' and runtime.get('main_authorized_by_this_file') is False,
            paths)
    if metadata is None:
        a.pending('pin_observed_metadata_available', paths);return
    selected = metadata.get('selected_model', {}); show = metadata.get('show', {})
    template = show.get('template')
    actual_template = sha(template.encode('utf-8')) if isinstance(template, str) else None
    a.check('observed_model_digest_engine_template_quantization', selected.get('name') == MODEL and
            selected.get('digest','').removeprefix('sha256:') == DIGEST and
            metadata.get('version',{}).get('version') == ENGINE and
            bool(actual_template) and actual_template == runtime.get('template_sha256') == metadata.get('template_sha256') and
            show.get('details',{}).get('quantization_level') == 'Q4_K_M', paths)


def snapshot_check(a, folder):
    for phase in ('before', 'after'):
        path = folder/f'inventory_{phase}.json'; value = a.json(path)
        if value is None:continue
        version, tags = value.get('ollama_version',{}), value.get('ollama_tags',{})
        if version.get('status') != 'ok' or tags.get('status') != 'ok':
            a.pending('inventory_snapshot_pins_observed', [path], 'The saved API observation was unavailable.');continue
        selected = [m for m in tags.get('value',{}).get('models',[]) if m.get('name') == MODEL]
        a.check('inventory_snapshot_engine_and_digest', version.get('value',{}).get('version') == ENGINE and
                len(selected) == 1 and selected[0].get('digest','').removeprefix('sha256:') == DIGEST, [path])


def inventory_check(a, folder):
    rp, mp = folder/'runtime_pinned.json', folder/'model_metadata.json'
    runtime, metadata = a.json(rp), a.json(mp)
    pin_check(a,runtime,metadata,[rp,mp])
    snapshot_check(a,folder)
    summary = a.json(folder/'summary.json')
    if summary is not None:
        a.check('inventory_no_model_generation', summary.get('diagnostic_calls') == 0 and
                summary.get('pilot_model_calls') == 0 and summary.get('main_model_calls') == 0,
                [folder/'summary.json'])
    return runtime


def stream_check(a, folder, result):
    raw = a.raw(folder/'raw_stream.bin'); events = a.lines(folder/'events.jsonl')
    response = a.json(folder/'response.json', required=result.get('status') == 'completed')
    decoded = []; broken = False
    if raw is not None:
        for line in raw.splitlines():
            if not line.strip():continue
            try:decoded.append(json.loads(line.decode('utf-8')))
            except (ValueError, UnicodeError):broken=True;break
    if events is not None and raw is not None:
        a.check('raw_stream_matches_logged_events', decoded == [x.get('event') for x in events], [folder/'raw_stream.bin',folder/'events.jsonl'])
    terminal = next((x for x in reversed(decoded) if isinstance(x,dict) and x.get('done') is True), None)
    messages = [x.get('message',{}) for x in decoded if isinstance(x,dict)]
    content = ''.join(m.get('content','') for m in messages)
    thinking = ''.join(m.get('thinking','') for m in messages)
    if result.get('status') == 'completed':
        a.check('completed_http_has_terminal_stream', not broken and terminal is not None and result.get('http_status') == 200, [folder/'result.json',folder/'raw_stream.bin'])
        assembled = dict(terminal or {})
        assembled['message'] = {'role':'assistant','content':content}
        if thinking:assembled['message']['thinking'] = thinking
        calls = [call for m in messages for call in m.get('tool_calls',[])]
        if calls:assembled['message']['tool_calls'] = calls
        a.check('saved_response_is_assembled_raw_stream', response == assembled, [folder/'response.json',folder/'raw_stream.bin'])
    if response is not None:
        a.check('response_model_matches_exact_tag', response.get('model') == MODEL, [folder/'response.json'])
    # An anomalous generation is an observed protocol outcome, not itself an audit inconsistency.
    a.check('thinking_anomaly_flag_matches_raw', result.get('unexpected_thinking_with_disabled_request') is bool(thinking), [folder/'result.json',folder/'raw_stream.bin'])
    return response, bool(thinking)


def calls_check(a, folder, kind, inventory_runtime):
    snapshot_check(a,folder)
    runtime_path = folder/'runtime_pinned.json'; runtime = a.json(runtime_path)
    if runtime is not None and inventory_runtime is not None:
        a.check(kind+'_runtime_pin_matches_inventory', all(runtime.get(k) == inventory_runtime.get(k) for k in PINS), [runtime_path])
    summary = a.json(folder/'summary.json')
    calls = {}; unexpected_thinking = []
    for call_folder in sorted(folder.glob('http_*')):
        if not call_folder.is_dir():continue
        rp, qp = call_folder/'result.json', call_folder/'request.json'
        result, envelope = a.json(rp), a.json(qp)
        if envelope is None:continue
        request = envelope.get('body', {})
        a.check('call_request_envelope', envelope.get('path') == '/api/chat' and envelope.get('kind') == kind,
                [qp])
        cap = 256 if kind == 'diagnose' else 8192
        valid = request.get('model') == MODEL and request.get('think') is False and request.get('stream') is True and request.get('format') == 'json' and request.get('keep_alive') == 0 and request.get('options') == {'temperature':0,'num_predict':cap,'num_ctx':65536}
        a.check(kind+'_call_settings', valid, [qp])
        if result is not None:
            a.check('call_kind_and_folder_match', result.get('kind') == kind and result.get('folder') == call_folder.name and result.get('no_automatic_retry') is True, [rp])
            response, thinking = stream_check(a,call_folder,result)
        else:
            response, thinking = None, False
        if thinking:unexpected_thinking.append(call_folder.name)
        calls[call_folder.name] = {'request':request,'response':response,'result':result or {},'folder':call_folder}
        observed = call_folder/'runtime_observation.json'
        if observed.is_file():pin_check(a,runtime,a.json(observed),[runtime_path,observed])
    if summary is not None:
        count_key = 'diagnostic_calls' if kind == 'diagnose' else 'pilot_model_calls'
        a.check(kind+'_summary_call_count', summary.get(count_key) == len(calls), [folder/'summary.json'])
        listed = summary.get('calls',[])
        a.check(kind+'_summary_call_records', len(listed) == len(calls) and len({x.get('folder') for x in listed}) == len(listed) and
                all(x.get('folder') in calls and calls[x['folder']]['result'] == x for x in listed), [folder/'summary.json'])
        a.check(kind+'_main_calls_remain_zero', summary.get('main_model_calls') == 0, [folder/'summary.json'])
    if kind == 'diagnose':
        for call in calls.values():
            a.check('diagnostic_is_synthetic_not_institution_task', call['request'].get('messages') ==
                    [{'role':'user','content':'Return exactly this JSON object: {"ready":true}'}], [call['folder']/'request.json'])
    if calls and not all((x['folder']/'runtime_observation.json').is_file() for x in calls.values()):
        a.limitations.append(kind+': live digest/template/engine checks are implemented in the deployed coordinator, but their per-call observations were not persisted. Request settings, initial inventory pins and response model tags are independently reconciled; per-call live pins are not independently reconstructed.')
    return runtime, summary, calls, unexpected_thinking


def pilot_check(a, folder, packets, market, hashes, inventory_runtime):
    from run_sector_workflow import SYSTEM, stage_message, evidence_ids, conservative_context_bound
    from sector_engine import parse_response, calculate_portfolio
    if not folder.is_dir():
        a.pending('pilot_artifacts_received', [folder], 'No pilot execution or failure is inferred from absent local files.')
        return {'artifact_status':'not_received', 'attempted_cases':None,'completed_cases':None,'not_started_cases':None,
                'attempted_http_calls':None,'completed_stage_records':None}
    runtime, outer, calls, thinking = calls_check(a,folder,'pilot',inventory_runtime)
    base = folder/'pilot'; summary = a.json(base/'summary.json'); roster = a.json(base/'planned_cases.json')
    saved_runtime = a.json(base/'runtime.json')
    if saved_runtime is not None:
        a.check('pilot_saved_runtime_matches_pin', saved_runtime.get('settings') == runtime and
                saved_runtime.get('split') == 'pilot', [base/'runtime.json',folder/'runtime_pinned.json'])
    a.json(base/'dependencies.json')
    recorded_hashes = a.json(base/'input_hashes.json')
    expected_hashes = {'packets_sha256':hashes.get(DEPLOYED[-1]),'market_sha256':hashes.get(DEPLOYED[-2]),
                       'coordinator_sha256':hashes.get(DEPLOYED[0]),'runner_sha256':hashes.get(DEPLOYED[1]),'engine_sha256':hashes.get(DEPLOYED[2])}
    if recorded_hashes is not None:a.check('pilot_execution_input_hashes',recorded_hashes == expected_hashes,[base/'input_hashes.json'])
    case_ids = [source+'__'+arm for source in SOURCES for arm in ('R1','R4')]
    if roster is not None:a.check('pilot_roster_exact_four_cases',[x.get('case_id') for x in roster] == case_ids,[base/'planned_cases.json'])
    reported = summary.get('records',[]) if summary is not None else []
    by_id = {x.get('case_id'):x for x in reported}
    if summary is not None:
        a.check('pilot_summary_preserves_full_roster', [x.get('case_id') for x in reported] == case_ids,[base/'summary.json'])
    packet_map = {p['source_id']:p for p in packets}; results = []; used_calls = []
    total_stage_records = 0
    for source in SOURCES:
        for arm in ('R1','R4'):
            cid = source+'__'+arm; target = base/cid; row = by_id.get(cid,{})
            if source not in packet_map or market is None:
                a.pending('pilot_public_inputs_available_for_reconstruction',[target]);continue
            packet = packet_map[source]; messages = [{'role':'system','content':SYSTEM}]
            stage_records = []; requests = 0
            folders = row.get('http_call_folders',[])
            used_calls.extend(folders)
            for stage in range(1,5):
                request_path = target/f'stage{stage}_request.json'
                if not request_path.exists():break
                requests += 1
                messages.append(stage_message(stage,arm,packet,market))
                request = a.json(request_path)
                a.check(cid+f':stage{stage}:exact_history_and_evidence_onset', request == messages, [request_path])
                if len(folders) >= stage:
                    call = calls.get(folders[stage-1])
                    a.check(cid+f':stage{stage}:HTTP_matches_saved_request', call is not None and call['request'].get('messages') == request,
                            [request_path]+([call['folder']/'request.json'] if call else []))
                    if request is not None:a.check(cid+f':stage{stage}:context_screen_passed_before_HTTP',conservative_context_bound(request)+8192<=65536,[request_path])
                else:call = None
                response_path = target/f'stage{stage}_response.json'
                response = a.json(response_path,required=False)
                if response is not None:
                    a.check(cid+f':stage{stage}:raw_response_matches_HTTP',call is not None and call['response'] == response,
                            [response_path]+([call['folder']/'response.json'] if call else []))
                record_path = target/f'stage{stage}_record.json'; record = a.json(record_path,required=False)
                if record is None:break
                stage_records.append(record); total_stage_records += 1
                content = (response or {}).get('message',{}).get('content')
                parsed = parse_response(content) if isinstance(content,str) else {'ok':False}
                valid = parsed.get('ok') and (response or {}).get('done_reason') != 'length'
                a.check(cid+f':stage{stage}:record_has_complete_parsed_response',bool(valid),[record_path,response_path])
                if not valid:break
                value = parsed['value']; visible = evidence_ids(packet) if arm=='R1' or stage==4 else []
                expected_calc = calculate_portfolio(value.get('weights',[]),market=market,visible_evidence_ids=visible,
                                                    submitted_constraints=value.get('submitted_constraints',[]))
                a.check(cid+f':stage{stage}:record_and_calculator_recomputed',
                        record.get('raw_proposal') == value and calculator_equal(record.get('calculator_result'), expected_calc) and
                        record.get('visible_evidence_ids') == visible and record.get('repair_applied') is False and
                        record.get('history_policy') == 'explicit_final_content' and record.get('stage') == stage and
                        record.get('calculator_arguments') == {'weights':value.get('weights',[]),'submitted_constraints':value.get('submitted_constraints',[])},
                        [record_path,response_path])
                messages.append({'role':'assistant','content':content})
                if stage<4:messages.append({'role':'user','content':json.dumps({'calculator_feedback':record.get('calculator_result')},ensure_ascii=False,allow_nan=False)})
            final = a.json(target/'final.json',required=False); trace = a.json(target/'trace.json',required=False)
            failure = a.json(target/'failure.json',required=False)
            outer_failure = a.json(base/(cid+'_coordinator_failure.json'),required=False)
            if target.is_dir():
                request_names = {p.name for p in target.glob('stage*_request.json')}
                a.check(cid+':no_missing_or_extra_stage_requests', request_names ==
                        {f'stage{s}_request.json' for s in range(1, requests+1)} and len(folders) <= requests,
                        [target])
            complete = len(stage_records)==4 and final is not None and trace is not None and failure is None and outer_failure is None
            if complete:a.check(cid+':final_and_trace_match_preserved_records',trace==stage_records and final==stage_records[-1].get('raw_proposal'),[target/'final.json',target/'trace.json'])
            inferred = 'completed' if complete else 'failed' if failure is not None or outer_failure is not None else 'incomplete_artifacts' if requests or folders else 'not_started' if summary is not None else 'not_observed'
            if summary is not None:
                a.check(cid+':reported_case_status_reconciles',row.get('status')==inferred,[base/'summary.json',target])
                if inferred != 'not_started':a.check(cid+':reported_http_attempts_reconcile',row.get('model_calls_attempted')==len(folders),[base/'summary.json'])
            if failure is not None:a.check(cid+':failed_case_retained',failure.get('excluded') is False,[target/'failure.json'])
            results.append({'case_id':cid,'status_from_artifacts':inferred,'stage_requests':requests,'completed_stage_records':len(stage_records),
                            'reported_http_call_folders':folders,'has_failure_record':failure is not None or outer_failure is not None})
    if summary is not None:
        a.check('pilot_HTTP_requests_assigned_once',len(used_calls)==len(set(used_calls)) and set(used_calls)==set(calls),[base/'summary.json'])
        if thinking:
            affected = [index for index,row in enumerate(reported)
                        if set(row.get('http_call_folders',[])) & set(thinking)]
            a.check('unexpected_thinking_stopped_case_and_remaining_roster', len(affected)==1 and
                    reported[affected[0]].get('status')=='failed' and
                    all(row.get('status')=='not_started' for row in reported[affected[0]+1:]),
                    [base/'summary.json'], 'A captured protocol violation can be faithfully audited; it is not a successful four-stage case.')
    counts=Counter(x['status_from_artifacts'] for x in results)
    attempted=sum(counts[x] for x in ('completed','failed','incomplete_artifacts'))
    if summary is not None:
        a.check('pilot_case_and_call_counts_reconciled',summary.get('planned_runs')==4 and summary.get('attempted_runs')==attempted and
                summary.get('completed_runs')==counts['completed'] and summary.get('pilot_model_calls')==len(calls) and summary.get('main_model_calls')==0,[base/'summary.json'])
        if outer is not None:a.check('outer_and_inner_pilot_summary_agree',all(outer.get(k)==summary.get(k) for k in ('planned_runs','attempted_runs','completed_runs','records','pilot_model_calls','main_model_calls','status')),[folder/'summary.json',base/'summary.json'])
    return {'artifact_status':'received','attempted_cases':attempted,'completed_cases':counts['completed'],
            'not_started_cases':counts['not_started'] if summary is not None else None,
            'failed_cases':counts['failed'],'attempted_http_calls':len(calls),
            'completed_http_streams':sum(x['result'].get('status')=='completed' for x in calls.values()),
            'completed_stage_records':total_stage_records,'unexpected_thinking_call_folders':thinking,'cases':results}


def build_audit(root=ROOT, received=None, pilot_dir=None, archive=None):
    root=Path(root).resolve();received=Path(received or root/'data/remote_sector_20261018').resolve()
    pilot_dir=Path(pilot_dir or received/'data/sector_runtime/pilot_v43').resolve()
    archive=Path(archive or root/'tmp/sector_bridge_20261018/bundle.tar.gz').resolve()
    a=Audit(root)
    packets,market,hashes=deployment(a,received,archive)
    runtime=inventory_check(a,received/'data/sector_runtime/inventory_v43')
    _,diagnostic,calls,thinking=calls_check(a,received/'data/sector_runtime/diagnose_v43','diagnose',runtime)
    pilot=pilot_check(a,pilot_dir,packets,market,hashes,runtime)
    a.stable()
    counts=Counter(c['status'] for c in a.checks)
    status='fail' if counts['fail'] else 'partial_evidence' if counts['not_observed'] else 'pass_with_stated_limits'
    return {'schema_version':'remote_sector_artifact_audit_1.0','generated_at_utc':datetime.now(timezone.utc).isoformat(),
            'status':status,'scope':'Saved artifact consistency only; no strategy-performance or semantic correctness verdict.',
            'inputs':{'received_root':a.path(received),'pilot_dir':a.path(pilot_dir),'deployment_archive':a.path(archive)},
            'audit_actions':{'model_calls':0,'network_calls':0,'runtime_records_modified':False,'evaluation_files_modified':False},
            'calculator_recomputation_tolerance':{'relative':CALC_REL_TOL,'absolute':CALC_ABS_TOL,
                'basis':'Engineering allowance for cross-platform floating-point arithmetic; not a paper-derived acceptance threshold. Saved history strings and raw proposals are compared exactly.'},
            'human_semantic_review':{'performed':False,'status':'not_assessed_by_this_script'},
            'main_execution_or_freeze':{'performed':False,'status':'not_certified_by_this_script'},
            'diagnostic':{'attempted_http_calls':len(calls),'reported_status':(diagnostic or {}).get('status'),
                          'completed_http_streams':sum(x['result'].get('status')=='completed' for x in calls.values()),
                          'unexpected_thinking_call_folders':thinking,'included_in_pilot_counts':False},
            'pilot':pilot,'check_counts':dict(counts),'checks':a.checks,
            'limitations':a.limitations+['Request-history reconstruction does not reveal the effective server-rendered prompt or independently verify absence of server truncation.',
                                       'Missing local artifacts are not evidence that remote execution did not occur. HTTP attempts and complete four-stage cases are separate counts.',
                                       'No evaluator-only gold is read. Calculator recomputation verifies arithmetic and exposed evidence IDs, not the validity of allocation reasons.'],
            'evidence_files':a.evidence,'audit_script_sha256':sha(Path(__file__).read_bytes())}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--received-root',type=Path)
    parser.add_argument('--pilot-dir',type=Path)
    parser.add_argument('--bundle',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--stdout-only',action='store_true',help='Validate and print the summary without writing an audit file')
    args=parser.parse_args(argv)
    report=build_audit(args.root,args.received_root,args.pilot_dir,args.bundle)
    destination=args.output or args.root/'research/remote_sector_audit_20261018.json'
    if not args.stdout_only:
        if not destination.resolve().is_relative_to((args.root/'research').resolve()) or destination.suffix!='.json':
            raise ValueError('Audit output must be a JSON file under research, outside runtime/evaluation records')
        if str(destination.resolve()) in {str((args.root/p).resolve()) for p in report['evidence_files']}:
            raise ValueError('Audit output cannot overwrite evidence')
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':report['check_counts'],'pilot':report['pilot'],
                      'diagnostic':report['diagnostic'],'output':None if args.stdout_only else str(destination),
                      'failed_checks':[x for x in report['checks'] if x['status']=='fail']},ensure_ascii=False,indent=2))
    return 1 if report['status']=='fail' else 0


if __name__=='__main__':
    raise SystemExit(main())
