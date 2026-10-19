"""Read-only integration of postprocessors against the still-running pilot.

No output content is opened, no model request is made, and no service is stopped.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import analyze_v492_pilot as analyzer
import build_v492_masked_review as masked
import watch_v492_postpilot as watcher

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'data/local_sector_runtime/v492_pilot_20261019'
CONFIG = ROOT / 'research/v492_postpilot_config_20261019.json'
OUTPUT = ROOT / 'research/v492_postprocessing_integration_20261019.json'
checks = []


def check(name, condition):
    checks.append({'check': name, 'pass': bool(condition)})
    if not condition:
        raise AssertionError(name)


def main():
    check('new receipt only', not OUTPUT.exists())
    check('actual pilot started', (RUN / 'execution_started.json').is_file())
    check('pilot still running; no terminal summary opened', not (RUN / 'pilot_summary.json').exists())
    config_sha = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    result = watcher.watch(ROOT, CONFIG, config_sha, dry_run=True)
    check('actual frozen configuration passes dry run', result['status'] == 'dry_run_validated_no_commands')
    check('dry run does not generate or shut down', result['model_calls'] == 0 and result['shutdown_performed'] is False)
    config = json.loads(CONFIG.read_text(encoding='utf8'))
    check('dry run creates no watcher status', not (ROOT / config['status_path']).exists())
    check('dry run creates no postprocessing output', not (ROOT / config['analysis_output']).exists())
    for role, expected in watcher.SCRIPTS.items():
        ref = config['scripts'][role]
        check('pinned current script: ' + role, ref['path'] == expected and hashlib.sha256((ROOT / expected).read_bytes()).hexdigest() == ref['sha256'])
    with patch.object(analyzer, 'read_json', side_effect=AssertionError('Analyzer must not open a live output')):
        try:
            analyzer.analyze(RUN)
        except ValueError as exc:
            check('analyzer rejects live run before reads', 'pilot_summary.json absent' in str(exc))
        else:
            raise AssertionError('Live analyzer unexpectedly ran')
    judge = ROOT / 'research/artifacts/v492_root_live_guard_20261019/judge'
    private = ROOT / 'research/artifacts/v492_root_live_guard_20261019/private'
    with patch.object(masked, 'read', side_effect=AssertionError('Masker must not open a live output')):
        try:
            masked.build(RUN, judge, private)
        except ValueError as exc:
            check('masker rejects live run before reads', 'pilot_summary.json required' in str(exc))
        else:
            raise AssertionError('Live masker unexpectedly ran')
    check('live rejection leaves no judge or mapping directories', not judge.exists() and not private.exists())
    check('owned service not stopped by integration', not (ROOT / config['service_evidence_dir'] / 'service_shutdown_receipt.json').exists())
    record = {'status': 'PASS', 'round': 3, 'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Actual immutable config/dry-run and live-output rejection; not pilot completion or semantic validation.',
              'config_ref': {'path': CONFIG.relative_to(ROOT).as_posix(), 'sha256': config_sha},
              'script_refs': config['scripts'], 'checks': checks, 'model_calls': 0,
              'actual_model_output_content_read': False, 'shutdown_performed': False,
              'dry_run': result}
    with OUTPUT.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': 'PASS', 'checks': len(checks), 'output': str(OUTPUT)}))


if __name__ == '__main__':
    main()
