"""Exact-value round trips only: no model, network, gold, or runtime mutation."""
import copy
import json
import math
from pathlib import Path
import unittest

from compact_sector_prompt import compact_json, compact_stage_content, project_market, restore_market
import run_sector_workflow as workflow


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class CompactSectorPromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.market = workflow.read(workflow.MARKET)
        cls.packets = [packet for packet in workflow.packets() if packet['split'] == 'pilot']

    def test_actual_market_round_trip_and_no_mutation(self):
        before = canonical(self.market)
        projected = project_market(self.market)
        restored = restore_market(json.loads(compact_json(projected)))
        self.assertEqual(canonical(restored), before)
        self.assertEqual(canonical(self.market), before)
        projected['covariance'][0][0] = -77.0
        projected['baseline_weights'][self.market['sector_codes'][0]] = 99.0
        self.assertEqual(canonical(self.market), before)

    def test_all_four_actual_stage_one_branches_round_trip(self):
        cases = []
        for packet in self.packets:
            for arm in ('R1', 'R4'):
                message = workflow.stage_message(1, arm, packet, self.market)
                original = json.loads(message['content'])
                compacted = compact_stage_content(message['content'])
                restored = json.loads(compacted)
                restored['common_market'] = restore_market(restored['common_market'])
                self.assertEqual(canonical(restored), canonical(original))
                self.assertEqual('institution_document' in restored, arm == 'R1')
                self.assertLess(len(compacted.encode('utf-8')), len(message['content'].encode('utf-8')))
                cases.append((packet['source_id'], arm))
        self.assertEqual(len(cases), 4)

    def test_rejects_nonidentical_duplicates_including_numeric_forms(self):
        for kind in ('matrix', 'baseline', 'signed_zero', 'integer_float'):
            with self.subTest(kind=kind):
                value = copy.deepcopy(self.market)
                if kind == 'matrix':
                    value['sample_covariance_ddof_1'][0][0] += 0.001
                elif kind == 'baseline':
                    value['baseline_weights_array'].reverse()
                elif kind == 'signed_zero':
                    value['covariance'][0][0] = -0.0
                    value['sample_covariance_ddof_1'][0][0] = 0.0
                else:
                    value['covariance'][0][0] = 1
                    value['sample_covariance_ddof_1'][0][0] = 1.0
                with self.assertRaises(ValueError):
                    project_market(value)

    def test_rejects_metadata_collision_missing_fields_and_code_ambiguity(self):
        for key in ('collision', 'missing_alias', 'duplicate_code'):
            with self.subTest(key=key):
                value = copy.deepcopy(self.market)
                if key == 'collision':value['covariance_ddof'] = 1
                elif key == 'missing_alias':del value['sample_covariance_ddof_1']
                else:value['sector_codes'][1] = value['sector_codes'][0]
                with self.assertRaises(ValueError):project_market(value)

    def test_rejects_lossy_json_values(self):
        for extra in (math.nan, math.inf, (1, 2), {1: 'not a string key'}):
            value = copy.deepcopy(self.market)
            value['extra'] = extra
            with self.assertRaises(ValueError):project_market(value)

    def test_restorer_rejects_wrong_metadata_or_existing_alias(self):
        for key, extra in (('covariance_ddof', True), ('covariance_ddof', 1.0),
                           ('covariance_ddof', 2), ('baseline_weights_array', [])):
            value = project_market(self.market)
            value[key] = extra
            with self.assertRaises(ValueError):restore_market(value)

    def test_unique_fields_and_string_whitespace_are_preserved(self):
        value = copy.deepcopy(self.market)
        value['additional_unique_data'] = {'text': '  source  text\n\t\uac70\uc2dc  ',
                                           'number': 1.2345678901234567, 'zero': -0.0}
        content = json.dumps({'stage': 1, 'common_market': value,
                              'document': ' Original text\n  unchanged '})
        result = json.loads(compact_stage_content(content))
        self.assertEqual(result['document'], ' Original text\n  unchanged ')
        self.assertEqual(canonical(restore_market(result['common_market'])), canonical(value))

    def test_nonmarket_stage_compacts_without_rewriting_and_duplicate_keys_fail(self):
        original = {'stage': 4, 'institution_document': {'text': '  Preserve this.  '}}
        self.assertEqual(json.loads(compact_stage_content(json.dumps(original))), original)
        with self.assertRaises(ValueError):compact_stage_content('{"stage":1,"stage":4}')
        with self.assertRaises(ValueError):compact_stage_content('{"stage":true,"common_market":{}}')


if __name__ == '__main__':
    unittest.main()
