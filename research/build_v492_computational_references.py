"""Two non-LLM reference strategies; no institutional gold allocation is assumed."""
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'data/sector_protocol/v491_design_20261019/public_compact_candidate.json'
INPUT_SHA = 'afe810b2bfb69ae4bfa372e65fa587bc6253eecf8028d5fde39cf3ec395bcb8d'
OUTPUT = ROOT / 'research/v492_computational_references_20261019.json'


def minimum_variance_by_faces(covariance):
    """Enumerate every simplex face, solve its equality-constrained stationary point.

    For a positive definite covariance, the minimum on the simplex lies at the
    positive stationary point of one of these faces (including vertices).
    No weight clipping, shrinkage, expected-return forecast, or risk lambda.
    """
    n = len(covariance)
    candidates = []
    for size in range(1, n + 1):
        for indexes in itertools.combinations(range(n), size):
            indexes = list(indexes)
            local = covariance[np.ix_(indexes, indexes)]
            inverse_one = np.linalg.solve(local, np.ones(size))
            local_weights = inverse_one / np.sum(inverse_one)
            if np.any(local_weights < 0):
                continue
            weights = np.zeros(n)
            weights[indexes] = local_weights
            candidates.append((float(weights @ covariance @ weights), weights, indexes))
    candidates.sort(key=lambda row: row[0])
    variance, weights, indexes = candidates[0]
    return weights, {'examined_faces': 2 ** n - 1, 'feasible_stationary_points': len(candidates),
                     'selected_support_indexes': indexes, 'daily_variance': variance}


def main():
    if OUTPUT.exists():
        raise ValueError('Preserve existing reference; use a new revision for changes')
    if hashlib.sha256(INPUT.read_bytes()).hexdigest() != INPUT_SHA:
        raise ValueError('The frozen public input changed')
    market = json.loads(INPUT.read_text(encoding='utf-8'))['common_market']
    covariance = np.asarray(market['covariance'], dtype=float)
    codes = market['sector_codes']
    if covariance.shape != (11, 11) or len(set(codes)) != 11:
        raise ValueError('Expected the existing ordered eleven-sector universe')
    if not np.isfinite(covariance).all() or not np.allclose(covariance, covariance.T, rtol=0, atol=1e-15):
        raise ValueError('Nonfinite or asymmetric covariance')
    eigenvalues = np.linalg.eigvalsh(covariance)
    if eigenvalues[0] <= 0:
        raise ValueError('Positive definiteness is required; no silent covariance repair')
    equal = np.full(11, 1 / 11)
    gmv, enumeration = minimum_variance_by_faces(covariance)
    benchmark = np.array([market['baseline_weights'][c] for c in codes])
    scale = float(np.trace(covariance) / len(covariance))
    scaled = covariance / scale
    independent = minimize(lambda w: float(w @ scaled @ w), equal,
        jac=lambda w: 2 * scaled @ w, method='SLSQP', bounds=[(0, 1)] * 11,
        constraints=[{'type': 'eq', 'fun': lambda w: float(np.sum(w) - 1), 'jac': lambda w: np.ones(11)}],
        options={'ftol': 1e-13, 'maxiter': 1000})
    variance = float(gmv @ covariance @ gmv)
    gradient = covariance @ gmv
    support = gmv > 0
    stationarity = float(np.max(np.abs(gradient[support] - variance)))
    inactive_min = float(np.min(gradient[~support] - variance)) if np.any(~support) else None
    tests = [
        ('all weights finite, nonnegative and sum one', all(np.isfinite(w).all() and np.all(w >= 0) and abs(np.sum(w) - 1) <= 1e-12 for w in (equal, gmv, benchmark))),
        ('KKT stationarity on positive support', stationarity <= 1e-12),
        ('KKT inactive inequality', inactive_min is None or inactive_min >= -1e-12),
        ('variance no greater than equal weighting or market benchmark', variance <= min(equal @ covariance @ equal, benchmark @ covariance @ benchmark) + 1e-12),
        ('independent SLSQP success', bool(independent.success)),
        ('independent SLSQP weight agreement', bool(np.max(np.abs(independent.x - gmv)) <= 1e-6)),
        ('independent SLSQP objective agreement', abs(float(independent.x @ covariance @ independent.x) - variance) <= 1e-12),
        ('input annualized volatility consistency', bool(np.allclose(np.sqrt(np.diag(covariance) * market['annualization_trading_days']), market['annualized_volatility_diagnostic'], rtol=0, atol=1e-12))),
    ]
    rows = []
    for name, weights in [('equal_weight', equal), ('long_only_minimum_variance', gmv), ('existing_market_benchmark', benchmark)]:
        rows.append({'reference_id': name, 'weights': dict(zip(codes, weights.tolist())),
                     'daily_variance': float(weights @ covariance @ weights),
                     'annualized_in_sample_volatility': float(np.sqrt(weights @ covariance @ weights * market['annualization_trading_days'])),
                     'historical_daily_mean': float(weights @ np.array(market['daily_mean_return'])),
                     'institution_specific': False, 'institutional_gold': False,
                     'is_AI_experimental_arm': False})
    record = {
        'protocol_version': '4.9.2', 'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'PASS' if all(ok for _, ok in tests) else 'FAIL',
        'visibility': 'evaluator_only_not_added_to_any_model_prompt',
        'input_ref': {'path': INPUT.relative_to(ROOT).as_posix(), 'sha256': INPUT_SHA},
        'input_pointer': '/common_market', 'covariance_unit': market['covariance_unit'],
        'dates': market['lookback_return_dates'], 'observations': market['return_observations'],
        'sector_codes': codes, 'sector_names': market['sector_names'],
        'formulas': {'equal_weight': 'w_i=1/N, N=11 supplied sectors',
                     'minimum_variance': 'argmin_w w^T Sigma w subject to w_i>=0 and sum(w_i)=1',
                     'annualized_in_sample_volatility': 'sqrt(252*w^T Sigma w)'},
        'paper_basis': {'url': 'https://arxiv.org/html/2605.27887v6',
                       'locations': ['Section3.1 classical baselines', 'AppendixC.4 classical strategies'],
                       'adopted': 'Equal weighting and long-only minimum-variance reference strategies on common trailing returns.',
                       'local_adaptation': 'Apply those strategies to the existing eleven-sector case. No replay, performance win, investor profile or institution-specific optimality is asserted.'},
        'solver': {'method': 'all-simplex-face stationary solutions', **enumeration,
                   'minimum_eigenvalue': float(eigenvalues[0]), 'condition_number': float(eigenvalues[-1] / eigenvalues[0]),
                   'KKT_support_max_residual': stationarity, 'KKT_inactive_min_margin': inactive_min,
                   'independent_method': 'scipy SLSQP, positive scalar objective scaling only',
                   'independent_success': bool(independent.success), 'independent_message': independent.message,
                   'independent_max_weight_difference': float(np.max(np.abs(independent.x - gmv)))},
        'implementation_numeric_tolerances': {'purpose': 'Floating-point/solver verification only; no behavioral cutoffs or investment thresholds.',
                                            'KKT_atol': 1e-12, 'SLSQP_ftol': 1e-13, 'cross_solver_weight_atol': 1e-6},
        'references': rows,
        'checks': [{'check': name, 'pass': bool(ok)} for name, ok in tests],
        'dependencies': {'numpy': np.__version__, 'scipy': scipy.__version__},
        'limitations': [
            'The sample covariance minimizes risk in the supplied past window; it is not a known future covariance.',
            'Risk minimization does not optimize the capital-appreciation objective or implement institutional qualitative views.',
            'These references do not interpret the supplied macro context; the matched common-context AI arm C is the strategic control.',
            'No institution-specific expected returns, risk coefficient, target weights, rating-to-weight rule or gold answer was invented.',
            'Current vendor-adjusted historical-price vintage is retained; this is not a point-in-time trading backtest.',
        ],
        'model_generation_requests': 0,
    }
    OUTPUT.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'status': record['status'], 'checks': len(tests), 'weights': rows[1]['weights'],
                      'cross_solver_max_difference': record['solver']['independent_max_weight_difference']}))
    if record['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
