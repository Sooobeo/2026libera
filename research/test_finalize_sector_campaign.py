"""Synthetic campaign artifacts only; no actual experiment responses or model calls."""
import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import finalize_sector_campaign as campaign
import test_finalize_sector_allocation_artifacts as artifacts

write_json = artifacts.write_json
read_json = artifacts.read_json
ref = artifacts.artifact_ref


class SyntheticRun:
    stage_dir = artifacts.FinalizeArtifactTests.stage_dir
    refresh_review = artifacts.FinalizeArtifactTests.refresh_review
    make_stage = artifacts.FinalizeArtifactTests.make_stage
    make_summary = artifacts.FinalizeArtifactTests.make_summary

    def __init__(self, run):
        self.run = run
        run.mkdir(parents=True)


def digest_tree(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob("*") if p.is_file()}


class Fixture:
    def __init__(self, base, purpose="pilot_continuation"):
        self.base, self.purpose = base, purpose
        self.run = base / "raw"
        self.reports = base / "reports"
        self.inputs = base / "inputs"
        self.raw = SyntheticRun(self.run)
        self.cases = campaign.PILOT[1:] if purpose == "pilot_continuation" else campaign.MAIN
        self.common = {"purpose": purpose, "case_order": list(self.cases),
                       "max_generation_requests": len(self.cases) * 2,
                       "automatic_retries": 0, "main_allowed": purpose == "main"}
        self.extra = {}
        if purpose == "pilot_continuation":
            self.common.update(historical_generation_requests=3, campaign_max_generation_requests=11,
                               old_outputs_observed=True,
                               explicit_retry_slots=[campaign.PILOT[1] + "__D0"])
            self.historical = SyntheticRun(base / "historical_raw")
            old_records = {
                campaign.PILOT[0]: [self.historical.make_stage(campaign.PILOT[0], "D0"),
                                   self.historical.make_stage(campaign.PILOT[0], "F0", first="0.6", second="0.4")],
                campaign.PILOT[1]: [self.historical.make_stage(campaign.PILOT[1], "D0",
                                                              status="hard_deadline", attempts=1)],
            }
            self.historical.make_summary(old_records, status="stopped")
            self.extra["historical_summary_ref"] = ref(self.historical.run / "pilot_summary.json")
            for name in ("historical_gate_ref", "historical_terminal_ref", "prepared_manifest_ref",
                         "finalizer_acceptance_ref"):
                self.extra[name] = write_json(self.inputs / (name + ".json"), {"synthetic": name})
        self.runtime = {"model": artifacts.MODEL, "synthetic_only": True, "num_ctx": 16384}
        self.protocol = copy.deepcopy(self.common)
        self.protocol.pop("old_outputs_observed", None)
        self.freeze = {**copy.deepcopy(self.common), **self.extra,
                       "status": "frozen_for_pilot_continuation_only" if purpose == "pilot_continuation" else "frozen_for_main_only",
                       "recorded_at_utc": "2026-10-26T00:00:00+00:00",
                       "run_directory": str(self.run), "output_root": str(self.reports),
                       "code_refs": [ref(Path(campaign.__file__)), ref(Path(campaign.math.__file__))]}
        self.gate = {**copy.deepcopy(self.common), **self.extra,
                     "status": "approved_for_continuation_before_generation" if purpose == "pilot_continuation" else "approved_for_main_before_generation",
                     "recorded_at_utc": "2026-10-26T00:00:01+00:00",
                     "run_directory": str(self.run), "output_root": str(self.reports)}
        self.declaration = {**copy.deepcopy(self.common), **self.extra,
                            "created_at_utc": "2026-10-26T00:00:02+00:00",
                            "run_directory": str(self.run), "output_root": str(self.reports),
                            "runtime": self.runtime}
        self.sync()
        write_json(self.run / "execution_started.json", {"at_utc": "2026-10-26T00:00:03+00:00"})
        self.summary({})

    def sync(self):
        runtime_ref = write_json(self.inputs / "runtime.json", self.runtime)
        protocol_ref = write_json(self.inputs / "protocol.json", self.protocol)
        self.freeze.update(runtime_ref=runtime_ref, protocol_ref=protocol_ref)
        freeze_ref = write_json(self.inputs / "freeze.json", self.freeze)
        self.gate.update(runtime_ref=runtime_ref, protocol_ref=protocol_ref, freeze_ref=freeze_ref)
        gate_ref = write_json(self.inputs / "gate.json", self.gate)
        self.declaration.update(runtime_ref=runtime_ref, protocol_ref=protocol_ref,
                                freeze_ref=freeze_ref, review_gate=gate_ref)
        write_json(self.run / "campaign_declaration.json", self.declaration)

    def stage(self, case, stage, *, status="completed", attempts=1, first="0.5", second="0.5"):
        record = self.raw.make_stage(case, stage, status=status, attempts=attempts, first=first, second=second)
        directory = self.raw.stage_dir(case, stage)
        spec = read_json(directory / "worker_spec.json")
        spec.update(runtime=copy.deepcopy(self.runtime), review_gate=self.declaration["review_gate"], raw_draft=None)
        messages = [{"role": "system", "content": "Synthetic input; never generated."},
                    {"role": "user", "content": "Synthetic own D0 for " + case}]
        if stage == "F0":
            draft_dir = self.raw.stage_dir(case, "D0")
            draft = read_json(draft_dir / "http_0001_generation/response.json")["message"]["content"]
            messages = read_json(draft_dir / "worker_spec.json")["body"]["messages"] + [
                {"role": "assistant", "content": draft}, {"role": "user", "content": "Synthetic F0 feedback"}]
            spec.update(raw_draft=draft, draft_artifacts={role: ref(draft_dir / name) for role, name in (
                ("response", "http_0001_generation/response.json"), ("worker_spec", "worker_spec.json"),
                ("worker_summary", "worker_summary.json"), ("supervisor_result", "supervisor_result.json"),
                ("transport_result", "transport_result.json"))})
        spec["body"]["messages"] = messages
        write_json(directory / "worker_spec.json", spec)
        for name in ("worker_summary.json", "supervisor_result.json"):
            write_json(directory / name, {"case_id": case, "stage": stage, "status": status, "synthetic": True})
        if status == "completed":
            self.raw.refresh_review(directory)
        return record

    def summary(self, records, status="stopped"):
        attempts = sum(s["generation_requests_attempted"] for rows in records.values() for s in rows)
        value = {"status": status, "case_order": list(self.cases),
                 "cases": [{"case_id": c, "stages": records.get(c, [])} for c in self.cases],
                 "generation_requests_attempted": attempts, "automatic_retries": 0, "post_final_calls": 0,
                 "main_model_calls": attempts if self.purpose == "main" else 0}
        if self.purpose == "pilot_continuation":
            value.update(max_generation_requests=8, historical_generation_requests=3,
                         campaign_generation_requests_attempted=3 + attempts, campaign_max_generation_requests=11,
                         original_planned_final_cells=5, segment_planned_final_cells=4)
        write_json(self.run / "campaign_summary.json", value)
        return value

    def full(self):
        records = {}
        weights = [("0.6", "0.4"), ("0.5", "0.5"), ("0.2", "0.8"), ("0.3", "0.7"), ("0.4", "0.6")]
        for case, (first, second) in zip(self.cases, weights):
            records[case] = [self.stage(case, "D0"), self.stage(case, "F0", first=first, second=second)]
        self.summary(records, status="attempt_sequence_finished")
        return records


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="campaign-finalizer-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()

    def test_continuation_complete_keeps_four_finals_eight_slots_and_raw_bytes(self):
        f = Fixture(self.base)
        f.full()
        before = digest_tree(self.base)
        result = campaign.finalize_campaign(f.run)
        self.assertEqual((result["planned_final_allocations"], result["planned_stage_slots"],
                          result["generation_requests_attempted"], result["finalized_finals"]), (4, 8, 8, 4))
        self.assertEqual(len(result["stage_records"]), 8)
        self.assertEqual(result["generation_calls"], 0)
        self.assertNotIn("derived_comparisons", result)
        self.assertTrue(all(s["final_total_units"] == 10000 for s in result["stage_records"]))
        self.assertEqual(before, digest_tree(self.base))
        self.assertIn("semantic errors remain", result["interpretation"])
        json.dumps(result, allow_nan=False)

    def test_main_five_ten_exact_comparisons_and_orientation(self):
        f = Fixture(self.base, "main")
        f.full()
        result = campaign.finalize_campaign(f.run)
        self.assertEqual((result["planned_final_allocations"], result["planned_stage_slots"],
                          result["generation_requests_attempted"], result["finalized_finals"]), (5, 10, 10, 5))
        pair = result["derived_comparisons"]["between_source"][0]
        self.assertEqual((pair["left"], pair["right"]), (campaign.MAIN[0] + ":F0", campaign.MAIN[2] + ":F0"))
        self.assertEqual(pair["total_variation_exact"], {"numerator": "2", "denominator": "5"})
        self.assertEqual(pair["final_unit_differences"]["10"], 4000)
        self.assertEqual(pair["final_unit_differences"]["15"], -4000)
        self.assertEqual({k: len(v) for k, v in result["derived_comparisons"].items()},
                         {"within_source": 2, "between_source": 2, "shared_control": 4, "own_D0_F0": 5})

    def test_combined_completion_retains_original_one_of_five_and_eleven_attempts(self):
        f = Fixture(self.base)
        f.full()
        before = digest_tree(self.base)
        result = campaign.complete_pilot_dataset(f.run, f.historical.run)
        self.assertEqual(result["finalized_finals"], 5)
        self.assertEqual(result["original_first_attempt_derived_report"]["finalized_finals"], 1)
        self.assertEqual(result["original_first_attempt_derived_report"]["planned_final_allocations"], 5)
        self.assertEqual(result["all_generation_requests_including_interrupted_attempt"], 11)
        self.assertEqual(result["continuation_generation_requests"], 8)
        self.assertTrue(result["not_the_original_first_attempt_pilot"])
        self.assertFalse(result["historical_failed_attempt_erased"])
        self.assertEqual(result["explicit_infrastructure_retry_slot"], campaign.PILOT[1] + "__D0")
        self.assertEqual(len(result["stage_records"]), 10)
        self.assertEqual(sum(r["selection_role"] == "prospectively_retained_completed_case" for r in result["stage_records"]), 2)
        old_failed = result["original_first_attempt_derived_report"]["stage_records"][2]
        self.assertEqual(old_failed["observed_transport_status"], "hard_deadline")
        self.assertEqual(before, digest_tree(self.base))

    def test_structure_failure_preflight_and_missing_keep_full_denominators(self):
        f = Fixture(self.base)
        records = {f.cases[0]: [f.stage(f.cases[0], "D0", status="model_structure_failure")],
                   f.cases[1]: [f.stage(f.cases[1], "D0", status="preflight_failed", attempts=0)]}
        f.summary(records)
        result = campaign.complete_pilot_dataset(f.run, f.historical.run)
        self.assertEqual((result["finalized_finals"], result["all_generation_requests_including_interrupted_attempt"]), (1, 4))
        segment = result["continuation_derived_report"]
        self.assertEqual((segment["planned_final_allocations"], segment["planned_stage_slots"]), (4, 8))
        self.assertEqual(sum(r.get("reasons") == ["not_attempted"] for r in segment["stage_records"]), 6)
        self.assertTrue(all(p["status"] == "unavailable" and p["total_variation_exact"] is None
                            for p in result["derived_comparisons"]["shared_control"]))

    def test_main_missing_finals_do_not_become_zero_distance(self):
        f = Fixture(self.base, "main")
        result = campaign.finalize_campaign(f.run)
        self.assertEqual(len(result["stage_records"]), 10)
        self.assertEqual(result["finalized_finals"], 0)
        self.assertTrue(all(p["status"] == "unavailable" and p["final_unit_differences"] is None
                            for group in result["derived_comparisons"].values() for p in group))

    def test_ordinary_negative_D0_retained_without_blocking_bound_F0(self):
        f = Fixture(self.base)
        c = f.cases[0]
        records = {c: [f.stage(c, "D0", first="-0.1", second="1.1"), f.stage(c, "F0")]}
        f.summary(records)
        result = campaign.finalize_campaign(f.run)
        self.assertEqual(result["stage_records"][0]["status"], "unavailable")
        self.assertEqual(result["stage_records"][1]["status"], "finalized")
        self.assertEqual(result["finalized_finals"], 1)

    def test_gate_protocol_freeze_scope_and_prospective_times_are_not_hash_only(self):
        f = Fixture(self.base)
        originals = {name: copy.deepcopy(getattr(f, name)) for name in ("gate", "protocol", "freeze")}
        mutations = [("gate", "status", "draft"), ("gate", "purpose", "main"),
                     ("protocol", "case_order", list(reversed(f.cases))),
                     ("protocol", "max_generation_requests", 10),
                     ("protocol", "old_outputs_observed", False),
                     ("freeze", "status", "frozen_for_main_only"),
                     ("freeze", "historical_generation_requests", True),
                     ("gate", "explicit_retry_slots", []),
                     ("gate", "old_outputs_observed", False),
                     ("gate", "recorded_at_utc", "2026-10-26T00:00:04+00:00"),
                     ("freeze", "recorded_at_utc", "2026-10-26T00:00:00"),
                     ("gate", "run_directory", str(self.base / "elsewhere"))]
        for owner, key, value in mutations:
            with self.subTest(owner=owner, key=key):
                for name, original in originals.items():
                    setattr(f, name, copy.deepcopy(original))
                getattr(f, owner)[key] = value
                f.sync()
                with self.assertRaises(ValueError):
                    campaign.finalize_campaign(f.run)

    def test_both_implementations_and_unique_code_refs_must_be_frozen(self):
        f = Fixture(self.base)
        original = copy.deepcopy(f.freeze["code_refs"])
        for refs in ([original[0]], [original[1]], original + [original[0]],
                     [original[0], {**original[1], "sha256": "0" * 64}]):
            with self.subTest(refs=refs):
                f.freeze["code_refs"] = refs
                f.sync()
                with self.assertRaises(ValueError):
                    campaign.finalize_campaign(f.run)

    def test_reference_hash_and_historical_binding_corruption_rejected(self):
        f = Fixture(self.base)
        path = f.inputs / "protocol.json"
        baseline = path.read_bytes()
        path.write_bytes(baseline + b" ")
        with self.assertRaisesRegex(ValueError, "artifact_hash_mismatch"):
            campaign.finalize_campaign(f.run)
        path.write_bytes(baseline)
        f.gate["historical_summary_ref"] = f.extra["historical_terminal_ref"]
        f.sync()
        with self.assertRaisesRegex(ValueError, "historical_reference_binding_mismatch"):
            campaign.finalize_campaign(f.run)

    def test_declaration_runtime_and_run_path_cannot_be_substituted(self):
        f = Fixture(self.base)
        original = copy.deepcopy(f.declaration)
        for key, value in (("runtime", {"synthetic_only": False}), ("run_directory", str(self.base)),
                           ("max_generation_requests", True), ("purpose", "main"),
                           ("main_allowed", True)):
            with self.subTest(key=key):
                declaration = copy.deepcopy(original)
                declaration[key] = value
                write_json(f.run / "campaign_declaration.json", declaration)
                with self.assertRaises(ValueError):
                    campaign.finalize_campaign(f.run)

    def test_summary_denominator_counts_and_retry_metadata_fail_closed(self):
        f = Fixture(self.base)
        baseline = read_json(f.run / "campaign_summary.json")
        mutations = [lambda s: s.update(status="running"), lambda s: s["cases"].pop(),
                     lambda s: s["cases"].reverse(), lambda s: s.update(generation_requests_attempted=True),
                     lambda s: s.update(automatic_retries=1), lambda s: s.update(post_final_calls=1),
                     lambda s: s.update(main_model_calls=1), lambda s: s.update(campaign_generation_requests_attempted=0),
                     lambda s: s.update(original_planned_final_cells=4), lambda s: s.update(segment_planned_final_cells=5)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                value = copy.deepcopy(baseline)
                mutate(value)
                write_json(f.run / "campaign_summary.json", value)
                with self.assertRaises(ValueError):
                    campaign.finalize_campaign(f.run)

    def test_unaccounted_stage_or_extra_generation_folder_rejected(self):
        f = Fixture(self.base)
        record = f.stage(f.cases[0], "D0")
        f.summary({f.cases[0]: [record]})
        for extra in (f.run / (f.cases[0] + "__F1"),
                      f.raw.stage_dir(f.cases[0], "D0") / "http_0002_generation"):
            with self.subTest(path=extra.name):
                extra.mkdir()
                with self.assertRaises(ValueError):
                    campaign.finalize_campaign(f.run)
                extra.rmdir()

    def test_declared_missing_artifacts_and_status_mismatch_rejected(self):
        f = Fixture(self.base)
        c = f.cases[0]
        record = f.stage(c, "D0")
        summary = f.summary({c: [record]})
        summary["cases"][0]["stages"][0]["status"] = "hard_deadline"
        write_json(f.run / "campaign_summary.json", summary)
        with self.assertRaisesRegex(ValueError, "summary_transport_accounting_mismatch"):
            campaign.finalize_campaign(f.run)
        f.summary({c: [record]})
        (f.raw.stage_dir(c, "D0") / "transport_result.json").unlink()
        with self.assertRaises(FileNotFoundError):
            campaign.finalize_campaign(f.run)

    def test_stage_runtime_and_response_binding_corruption_rejected(self):
        f = Fixture(self.base)
        c = f.cases[0]
        record = f.stage(c, "D0")
        f.summary({c: [record]})
        directory = f.raw.stage_dir(c, "D0")
        path = directory / "worker_spec.json"
        original = read_json(path)
        spec = copy.deepcopy(original)
        spec["runtime"]["num_ctx"] = 1
        write_json(path, spec)
        f.raw.refresh_review(directory)
        with self.assertRaisesRegex(ValueError, "stage_runtime_differs"):
            campaign.finalize_campaign(f.run)
        write_json(path, original)
        f.raw.refresh_review(directory)
        response_path = directory / "http_0001_generation/response.json"
        response = read_json(response_path)
        response["message"]["content"] += " "
        write_json(response_path, response)
        with self.assertRaisesRegex(ValueError, "completed_response_binding"):
            campaign.finalize_campaign(f.run)

    def test_completed_but_ineligible_is_binding_failure_not_ordinary_model_failure(self):
        f = Fixture(self.base)
        c = f.cases[0]
        record = f.stage(c, "D0")
        f.summary({c: [record]})
        directory = f.raw.stage_dir(c, "D0")
        transport = read_json(directory / "transport_result.json")
        transport["continuation_eligible"] = False
        write_json(directory / "transport_result.json", transport)
        f.raw.refresh_review(directory)
        with self.assertRaisesRegex(ValueError, "completed_response_binding"):
            campaign.finalize_campaign(f.run)

    def test_F0_requires_actual_new_D0_history_and_exact_five_references(self):
        f = Fixture(self.base)
        c = f.cases[0]
        records = {c: [f.stage(c, "D0"), f.stage(c, "F0")]}
        f.summary(records)
        directory = f.raw.stage_dir(c, "F0")
        path = directory / "worker_spec.json"
        original = read_json(path)
        mutations = [lambda s: s.update(raw_draft="historical or invented draft"),
                     lambda s: s["draft_artifacts"].pop("worker_summary"),
                     lambda s: s["draft_artifacts"].update(response=f.extra["historical_summary_ref"]),
                     lambda s: s["body"]["messages"][0].update(content="changed system history"),
                     lambda s: s["body"]["messages"][2].update(content="different assistant history")]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                spec = copy.deepcopy(original)
                mutate(spec)
                write_json(path, spec)
                f.raw.refresh_review(directory)
                with self.assertRaisesRegex(ValueError, "F0_new_D0_history_binding"):
                    campaign.finalize_campaign(f.run)

    def test_F0_after_failed_D0_is_rejected_even_with_summary_sequence(self):
        f = Fixture(self.base)
        c = f.cases[0]
        records = {c: [f.stage(c, "D0"), f.stage(c, "F0")]}
        records[c][0]["status"] = "model_structure_failure"
        transport_path = f.raw.stage_dir(c, "D0") / "transport_result.json"
        transport = read_json(transport_path)
        transport["status"] = "model_structure_failure"
        write_json(transport_path, transport)
        f.summary(records)
        with self.assertRaisesRegex(ValueError, "F0_requires_completed_own_new_D0"):
            campaign.finalize_campaign(f.run)

    def test_historical_wrong_run_or_interruption_pattern_rejected(self):
        f = Fixture(self.base)
        other = self.base / "other_historical"
        other.mkdir()
        write_json(other / "pilot_summary.json", read_json(f.historical.run / "pilot_summary.json"))
        with self.assertRaisesRegex(ValueError, "historical_run_binding"):
            campaign.complete_pilot_dataset(f.run, other)
        summary_path = f.historical.run / "pilot_summary.json"
        summary = read_json(summary_path)
        summary["cases"][1]["stages"][0]["status"] = "model_structure_failure"
        write_json(summary_path, summary)
        transport_path = f.historical.stage_dir(campaign.PILOT[1], "D0") / "transport_result.json"
        transport = read_json(transport_path)
        transport["status"] = "model_structure_failure"
        write_json(transport_path, transport)
        for obj in (f.declaration, f.freeze, f.gate):
            obj["historical_summary_ref"] = ref(summary_path)
        f.sync()
        with self.assertRaisesRegex(ValueError, "fixed_interruption_pattern"):
            campaign.complete_pilot_dataset(f.run, f.historical.run)

    def test_historical_stage_changed_after_read_is_detected(self):
        f = Fixture(self.base)
        original = campaign.math.finalize_run
        def mutate_after_read(run):
            value = original(run)
            path = f.historical.stage_dir(campaign.PILOT[0], "D0") / "worker_spec.json"
            path.write_bytes(path.read_bytes() + b" ")
            return value
        with patch.object(campaign.math, "finalize_run", side_effect=mutate_after_read):
            with self.assertRaisesRegex(ValueError, "artifact_changed_during_finalization"):
                campaign.complete_pilot_dataset(f.run, f.historical.run)

    def test_main_cannot_select_historical_pilot_rows(self):
        f = Fixture(self.base, "main")
        with self.assertRaisesRegex(ValueError, "only_explicit_pilot_continuation"):
            campaign.complete_pilot_dataset(f.run, self.base / "unused")

    def test_CLI_external_output_is_exclusive_and_never_writes_raw(self):
        f = Fixture(self.base)
        output = f.reports / "math.json"
        before = digest_tree(f.run)
        argv = ["finalize_sector_campaign.py", "--run-dir", str(f.run), "--output", str(output)]
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            campaign.main()
        original_output = output.read_bytes()
        self.assertEqual(read_json(output)["generation_calls"], 0)
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            with self.assertRaises(FileExistsError):
                campaign.main()
        self.assertEqual(output.read_bytes(), original_output)
        for raw in (f.run, f.historical.run):
            args = ["finalize_sector_campaign.py", "--run-dir", str(f.run),
                    "--historical-run", str(f.historical.run), "--output", str(raw / "forbidden.json")]
            with patch.object(sys, "argv", args), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    campaign.main()
            self.assertFalse((raw / "forbidden.json").exists())
        self.assertEqual(before, digest_tree(f.run))


if __name__ == "__main__":
    unittest.main(verbosity=2)
