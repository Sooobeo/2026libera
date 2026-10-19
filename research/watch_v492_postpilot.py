"""One-shot offline postprocessing after the declared pilot has safely ended.

No generation, semantic scoring, archive/deletion, or changes to frozen code.
The root agent must prepare/review the configuration and explicitly launch watch.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CASES = ['fidelity_q2_2026__E', 'fidelity_q2_2026__L', 'ubs_june_2026__E', 'ubs_june_2026__L', 'common_market_only__C']
SCRIPTS = {'analysis': 'research/analyze_v492_pilot.py', 'masked': 'research/build_v492_masked_review.py', 'shutdown': 'research/stop_sector_v492_cpu.ps1'}


def now():
    return datetime.now(timezone.utc).isoformat()


def path(root, value):
    p = (root / value).resolve()
    if not p.is_relative_to(root.resolve()):
        raise ValueError('Path escapes workspace: ' + str(value))
    return p


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def ref(root, p):
    p = path(root, p)
    return {'path': p.relative_to(root).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


def checked(root, item):
    if ref(root, item['path'])['sha256'] != item['sha256']:
        raise ValueError('Pinned artifact changed: ' + item['path'])
    return path(root, item['path'])


def refs_in(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            yield value
        for child in value.values():
            yield from refs_in(child)
    elif isinstance(value, list):
        for child in value:
            yield from refs_in(child)


def atomic_json(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_name(p.name + '.writing')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    os.replace(temp, p)


def preflight(root, config):
    if config.get('version') != 'v492_postpilot_watcher_1' or config.get('poll_seconds') != 30 or config.get('observer_lifetime_seconds') != 86400 or config.get('stable_invalid_summary_limit') != 3:
        raise ValueError('Expected fixed watcher version and 30-second poll interval')
    for item in refs_in(config):
        checked(root, item)
    for role, filename in SCRIPTS.items():
        if config['scripts'][role]['path'] != filename:
            raise ValueError('Unexpected postprocessor role/path')
    run = path(root, config['run_dir'])
    declaration = read(checked(root, config['declaration_ref']))
    if checked(root, config['declaration_ref']) != run / 'pilot_declaration.json':
        raise ValueError('Declaration is not for this run')
    gate = read(checked(root, config['gate_ref']))
    freeze = read(checked(root, config['freeze_ref']))
    if (declaration.get('review_gate', {}).get('path') != config['gate_ref']['path'] or
            declaration['review_gate']['sha256'] != config['gate_ref']['sha256'] or
            gate.get('freeze_ref', {}).get('path') != config['freeze_ref']['path'] or
            gate['freeze_ref']['sha256'] != config['freeze_ref']['sha256']):
        raise ValueError('Declaration/gate/freeze identity differs')
    if (declaration.get('purpose') != 'pilot_only' or declaration.get('case_order') != CASES or
            declaration.get('max_generation_requests') != 10 or declaration.get('automatic_retries') != 0 or
            declaration.get('main_model_calls') != 0 or declaration.get('main_frozen') is not False or
            freeze.get('status') != 'frozen_for_pilot_only' or freeze.get('main_allowed') is not False or
            gate.get('status') != 'approved_for_pilot_before_generation'):
        raise ValueError('Only the frozen five-case, no-retry pilot is allowed')
    for item in refs_in(freeze):
        checked(root, item)
    runtime = read(checked(root, freeze['runtime_ref']))
    if declaration.get('runtime') != runtime or declaration.get('runtime_sha256') != freeze['runtime_ref']['sha256']:
        raise ValueError('Declared runtime differs from freeze')
    service = read(checked(root, config['service_ref']))
    evidence = path(root, config['service_evidence_dir'])
    if checked(root, config['service_ref']) != evidence / 'service_receipt.json' or service.get('origin') != declaration.get('origin') or service.get('origin') != 'http://127.0.0.1:11435' or service.get('status') != 'ready':
        raise ValueError('Owned service evidence differs from pilot origin')
    for key in ['analysis_output', 'judge_dir', 'mapping_dir', 'status_path']:
        path(root, config[key])
    judge, private = path(root, config['judge_dir']), path(root, config['mapping_dir'])
    if judge == private or judge.is_relative_to(private) or private.is_relative_to(judge):
        raise ValueError('Judge and private mapping must be separate sibling trees')
    return declaration


def valid_summary(root, config):
    """Return completed records only; partial JSON/shape waits without a retry."""
    run = path(root, config['run_dir'])
    summary = read(run / 'pilot_summary.json')
    if not isinstance(summary, dict):
        raise ValueError('Summary must be a JSON object')
    if summary.get('status') not in ['stopped', 'pilot_attempt_sequence_finished']:
        raise ValueError('Pilot summary is not terminal')
    if [c.get('case_id') for c in summary.get('cases', [])] != CASES:
        raise ValueError('Terminal summary must retain all five ordered cases')
    for key in ['main_model_calls', 'automatic_retries', 'post_final_calls']:
        if type(summary.get(key)) is not int or summary[key] != 0:
            raise ValueError('Disallowed main/retry/post-final count')
    if (summary.get('frozen_for_pilot') is not True or summary.get('main_frozen') is not False or
            summary.get('AI_preoutput_review_completed') is not True or
            summary.get('review_mode') != 'AI_delegated_by_user' or
            summary.get('independent_human_review_completed') is not False):
        raise ValueError('Summary review/freeze flags differ')
    total, cleanup, declared_folders = 0, [], set()
    for row in summary['cases']:
        stages = row.get('stages', [])
        if [s.get('stage') for s in stages] not in [[], ['D0'], ['D0', 'F0']] or not isinstance(row.get('status'), str):
            raise ValueError('Invalid stage order or missing case outcome')
        allowed = ['not_attempted_after_stop', 'cancelled_before_stage'] if not stages else ['cancelled_before_stage', 'incomplete_first_attempt_retained', 'stopped_for_integrity_or_cancellation', 'two_stages_completed_semantic_review_pending']
        if row['status'] not in allowed or (row['status'] == 'two_stages_completed_semantic_review_pending' and (len(stages) != 2 or not all(s.get('continuation_eligible') is True for s in stages))):
            raise ValueError('Case outcome is inconsistent with retained stages')
        if len(stages) == 2 and (stages[0].get('status') != 'completed' or stages[0].get('continuation_eligible') is not True):
            raise ValueError('F0 cannot follow an ineligible draft')
        for stage in stages:
            count = stage.get('generation_requests_attempted')
            if type(count) is not int or count not in [0, 1] or type(stage.get('continuation_eligible')) is not bool:
                raise ValueError('Stage count/continuation type is invalid')
            total += count
            folder = run / (row['case_id'] + '__' + stage['stage'])
            declared_folders.add(folder.name)
            transport = read(folder / 'transport_result.json')
            if any(stage.get(k) != transport.get(k) for k in ['status', 'generation_requests_attempted', 'continuation_eligible']):
                raise ValueError('Summary stage differs from transport receipt')
            clean = read(folder / 'unload_and_residency.json')
            cleanup.append({'case_id': row['case_id'], 'stage': stage['stage'], 'status': clean.get('status'),
                            'receipt': ref(root, folder / 'unload_and_residency.json')})
    if type(summary.get('generation_requests_attempted')) is not int or total != summary['generation_requests_attempted'] or total > 10:
        raise ValueError('Total first-attempt count differs')
    observed_folders = {p.name for p in run.iterdir() if p.is_dir() and p.name.endswith(('__D0', '__F0'))}
    if observed_folders != declared_folders:
        raise ValueError('Stage directory accounting differs from completed summary')
    return summary, cleanup


def commands(root, config):
    py = config['python_executable']
    common = [py, '-B', '-X', 'utf8']
    return {
        'analysis': common + [str(path(root, SCRIPTS['analysis'])), '--run-dir', str(path(root, config['run_dir'])), '--output', str(path(root, config['analysis_output']))],
        'masked': common + [str(path(root, SCRIPTS['masked'])), '--run-dir', str(path(root, config['run_dir'])), '--output-dir', str(path(root, config['judge_dir'])), '--mapping-dir', str(path(root, config['mapping_dir']))],
        'shutdown': ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(path(root, SCRIPTS['shutdown'])), '-EvidenceDirectory', str(path(root, config['service_evidence_dir']))],
    }


def subprocess_once(argv, *, root, stdout, stderr, timeout):
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with stdout.open('xb') as out, stderr.open('xb') as err:
        result = subprocess.run(argv, cwd=root, stdout=out, stderr=err, timeout=timeout, shell=False, creationflags=flags)
    return result.returncode


def process_once(root, config, summary, cleanup, status, runner=subprocess_once):
    """Each step attempted once; processing failure does not bypass safe cleanup."""
    calls = commands(root, config)
    status['state'] = 'postprocessing'; status['summary_ref'] = ref(root, path(root, config['run_dir']) / 'pilot_summary.json')
    status['pilot_status'] = summary['status']; status['generation_requests_attempted'] = summary['generation_requests_attempted']
    status['stage_cleanup_records'] = cleanup; status['steps'] = []
    status_path = path(root, config['status_path'])
    logdir = status_path.parent / (status_path.stem + '_logs')
    logdir.mkdir(exist_ok=True)
    all_processing_ok = True
    def step(role):
        entry = {'role': role, 'started_at_utc': now(), 'command': calls[role], 'automatic_retry': False}
        status['steps'].append(entry); atomic_json(status_path, status)
        try:
            checked(root, config['scripts'][role])
            code = runner(calls[role], root=root, stdout=logdir / (role + '.stdout.txt'), stderr=logdir / (role + '.stderr.txt'), timeout=180 if role == 'shutdown' else 600)
            entry['returncode'] = code
            if code != 0:
                raise RuntimeError('Command returned nonzero: ' + str(code))
            if role == 'analysis':
                read(path(root, config['analysis_output']))
                entry['artifact_ref'] = ref(root, config['analysis_output'])
            elif role == 'masked':
                marker = read(path(root, config['judge_dir']) / 'COMPLETE.json')
                if marker.get('status') != 'complete' or marker.get('items') != 5 or marker.get('scoring_performed') is not False:
                    raise ValueError('Masked bundle completion marker invalid')
                entry['artifact_ref'] = ref(root, path(root, config['judge_dir']) / 'COMPLETE.json')
                entry['private_mapping_ref'] = ref(root, path(root, config['mapping_dir']) / 'private_mapping.json')
            else:
                receipt = path(root, config['service_evidence_dir']) / 'service_shutdown_receipt.json'
                stop = read(receipt)
                if stop.get('status') != 'owned_pilot_service_stopped' or any(stop.get(k) is not True for k in ['no_resident_models_before_stop', 'owned_port_closed', 'existing_11434_listener_unchanged']):
                    raise ValueError('Owned shutdown did not confirm isolation and idle state')
                entry['artifact_ref'] = ref(root, receipt)
            entry['status'] = 'completed'
        except Exception as exc:
            entry.update(status='failed_no_retry', error_type=type(exc).__name__, error=str(exc))
        finally:
            entry['finished_at_utc'] = now(); atomic_json(status_path, status)
        return entry['status'] == 'completed'
    try:
        for role in ['analysis', 'masked']:
            # Non-short-circuit evaluation ensures both independent tasks run once.
            okay = step(role); all_processing_ok = all_processing_ok and okay
    finally:
        if all(x['status'] == 'no_resident_models_observed' for x in cleanup):
            # With zero attempted stages, the frozen stop script itself checks
            # /api/ps before any process termination. No generation call occurs.
            stopped = step('shutdown')
        else:
            stopped = False
            status['steps'].append({'role': 'shutdown', 'status': 'not_attempted_cleanup_not_confirmed', 'automatic_retry': False})
        status['state'] = 'completed_semantic_review_pending' if all_processing_ok and stopped else 'completed_with_errors_attention_required'
        status['semantic_evaluation'] = 'pending_AI_assisted_review_not_automatically_scored'
        status['owned_service_stopped'] = stopped
        status['finished_at_utc'] = now(); atomic_json(status_path, status)
    return status


def prepare_config(root, target, run_dir, service_dir, status_path):
    target = path(root, target)
    if target.exists():
        raise ValueError('Configuration already exists')
    run, evidence = path(root, run_dir), path(root, service_dir)
    decl = read(run / 'pilot_declaration.json'); gate_ref = decl['review_gate']; gate = read(checked(root, gate_ref))
    config = {'version': 'v492_postpilot_watcher_1', 'created_at_utc': now(), 'poll_seconds': 30,
              'observer_lifetime_seconds': 86400, 'stable_invalid_summary_limit': 3,
              'observer_limit_basis': 'Explicit engineering observer limits: three unchanged invalid summary polls and a 24-hour watcher lifetime. Neither changes a model-stage deadline, creates a retry, or stops active model work.',
              'python_executable': sys.executable, 'run_dir': run.relative_to(root).as_posix(),
              'service_evidence_dir': evidence.relative_to(root).as_posix(), 'status_path': path(root, status_path).relative_to(root).as_posix(),
              'declaration_ref': ref(root, run / 'pilot_declaration.json'), 'gate_ref': {k: gate_ref[k] for k in ['path', 'sha256']},
              'freeze_ref': {k: gate['freeze_ref'][k] for k in ['path', 'sha256']}, 'service_ref': ref(root, evidence / 'service_receipt.json'),
              'watcher_ref': ref(root, 'research/watch_v492_postpilot.py'),
              'scripts': {role: ref(root, filename) for role, filename in SCRIPTS.items()},
              'analysis_output': 'research/v492_pilot_arithmetic_20261019.json',
              'judge_dir': 'research/artifacts/v492_pilot_review_20261019/judge',
              'mapping_dir': 'research/artifacts/v492_pilot_review_20261019/private',
              'model_calls': 0, 'semantic_scoring': False, 'automatic_retry': False, 'archive_or_delete': False}
    preflight(root, config)
    for key in ['analysis_output', 'judge_dir', 'mapping_dir', 'status_path']:
        if path(root, config[key]).exists():
            raise ValueError('Output already exists; no reuse or automatic retry: ' + key)
    atomic_json(target, config)
    return ref(root, target)


def watch(root, config_path, expected_sha, *, dry_run=False, runner=subprocess_once, sleeper=time.sleep, max_polls=None, clock=time.monotonic):
    config_ref = {'path': path(root, config_path).relative_to(root).as_posix(), 'sha256': expected_sha}
    config = read(checked(root, config_ref)); preflight(root, config)
    status_path = path(root, config['status_path'])
    if dry_run:
        return {'status': 'dry_run_validated_no_commands', 'config_ref': config_ref, 'commands': commands(root, config), 'model_calls': 0, 'shutdown_performed': False}
    if status_path.exists():
        raise ValueError('Watcher status already exists; no automatic resume')
    lock = status_path.with_name(status_path.name + '.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('x', encoding='utf8') as f:
        f.write(json.dumps({'pid': os.getpid(), 'started_at_utc': now(), 'config_ref': config_ref}))
    status = {'watcher_version': config['version'], 'started_at_utc': now(), 'pid': os.getpid(), 'config_ref': config_ref,
              'state': 'waiting_pilot_summary', 'model_calls': 0, 'semantic_evaluation': 'pending', 'automatic_retry': False,
              'archive_or_delete': False, 'launch_script_refs': config['scripts'], 'poll_seconds': 30}
    polls = 0; started_monotonic = clock(); invalid_hash = None; invalid_count = 0
    try:
        while True:
            if clock() - started_monotonic >= config['observer_lifetime_seconds']:
                status.update(state='observer_lifetime_exceeded_attention_required', finished_at_utc=now(),
                              reason='24-hour observer limit reached; no model cancellation, postprocessing, shutdown or retry performed.')
                atomic_json(status_path, status); return status
            # Small identity checks only while waiting; no model or HTTP request.
            checked(root, config_ref); checked(root, config['declaration_ref']); checked(root, config['freeze_ref'])
            status['last_checked_at_utc'] = now(); polls += 1; status['polls'] = polls
            try:
                summary, cleanup = valid_summary(root, config)
            except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
                status['state'] = 'waiting_valid_completed_pilot_summary'
                status['last_wait_reason'] = type(exc).__name__ + ': ' + str(exc)
                candidate = path(root, config['run_dir']) / 'pilot_summary.json'
                try:
                    current_hash = ref(root, candidate)['sha256']
                except OSError:
                    current_hash = None
                invalid_count = (invalid_count + 1 if current_hash == invalid_hash else 1) if current_hash else 0
                invalid_hash = current_hash
                status['unchanged_invalid_summary_polls'] = invalid_count
                if invalid_count >= config['stable_invalid_summary_limit']:
                    status.update(state='stable_invalid_summary_attention_required', finished_at_utc=now(),
                                  reason='Same summary bytes failed completion/transport validation in three consecutive polls. No shutdown: completed run identity not established.')
                    atomic_json(status_path, status); return status
                atomic_json(status_path, status)
                if max_polls is not None and polls >= max_polls:
                    return status  # Test hook; CLI never supplies this.
                sleeper(30); continue
            status.pop('last_wait_reason', None)
            return process_once(root, config, summary, cleanup, status, runner=runner)
    except Exception as exc:
        status.update(state='watcher_error_no_retry', error_type=type(exc).__name__, error=str(exc), finished_at_utc=now())
        atomic_json(status_path, status)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare-config')
    prep.add_argument('--config', required=True); prep.add_argument('--run-dir', required=True)
    prep.add_argument('--service-evidence-dir', required=True); prep.add_argument('--status-path', required=True)
    run = sub.add_parser('watch'); run.add_argument('--config', required=True); run.add_argument('--config-sha', required=True); run.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    result = prepare_config(ROOT, args.config, args.run_dir, args.service_evidence_dir, args.status_path) if args.command == 'prepare-config' else watch(ROOT, args.config, args.config_sha, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get('state', '').endswith('attention_required') else 0


if __name__ == '__main__':
    raise SystemExit(main())
