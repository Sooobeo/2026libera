"""External proportional normalization, followed by the original constraints.

This policy never clips, sign-flips, optimizes, or rewrites a model response.
Its checks must use the original holdings, covariance and explicit constraints.
"""
from copy import deepcopy
import math
from numbers import Real

POLICY_ID = 'proportional_nonnegative_100_then_original_constraints_v1'


def normalize_and_check(raw_weights, h, check_weights, *, raw_check=None):
    """Return a separate policy record; preserve both input vectors unchanged."""
    if check_weights(h).get('valid') is not True:
        raise ValueError('Original holdings must satisfy the original constraints before fallback.')
    if raw_check is None:
        raw_check = check_weights(raw_weights)
    result = {
        'policy_id': POLICY_ID, 'eligible': False, 'normalization_performed': False,
        'normalized_weights': None, 'normalized_check': None,
        'raw_valid': raw_check.get('valid') is True, 'postprocessed_valid': False,
        'effective_weights': deepcopy(h), 'fallback': True, 'failure_reason': None,
        'original_sum': None, 'normalized_sum': None,
        'residual_correction_index': None, 'residual_correction': 0.0,
    }
    if not isinstance(raw_weights, (list, tuple)) or len(raw_weights) != 12:
        result['failure_reason'] = 'invalid_weight_vector_shape'
        return result
    if any(isinstance(x, bool) or not isinstance(x, Real) or not math.isfinite(x) for x in raw_weights):
        result['failure_reason'] = 'nonnumeric_or_nonfinite_weights'
        return result
    if any(x < 0 for x in raw_weights):
        result['failure_reason'] = 'negative_weights'
        return result
    try:
        total = math.fsum(raw_weights)
    except OverflowError:
        result['failure_reason'] = 'nonfinite_weight_sum'
        return result
    if not math.isfinite(total):
        result['failure_reason'] = 'nonfinite_weight_sum'
        return result
    result['original_sum'] = total
    if total <= 0:
        result['failure_reason'] = 'nonpositive_weight_sum'
        return result
    result['eligible'] = True
    normalized = [float(x) / total for x in raw_weights]
    # Remove only floating-point summation residual, at the largest component.
    # Python's max chooses the first index on ties, making this deterministic.
    residual = 1.0 - math.fsum(normalized)
    if residual:
        index = max(range(12), key=normalized.__getitem__)
        normalized[index] += residual
        result.update(residual_correction_index=index, residual_correction=residual)
    if not all(math.isfinite(x) and x >= 0 for x in normalized):
        result['failure_reason'] = 'normalization_numeric_error'
        return result
    result.update(normalization_performed=True, normalized_weights=normalized,
                  normalized_sum=math.fsum(normalized))
    checked = check_weights(normalized)
    result['normalized_check'] = deepcopy(checked)
    if checked.get('valid') is not True:
        result['failure_reason'] = 'normalized_constraints_failed'
        return result
    result.update(postprocessed_valid=True, effective_weights=deepcopy(normalized), fallback=False)
    return result
