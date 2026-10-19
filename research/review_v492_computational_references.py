"""Independent formula/input/scope audit of the completed reference artifact.

No reference builder is imported or rerun; this checks saved results directly.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/v492_computational_reference_review_20261019.json'


def ref(path):
    p = ROOT / path
    return {'path': p.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf8'))


def main():
    if OUT.exists():
        raise SystemExit('Keep the completed audit immutable; use a new revision for changes.')
    record_path = 'research/v492_computational_references_20261019.json'
    source_path = 'data/sector_protocol/v491_design_20261019/public_compact_candidate.json'
    r, public = read(record_path), read(source_path)
    m = public['common_market']
    codes = ['10', '15', '20', '25', '30', '35', '40', '45', '50', '55', '60']
    sigma = np.array(m['covariance'], dtype=float)
    checks = []

    def check(name, truth):
        checks.append({'check': name, 'pass': bool(truth)})

    check('record binds exact frozen public input SHA', r['input_ref'] == ref(source_path))
    check('covariance and all reference rows use the same 11-sector code order', r['sector_codes'] == m['sector_codes'] == codes and all(list(x['weights']) == codes for x in r['references']))
    check('sector names and 60-return window preserve input identity', r['sector_names'] == m['sector_names'] and r['dates'] == m['lookback_return_dates'] and r['observations'] == m['return_observations'] == 60)
    check('daily squared-decimal covariance unit and sample-ddof retained', r['covariance_unit'] == m['covariance_unit'] == 'daily_decimal_return_squared' and m['covariance_ddof'] == 1)
    check('exact covariance symmetry, finite values and positive-definite eigenspectrum', sigma.shape == (11, 11) and np.isfinite(sigma).all() and np.array_equal(sigma, sigma.T) and np.linalg.eigvalsh(sigma)[0] > 0)
    check('252 annualization agrees with supplied volatility diagnostics', m['annualization_trading_days'] == 252 and np.allclose(np.sqrt(np.diag(sigma) * 252), m['annualized_volatility_diagnostic'], atol=1e-12, rtol=0))
    rows = {x['reference_id']: x for x in r['references']}
    check('exact reference set has two calculated references and existing market benchmark', set(rows) == {'equal_weight', 'long_only_minimum_variance', 'existing_market_benchmark'})
    vectors = {}
    for name, row in rows.items():
        w = np.array([row['weights'][c] for c in codes])
        vectors[name] = w
        v = float(np.dot(w, sigma.dot(w)))
        check(name + ': raw feasible long-only sum-one vector', np.isfinite(w).all() and np.all(w >= 0) and abs(w.sum() - 1) < 1e-12)
        check(name + ': saved variance, annualized volatility and historical daily mean recompute', abs(v - row['daily_variance']) < 1e-15 and abs(np.sqrt(252 * v) - row['annualized_in_sample_volatility']) < 1e-12 and abs(w @ np.array(m['daily_mean_return']) - row['historical_daily_mean']) < 1e-15)
        check(name + ': institution gold and AI-arm flags remain false', row['institution_specific'] is False and row['institutional_gold'] is False and row['is_AI_experimental_arm'] is False)
    check('equal-weight construction is exactly 1/11', np.array_equal(vectors['equal_weight'], np.ones(11) / 11))
    check('existing benchmark is carried verbatim from supplied comparison anchor', np.array_equal(vectors['existing_market_benchmark'], [m['baseline_weights'][c] for c in codes]))

    w = vectors['long_only_minimum_variance']
    var = float(w @ sigma @ w)
    active = w > 0
    support = np.flatnonzero(active)
    # Independently solve the equality KKT system for the recorded active set.
    # This does not call the builder's inverse-one stationary-point function.
    block = np.block([[2 * sigma[np.ix_(active, active)], -np.ones((sum(active), 1))],
                      [np.ones((1, sum(active))), np.zeros((1, 1))]])
    right = np.r_[np.zeros(sum(active)), 1.0]
    kkt_solution = np.linalg.solve(block, right)
    active_error = float(np.max(np.abs(w[active] - kkt_solution[:-1])))
    lagrange = float(kkt_solution[-1])
    reduced_gradient = 2 * sigma @ w - lagrange
    check('independent active-set KKT linear system reproduces saved weights', active_error < 1e-12)
    check('positive support stationarity and inactive inequalities hold', np.max(np.abs(reduced_gradient[active])) < 1e-12 and np.min(reduced_gradient[~active]) >= -1e-12)
    check('saved support indices and exhaustive nonempty-face count agree', support.tolist() == r['solver']['selected_support_indexes'] and r['solver']['examined_faces'] == 2 ** 11 - 1)
    check('saved eigenvalue and objective agree with direct calculations', abs(np.linalg.eigvalsh(sigma)[0] - r['solver']['minimum_eigenvalue']) < 1e-15 and abs(var - r['solver']['daily_variance']) < 1e-15)
    check('GMV objective no higher than either feasible comparison', var <= min(vectors['equal_weight'] @ sigma @ vectors['equal_weight'], vectors['existing_market_benchmark'] @ sigma @ vectors['existing_market_benchmark']) + 1e-15)
    check('no generation and no reference added to prompts declared', r['model_generation_requests'] == 0 and r['visibility'] == 'evaluator_only_not_added_to_any_model_prompt')
    check('local implementation does not claim expected-return or macro optimization', any('capital-appreciation' in x for x in r['limitations']) and any('macro context' in x for x in r['limitations']))

    paper_path = 'research/evidence/v48_reference_20261018/portbench_2605_27887v6.html'
    paper = (ROOT / paper_path).read_text(encoding='utf8')
    check('preserved primary paper identifies both standard comparator families', 'Equal-Weight' in paper and 'Minimum Variance' in paper)
    result = {
        'protocol_version': '4.9.2', 'status': 'PASS' if all(x['pass'] for x in checks) else 'FAIL',
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'reviewer': 'Codex /root/v491_review_pack, separate review from reference builder author',
        'review_kind': 'AI mathematical/input/methods audit, not independent human review',
        'input_refs': [ref(record_path), ref(source_path), ref('research/build_v492_computational_references.py'), ref(paper_path)],
        'checks': checks,
        'independent_recalculation': {'method': 'KKT block linear system for saved positive support, then nonnegative dual-residual and positive-definite Hessian checks',
            'support_indices': support.tolist(), 'max_active_weight_difference': active_error,
            'stationarity_max_abs_residual': float(np.max(np.abs(reduced_gradient[active]))),
            'inactive_min_reduced_gradient': float(np.min(reduced_gradient[~active])),
            'daily_variance': var,
            'sufficient_optimality_reason': 'The positive-definite covariance makes the objective strictly convex on the simplex. Primal feasibility, equality stationarity on positive weights and nonnegative inactive reduced gradients establish the unique constrained minimum to the stated numerical tolerance.'},
        'primary_paper_review': {'url': 'https://arxiv.org/html/2605.27887v6', 'locations': ['Section 3.1 classical baselines', 'Appendix C.4 Classical strategies'],
            'verified_on': '2026-10-19', 'inspection': 'Fresh official arXiv page read and preserved prior HTML bound by SHA.',
            'supported': 'The paper uses uniform allocation and long-only minimum variance as classical comparators; covariance strategies use common trailing returns and 252-day annualization.',
            'adaptation': 'This audit approves their formulas on the frozen eleven-sector data only. It does not import the paper\'s multi-asset eligibility, replay, costs, investor profiles, outcome ranking or stage gold scores.'},
        'topic_connection': 'References expose the allocation produced by simple transparent numerical rules. They cannot interpret institution prose or the supplied macro context, so the common-context AI C arm supplies the appropriate task-level comparison while these remain arithmetic/risk references.',
        'claims_allowed': ['Equal weight is uniform over the eleven supplied sectors.', 'GMV is the minimum-variance long-only portfolio for this particular past-window sample covariance.', 'Distances to these references describe allocations; they are not source-fidelity scores.'],
        'claims_not_allowed': ['This is the optimal investment for the common capital-appreciation objective.', 'This vector recovers Fidelity or UBS strategy.', 'Lower in-sample volatility establishes future superiority or lower actual realized risk.', '1/N or GMV replaces the C control or proves a causal effect of institutional information.'],
        'scope_limitations': ['The saved sample covariance was checked for identity and units; no new market data were downloaded.', 'The parent separately enumerated 2047 faces and ran SLSQP; this reviewer independently checked the saved solution with a different KKT formulation.', 'Source review and computation review are AI-assisted, with no fabricated human approval.', 'Solver tolerances are engineering precision conventions and not behavioral or investment thresholds.'],
        'material_findings': [], 'model_generation_requests': 0,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    print(json.dumps({'path': OUT.relative_to(ROOT).as_posix(), 'status': result['status'], 'checks': len(checks), 'sha256': ref(OUT.relative_to(ROOT).as_posix())['sha256'], 'max_active_weight_difference': active_error}, indent=2))
    if result['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
