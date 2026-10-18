"""Pure checks that planning is not confused with a submitted allocation."""
import copy
from decimal import Decimal
import unittest

from build_v47_priority1_round2_audit import planning_contract


SCHEMA = {'type': 'object', 'properties': {
    'weights': {'type': 'array', 'items': {'type': 'number'}},
    'plan': {'type': 'string', 'minLength': 1}},
    'required': ['weights', 'plan'], 'additionalProperties': False}


class PlanningRoleAuditTests(unittest.TestCase):
    def test_empty_plan_is_not_a_numeric_portfolio(self):
        proposal = {'weights': [], 'plan': 'Future plan only.'}
        record = {'calculator_called': False, 'financial_acceptance': None,
                  'planner_contract_satisfied': True}
        before = copy.deepcopy(proposal)
        result = planning_contract(proposal, record, SCHEMA)
        self.assertTrue(result['valid']); self.assertEqual(proposal, before)
        self.assertNotIn('sum', result)

    def test_nonempty_planner_is_role_failure_without_repair(self):
        proposal = {'weights': [Decimal(1)], 'plan': 'Invalid planning role.'}
        record = {'calculator_called': False, 'financial_acceptance': None,
                  'planner_contract_satisfied': False}
        self.assertFalse(planning_contract(proposal, record, SCHEMA)['valid'])
        self.assertEqual(proposal['weights'], [Decimal(1)])

    def test_calculation_or_acceptance_cannot_be_assigned_to_plan(self):
        proposal = {'weights': [], 'plan': 'Future plan only.'}
        for record in ({'calculator_called': True, 'financial_acceptance': None, 'planner_contract_satisfied': True},
                       {'calculator_called': False, 'financial_acceptance': False, 'planner_contract_satisfied': True},
                       {'calculator_called': False, 'financial_acceptance': True, 'planner_contract_satisfied': True}):
            self.assertFalse(planning_contract(proposal, record, SCHEMA)['valid'])


if __name__ == '__main__':
    unittest.main()
