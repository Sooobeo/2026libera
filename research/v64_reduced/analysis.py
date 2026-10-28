"""Descriptive analysis of an exactly frozen reduced schedule; never confirmatory.

Only completed selected phases are published. Missing or blocked trajectories do
not become hold-h observations. The old v6.3 statistical family is not invoked.
"""
from __future__ import annotations

from collections import Counter
import itertools
import json
from pathlib import Path

import numpy as np

from research.v63.campaign_control import atomic_json
from research.v63.evaluate import FUNDS, _hash_object, _replicate_metrics
from research.v63.numerics import check_portfolio, jsonable, pair_metrics, regret_bounds, sha256, tv
from research.v63.retrieval import canonical, sha
from research.v64_reduced.policy import POLICY_ID, normalize_and_check

TERMINAL = {'completed', 'model_output_failure', 'operational_failure'}
KEY_FIELDS = ('block', 'scenario', 'fund_id', 'arm', 'replicate')


def key(row):
    return tuple(row[field] if field != 'replicate' else int(row[field]) for field in KEY_FIELDS)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def provenance(root):
    paths = ['research/v64_reduced/analysis.py', 'research/v64_reduced/policy.py',
             'research/v63/evaluate.py', 'research/v63/numerics.py']
    return {path: sha256(Path(root) / path) for path in paths}


def indexed(rows):
    result = {}
    for row in rows:
        identity = key(row)
        if identity in result:
            raise ValueError('Duplicate trajectory identity')
        result[identity] = row
    return result


def load_trace(root, record, *, allow_synthetic=False):
    if 'trace' in record:
        if not allow_synthetic or record['trace'].get('engineering_only') is not True:
            raise ValueError('Inline traces require marked synthetic verification')
        trace = record['trace']
        source = {'synthetic': True, 'sha256': _hash_object(trace)}
    else:
        path = Path(record['trace_path'])
        path = (Path(root) / path).resolve()
        if Path(root).resolve() not in path.parents:
            raise ValueError('Trace outside workspace')
        if not path.is_file():
            return None, {'path': str(path), 'missing': True}
        digest = sha256(path)
        if not record.get('trace_sha256') or digest != record['trace_sha256']:
            raise ValueError('Trace hash missing or changed')
        trace = read(path)
        if trace.get('engineering_only'):
            raise ValueError('Engineering trace cannot enter experimental analysis')
        source = {'path': path.relative_to(Path(root).resolve()).as_posix(), 'sha256': digest, 'synthetic': False}
    if trace.get('arm') != record['arm'] or trace.get('fund_id') != record['fund_id']:
        raise ValueError('Trace identity differs from frozen schedule')
    if record.get('trajectory_status') is not None and trace.get('status') != record['trajectory_status']:
        raise ValueError('Record status differs from trace')
    return trace, source


def terminal_policy(root, record, profile, *, model_sha256, allow_synthetic=False):
    if not isinstance(model_sha256, str) or not model_sha256:
        raise ValueError('Frozen model hash required')
    trace, source = load_trace(root, record, allow_synthetic=allow_synthetic)
    if trace is None or trace.get('status') not in TERMINAL:
        return {'eligible': False, 'status': trace.get('status') if trace else 'not_attempted', 'source': source}
    if trace.get('normalization_policy_id') != POLICY_ID:
        raise ValueError('Wrong normalization policy')
    calls = trace.get('calls', [])
    if not calls:
        raise ValueError('Terminal record without an actual attempt')
    for call in calls:
        response = call.get('raw_response')
        if response and response.get('finish_reason') != 'incomplete' and response.get('model_sha256') != model_sha256:
            raise ValueError('Unpinned model in trace')
    h = np.asarray(profile['h'], float)
    check = lambda weights: check_portfolio(weights, h, profile['Sigma'], profile.get('A'), profile.get('b'))
    if not check(h)['valid']:
        raise ValueError('Infeasible fallback h')
    stages = trace.get('stages', [])
    finals = [stage for stage in stages if stage.get('stage') == 3]
    if len(finals) > 1:
        raise ValueError('Duplicate final stage')
    final = finals[0] if finals else {}
    output = final.get('raw_output')
    raw_weights = output.get('weights') if isinstance(output, dict) else None
    normalized = final.get('normalization')
    recomputed = normalize_and_check(raw_weights, h, check)
    if normalized is not None:
        for field, value in recomputed.items():
            if field not in normalized or _hash_object(normalized[field]) != _hash_object(value):
                raise ValueError('Normalization receipt differs from recomputed policy: ' + field)
    completed = trace['status'] == 'completed'
    if completed and (normalized is None or not recomputed['postprocessed_valid']):
        raise ValueError('Completed trace lacks valid normalized final weights')
    weights = np.asarray(recomputed['normalized_weights'] if completed else h, float)
    if not np.array_equal(np.asarray(trace.get('effective_weights'), float), weights):
        raise ValueError('Effective weights differ from normalized-or-h policy')
    if trace.get('policy_output_valid') is not completed:
        raise ValueError('Policy-valid flag differs from terminal status')
    raw_valid = bool(normalized is not None and recomputed['raw_valid'])
    if bool(trace.get('raw_output_valid')) != raw_valid:
        raise ValueError('Raw-valid flag differs from original weights')
    reached = max((int(stage['stage']) for stage in stages if 'exposed_evidence_ids' in stage), default=0)
    onset = {'R0': None, 'R1': 1, 'R2': 2, 'R3': 3, 'C-context': 1}.get(record['arm'])
    available = record['arm'] if onset is not None and reached >= onset else 'R0'
    citations = []
    for stage in stages:
        candidates = set(stage.get('unexposed_citation_ids', []))
        raw = stage.get('raw_output')
        if isinstance(raw, dict):
            for cited in raw.get('evidence', []):
                if isinstance(cited, dict) and cited.get('evidence_id') not in stage.get('exposed_evidence_ids', []):
                    candidates.add(cited.get('evidence_id'))
        citations.extend({'stage': stage.get('stage'), 'evidence_id': eid} for eid in sorted(candidates, key=str))
    usage = Counter()
    for call in calls:
        for field, value in ((call.get('raw_response') or {}).get('usage') or {}).items():
            if isinstance(value, (int, float)):
                usage[field] += value
    changed = normalized is not None and normalized.get('normalized_weights') is not None and not np.array_equal(np.asarray(raw_weights), np.asarray(normalized['normalized_weights']))
    return dict(eligible=True, status=trace['status'], weights=weights, fallback=not completed,
                raw_valid=raw_valid, raw_numeric_valid=bool(recomputed['raw_valid']), raw_terminal_status=trace.get('raw_terminal_status'),
                policy_valid=completed, normalization_performed=bool(normalized and normalized.get('normalization_performed')),
                normalization_changed=changed, normalized_valid=bool(normalized and recomputed['postprocessed_valid']),
                rescued_by_normalization=completed and not recomputed['raw_valid'],
                raw_final=raw_weights, validation=check(raw_weights) if raw_weights is not None else None,
                normalized_validation=recomputed.get('normalized_check'), available_reference_key=available,
                last_attempted_stage=reached, source=source, actual_model_calls=len(calls), usage=dict(usage),
                unexposed_citation_candidates=citations)


def collect(root, package, records, bank, model_sha256, *, allow_synthetic=False):
    expected, observed = indexed(package['entries']), indexed(records)
    if set(observed) - set(expected):
        raise ValueError('Unregistered trajectory outside frozen schedule')
    missing = sorted(set(expected) - set(observed))
    policies, blocked = {}, []
    for identity, record in observed.items():
        entry = expected[identity]
        if not allow_synthetic and (not entry.get('input_sha256') or entry.get('input_sha256') != record.get('input_sha256')):
            raise ValueError('Record input hash differs from frozen schedule')
        _, sid, fid, _, _ = identity
        policy = terminal_policy(root, record, bank[sid][fid], model_sha256=model_sha256, allow_synthetic=allow_synthetic)
        policies[identity] = policy
        if not policy['eligible']:
            blocked.append({'identity': identity, 'status': policy['status']})
    if missing or blocked:
        return None, dict(status='incomplete_no_descriptive_analysis', missing=missing, blocked=blocked,
                          expected_trajectories=len(expected), observed_records=len(observed), not_attempted_filled_with_h=False)
    return policies, None


def diagnostic_summary(policies):
    result = {'terminal_counts': dict(Counter(p['status'] for p in policies.values())), 'trajectory_diagnostics': []}
    fields = ['raw_valid', 'policy_valid', 'normalization_performed', 'normalization_changed', 'normalized_valid', 'rescued_by_normalization', 'fallback']
    result['policy_counts'] = {field: sum(bool(p[field]) for p in policies.values()) for field in fields}
    result['unexposed_citation_candidate_trajectories'] = sum(bool(p['unexposed_citation_candidates']) for p in policies.values())
    result['unexposed_citation_candidate_locations'] = sum(len(p['unexposed_citation_candidates']) for p in policies.values())
    for identity, p in sorted(policies.items()):
        result['trajectory_diagnostics'].append({'identity': identity, **{name: value for name, value in p.items() if name not in {'weights', 'raw_final', 'eligible'}}})
    return result


def describe_main(policies, bank, scenarios):
    ids = [scenario['scenario_id'] for scenario in scenarios]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate frozen scenario')
    arms = sorted({identity[3] for identity in policies})
    reps = sorted({identity[4] for identity in policies})
    expected = set(itertools.product(ids, FUNDS, arms, reps))
    if {identity[1:] for identity in policies} != expected or set(bank) != set(ids):
        raise ValueError('Main schedule must contain all selected scenario/fund/arm/replicate cells')
    by_cell, scenario_rows, detailed = {}, [], []
    for arm, sid in itertools.product(arms, ids):
        values = []
        for rep in reps:
            selected = {fid: next(p for identity, p in policies.items() if identity[1:] == (sid, fid, arm, rep)) for fid in FUNDS}
            item = _replicate_metrics(selected, bank[sid], arm)
            item['nonfallback_only_diagnostics'] = item.pop('valid_only_diagnostics')
            metrics = item['metrics']
            for old, new in [('G_full_valid_pair_contribution', 'G_full_nonfallback_pair_contribution'),
                             ('R_full_valid_contribution', 'R_full_nonfallback_contribution'),
                             ('valid_only_pair_count', 'nonfallback_pair_count')]:
                metrics[new] = metrics.pop(old)
            for group in ('raw_valid', 'normalized_rescue', 'fallback'):
                pairs = []
                funds = []
                for pair in item['full_pairs']:
                    ps = [selected[pair['fund_i']], selected[pair['fund_j']]]
                    label = 'fallback' if any(p['fallback'] for p in ps) else ('raw_valid' if all(p['raw_valid'] for p in ps) else 'normalized_rescue')
                    if label == group:
                        pairs.append(pair)
                for regret in item['full_regret']:
                    p = selected[regret['fund_id']]
                    label = 'fallback' if p['fallback'] else ('raw_valid' if p['raw_valid'] else 'normalized_rescue')
                    if label == group:
                        funds.append(regret)
                metrics[f'G_full_{group}_partition_contribution'] = sum(p['G'] for p in pairs) / 6
                metrics[f'R_full_{group}_partition_contribution'] = sum(p['point'] for p in funds) / 4
            detailed.append(dict(scenario=sid, arm=arm, replicate=rep, **item))
            values.append(metrics)
        means = {name: float(np.mean([value[name] for value in values])) for name in values[0]}
        scenario_rows.append(dict(scenario=sid, arm=arm, **means))
        by_cell[(sid, arm)] = means
    summaries = {arm: {name: float(np.mean([by_cell[(sid, arm)][name] for sid in ids])) for name in by_cell[(ids[0], arm)]} for arm in arms}
    return dict(independent_scenarios=len(ids), precision_strata=dict(Counter(str(s.get('r')) for s in scenarios)),
                per_scenario=scenario_rows, arm_means=summaries, replicate_details=detailed,
                fund_pairs_independent=False, replicates_independent=False, inference='descriptive_only_no_p_values_or_confirmatory_claims',
                aggregation='Metrics within replicate, then replicate mean within scenario, then equal scenario mean.')


def describe_counterfactual(policies, baseline_policies, bank, baseline_bank, assignments):
    if len({a['scenario_id'] for a in assignments}) != len(assignments):
        raise ValueError('Duplicate replacement assignment')
    targets = {(a['scenario_id'], a['fund_id']) for a in assignments}
    if {(identity[1], identity[2]) for identity in policies} != targets:
        raise ValueError('Replacement schedule differs from frozen assignments')
    if {a['scenario_id'] for a in assignments} != set(baseline_bank) or set(bank) != set(baseline_bank):
        raise ValueError('Replacement and main scenarios differ')
    for sid, fid in targets:
        for name in ('h', 'Sigma', 'A', 'b'):
            if _hash_object(bank[sid][fid].get(name)) != _hash_object(baseline_bank[sid][fid].get(name)):
                raise ValueError('Replacement changed a held-fixed profile')
        for other in FUNDS:
            if other != fid and _hash_object(bank[sid][other]['full']['mu']) != _hash_object(baseline_bank[sid][other]['full']['mu']):
                raise ValueError('Replacement changed another fund information')
    rows = []
    for identity, after in sorted(policies.items()):
        _, sid, fid, arm, rep = identity
        baseline_key = ('B-main', sid, fid, arm, rep)
        if baseline_key not in baseline_policies:
            raise ValueError('Missing exact matched new-main baseline')
        before = baseline_policies[baseline_key]
        ra, rb = baseline_bank[sid][fid]['full']['reference'], bank[sid][fid]['full']['reference']
        actual = after['weights'] - before['weights']
        reference = np.asarray(rb['weights']) - np.asarray(ra['weights'])
        error, eta = tv(actual, reference), ra['eta'] + rb['eta']
        rows.append(dict(identity=identity, response_error=error, response_error_interval=[max(0, error-eta), error+eta],
                         actual_change_tv=float(.5*np.abs(actual).sum()), reference_change_tv=float(.5*np.abs(reference).sum()),
                         zero_reference_change=bool(np.all(reference == 0)), fallback_a=before['fallback'], fallback_b=after['fallback'],
                         raw_valid_a=before['raw_valid'], raw_valid_b=after['raw_valid'],
                         normalized_a=before['normalization_performed'], normalized_b=after['normalization_performed']))
    summaries = {}
    for arm in sorted({row['identity'][3] for row in rows}):
        values = [{'scenario': sid, 'response_error': float(np.mean([row['response_error'] for row in rows if row['identity'][1] == sid and row['identity'][3] == arm]))} for sid, _ in sorted(targets)]
        summaries[arm] = dict(per_scenario=values, mean=float(np.mean([row['response_error'] for row in values])), independent_scenarios=len(targets))
    return dict(rows=rows, arm_summaries=summaries, zero_reference_change_retained=True, exact_new_main_matching=True)


def describe_negative(policies, records, bank):
    indexed_records = indexed(records)
    ids = sorted({identity[1] for identity in policies})
    labels = tuple(f'N{i:02d}' for i in range(1, 5))
    arms, reps = sorted({identity[3] for identity in policies}), sorted({identity[4] for identity in policies})
    if {identity[1:] for identity in policies} != set(itertools.product(ids, labels, arms, reps)):
        raise ValueError('Incomplete negative-control factor cells')
    rows = []
    for sid, arm, rep in itertools.product(ids, arms, reps):
        canonical = bank[sid][labels[0]]
        for label in labels[1:]:
            other = bank[sid][label]
            for name in ('h', 'Sigma', 'A', 'b', 'full'):
                a, b = canonical.get(name), other.get(name)
                if name == 'full':
                    a, b = {k: a[k] for k in ('mu', 'reference')}, {k: b[k] for k in ('mu', 'reference')}
                if _hash_object(a) != _hash_object(b):
                    raise ValueError('Negative-control canonical profile/reference mismatch')
            for name in ('mu', 'reference'):
                if _hash_object(canonical['available'][arm][name]) != _hash_object(other['available'][arm][name]):
                    raise ValueError('Negative-control available reference mismatch')
        hashes = [indexed_records[('negative-control', sid, label, arm, rep)].get('normalized_input_sha256') for label in labels]
        if any(not value for value in hashes) or len(set(hashes)) != 1:
            raise ValueError('Negative-control label-normalized input hashes differ or missing')
        for i, j in itertools.combinations(labels, 2):
            a, b = policies[('negative-control', sid, i, arm, rep)], policies[('negative-control', sid, j, arm, rep)]
            reference = canonical['full']['reference']
            metrics = pair_metrics(a['weights'], b['weights'], reference, reference)
            mu = np.asarray(canonical['full']['mu'])
            metrics.update(mean_full_regret=float(np.mean([mu @ (np.asarray(reference['weights']) - p['weights']) for p in (a, b)])),
                           mean_full_regret_interval=np.mean([regret_bounds(mu, p['weights'], reference) for p in (a, b)], axis=0).tolist())
            rows.append(dict(scenario=sid, arm=arm, replicate=rep, label_i=i, label_j=j, fallback_involved=a['fallback'] or b['fallback'], **metrics))
    per_scenario = [dict(scenario=sid, arm=arm, **{name: float(np.mean([row[name] for row in rows if row['scenario'] == sid and row['arm'] == arm])) for name in ('D', 'G', 'E', 'A', 'mean_full_regret')}) for sid, arm in itertools.product(ids, arms)]
    return dict(rows=rows, per_scenario=per_scenario, independent_scenarios=len(ids), canonical_reference_distance_zero=True,
                interpretation='Label/generation variability under the normalization-and-fallback policy; distance alone is not economic error. Pair rows are not independent observations.')


def describe_actual(root, policies, records, profiles, catalog, *, allow_synthetic=False):
    rows, facts = [], []
    for record in records:
        identity = key(record)
        _, module, fid, _, _ = identity
        p = policies[identity]
        trace, _ = load_trace(root, record, allow_synthetic=allow_synthetic)
        cutoff = {'A': '2026-03-31', 'C': '2026-06-30'}[module]
        for stage in trace.get('stages', []):
            output = stage.get('raw_output')
            if not isinstance(output, dict):
                continue
            for cited in output.get('evidence', []):
                if not isinstance(cited, dict):
                    continue
                eid = cited.get('evidence_id')
                gold = catalog.get(eid)
                fact = dict(identity=identity, stage=stage['stage'], evidence_id=eid,
                            exposed=eid in stage.get('exposed_evidence_ids', []), source_fact_scored=gold is not None)
                if gold is not None:
                    candidates = gold.get('facts')
                    if candidates:
                        comparisons = [{field: cited.get(field) == candidate[field] for field in ('value', 'unit', 'date') if field in candidate} for candidate in candidates]
                        exact = [i for i, comparison in enumerate(comparisons) if comparison and all(comparison.values())]
                        best = exact[0] if exact else max(range(len(comparisons)), key=lambda i: sum(comparisons[i].values()))
                        matches = comparisons[best]
                    else:
                        exact = []
                        matches = {field: cited.get(field) == gold[field] for field in ('value', 'unit', 'date') if field in gold}
                    fact.update(source_url=gold.get('source_url'), correct_fund_attribution=gold.get('fund_id') in (fid, 'COMMON'),
                                publication_within_cutoff=bool(gold.get('publication_date') and gold['publication_date'] <= cutoff and (module != 'C' or gold['publication_date'] > '2026-03-31')),
                                correct_period=gold.get('period', module) == module, literal_field_matches=matches,
                                matching_source_fact_indices=exact, numeric_fact_scored=bool(candidates or 'value' in gold),
                                requires_semantic_review=bool(gold.get('semantic_review_required')) or not all(matches.values()) or (bool(candidates) and not exact))
                else:
                    fact['not_scored_reason'] = 'No independently grounded source fact record supplied'
                facts.append(fact)
        rows.append(dict(identity=identity, allocation_change_from_h_tv=tv(p['weights'], profiles[module][fid]['h']),
                         raw_valid=p['raw_valid'], policy_valid=p['policy_valid'], fallback=p['fallback']))
    return dict(rows=rows, fact_checks=facts, exact_allocation_gold=False, regret_evaluation_applied=False,
                qualitative_text_converted_to_synthetic_signals=False,
                fact_scoring_coverage=sum(f['source_fact_scored'] for f in facts)/len(facts) if facts else None,
                interpretation='Literal numeric/source candidates, not confirmed semantic error rates. Source dates, attribution and exposure are separate flags; no independent human review is invented.')


def verify_phase(root, directory, package, records, bank, run_id, freeze):
    root, directory = Path(root).resolve(), Path(directory).resolve()
    if root not in directory.parents or directory.parent.name != run_id:
        raise ValueError('Phase directory is not under selected run identity')
    identity = read(directory / 'runtime_identity.json')
    if sha(canonical(identity)) != run_id:
        raise ValueError('Phase runtime identity mismatch')
    if read(directory / 'frozen_runtime.json') != jsonable(freeze):
        raise ValueError('Analysis freeze differs from phase freeze')
    serialized = {k: v for k, v in package.items() if k not in {'scenarios_evaluator_only', 'hidden_evaluator_only'}}
    required = {directory/'prepared_inputs.json': serialized, directory/'evaluator_only/reference_bank.json': bank,
                directory/'evaluator_only/frozen_scenarios.json': package['scenarios_evaluator_only']}
    bound = set()
    for item in freeze.get('artifacts', []):
        path = (root / item['path']).resolve()
        if root not in path.parents or not path.is_file() or sha256(path) != item['sha256']:
            raise ValueError('Frozen artifact missing or changed')
        bound.add(path)
    if not set(required).issubset(bound):
        raise ValueError('Frozen artifacts do not bind package, bank and scenarios')
    for path, value in required.items():
        if read(path) != jsonable(value):
            raise ValueError('Analysis inputs differ from frozen file')
    if read(directory/'records.json') != jsonable(records):
        raise ValueError('Analysis records differ from terminal records file')
    for record in records:
        trace_path = (root / record['trace_path']).resolve()
        if run_id not in trace_path.parts:
            raise ValueError('Historical or different-run trace cannot enter reduced sample')
    return {str(path.relative_to(root)): sha256(path) for path in [*required, directory/'records.json', directory/'runtime_identity.json', directory/'frozen_runtime.json']}


def _load_phase(root, directory, run_id):
    package = read(directory/'prepared_inputs.json')
    package['scenarios_evaluator_only'] = read(directory/'evaluator_only/frozen_scenarios.json')
    package['hidden_evaluator_only'] = read(directory/'evaluator_only/hidden_truth.json')
    records = read(directory/'records.json')
    bank = read(directory/'evaluator_only/reference_bank.json')
    freeze = read(directory/'frozen_runtime.json')
    hashes = verify_phase(root, directory, package, records, bank, run_id, freeze)
    return package, records, bank, freeze, hashes


def policy_profiles(package, bank):
    if package['phase'] not in {'A', 'C'}:
        return bank
    return {package['phase']: {fund: {'h': profile['h'], 'Sigma': package['calibration']['Sigma'],
                                    'A': profile.get('A'), 'b': profile.get('b')}
                               for fund, profile in package['profiles'].items()}}


def analyze_phase(root, config, phase_dir, package, records, bank, run_id, freeze):
    """Validate selected artifacts and write analysis.json only for complete input.

    package has v63 build_phase keys (phase, entries, scenarios_evaluator_only,
    replacement_assignments); counts are derived from the frozen entries.
    C combines A+C when A is enabled by the bound design manifest.
    """
    root, phase_dir = Path(root).resolve(), Path(phase_dir).resolve()
    hashes = verify_phase(root, phase_dir, package, records, bank, run_id, freeze)
    phase = package['phase']
    if phase_dir.name != phase:
        raise ValueError('Package phase differs from phase directory')
    policy_bank = policy_profiles(package, bank)
    policies, incomplete = collect(root, package, records, policy_bank, freeze['model_sha256'])
    if incomplete:
        return incomplete
    combined_policies, combined_records = policies, records
    if phase in {'B-main', 'development-pilot', 'technical-smoke', 'paired-feasibility'}:
        result = describe_main(policies, bank, package['scenarios_evaluator_only'])
    elif phase == 'x-replacement':
        other_dir = phase_dir.parent/'B-main'
        try:
            main_package, main_records, main_bank, main_freeze, other_hashes = _load_phase(root, other_dir, run_id)
        except FileNotFoundError:
            return {'status': 'incomplete_no_descriptive_analysis', 'missing_dependency': 'same-run B-main'}
        if main_freeze['model_sha256'] != freeze['model_sha256']:
            raise ValueError('Counterfactual baseline model differs')
        baseline, incomplete = collect(root, main_package, main_records, main_bank, freeze['model_sha256'])
        if incomplete:
            return incomplete
        hashes.update(other_hashes)
        result = describe_counterfactual(policies, baseline, bank, main_bank, package['replacement_assignments'])
    elif phase == 'negative-control':
        result = describe_negative(policies, records, bank)
    elif phase in {'A', 'C'}:
        profiles = policy_bank
        design_ref = package.get('design_manifest')
        if design_ref:
            design_path = root/design_ref['path']
            if sha256(design_path) != design_ref['sha256']:
                raise ValueError('Design manifest changed')
            enabled = read(design_path)['enabled_phases']
            hashes[design_ref['path']] = design_ref['sha256']
        else:
            enabled = config.get('phases', ['A', 'C'])
        if phase == 'C' and 'A' in enabled:
            try:
                a_package, a_records, a_bank, a_freeze, other_hashes = _load_phase(root, phase_dir.parent/'A', run_id)
            except FileNotFoundError:
                return {'status': 'incomplete_no_descriptive_analysis', 'missing_dependency': 'selected same-run A'}
            if a_freeze['model_sha256'] != freeze['model_sha256']:
                raise ValueError('A/C model differs')
            a_policy_bank = policy_profiles(a_package, a_bank)
            a_policies, incomplete = collect(root, a_package, a_records, a_policy_bank, freeze['model_sha256'])
            if incomplete:
                return incomplete
            combined_policies = {**a_policies, **policies}
            combined_records = a_records + records
            profiles = {**a_policy_bank, **policy_bank}
            hashes.update(other_hashes)
        catalog = read(root/config['source_catalog_path']) if config.get('source_catalog_path') else {}
        if config.get('source_catalog_path'):
            catalog_path = (root/config['source_catalog_path']).resolve()
            if not any((root/item['path']).resolve() == catalog_path and item['sha256'] == sha256(catalog_path)
                       for item in freeze.get('artifacts', [])):
                raise ValueError('Source catalog is not bound by frozen artifacts')
            hashes[config['source_catalog_path']] = sha256(catalog_path)
        result = describe_actual(root, combined_policies, combined_records, profiles, catalog)
    else:
        raise ValueError('Unknown reduced-analysis phase')
    for policy in combined_policies.values():
        hashes[policy['source']['path']] = policy['source']['sha256']
    output = jsonable(dict(status='completed_descriptive_analysis', phase=phase, runtime_identity_sha256=run_id,
                           expected_trajectories=len(combined_policies), phase_expected_trajectories=len(package['entries']),
                           normalization_policy_id=POLICY_ID, confirmatory_analysis=False, synthetic_verification=False,
                           input_hashes=hashes, input_fingerprint=_hash_object([package['entries'], package['scenarios_evaluator_only'], bank]),
                           provenance=provenance(root), **diagnostic_summary(combined_policies), **result))
    # Detect evidence changes occurring during analysis before publishing.
    for path, digest in hashes.items():
        if sha256(root/path) != digest:
            raise ValueError('Analysis evidence changed before publication')
    atomic_json(phase_dir/'analysis.json', output)
    return output
