"""v4.5 response structure only; no answer labels, weights, or evaluator access.

The grammar is a generation aid. The independent, strict validator remains
authoritative for types and array lengths. Sector coverage is diagnostic only.
Portfolio sums, signs and constraint compliance stay with the unchanged engine.
"""
from __future__ import annotations

import copy
import hashlib
import math

from sector_engine import SECTOR_CODES, parse_response

SCHEMA_VERSION = 'sector_response_structure_v45'
GROUNDING_VERSION = 'stage_schema_grounding_v45'
REQUIRED_KEYS = ('source_id', 'interpretations', 'weights', 'alternatives',
                 'risk_discussion', 'unresolved', 'submitted_constraints')
CONTRACT_INSTRUCTION = (
    'Return only the requested response object satisfying response_schema. '
    'Fill its seven fields with your analysis. common_market and institution_document '
    'are evidence, not response fields. Do not reproduce the input object. '
    'The schema supplies no correct ratings, evidence selections or portfolio weights. '
    'Structural compliance is not a claim that the analysis is correct.'
)


def _object(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def response_schema(stage, institution_visible=True):
    if type(stage) is not int or stage not in (1, 2, 3, 4):
        raise ValueError('A stage from 1 through 4 is required')
    text = {'type': 'string', 'minLength': 1}
    code = {'type': 'string', 'enum': list(SECTOR_CODES)}
    ids = {'type': 'array', 'items': text}
    interpretation = _object({'sector_code': code, 'rating': text,
                              'evidence_ids': ids, 'reason': text})
    weight = _object({'sector_code': code, 'weight': {'type': 'number'},
                      'rationale': text, 'evidence_ids': ids})
    all_weights = {'type': 'array', 'items': weight, 'minItems': 11, 'maxItems': 11}
    # Do not use tuple/prefixItems or uniqueItems: the pinned grammar converter
    # does not establish their support. Code coverage is checked after generation.
    weights = ({'anyOf': [{'type': 'array', 'items': weight, 'maxItems': 0}, all_weights]}
               if stage < 3 else all_weights)
    constraint = _object({'constraint_id': text, 'sector_code': code,
                         'kind': {'type': 'string', 'enum': ['sector_min_weight', 'sector_max_weight']},
                         'bound': {'type': 'number'}, 'evidence_ids': ids})
    schema = _object({
        'source_id': {'type': ['string', 'null']},
        'interpretations': {'type': 'array', 'items': interpretation,
                            'minItems': 11 if institution_visible else 0,
                            'maxItems': 11 if institution_visible else 0},
        'weights': weights,
        'alternatives': text, 'risk_discussion': text,
        'unresolved': {'type': 'array', 'items': text},
        'submitted_constraints': {'type': 'array', 'items': constraint},
    })
    return copy.deepcopy(schema)


def _type_ok(value, kind):
    if kind == 'null': return value is None
    if kind == 'string': return isinstance(value, str)
    if kind == 'object': return isinstance(value, dict)
    if kind == 'array': return isinstance(value, list)
    if kind == 'number':
        if isinstance(value, bool) or not isinstance(value, (int, float)): return False
        try: return math.isfinite(float(value))
        except (OverflowError, ValueError): return False
    raise ValueError('Unsupported schema type: ' + str(kind))


def _errors(value, schema, path='$'):
    """Validate the exact supported subset emitted above, without dependencies."""
    errors = []
    if 'anyOf' in schema:
        if not any(not _errors(value, option, path) for option in schema['anyOf']):
            errors.append(path + ': no allowed structural alternative')
        return errors
    kinds = schema['type'] if isinstance(schema['type'], list) else [schema['type']]
    if not any(_type_ok(value, kind) for kind in kinds):
        return [path + ': invalid type or nonfinite number']
    if 'enum' in schema and value not in schema['enum']:
        errors.append(path + ': value outside public structural vocabulary')
    if isinstance(value, dict):
        for key in schema['required']:
            if key not in value: errors.append(path + ': missing key ' + key)
        for key in value:
            if key not in schema['properties']:
                errors.append(path + ': unexpected key ' + key)
            else:
                errors.extend(_errors(value[key], schema['properties'][key], path + '.' + key))
    elif isinstance(value, list):
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', math.inf):
            errors.append(path + ': incorrect row count')
        for index, item in enumerate(value):
            errors.extend(_errors(item, schema['items'], path + '[' + str(index) + ']'))
    elif isinstance(value, str) and len(value) < schema.get('minLength', 0):
        errors.append(path + ': empty required text')
    return errors


def validate_response(text, stage, expected_source_id, institution_visible=True):
    """No repairs. No numerical target, rating truth or citation truth is read."""
    parsed = parse_response(text)
    errors = [] if parsed['ok'] else [parsed['error']]
    coverage, identity_matches = {}, None
    if parsed['ok']:
        value = parsed['value']
        errors.extend(_errors(value, response_schema(stage, institution_visible)))
        # Identity comes only from already-visible public metadata, not gold.
        expected = expected_source_id if institution_visible else None
        identity_matches = value.get('source_id') == expected
        for field in ('interpretations', 'weights'):
            rows = value.get(field)
            if isinstance(rows, list) and rows:
                codes = [r.get('sector_code') for r in rows if isinstance(r, dict)]
                complete = (len(codes) == len(SECTOR_CODES) and all(isinstance(c, str) for c in codes)
                            and set(codes) == set(SECTOR_CODES) and len(set(codes)) == len(codes))
                coverage[field] = {'all_public_codes_once': complete,
                                   'blocking': False, 'basis': 'public_taxonomy_only'}
    return {'status': 'valid_structure' if not errors else 'invalid_structure',
            'valid': not errors, 'stage': stage, 'schema_version': SCHEMA_VERSION,
            'content_utf8_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest() if isinstance(text, str) else None,
            'errors': errors, 'response_repaired': False,
            'source_identity_matches_visible_metadata': identity_matches,
            'row_coverage_diagnostics': coverage,
            'source_identity_basis': 'already-visible document metadata only',
            'assessment_scope': 'structure_and_public_metadata_only_not_semantic_or_financial_pass',
            'human_semantic_pass': False, 'rating_correctness_assessed': False,
            'citation_correctness_assessed': False, 'weight_sum_or_sign_repaired': False}
