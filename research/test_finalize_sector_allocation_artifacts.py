"""Synthetic artifact-binding tests; no real experiment outputs are read."""

import hashlib
import json
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import finalize_sector_allocation as finalizer


CASES = (
    "fidelity_q2_2026__E", "fidelity_q2_2026__L", "ubs_june_2026__E",
    "ubs_june_2026__L", "common_market_only__C",
)
CODES = ("10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60")
MODEL = "synthetic-model-no-generation"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return artifact_ref(path)


def artifact_ref(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def content(first="0.5", second="0.5"):
    tokens = [first, second] + ["0"] * 9
    return '{"sectors":[' + ",".join(
        '{"sector_code":' + json.dumps(code) + ',"weight":' + token + "}"
        for code, token in zip(CODES, tokens)
    ) + "]}"


class FinalizeArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="allocation-artifact-test-")
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name).resolve() / "synthetic_run"
        self.run.mkdir()

    def stage_dir(self, case=CASES[0], stage="D0"):
        return self.run / (case + "__" + stage)

    def refresh_review(self, directory):
        spec_path = directory / "worker_spec.json"
        spec = read_json(spec_path)
        return write_json(directory / "stage_review.json", {
            "case_id": spec["case_id"], "stage": spec["stage"],
            "instrument_integrity_pass": True,
            "input_refs": [artifact_ref(spec_path), artifact_ref(directory / "transport_result.json"),
                           artifact_ref(directory / "http_0001_generation" / "response.json")],
        })

    def make_stage(self, case=CASES[0], stage="D0", *, status="completed", attempts=1,
                   first="0.5", second="0.5"):
        directory = self.stage_dir(case, stage)
        write_json(directory / "worker_spec.json", {
            "case_id": case, "stage": stage, "run_directory": str(self.run),
            "body": {"model": MODEL},
        })
        transport = {"status": status, "generation_requests_attempted": attempts}
        if attempts == 1:
            (directory / "http_0001_generation").mkdir(exist_ok=True)
        if status == "completed":
            response = {"model": MODEL, "message": {"role": "assistant", "content": content(first, second)},
                        "done": True, "done_reason": "stop"}
            response_ref = write_json(directory / "http_0001_generation" / "response.json", response)
            transport.update(response=response, response_artifact=response_ref,
                             system_integrity_incident=False, continuation_eligible=True,
                             artifact_preservation_error=None, accounting_artifact_errors={},
                             unexpected_generation_evidence_in_render=False)
        write_json(directory / "transport_result.json", transport)
        if status == "completed":
            self.refresh_review(directory)
        return {"stage": stage, "status": status, "generation_requests_attempted": attempts}

    def make_summary(self, records, *, status="pilot_attempt_sequence_finished"):
        summary = {
            "status": status,
            "cases": [{"case_id": case, "stages": records.get(case, [])} for case in CASES],
            "generation_requests_attempted": sum(r["generation_requests_attempted"] for rs in records.values() for r in rs),
            "main_model_calls": 0, "automatic_retries": 0, "post_final_calls": 0,
        }
        write_json(self.run / "pilot_summary.json", summary)
        return summary

    def make_complete_run(self):
        finals = [("0.6", "0.4"), ("0.5", "0.5"), ("0.2", "0.8"), ("0.3", "0.7"), ("0.4", "0.6")]
        records = {}
        for case, (first, second) in zip(CASES, finals):
            records[case] = [self.make_stage(case, "D0"), self.make_stage(case, "F0", first=first, second=second)]
        return self.make_summary(records)

    def assert_bound_refs(self, refs):
        for ref in refs:
            path = Path(ref["path"])
            self.assertTrue(path.is_relative_to(self.run))
            self.assertEqual(ref, artifact_ref(path))

    def test_complete_run_has_five_finals_ten_slots_and_no_input_mutation(self):
        self.make_complete_run()
        before = {str(p.relative_to(self.run)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in self.run.rglob("*") if p.is_file()}
        result = finalizer.finalize_run(self.run)
        self.assertEqual(result["planned_final_allocations"], 5)
        self.assertEqual(result["planned_stage_slots"], 10)
        self.assertEqual(result["first_attempt_requests"], 10)
        self.assertEqual(result["finalized_finals"], 5)
        self.assertEqual(result["generation_calls"], 0)
        self.assertFalse(result["missing_finals_replaced"])
        self.assertEqual([(r["case_id"], r["stage"]) for r in result["stage_records"]],
                         [(case, stage) for case in CASES for stage in ("D0", "F0")])
        self.assert_bound_refs([result["run_summary_ref"]])
        for row in result["stage_records"]:
            self.assertEqual(row["status"], "finalized")
            self.assertEqual(row["final_total_units"], 10000)
            self.assertEqual(row["stage_role"], "derived_final_allocation" if row["stage"] == "F0"
                             else "draft_diagnostic_not_a_final_submission")
            self.assert_bound_refs(row["input_refs"])
        after = {str(p.relative_to(self.run)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.run.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        json.dumps(result, allow_nan=False)

    def test_failed_preflight_and_nonattempted_slots_keep_full_denominator(self):
        records = {
            CASES[0]: [self.make_stage(CASES[0], "D0"), self.make_stage(CASES[0], "F0")],
            CASES[1]: [self.make_stage(CASES[1], "D0", status="generation_timeout", attempts=1)],
            CASES[2]: [self.make_stage(CASES[2], "D0", status="preflight_failed", attempts=0)],
        }
        self.make_summary(records, status="stopped")
        result = finalizer.finalize_run(self.run)
        self.assertEqual(result["planned_final_allocations"], 5)
        self.assertEqual(len(result["stage_records"]), 10)
        self.assertEqual(result["first_attempt_requests"], 3)
        self.assertEqual(result["finalized_finals"], 1)
        self.assertEqual(sum(r.get("reasons") == ["not_attempted"] for r in result["stage_records"]), 6)
        self.assertTrue(all(p["status"] == "unavailable" for p in result["derived_comparisons"]["shared_control"]))
        for pair in result["derived_comparisons"]["shared_control"]:
            self.assertIsNone(pair["total_variation_exact"])
            self.assertIsNone(pair["final_unit_differences"])
        self.assertEqual(result["derived_comparisons"]["own_D0_F0"][0]["status"], "computed")

    def test_exact_distances_and_difference_orientation_match_declared_pairs(self):
        self.make_complete_run()
        result = finalizer.finalize_run(self.run)
        pair = result["derived_comparisons"]["between_source"][0]
        self.assertEqual(pair["left"], CASES[0] + ":F0")
        self.assertEqual(pair["right"], CASES[2] + ":F0")
        self.assertEqual(Fraction(int(pair["total_variation_exact"]["numerator"]),
                                  int(pair["total_variation_exact"]["denominator"])), Fraction(2, 5))
        self.assertEqual(pair["total_variation_exact_decimal"], "0.4")
        self.assertEqual(pair["final_unit_differences"]["10"], 4000)
        self.assertEqual(pair["final_unit_differences"]["15"], -4000)
        own = result["derived_comparisons"]["own_D0_F0"][0]
        self.assertEqual(own["left"], CASES[0] + ":F0")
        self.assertEqual(own["right"], CASES[0] + ":D0")
        self.assertEqual(own["final_unit_differences"]["10"], 1000)
        lookup = {(row["case_id"], row["stage"]): row for row in result["stage_records"]}
        reverse = finalizer.compare_finalized(lookup[(CASES[2], "F0")], lookup[(CASES[0], "F0")])
        self.assertEqual(reverse["total_variation_exact"], pair["total_variation_exact"])
        self.assertEqual(reverse["final_unit_differences"], {c: -v for c, v in pair["final_unit_differences"].items()})
        self.assertEqual({k: len(v) for k, v in result["derived_comparisons"].items()},
                         {"within_source": 2, "between_source": 2, "shared_control": 4, "own_D0_F0": 5})

    def test_nonterminal_incomplete_or_reordered_summary_is_rejected(self):
        baseline = self.make_summary({}, status="stopped")
        mutations = [lambda s: s.update(status="running"), lambda s: s["cases"].pop(),
                     lambda s: s["cases"].reverse()]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                summary = json.loads(json.dumps(baseline))
                mutate(summary)
                write_json(self.run / "pilot_summary.json", summary)
                with self.assertRaises(ValueError):
                    finalizer.finalize_run(self.run)

    def test_summary_transport_status_and_attempt_count_mismatches_fail_closed(self):
        record = self.make_stage()
        baseline = self.make_summary({CASES[0]: [record]}, status="stopped")
        mutations = [
            lambda s: s["cases"][0]["stages"][0].update(status="generation_timeout"),
            lambda s: s["cases"][0]["stages"][0].update(generation_requests_attempted=0),
            lambda s: s["cases"][0]["stages"][0].update(generation_requests_attempted=True),
            lambda s: s.update(generation_requests_attempted=0),
            lambda s: s.update(generation_requests_attempted=True),
            lambda s: s.update(automatic_retries=1),
            lambda s: s.update(main_model_calls=False),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                summary = json.loads(json.dumps(baseline))
                mutate(summary)
                write_json(self.run / "pilot_summary.json", summary)
                with self.assertRaises(ValueError):
                    finalizer.finalize_run(self.run)

    def test_response_hash_or_envelope_binding_corruption_is_rejected(self):
        for kind in ("response_bytes", "declared_hash", "embedded_response"):
            with self.subTest(kind=kind):
                self.make_stage()
                directory = self.stage_dir()
                response_path = directory / "http_0001_generation" / "response.json"
                transport_path = directory / "transport_result.json"
                if kind == "response_bytes":
                    response = read_json(response_path)
                    response["message"]["content"] = content("0.9", "0.1")
                    write_json(response_path, response)
                else:
                    transport = read_json(transport_path)
                    if kind == "declared_hash":
                        transport["response_artifact"]["sha256"] = "0" * 64
                    else:
                        transport["response"]["message"]["content"] = content("0.9", "0.1")
                    write_json(transport_path, transport)
                with self.assertRaisesRegex(ValueError, "completed_response_binding_or_status_mismatch"):
                    finalizer.finalize_stage(directory)

    def test_review_binding_or_integrity_flag_corruption_is_rejected(self):
        for kind in ("reference", "integrity", "stage"):
            with self.subTest(kind=kind):
                self.make_stage()
                path = self.stage_dir() / "stage_review.json"
                review = read_json(path)
                if kind == "reference":
                    review["input_refs"][0]["sha256"] = "0" * 64
                elif kind == "integrity":
                    review["instrument_integrity_pass"] = False
                else:
                    review["stage"] = "F0"
                write_json(path, review)
                with self.assertRaisesRegex(ValueError, "completed_stage_integrity_review_binding_mismatch"):
                    finalizer.finalize_stage(self.stage_dir())

    def test_wrong_stage_or_run_path_identity_is_rejected(self):
        for mutation in ({"stage": "F0"}, {"run_directory": str(self.run.parent / "different_run")}):
            with self.subTest(mutation=mutation):
                self.make_stage()
                path = self.stage_dir() / "worker_spec.json"
                spec = read_json(path)
                spec.update(mutation)
                write_json(path, spec)
                with self.assertRaisesRegex(ValueError, "stage_directory_identity_mismatch"):
                    finalizer.finalize_stage(self.stage_dir())

    def test_consistently_bound_unsupported_stage_is_rejected(self):
        self.make_stage(stage="F1")
        with self.assertRaises(ValueError):
            finalizer.finalize_stage(self.stage_dir(stage="F1"))

    def test_transport_request_boolean_is_not_an_integer_attempt(self):
        self.make_stage()
        path = self.stage_dir() / "transport_result.json"
        transport = read_json(path)
        transport["generation_requests_attempted"] = True
        write_json(path, transport)
        with self.assertRaisesRegex(ValueError, "first_attempt_only_accounting_required"):
            finalizer.finalize_stage(self.stage_dir())

    def test_declared_missing_stage_or_completed_response_fails_closed(self):
        record = {"stage": "D0", "status": "completed", "generation_requests_attempted": 1}
        self.make_summary({CASES[0]: [record]}, status="stopped")
        with self.assertRaises(FileNotFoundError):
            finalizer.finalize_run(self.run)
        self.make_stage()
        (self.stage_dir() / "http_0001_generation" / "response.json").unlink()
        with self.assertRaises(FileNotFoundError):
            finalizer.finalize_run(self.run)

    def test_unexpected_declared_stage_sequence_is_rejected(self):
        record = {"stage": "F0", "status": "completed", "generation_requests_attempted": 1}
        self.make_summary({CASES[0]: [record]}, status="stopped")
        with self.assertRaisesRegex(ValueError, "unexpected_stage_sequence"):
            finalizer.finalize_run(self.run)

    def test_unexpected_known_stage_directory_is_not_ignored(self):
        self.make_summary({}, status="stopped")
        self.make_stage()
        with self.assertRaisesRegex(ValueError, "summary_stage_directory_accounting_mismatch"):
            finalizer.finalize_run(self.run)

    def test_unexpected_populated_unknown_stage_directory_is_not_ignored(self):
        self.make_summary({}, status="stopped")
        self.make_stage(stage="F1")
        with self.assertRaisesRegex(ValueError, "summary_stage_directory_accounting_mismatch"):
            finalizer.finalize_run(self.run)

    def test_unreported_second_generation_directory_is_rejected(self):
        self.make_stage()
        (self.stage_dir() / "http_0002_generation").mkdir()
        with self.assertRaisesRegex(ValueError, "generation_directory_attempt_accounting_mismatch"):
            finalizer.finalize_stage(self.stage_dir())


if __name__ == "__main__":
    unittest.main()
