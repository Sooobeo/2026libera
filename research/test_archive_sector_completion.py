"""Tempfile-only archive guards; real services/processes and raw outputs untouched."""
import copy
from contextlib import ExitStack, redirect_stderr
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive_sector_completion as archive
import finalize_sector_campaign as campaign
from test_finalize_sector_campaign import Fixture, ref, read_json, write_json


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="completion-archive-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()

    def fixture(self, purpose="pilot_continuation"):
        f = Fixture(self.base / "data/local_sector_runtime", purpose)
        sources = self.base / "sources"
        sources.mkdir()
        copied = {}
        for module in (archive, archive.inherited, campaign, campaign.math):
            path = Path(module.__file__)
            copied[path.name] = sources / path.name
            copied[path.name].write_bytes(path.read_bytes())
        copied["restore_research_artifacts.py"] = sources / "restore_research_artifacts.py"
        copied["restore_research_artifacts.py"].write_bytes(archive.RESTORE_SOURCE.read_bytes())
        f.freeze["code_refs"] = [ref(copied["finalize_sector_campaign.py"]), ref(copied["finalize_sector_allocation.py"])]
        f.declaration["coordinator_pid"] = 501
        f.sync()
        write_json(f.run / "execution_started.json", {"at_utc": "2026-10-26T00:00:03+00:00", "coordinator_pid": 501})
        release = {"status": "released", "coordinator_pid": 501, "owner_thread_id": 601,
                   "clear_flags": 0x80000000, "permanent_power_settings_changed": False}
        write_json(f.reports / "coordinator_awake_release.json", release)
        write_json(f.reports / "events/acquired.json", {
            "event": "coordinator_awake_acquired", "at_utc": "2026-10-26T00:00:03+00:00",
            "coordinator_pid": 501, "owner_thread_id": 601, "flags": 0x80000003,
            "helper_process_created": False, "permanent_power_settings_changed": False})
        terminal = {"purpose": purpose, "status": "stopped_semantic_review_pending",
                    "run_directory": str(f.run), "output_root": str(f.reports),
                    "declaration_ref": ref(f.run / "campaign_declaration.json"),
                    "summary_ref": ref(f.run / "campaign_summary.json"), "generation_requests_attempted": 0,
                    "awake_release": release}
        write_json(f.reports / "terminal_receipt.json", terminal)
        service = {"status": "ready", "pid": 502, "origin": "http://127.0.0.1:11435",
                   "executable": str(self.base / "portable" / "ollama.exe"), "executable_sha256": "a" * 64,
                   "process_created_at_utc": "2026-10-26T00:00:00+00:00"}
        write_json(f.reports / "service_receipt.json", service)
        shutdown = {"status": "owned_service_stopped", "stopped_pid": 502,
                    "executable": service["executable"], "executable_sha256": service["executable_sha256"],
                    "process_created_at_utc": service["process_created_at_utc"],
                    "owned_port_closed": True, "no_resident_models_before_stop": True,
                    "existing_11434_listener_unchanged": True, "persistent_environment_changed": False}
        write_json(f.reports / "shutdown.json", shutdown)
        output = self.base / "artifacts"
        output.mkdir()
        prior_source = self.base / "historical_note.txt"
        prior_source.write_text("Historical first-attempt evidence remains separate.", encoding="utf-8")
        prior_files = [prior_source]
        if purpose == "pilot_continuation":
            prior_files += [p for p in f.historical.run.rglob("*") if p.is_file()]
        prior_entries = []
        with zipfile.ZipFile(output / "prior.zip", "x", compression=zipfile.ZIP_STORED) as bundle:
            for path in prior_files:
                data = path.read_bytes()
                name = path.relative_to(self.base).as_posix()
                bundle.writestr(name, data)
                prior_entries.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        prior_hash = hashlib.sha256((output / "prior.zip").read_bytes()).hexdigest()
        manifest = {"archive": "prior.zip", "archive_sha256": prior_hash, "files": prior_entries}
        mr = write_json(output / "prior.manifest.json", manifest)
        vr = write_json(output / "prior.verification.json", {"verified_files": len(prior_entries), "archive_sha256": prior_hash})
        f.plan = {"version": "sector_campaign_archive_plan_1", "archive_stem": "completion-test",
                  "output_directory": "artifacts", "raw_campaign_parent": "data/local_sector_runtime",
                  "report_roots": [str(f.reports), str(f.inputs)], "extra_roots": [str(sources)],
                  "campaigns": [{"purpose": purpose, "run_directory": str(f.run), "reports_directory": str(f.reports),
                                 "service_receipt": str(f.reports / "service_receipt.json"),
                                 "shutdown_receipt": str(f.reports / "shutdown.json")}],
                  "main_state": {"status": "pending_not_run" if purpose == "pilot_continuation" else "included_terminal_main",
                                 "reason": "Synthetic test scope only; no actual main execution."},
                  "previous_archives": [{"manifest_ref": mr, "verification_ref": vr}]}
        f.plan_path = f.reports / "archive_plan.json"
        write_json(f.plan_path, f.plan)
        completion_scope = {"purpose": "pilot_completion", "case_order": list(archive.completion.CASES),
            "max_generation_requests": 6, "historical_generation_requests": 5, "campaign_max_generation_requests": 11,
            "automatic_retries": 0, "main_model_calls": 0, "main_allowed": False, "old_outputs_observed": True,
            "historical_first_attempt_results_unchanged": True, "explicit_retry_slots": [],
            "historical_explicit_retry_slots": ["fidelity_q2_2026__L__D0"],
            "analysis_role": "primary_exploratory", "excluded_new_main_execution": True}
        f.runtime["backend_evidence"] = [{**ref(f.reports / "service_receipt.json"), "role": "cpu_service"}]
        f.declaration.update(completion_scope)
        f.sync()
        summary = read_json(f.run / "campaign_summary.json")
        summary.update(completion_scope)
        summary["cases"] = [{"case_id": c, "stages": []} for c in archive.completion.CASES]
        write_json(f.run / "campaign_summary.json", summary)
        terminal = read_json(f.reports / "terminal_receipt.json")
        terminal.update(purpose="pilot_completion", declaration_ref=ref(f.run / "campaign_declaration.json"),
                        summary_ref=ref(f.run / "campaign_summary.json"))
        write_json(f.reports / "terminal_receipt.json", terminal)
        f.plan.update(version="sector_completion_archive_plan_1", analysis_role="primary_exploratory",
                      new_main_state={"status": "excluded_not_run", "reason": "NewQ3/July main explicitly excluded"})
        f.plan.pop("main_state")
        f.plan["campaigns"][0]["purpose"] = "pilot_completion"
        write_json(f.plan_path, f.plan)
        f.accounting = {"input_refs": [], "segment_case_order": list(archive.completion.CASES),
            "segment_planned_final_allocations": 3, "segment_planned_stage_slots": 6,
            "completion_generation_requests": 0, "all_generation_requests_including_interrupted_attempt": 5,
            "planned_final_allocations": 5, "logical_stage_slots": 10, "finalized_finals": 2}
        self.account_calls = []
        f.output, f.copied = output, copied
        return f

    def execute(self, f, *, probe=None):
        with ExitStack() as stack:
            stack.enter_context(patch.object(archive, "__file__", str(f.copied["archive_sector_completion.py"])))
            stack.enter_context(patch.object(archive, "RESTORE_SOURCE", f.copied["restore_research_artifacts.py"]))
            stack.enter_context(patch.object(campaign, "__file__", str(f.copied["finalize_sector_campaign.py"])))
            stack.enter_context(patch.object(campaign.math, "__file__", str(f.copied["finalize_sector_allocation.py"])))
            stack.enter_context(patch.object(archive.inherited, "__file__", str(f.copied["archive_sector_continuation.py"])))
            def counted_finalizer(run):
                self.account_calls.append(str(run))
                if hasattr(f, "accounting_error"):
                    raise f.accounting_error
                return copy.deepcopy(f.accounting)
            stack.enter_context(patch.object(archive.completion, "finalize_completion", side_effect=counted_finalizer))
            return archive.archive(f.plan_path, workspace=self.base,
                                   activity_probe=probe or (lambda _: {"processes": [], "listeners": []}))

    def assert_no_success(self, f):
        self.assertFalse((f.output / "completion-test.verification.json").exists())

    def test_quiet_archive_verifies_exact_members_and_preserves_old_archive(self):
        f = self.fixture()
        old = (f.output / "prior.zip").read_bytes()
        result = self.execute(f)
        manifest_path = f.output / "completion-test.manifest.json"
        manifest = read_json(manifest_path)
        verified = archive.restore(manifest_path, self.base, write=False)
        self.assertEqual(result["verified_files"], verified["verified_files"])
        self.assertGreater(result["verified_files"], 10)
        self.assertEqual(manifest["new_main_state"]["status"], "excluded_not_run")
        self.assertFalse(manifest["semantic_success_claimed"])
        self.assertEqual(manifest["campaign_accounting"][0]["segment_planned_stage_slots"], 6)
        self.assertEqual(manifest["campaign_accounting"][0]["generation_requests_attempted"], 0)
        self.assertTrue(any(row["path"] == "data/local_sector_runtime/raw/campaign_summary.json" for row in manifest["files"]))
        self.assertFalse(any(row["path"].endswith("prior.zip") for row in manifest["files"]))
        self.assertEqual((f.output / "prior.zip").read_bytes(), old)
        self.assertEqual(result["restored_files"], 0)
        self.assertFalse(result["source_files_deleted"])
        self.assertTrue(result["narrow_duplicate_ignore_eligible_only_for_exact_verified_members"])
        self.assertEqual(result["archive_bytes"], (f.output / "completion-test.zip").stat().st_size)
        self.assertEqual(manifest["archive_bytes"], result["archive_bytes"])

    def test_windows_idle_pid_zero_is_valid_but_boolean_pid_is_not(self):
        context = {"pids": {501}, "ports": {11435}, "service_executables": {"owned.exe"},
                   "command_markers": {"declared-raw-run"}}
        result = archive.quiet(context, lambda _: {"processes": [{"ProcessId": 0}], "listeners": []})
        self.assertEqual(result["processes_observed"], 1)
        with self.assertRaisesRegex(ValueError, "Malformed process"):
            archive.quiet(context, lambda _: {"processes": [{"ProcessId": False}], "listeners": []})

    def test_release_binds_the_actual_acquisition_thread_and_unique_event(self):
        f = self.fixture()
        acquire_path = f.reports / "events/acquired.json"
        original = read_json(acquire_path)
        mutations = [{**original, "owner_thread_id": 602}, {**original, "coordinator_pid": 502},
                     {**original, "flags": 0x80000001}, {**original, "helper_process_created": True}]
        for value in mutations:
            with self.subTest(value=value):
                write_json(acquire_path, value)
                with self.assertRaisesRegex(ValueError, "same-thread identity"):
                    archive.terminal_evidence(self.base, f.plan["campaigns"][0])
        write_json(acquire_path, original)
        write_json(f.reports / "events/duplicate.json", original)
        with self.assertRaisesRegex(ValueError, "Exactly one"):
            archive.terminal_evidence(self.base, f.plan["campaigns"][0])
        self.assert_no_success(f)

    def test_no_request_release_requires_zero_attempts_and_no_acquisition_event(self):
        f = self.fixture()
        release_path = f.reports / "coordinator_awake_release.json"
        terminal_path = f.reports / "terminal_receipt.json"
        release = read_json(release_path)
        release["status"] = "no_request_acquired"
        write_json(release_path, release)
        terminal = read_json(terminal_path)
        terminal["awake_release"] = release
        write_json(terminal_path, terminal)
        with self.assertRaisesRegex(ValueError, "zero generation attempts and no acquisition"):
            archive.terminal_evidence(self.base, f.plan["campaigns"][0])
        (f.reports / "events/acquired.json").unlink()
        self.assertEqual(archive.terminal_evidence(self.base, f.plan["campaigns"][0])["summary"]
                         ["generation_requests_attempted"], 0)
        summary = read_json(f.run / "campaign_summary.json")
        summary["generation_requests_attempted"] = 1
        write_json(f.run / "campaign_summary.json", summary)
        terminal.update(summary_ref=ref(f.run / "campaign_summary.json"), generation_requests_attempted=1)
        write_json(terminal_path, terminal)
        with self.assertRaisesRegex(ValueError, "zero generation attempts and no acquisition"):
            archive.terminal_evidence(self.base, f.plan["campaigns"][0])
        self.assert_no_success(f)

    def test_raw_parent_cannot_be_redirected_to_hide_new_campaigns(self):
        f = self.fixture()
        unrelated = self.base / "empty-namespace"
        unrelated.mkdir()
        f.plan["raw_campaign_parent"] = str(unrelated)
        write_json(f.plan_path, f.plan)
        with self.assertRaisesRegex(ValueError, "canonical campaign parent"):
            self.execute(f)
        self.assert_no_success(f)

    def test_exclusive_archive_race_cannot_write_competitors_failure_receipt(self):
        f = self.fixture()
        target = f.output / "completion-test.zip"
        original = Path.open
        def competing_open(path, mode="r", *args, **kwargs):
            if path == target and mode == "xb":
                with original(path, "xb") as handle:
                    handle.write(b"competing writer owns this attempt")
                raise FileExistsError(str(path))
            return original(path, mode, *args, **kwargs)
        with patch.object(Path, "open", competing_open):
            with self.assertRaises(FileExistsError):
                self.execute(f)
        self.assertEqual(target.read_bytes(), b"competing writer owns this attempt")
        self.assertFalse((f.output / "completion-test.failure.json").exists())
        self.assertFalse((f.output / "completion-test.manifest.json").exists())
        self.assert_no_success(f)

    def test_active_process_service_or_port_blocks_before_response_accounting(self):
        f = self.fixture()
        observations = [
            {"processes": [{"ProcessId": 501}], "listeners": []},
            {"processes": [{"ProcessId": 900, "CommandLine": "python run_sector_continuation.py"}], "listeners": []},
            {"processes": [{"ProcessId": 901, "ExecutablePath": str(self.base / "portable/ollama.exe")}], "listeners": []},
            {"processes": [], "listeners": [{"LocalPort": 11435, "OwningProcess": 902}]},
        ]
        # This minimal freeze only has finalizers, so provide raw-run marker for
        # a worker with a new PID; production frozen runtime filenames add markers.
        observations[1]["processes"][0]["CommandLine"] += " --run-dir " + str(f.run)
        for observed in observations:
            with self.subTest(observed=observed), patch.object(campaign, "finalize_campaign") as accounting:
                with self.assertRaisesRegex(ValueError, "active|listening"):
                    self.execute(f, probe=lambda _: observed)
                accounting.assert_not_called()
                self.assertEqual(self.account_calls, [])
                self.assert_no_success(f)

    def test_missing_release_loaded_model_or_incomplete_shutdown_fail_closed(self):
        f = self.fixture()
        shutdown_path = f.reports / "shutdown.json"
        original = read_json(shutdown_path)
        for key, value in (("no_resident_models_before_stop", False), ("owned_port_closed", False),
                           ("stopped_pid", 999), ("existing_11434_listener_unchanged", False)):
            with self.subTest(key=key):
                record = {**original, key: value}
                write_json(shutdown_path, record)
                with self.assertRaises(ValueError):
                    self.execute(f)
                self.assert_no_success(f)
        write_json(shutdown_path, original)
        (f.reports / "coordinator_awake_release.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.execute(f)
        self.assert_no_success(f)

    def test_terminal_binding_and_accounting_mismatch_rejected(self):
        f = self.fixture()
        path = f.reports / "terminal_receipt.json"
        value = read_json(path)
        value["summary_ref"]["sha256"] = "0" * 64
        write_json(path, value)
        with self.assertRaisesRegex(ValueError, "binding mismatch"):
            self.execute(f)
        value["summary_ref"] = ref(f.run / "campaign_summary.json")
        value["generation_requests_attempted"] = 1
        write_json(path, value)
        with self.assertRaisesRegex(ValueError, "accounting mismatch"):
            self.execute(f)
        self.assert_no_success(f)

    def test_duplicate_overlap_external_root_and_archive_self_cycle_rejected(self):
        f = self.fixture()
        original = copy.deepcopy(f.plan)
        mutations = [lambda p: p["extra_roots"].append(p["extra_roots"][0]),
                     lambda p: p["extra_roots"].append(str(f.inputs / "runtime.json")),
                     lambda p: p["extra_roots"].append("../external"),
                     lambda p: p["report_roots"].append(str(f.output))]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                value = copy.deepcopy(original)
                mutate(value)
                write_json(f.plan_path, value)
                with self.assertRaises(ValueError):
                    self.execute(f)
                self.assert_no_success(f)

    def test_byte_mutation_with_restored_size_mtime_leaves_failed_unverified_zip(self):
        f = self.fixture()
        note = f.reports / "note.txt"
        note.write_bytes(b"good")
        stamp = note.stat()
        original = zipfile.ZipFile.writestr
        def mutate(bundle, name, data, *args, **kwargs):
            result = original(bundle, name, data, *args, **kwargs)
            if name == note.relative_to(self.base).as_posix():
                note.write_bytes(b"evil")
                os.utime(note, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            return result
        with patch.object(zipfile.ZipFile, "writestr", mutate):
            with self.assertRaisesRegex(ValueError, "bytes changed"):
                self.execute(f)
        self.assertTrue((f.output / "completion-test.zip").exists())
        self.assertFalse((f.output / "completion-test.manifest.json").exists())
        self.assert_no_success(f)
        self.assertEqual(read_json(f.output / "completion-test.failure.json")["status"], "archive_attempt_failed_no_success_claim")

    def test_new_file_appearing_during_snapshot_is_rejected(self):
        f = self.fixture()
        original = zipfile.ZipFile.writestr
        def mutate(bundle, name, data, *args, **kwargs):
            result = original(bundle, name, data, *args, **kwargs)
            (f.reports / "late.txt").write_text("late writer", encoding="utf-8")
            return result
        with patch.object(zipfile.ZipFile, "writestr", mutate):
            with self.assertRaisesRegex(ValueError, "inventory changed"):
                self.execute(f)
        self.assert_no_success(f)

    def test_second_quiet_probe_detects_new_writer_and_never_reports_success(self):
        f = self.fixture()
        calls = []
        def probe(_):
            calls.append(True)
            return {"processes": [] if len(calls) == 1 else [{"ProcessId": 501}], "listeners": []}
        with self.assertRaisesRegex(ValueError, "remains active"):
            self.execute(f, probe=probe)
        self.assertEqual(len(calls), 2)
        self.assert_no_success(f)

    def test_existing_archive_and_corrupt_prior_archive_cannot_be_overwritten(self):
        f = self.fixture()
        target = f.output / "completion-test.zip"
        target.write_bytes(b"historical attempt")
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.execute(f)
        self.assertEqual(target.read_bytes(), b"historical attempt")
        # Separate fresh stem, preserving the earlier partial attempt.
        f.plan["archive_stem"] = "second-attempt"
        write_json(f.plan_path, f.plan)
        path = f.output / "prior.zip"
        path.write_bytes(path.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.execute(f)
        self.assertFalse((f.output / "second-attempt.verification.json").exists())

    def test_main_pending_cannot_hide_new_main_declaration(self):
        f = self.fixture()
        write_json(f.run.parent / "unlisted_main/campaign_declaration.json", {"purpose": "main"})
        with self.assertRaisesRegex(ValueError, "Unlisted new campaign"):
            self.execute(f)
        self.assert_no_success(f)

    def test_unknown_main_status_or_missing_probe_data_is_not_quiet_success(self):
        f = self.fixture()
        f.plan["new_main_state"]["status"] = "probably_ready"
        write_json(f.plan_path, f.plan)
        with self.assertRaisesRegex(ValueError, "excluded new-main"):
            self.execute(f)
        f.plan["new_main_state"]["status"] = "excluded_not_run"
        write_json(f.plan_path, f.plan)
        with self.assertRaisesRegex(ValueError, "Complete process"):
            self.execute(f, probe=lambda _: {"processes": []})
        self.assert_no_success(f)

    def test_CLI_without_explicit_execute_cannot_archive(self):
        with patch.object(sys, "argv", ["archive_sector_completion.py", "--plan", "unused.json"]), \
                patch.object(archive, "archive") as execute, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                archive.main()
            execute.assert_not_called()



    def test_nested_previous_zip_dependencies_are_verified_and_not_nested_as_payloads(self):
        f = self.fixture()
        leaf_path = f.output / "earlier.zip"
        data = b"earlier immutable evidence"
        with zipfile.ZipFile(leaf_path, "x") as bundle:
            bundle.writestr("earlier_note.txt", data)
        leaf_hash = hashlib.sha256(leaf_path.read_bytes()).hexdigest()
        mr = write_json(f.output / "earlier.manifest.json", {"archive": leaf_path.name, "archive_sha256": leaf_hash,
            "files": [{"path": "earlier_note.txt", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}]})
        vr = write_json(f.output / "earlier.verification.json", {"verified_files": 1, "archive_sha256": leaf_hash})
        current_manifest = f.output / "prior.manifest.json"
        prior = read_json(current_manifest)
        prior["previous_archive_dependencies"] = [{"manifest_ref": mr, "verification_ref": vr, "archive_ref": ref(leaf_path)}]
        f.plan["previous_archives"][0]["manifest_ref"] = write_json(current_manifest, prior)
        write_json(f.plan_path, f.plan)
        self.execute(f)
        manifest = read_json(f.output / "completion-test.manifest.json")
        self.assertEqual(len(manifest["previous_archive_dependencies"]), 2)
        self.assertFalse(any(row["path"].endswith(("prior.zip", "earlier.zip")) for row in manifest["files"]))
        self.assertEqual(hashlib.sha256(leaf_path.read_bytes()).hexdigest(), leaf_hash)

    def test_nested_archive_reference_hash_must_match_verified_payload(self):
        f = self.fixture()
        entry = copy.deepcopy(f.plan["previous_archives"][0])
        entry["archive_ref"] = {"path": str(f.output / "prior.zip"), "sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "Nested prior archive reference"):
            archive.verified_dependencies(self.base, [entry])
        self.assert_no_success(f)

    def test_unlisted_new_completion_cannot_be_hidden(self):
        f = self.fixture()
        write_json(f.run.parent / "unlisted_completion/campaign_declaration.json", {"purpose": "pilot_completion"})
        with self.assertRaisesRegex(ValueError, "Unlisted new campaign"):
            self.execute(f)
        self.assert_no_success(f)

    def test_finalizer_ack_or_accounting_failure_prevents_zip_creation(self):
        f = self.fixture()
        f.accounting_error = ValueError("synthetic progression_without_valid_external_review_acknowledgement")
        with self.assertRaisesRegex(ValueError, "valid_external_review"):
            self.execute(f)
        self.assertFalse((f.output / "completion-test.zip").exists())
        self.assert_no_success(f)

    def test_completion_scope_cannot_include_previously_completed_Fidelity(self):
        f = self.fixture()
        declaration = read_json(f.run / "campaign_declaration.json")
        declaration["case_order"][0] = "fidelity_q2_2026__E"
        write_json(f.run / "campaign_declaration.json", declaration)
        terminal = read_json(f.reports / "terminal_receipt.json")
        terminal["declaration_ref"] = ref(f.run / "campaign_declaration.json")
        write_json(f.reports / "terminal_receipt.json", terminal)
        with self.assertRaisesRegex(ValueError, "completion_scope"):
            self.execute(f)
        self.assert_no_success(f)

    def test_archive_service_must_be_exact_runtime_bound_service(self):
        f = self.fixture()
        alternate = f.reports / "unrelated_service_receipt.json"
        write_json(alternate, read_json(f.reports / "service_receipt.json"))
        f.plan["campaigns"][0]["service_receipt"] = str(alternate)
        write_json(f.plan_path, f.plan)
        with self.assertRaisesRegex(ValueError, "runtime-bound service"):
            self.execute(f)
        self.assertEqual(self.account_calls, [])
        self.assert_no_success(f)

    def test_duplicate_dependency_cannot_hide_a_conflicting_archive_ref(self):
        f = self.fixture()
        entry = copy.deepcopy(f.plan["previous_archives"][0])
        wrong = {**copy.deepcopy(entry), "archive_ref": {"path": str(f.output / "prior.zip"), "sha256": "0" * 64}}
        with self.assertRaisesRegex(ValueError, "Nested prior archive reference"):
            archive.verified_dependencies(self.base, [entry, wrong])
        dependencies, _ = archive.verified_dependencies(self.base, [entry, copy.deepcopy(entry)])
        self.assertEqual(len(dependencies), 1)
        self.assert_no_success(f)


if __name__ == "__main__":
    unittest.main(verbosity=2)
