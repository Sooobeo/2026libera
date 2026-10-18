"""Record a narrow phase transition only after three audits of one settled run."""
import argparse
import hashlib
import json
from pathlib import Path
from research_progress_log import ROOT, append, read_verified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['priority1', 'priority2', 'priority3', 'pilot_integration'], required=True)
    parser.add_argument('--audit', type=Path, action='append', required=True)
    parser.add_argument('--detail', required=True)
    args = parser.parse_args()
    if len(args.audit) != 3 or len({p.resolve() for p in args.audit}) != 3:
        raise ValueError('Exactly three distinct audit files required')
    reports = [json.loads(p.read_text(encoding='utf-8-sig')) for p in args.audit]
    if {x.get('round') for x in reports} != {1, 2, 3}:
        raise ValueError('Three named rounds required')
    if any(x.get('phase') != args.phase or x.get('all_passed') is not True for x in reports):
        raise ValueError('All three phase-scoped audits must pass')
    if len({x.get('run_dir') for x in reports}) != 1 or not reports[0].get('run_dir'):
        raise ValueError('Audits must address the same recorded run')
    all_refs = {}
    review_paths = []
    for report in reports:
        if report.get('failed_checks'):
            raise ValueError('Audit contains failures')
        if report.get('audit_completed') is not True or report.get('not_observed_checks'):
            raise ValueError('Audit is incomplete or contains unobserved requirements')
        if not report.get('checks') or any(check.get('status') != 'pass' for check in report['checks']):
            raise ValueError('Audit check does not pass')
        refs = report.get('source_files', report.get('sources', []))
        if not refs:
            raise ValueError('Audit must identify its source artifacts')
        these_paths = set()
        for ref in refs:
            path = Path(ref['path'])
            path = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != ref['sha256']:
                raise ValueError('Audited artifact changed: ' + str(path))
            if str(path) in all_refs and all_refs[str(path)] != actual:
                raise ValueError('Audits reference different versions')
            all_refs[str(path)] = actual
            these_paths.add(str(path))
        review_paths.append(these_paths)
    shared = set.intersection(*review_paths)
    run_path = (ROOT / reports[0]['run_dir']).resolve()
    if str(run_path / 'summary.json') not in shared:
        raise ValueError('All three audits must hash the same settled run summary')
    summary = json.loads((run_path / 'summary.json').read_text(encoding='utf-8-sig'))
    if args.phase == 'priority1':
        expected = {'4.6': ('completed_one_diagnostic', 1),
                    '4.7': ('completed_plan_execute_diagnostic', 2)}.get(summary.get('protocol_version'))
        if expected is None:
            raise ValueError('Unregistered priority1 diagnostic protocol')
        if not (
            summary.get('status') == expected[0]
            and summary.get('numeric_acceptance') is True
            and summary.get('weight_vector_changed') is True
            and summary.get('generation_requests_attempted') == expected[1]
            and summary.get('http_streams_completed') == expected[1]
            and summary.get('main_model_calls') == summary.get('automatic_retries') == 0):
            raise ValueError('The recorded priority1 diagnostic did not actually succeed')
        if expected[1] == 2 and not (summary.get('planner_contract_satisfied') is True
                                    and summary.get('planner_completed') is True
                                    and summary.get('executor_completed') is True):
            raise ValueError('Planning and execution have not both completed')
    order = ['priority1', 'priority2', 'priority3', 'pilot_integration']
    events = read_verified()
    accepted = {row['phase'] for row in events if row['status'] == 'phase_accepted'}
    if args.phase in accepted:
        raise ValueError('Phase acceptance already recorded; use a new explicit revision')
    if any(earlier not in accepted for earlier in order[:order.index(args.phase)]):
        raise ValueError('Earlier priority has not passed its three audits')
    event = append(args.phase, 'phase_accepted', args.detail, args.audit)
    print(json.dumps(event, ensure_ascii=False))


if __name__ == '__main__':
    main()
