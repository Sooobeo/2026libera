"""Completed-phase reuse checks with synthetic files and mocked children only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research import run_v63_candidate_003_development as supervisor
from research.v63.build_run import select_phase_schedule


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return path


def bytes_under(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in folder.rglob('*') if p.is_file()}


@pytest.fixture
def development(tmp_path, monkeypatch):
    root = tmp_path
    run_id = 'synthetic-runtime'
    source = b'synthetic source snapshot, never executed\n'
    identity = {'code': {'campaign.py': hashlib.sha256(source).hexdigest()}, 'marker': 'original'}
    freeze = {'main_model_frozen': False, 'context_tokens': 100, 'model_sha256': 'm' * 64,
              'marker': 'original'}
    put(root / 'freeze.json', freeze)
    put(root / 'tokenizer.json', {'synthetic': True})
    config = {'output_root': 'outputs', 'runtime_freeze_path': 'freeze.json',
              'tokenizer_config_path': 'tokenizer.json', 'execution_amendment': {'synthetic': True},
              'smoke_fund_id': 'F03', 'phase_budgets': {
                  phase: {'max_generation_requests': 1000, 'max_wall_seconds': 1000}
                  for phase in ('technical-smoke', 'paired-feasibility')}}
    config_path = put(root / 'config.json', config)
    put(root / 'selection_receipt.json', {
        'new_run_id': run_id, 'config': supervisor.file_ref(config_path, root)})
    monkeypatch.setattr(supervisor, 'ROOT', root)
    monkeypatch.setattr(supervisor.sys, 'argv', ['supervisor', '--config', str(config_path)])
    monkeypatch.setattr(supervisor, 'runtime_identity', lambda root, frozen, *args:
        (run_id if frozen.get('marker') == 'original' else 'changed-runtime', deepcopy(identity)))
    monkeypatch.setattr(supervisor, 'ctypes', SimpleNamespace(windll=SimpleNamespace(
        kernel32=SimpleNamespace(SetThreadExecutionState=lambda flags: 0x80000000))))

    def make_phase(phase):
        directory = root / 'outputs/phases' / run_id / phase
        records = []
        for index, row in enumerate(select_phase_schedule(phase, config['smoke_fund_id'])):
            row = {key: row[key] for key in ('block', 'scenario', 'fund_id', 'arm', 'replicate')}
            trace = {'fund_id': row['fund_id'], 'arm': row['arm'], 'status': 'completed',
                     'effective_weights': [1.0] + [0.0] * 11, 'actual_model_calls': 3,
                     'calls': [{'stage': stage, 'status': 'response', 'elapsed_seconds': 1.0,
                                'raw_response': {'usage': {'prompt_eval_count': stage},
                                                 'model_sha256': freeze['model_sha256']}}
                               for stage in (1, 2, 3)],
                     'stages': [{'stage': stage, 'status': 'completed', 'prompt_token_counts': [stage]}
                                for stage in (1, 2, 3)]}
            path = put(directory / 'synthetic_traces' / f'{index}.json', trace)
            row.update(trace_path=str(path), trace_sha256=supervisor.file_ref(path, root)['sha256'])
            records.append(row)
        put(directory / 'records.json', records)
        put(directory / 'measurements.json', {
            'status': 'completed', 'runtime_identity_sha256': run_id,
            'phase_trajectories': len(records), 'terminal_trajectories': len(records),
            'phase_generation_requests': len(records) * 3, 'cumulative_wall_seconds': 100.0,
            'max_observed_prompt_tokens': 3, 'full_history_observed': True})
        prepared = put(directory / 'prepared_inputs.json', {'synthetic': phase})
        put(directory / 'runtime_identity.json', identity)
        put(directory / 'frozen_runtime.json', {**freeze, 'execution_phase': phase,
                                               'artifacts': [supervisor.file_ref(prepared, root)]})
        snapshot = directory / 'source_snapshot/campaign.py'
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(source)
        put(directory / 'budget_state.json', {'limits': config['phase_budgets'][phase],
            'first_started_at_utc': '2000-01-01T00:00:00+00:00'})
        return directory

    return SimpleNamespace(root=root, config=config, run_id=run_id, identity=identity, make_phase=make_phase)


def test_completed_phases_skip_children_and_preserve_original_clocks_and_counts(development, monkeypatch):
    d = development
    for phase in d.config['phase_budgets']:
        d.make_phase(phase)
    phases = d.root / 'outputs/phases'
    before = bytes_under(phases)
    monkeypatch.setattr(supervisor.subprocess, 'Popen', lambda *args, **kwargs:
                        pytest.fail('Completed phase must never launch a child'))
    assert supervisor.main() == 0
    assert bytes_under(phases) == before
    state = supervisor.read_json(d.root / 'outputs/development_supervisor' / d.run_id / 'state.json')
    assert state['main_auto_launch'] is False
    assert set(state['completed_phase_reuse']) == set(d.config['phase_budgets'])
    for phase, ref in state['completed_phase_reuse'].items():
        receipt = supervisor.read_json(d.root / ref['path'])
        assert supervisor.file_ref(d.root / ref['path'], d.root) == ref
        assert receipt['campaign_child_launched'] is False
        assert receipt['phase_artifacts_modified'] is False
        assert receipt['new_generation_requests'] == 0
        assert receipt['original_budget_first_started_at_utc'].startswith('2000-01-01')
        assert receipt['original_cumulative_wall_seconds'] == 100.0
        original = supervisor.read_json(phases / d.run_id / phase / 'measurements.json')
        assert receipt['original_phase_generation_requests'] == original['phase_generation_requests']
        for artifact in receipt['phase_artifacts'].values():
            assert supervisor.file_ref(d.root / artifact['path'], d.root) == artifact
    # A later restart emits separate reuse evidence; it cannot overwrite the
    # first supervisor's immutable receipts or touch the finished phase.
    first_receipts = {ref['path']: (d.root / ref['path']).read_bytes()
                      for ref in state['completed_phase_reuse'].values()}
    assert supervisor.main() == 0
    assert bytes_under(phases) == before
    assert all((d.root / path).read_bytes() == value for path, value in first_receipts.items())


def test_only_incomplete_phase_launches_and_uses_existing_gate(development, monkeypatch):
    d = development
    smoke = d.make_phase('technical-smoke')
    paired = d.make_phase('paired-feasibility')
    measurements = supervisor.read_json(paired / 'measurements.json')
    put(paired / 'measurements.json', {**measurements, 'status': 'incomplete'})
    smoke_before = bytes_under(smoke)
    commands = []

    def launch(command, **kwargs):
        commands.append(command)
        put(paired / 'measurements.json', measurements)
        return SimpleNamespace(pid=12345, returncode=0, poll=lambda: 0)

    monkeypatch.setattr(supervisor.subprocess, 'Popen', launch)
    assert supervisor.main() == 0
    assert len(commands) == 1 and commands[0][-1] == 'paired-feasibility'
    assert bytes_under(smoke) == smoke_before
    state = supervisor.read_json(d.root / 'outputs/development_supervisor' / d.run_id / 'state.json')
    assert set(state['completed_phase_reuse']) == {'technical-smoke'}
    assert set(state['completed_phase_reviews']) == set(d.config['phase_budgets'])


def test_absent_measurement_does_not_claim_completion(development):
    d = development
    assert supervisor.completed_phase_review(d.root, d.config, d.run_id, 'technical-smoke',
                                            d.identity, 100) is None


@pytest.mark.parametrize('corruption', [
    'measurement_identity', 'saved_identity', 'frozen_identity', 'prepared_hash',
    'missing_prepared', 'source_snapshot', 'budget_limits', 'trace_hash', 'missing_full_history',
])
def test_invalid_completed_phase_fails_closed_without_child_or_repair(development, monkeypatch, corruption):
    d = development
    directory = d.make_phase('technical-smoke')
    if corruption == 'measurement_identity':
        path = directory / 'measurements.json'
        put(path, {**supervisor.read_json(path), 'runtime_identity_sha256': 'other'})
    elif corruption == 'saved_identity':
        put(directory / 'runtime_identity.json', {'changed': True})
    elif corruption == 'frozen_identity':
        path = directory / 'frozen_runtime.json'
        put(path, {**supervisor.read_json(path), 'marker': 'changed'})
    elif corruption == 'prepared_hash':
        put(directory / 'prepared_inputs.json', {'changed': True})
    elif corruption == 'missing_prepared':
        (directory / 'prepared_inputs.json').unlink()
    elif corruption == 'source_snapshot':
        (directory / 'source_snapshot/campaign.py').write_text('changed', encoding='utf-8')
    elif corruption == 'budget_limits':
        path = directory / 'budget_state.json'
        put(path, {**supervisor.read_json(path), 'limits': {'max_generation_requests': 0}})
    elif corruption == 'trace_hash':
        put(directory / 'synthetic_traces/0.json', {'changed': True})
    elif corruption == 'missing_full_history':
        records = supervisor.read_json(directory / 'records.json')
        row = next(row for row in records if row['arm'] == 'C-context')
        path = Path(row['trace_path'])
        trace = supervisor.read_json(path)
        put(path, {**trace, 'calls': trace['calls'][:2], 'stages': trace['stages'][:2]})
        row['trace_sha256'] = supervisor.file_ref(path, d.root)['sha256']
        put(directory / 'records.json', records)
    before = bytes_under(directory)
    monkeypatch.setattr(supervisor.subprocess, 'Popen', lambda *args, **kwargs:
                        pytest.fail('Invalid completed phase must not launch a child'))
    with pytest.raises((ValueError, RuntimeError, FileNotFoundError)):
        supervisor.main()
    assert bytes_under(directory) == before
    supervisor_dir = d.root / 'outputs/development_supervisor' / d.run_id
    assert not list(supervisor_dir.rglob('*.reuse.json'))
    assert supervisor.read_json(supervisor_dir / 'state.json')['status'] == 'stopped_requires_review'
