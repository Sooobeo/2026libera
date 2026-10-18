"""Pure, reversible prompt representation; no files, models, or network access.

This is an engineering candidate, not a new paper parameter or an information
ablation. It removes only two verified duplicate fields. All unique field values
and numeric values remain available, including the full covariance/correlation
matrices. Original JSON whitespace/key ordering is not part of the contract.
Adopting this representation still requires a recorded protocol revision: equal
JSON values do not guarantee equal language-model behavior.
"""
from __future__ import annotations

import copy
import json
import math
from typing import Any


PROJECTION_VERSION = 'sector_market_exact_duplicates_v1'
DDOF_KEY = 'covariance_ddof'


def _check_json(value: Any) -> None:
    """Reject lossy Python-to-JSON coercions, nonfinite numbers and foreign types."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError('Nonfinite numbers cannot be preserved in JSON')
        return
    if type(value) is list:
        for item in value:
            _check_json(item)
        return
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError('JSON object keys must be strings; no key coercion')
        for item in value.values():
            _check_json(item)
        return
    raise ValueError('Only JSON-native values are supported')


def compact_json(value: Any) -> str:
    """Remove serialization whitespace, never whitespace inside a string value."""
    _check_json(value)
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _same_values(left: Any, right: Any) -> bool:
    # Python equality would silently identify True with 1 and -0.0 with 0.0.
    # Canonical JSON additionally preserves int/float forms and signed zero.
    return json.dumps(left, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(',', ':')) == json.dumps(
        right, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))


def _check_retained_fields(market: dict) -> None:
    codes = market.get('sector_codes')
    baseline = market.get('baseline_weights')
    covariance = market.get('covariance')
    if (type(codes) is not list or not codes
            or any(type(code) is not str for code in codes)
            or len(set(codes)) != len(codes)):
        raise ValueError('A unique sector code order is required')
    if type(baseline) is not dict or set(baseline) != set(codes):
        raise ValueError('Baseline weights must match the sector code order')
    if any(type(baseline[code]) not in (int, float) for code in codes):
        raise ValueError('Baseline weights must be numeric, not booleans')
    if (type(covariance) is not list or len(covariance) != len(codes)
            or any(type(row) is not list or len(row) != len(codes)
                   or any(type(x) not in (int, float) for x in row)
                   for row in covariance)):
        raise ValueError('Covariance shape must match the sector code order')


def project_market(market: dict) -> dict:
    """Return a detached projection, refusing missing/unequal duplicate fields.

    `sample_covariance_ddof_1` is replaced by explicit `covariance_ddof: 1`;
    `covariance` retains every matrix value. The baseline array is reconstructible
    from `baseline_weights` in the unchanged `sector_codes` order. A pre-existing
    metadata key is rejected instead of overwritten. No rounding is performed.
    """
    _check_json(market)
    if type(market) is not dict:
        raise ValueError('Market must be a JSON object')
    if DDOF_KEY in market:
        raise ValueError('Reserved covariance metadata already exists')
    _check_retained_fields(market)
    if 'sample_covariance_ddof_1' not in market or not _same_values(
            market['covariance'], market['sample_covariance_ddof_1']):
        raise ValueError('Covariance fields are not exact duplicates')
    expected = [market['baseline_weights'][code] for code in market['sector_codes']]
    if 'baseline_weights_array' not in market or not _same_values(
            expected, market['baseline_weights_array']):
        raise ValueError('Baseline fields are not exact duplicates in sector order')
    result = copy.deepcopy(market)
    del result['sample_covariance_ddof_1']
    del result['baseline_weights_array']
    result[DDOF_KEY] = 1
    return result


def restore_market(projected: dict) -> dict:
    """Reconstruct every original field value; key ordering is not preserved.

    This function validates the projection structure, not its provenance or hash.
    Callers must archive/hash the original packet and representation version.
    """
    _check_json(projected)
    if type(projected) is not dict:
        raise ValueError('Projected market must be a JSON object')
    if type(projected.get(DDOF_KEY)) is not int or projected[DDOF_KEY] != 1:
        raise ValueError('Exact ddof=1 metadata is required')
    if 'sample_covariance_ddof_1' in projected or 'baseline_weights_array' in projected:
        raise ValueError('Projection unexpectedly contains removed duplicate fields')
    _check_retained_fields(projected)
    result = copy.deepcopy(projected)
    del result[DDOF_KEY]
    result['sample_covariance_ddof_1'] = copy.deepcopy(result['covariance'])
    result['baseline_weights_array'] = [result['baseline_weights'][code]
                                       for code in result['sector_codes']]
    return result


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate JSON keys cannot be compacted losslessly')
        value[key] = item
    return value


def compact_stage_content(content: str) -> str:
    """Compact existing stage-payload JSON; project common_market only in stage 1.

    Evidence text and all other string values are unchanged. This does not process
    model responses, strip Markdown, repair outputs, or select evidence.
    """
    value = json.loads(content, object_pairs_hook=_unique_object)
    if type(value) is not dict:
        raise ValueError('Stage payload must be a JSON object')
    if 'common_market' in value:
        if type(value.get('stage')) is not int or value['stage'] != 1:
            raise ValueError('Common market projection is only defined for stage 1')
        value['common_market'] = project_market(value['common_market'])
    return compact_json(value)
