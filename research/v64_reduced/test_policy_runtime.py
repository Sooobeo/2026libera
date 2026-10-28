"""Synthetic numeric and mocked-client tests; no model, HTTP, or service calls."""
from copy import deepcopy
import json
import math

import numpy as np
import pytest

from research.v63.numerics import check_portfolio, jsonable
from research.v63.recovery import RecoveryInterruption
from research.v63.test_runtime_retrieval import baseline, final, packet, response
from research.v64_reduced import runtime
from research.v64_reduced.policy import POLICY_ID, normalize_and_check


H = [1 / 12] * 12


def checker(sigma=None, a=None, b=None):
    sigma = np.eye(12) if sigma is None else sigma
    return lambda w: jsonable(check_portfolio(w, H, sigma, a, b))


def test_proportional_100_keeps_raw_and_original_holdings_unchanged():
    raw = [20.] * 12
    original = deepcopy(raw)
    h = deepcopy(H)
    result = normalize_and_check(raw, h, checker())
    assert raw == original and h == H
    assert result['policy_id'] == POLICY_ID
    assert result['raw_valid'] is False and result['postprocessed_valid'] is True
    assert math.fsum(result['effective_weights']) == 1.
    assert result['effective_weights'] == H
    assert result['fallback'] is False and result['original_sum'] == 240.


def test_already_one_remains_valid_and_not_fallback():
    raw = [1., 0.] + [0.] * 10
    # Zero covariance permits this originally valid concentrated portfolio.
    result = normalize_and_check(raw, H, checker(np.zeros((12, 12))))
    assert result['raw_valid'] is True and result['postprocessed_valid'] is True
    assert result['effective_weights'] == raw and result['fallback'] is False
    assert result['residual_correction'] == 0.


@pytest.mark.parametrize('weights,reason', [
    ([0.] * 12, 'nonpositive_weight_sum'),
    ([-1.] * 12, 'negative_weights'),
    ([-.1, .2] + [.1] * 10, 'negative_weights'),
    ([float('nan')] + [1.] * 11, 'nonnumeric_or_nonfinite_weights'),
    ([float('inf')] + [1.] * 11, 'nonnumeric_or_nonfinite_weights'),
    ([True] + [1.] * 11, 'nonnumeric_or_nonfinite_weights'),
    ([1.] * 11, 'invalid_weight_vector_shape'),
])
def test_ineligible_vectors_use_original_h_without_any_normalization(weights, reason):
    result = normalize_and_check(weights, H, checker())
    assert result['failure_reason'] == reason
    assert result['eligible'] is False and result['normalization_performed'] is False
    assert result['normalized_weights'] is None and result['normalized_check'] is None
    assert result['effective_weights'] == H and result['fallback'] is True


def test_finite_components_with_overflowing_sum_are_not_normalized():
    check = lambda w: {'valid': list(w) == H}
    result = normalize_and_check([1e308] * 12, H, check)
    assert result['failure_reason'] == 'nonfinite_weight_sum'
    assert result['effective_weights'] == H and not result['normalization_performed']


def test_normalization_can_cross_original_risk_cap_and_must_fallback():
    raw = [.1] + [0.] * 11
    raw_check = checker()(raw)
    assert raw_check['risk'] < raw_check['risk_cap']
    result = normalize_and_check(raw, H, checker(), raw_check=raw_check)
    assert result['normalized_weights'] == [1.] + [0.] * 11
    assert result['normalized_check']['failures'] == ['risk_cap']
    assert result['normalization_performed'] and not result['postprocessed_valid']
    assert result['effective_weights'] == H and result['fallback']


def test_normalization_rechecks_the_original_linear_constraints():
    a = [[1.] + [0.] * 11]
    result = normalize_and_check([.1] + [0.] * 11, H,
                                 checker(np.zeros((12, 12)), a, [.2]))
    assert result['normalized_check']['failures'] == ['explicit_constraint']
    assert result['effective_weights'] == H and result['fallback']


def test_invalid_original_holdings_fail_closed_instead_of_becoming_fallback():
    with pytest.raises(ValueError, match='Original holdings'):
        normalize_and_check([.2] * 12, [0.] * 12, checker())


def test_residual_correction_is_deterministic_at_first_largest_component():
    # Search only for a floating representation that requires a nonzero residual,
    # then verify the operation against an independent proportional calculation.
    candidates = [[float(i * k + 1) for i in range(12)] for k in range(1, 100)]
    raw = next(w for w in candidates if 1. - math.fsum(x / math.fsum(w) for x in w))
    expected = [x / math.fsum(raw) for x in raw]
    residual = 1. - math.fsum(expected)
    index = max(range(12), key=expected.__getitem__)
    expected[index] += residual
    result = normalize_and_check(raw, H, checker(np.zeros((12, 12))))
    assert result['residual_correction_index'] == index
    assert result['residual_correction'] == residual
    assert result['normalized_weights'] == expected
    assert math.isclose(math.fsum(expected), 1., abs_tol=1e-15, rel_tol=0)
    assert normalize_and_check(raw, H, checker(np.zeros((12, 12)))) == result


def run_fake(tmp_path, responses, *, weights_check=None):
    requests = []
    def client(raw):
        requests.append(json.loads(raw))
        item = responses[len(requests) - 1]
        if isinstance(item, BaseException):
            raise item
        return deepcopy(item)
    trace = runtime.run_trajectory(baseline(), packet(), 'R1', client,
        lambda *args: {'error': 'synthetic-only'}, weights_check or checker(),
        {'model': 'synthetic', 'model_sha256': 'TEST_ONLY', 'context_tokens': 100000, 'output_tokens': 4096},
        output_dir=tmp_path / 'trajectory', count_rendered_request=lambda req: len(json.dumps(req).split()),
        engineering=True)
    assert json.loads((tmp_path / 'trajectory/trace.json').read_bytes()) == trace
    return trace, requests


def test_stage2_retains_raw_payload_and_labels_external_feedback(tmp_path):
    raw = [.2] * 12
    trace, requests = run_fake(tmp_path, [response(final(1)), response(final(2, raw)), response(final(3))])
    stage2 = trace['stages'][1]
    assert stage2['raw_output']['weights'] == raw
    assert stage2['raw_weight_check']['valid'] is False
    assert stage2['normalization']['postprocessed_valid'] is True
    message = next(m for m in requests[2]['messages'] if m['content'].startswith('EXTERNAL WEIGHT'))
    feedback = json.loads(message['content'].split('\n', 1)[1])
    assert feedback['original_model_output_retained'] is True
    assert feedback['raw_weight_check']['valid'] is False
    assert feedback['external_normalization']['effective_weights'] == H
    assert 'produced externally by the host' in feedback['instruction']
    prior_assistant = [m for m in requests[2]['messages'] if m['role'] == 'assistant'][-1]
    assert json.loads(prior_assistant['content'])['output']['weights'] == raw
    assert trace['actual_model_calls'] == 3 and trace['status'] == 'completed'


def test_stage3_distinguishes_raw_failure_from_valid_applied_policy(tmp_path):
    raw = [.2] * 12
    trace, _ = run_fake(tmp_path, [response(final(1)), response(final(2)), response(final(3, raw))])
    assert trace['stages'][2]['raw_output']['weights'] == raw
    assert trace['stages'][2]['raw_weight_check']['valid'] is False
    assert trace['raw_output_valid'] is False and trace['raw_terminal_status'] == 'model_output_failure'
    assert trace['policy_output_valid'] is True and trace['status'] == 'completed'
    assert trace['effective_weights'] == H and trace['fallback'] is False


@pytest.mark.parametrize('raw', [[-.1] * 12, [0.] * 12, [.1] + [0.] * 11])
def test_stage3_ineligible_or_recheck_failure_falls_back_without_rewriting_raw(tmp_path, raw):
    trace, _ = run_fake(tmp_path, [response(final(1)), response(final(2)), response(final(3, raw))])
    assert trace['status'] == 'model_output_failure' and trace['fallback'] is True
    assert trace['effective_weights'] == H and trace['policy_output_valid'] is False
    assert trace['stages'][2]['raw_output']['weights'] == raw
    assert trace['stages'][2]['normalization']['postprocessed_valid'] is False


def test_failed_stage2_policy_still_allows_stage3_to_submit_new_raw_vector(tmp_path):
    trace, requests = run_fake(tmp_path, [response(final(1)), response(final(2, [-.1] * 12)), response(final(3))])
    assert trace['stages'][1]['normalization']['fallback'] is True
    assert trace['status'] == 'completed' and trace['raw_output_valid'] is True
    assert len(requests) == 3


@pytest.mark.parametrize('content', ['{bad', '{"kind":"final","output":NaN}',
                                    '{"kind":"final","output":Infinity}',
                                    '{"kind":"final","output":1e309}'])
def test_invalid_or_nonfinite_json_never_normalizes_or_fills_unattempted_stages(tmp_path, content, monkeypatch):
    monkeypatch.setattr(runtime, 'normalize_and_check', lambda *args, **kwargs: pytest.fail('No numeric policy for malformed response'))
    item = response({});item['content'] = content
    trace, requests = run_fake(tmp_path, [item])
    assert len(requests) == 1 and trace['status'] == 'model_output_failure'
    assert trace['calls'][0]['raw_response']['content'] == content
    assert [s['status'] for s in trace['stages']] == ['model_output_failure', 'parent_failure', 'parent_failure']
    assert not any('normalization' in s for s in trace['stages'])
    assert trace['effective_weights'] == H


@pytest.mark.parametrize('failure,status', [
    (RecoveryInterruption('uncertain previous dispatch'), 'recovery_interrupted'),
    (runtime.ProtocolViolation('identity mismatch'), 'protocol_violation'),
])
def test_recovery_or_protocol_interruption_never_becomes_policy_fallback(tmp_path, failure, status, monkeypatch):
    monkeypatch.setattr(runtime, 'normalize_and_check', lambda *args, **kwargs: pytest.fail('No numeric policy for interruption'))
    trace, requests = run_fake(tmp_path, [failure])
    assert trace['status'] == status and trace['effective_weights'] is None and trace['fallback'] is False
    assert trace['raw_terminal_status'] == status and len(requests) == 1
    assert all(s['status'] == 'not_attempted' for s in trace['stages'][1:])


def test_parent_hash_drift_stops_before_any_request_or_trace(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'PARENT_RUNTIME_SHA256', '0' * 64)
    with pytest.raises(ValueError, match='parent runtime changed'):
        run_fake(tmp_path, [])
    assert not (tmp_path / 'trajectory').exists()
