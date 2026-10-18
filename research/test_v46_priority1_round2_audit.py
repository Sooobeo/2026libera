"""Pure offline checks of the independent audit; no model or network access."""
import copy
from decimal import Decimal
from fractions import Fraction
import unittest

from build_v46_priority1_round2_audit import (
    arithmetic, constraint_checks, exact_text, strict_json, structural_errors)


CODES = ['10', '15', '20', '25', '30', '35', '40', '45', '50', '55', '60']
TOLERANCE = Decimal('0.000001')


def rows():
    values = ['.025', '.015', '.1', '.09', '.04', '.09', '.11', '.37', '.02', '.02', '.085']
    return [{'sector_code': code, 'weight': Decimal(value)} for code, value in zip(CODES, values)]


class IndependentArithmeticTests(unittest.TestCase):
    def test_literal_parser_rejects_duplicate_keys_and_nonfinite(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(ValueError):
                strict_json(text)
        self.assertEqual(strict_json('{"weight":0.090000000000000001}')['weight'], Decimal('0.090000000000000001'))

    def test_original_failure_exact_and_not_mutated(self):
        original = rows(); before = copy.deepcopy(original)
        result = arithmetic(original, CODES, TOLERANCE)
        self.assertEqual(result['sum'], Fraction(965, 1000))
        self.assertEqual(result['residual'], Fraction(-35, 1000))
        self.assertFalse(result['valid']); self.assertEqual(original, before)
        self.assertEqual(exact_text(result['sum']), '0.965')

    def test_valid_correction_is_not_an_engine_target(self):
        proposal = rows()
        # Deliberately synthetic fixture, never included in any model request.
        proposal[-1]['weight'] += Decimal('.035')
        result = arithmetic(proposal, CODES, TOLERANCE)
        self.assertTrue(result['valid']); self.assertEqual(result['sum'], 1)

    def test_zero_explicit_and_long_only_bounds(self):
        proposal = [{'sector_code': c, 'weight': Decimal(1 if i == 0 else 0)} for i, c in enumerate(CODES)]
        self.assertTrue(arithmetic(proposal, CODES, TOLERANCE)['valid'])
        proposal[0]['weight'] = Decimal('1.1'); proposal[1]['weight'] = Decimal('-.1')
        result = arithmetic(proposal, CODES, TOLERANCE)
        self.assertEqual(result['sum'], 1); self.assertFalse(result['valid'])

    def test_duplicate_missing_unknown_and_boolean_fail(self):
        for change in ('duplicate', 'unknown', 'boolean', 'missing'):
            proposal = rows()
            if change == 'duplicate': proposal[0]['sector_code'] = proposal[1]['sector_code']
            if change == 'unknown': proposal[0]['sector_code'] = '99'
            if change == 'boolean': proposal[0]['weight'] = True
            if change == 'missing': proposal.pop()
            self.assertFalse(arithmetic(proposal, CODES, TOLERANCE)['valid'])

    def test_existing_tolerance_boundary_exact(self):
        proposal = rows(); proposal[-1]['weight'] += Decimal('.035001')
        self.assertTrue(arithmetic(proposal, CODES, TOLERANCE)['valid'])
        proposal[-1]['weight'] += Decimal('.0000000000000000001')
        self.assertFalse(arithmetic(proposal, CODES, TOLERANCE)['valid'])

    def test_independent_shape_rejects_extra_keys_and_numeric_bool(self):
        schema = {'type': 'object', 'properties': {'weight': {'type': 'number'}},
                  'required': ['weight'], 'additionalProperties': False}
        self.assertFalse(structural_errors(strict_json('{"weight":-0.1}'), schema))
        self.assertTrue(structural_errors({'weight': True}, schema))
        self.assertTrue(structural_errors(strict_json('{"weight":0.1,"x":0}'), schema))

    def test_bound_violation_and_hidden_evidence_are_not_accepted(self):
        proposal = {'submitted_constraints': [{'constraint_id': 'a', 'sector_code': '10',
                    'kind': 'sector_max_weight', 'bound': Decimal('.1'), 'evidence_ids': ['public']}]}
        findings = constraint_checks(proposal, {'10': Fraction(2, 10)}, CODES, {'public'})
        self.assertFalse(findings[0]['valid']); self.assertEqual(findings[0]['exact_violation'], '0.1')
        proposal['submitted_constraints'][0]['evidence_ids'] = ['hidden']
        self.assertFalse(constraint_checks(proposal, {'10': Fraction(0)}, CODES, {'public'})[0]['valid'])


if __name__ == '__main__':
    unittest.main()
