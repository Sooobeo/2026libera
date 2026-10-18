"""Synthetic guard lifecycle tests; no generation and no Windows power calls."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_sector_v48_guarded_pilot as wrapper


class GuardedPilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / "prepared/manifest.json"
        self.prior = self.root / "prior/summary.json"
        self.operation = self.root / "operation.json"
        self.registration = self.root / "registration.json"
        self.args = argparse.Namespace(manifest=str(self.manifest), registration=str(self.registration),
            output=str(self.root / "new_run"), guard_output=str(self.root / "guard"), server_log="unused",
            base_url="http://127.0.0.1:11434")
        self.write(self.manifest, {"synthetic": True})
        self.write(self.prior, {"status": "stopped_system_integrity_incident", "main_model_calls": 0})
        hashes = {name: wrapper.ref(wrapper.ROOT / "research" / name)["sha256"] for name in wrapper.SOFTWARE}
        reviews = []
        for i in range(1, 4):
            path = self.root / f"synthetic_review{i}.json"
            self.write(path, {"synthetic_fixture_not_real_review": True, "round": i, "status": "PASS", "reviewed_software": hashes})
            reviews.append(wrapper.ref(path))
        self.op = {"kind": "one_explicit_sleep_disrupted_pilot_repeat", "main_authorized": False,
            "automatic_retries": 0, "repeat_bundle_limit": 1, "roster": list(wrapper.pilot.ROSTER),
            "manifest": wrapper.ref(self.manifest), "new_run_root": self.args.output,
            "guard_record_root": self.args.guard_output, "prior_run_summary": wrapper.ref(self.prior),
            "operating_software_hashes": hashes, "operating_reviews": reviews,
            "prior_run_reviews": reviews, "environment_evidence": []}
        self.sync()
        self.token = {"status": "active", "synthetic_mock": True}
        self.patches = [patch.object(wrapper.pilot, "verify_manifest"),
                       patch.object(wrapper.pilot, "verify_registration", side_effect=lambda *a: wrapper.read(self.registration)),
                       patch.object(wrapper.pilot, "run", return_value=0),
                       patch.object(wrapper.awake, "acquire", return_value=self.token),
                       patch.object(wrapper.awake, "release", return_value={"status": "released"})]
        self.mocks = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def sync(self):
        self.write(self.operation, self.op)
        self.write(self.registration, {"operating_addendum": wrapper.ref(self.operation)})

    def test_single_call_then_release(self):
        self.assertEqual(wrapper.run(self.args), 0)
        self.mocks[2].assert_called_once_with(self.args)
        self.mocks[4].assert_called_once_with(self.token)
        saved = wrapper.read(Path(self.args.guard_output) / "summary.json")
        self.assertEqual(saved["status"], "pilot_returned")
        self.assertEqual(saved["main_model_calls"], 0)

    def test_acquire_failure_never_starts_pilot(self):
        self.mocks[3].return_value = {"status": "request_failed"}
        with self.assertRaises(RuntimeError):
            wrapper.run(self.args)
        self.mocks[2].assert_not_called()
        self.mocks[4].assert_not_called()

    def test_pilot_exception_still_releases(self):
        self.mocks[2].side_effect = ValueError("synthetic operation error")
        with self.assertRaisesRegex(ValueError, "synthetic"):
            wrapper.run(self.args)
        self.mocks[4].assert_called_once_with(self.token)

    def test_acquire_record_write_failure_still_releases(self):
        real = wrapper.save_new
        def failing(path, value):
            if Path(path).name == "acquire.json":
                raise OSError("synthetic disk failure")
            return real(path, value)
        with patch.object(wrapper, "save_new", side_effect=failing), self.assertRaises(OSError):
            wrapper.run(self.args)
        self.mocks[4].assert_called_once_with(self.token)
        self.mocks[2].assert_not_called()

    def test_failed_release_not_success(self):
        self.mocks[4].return_value = {"status": "release_failed"}
        with self.assertRaisesRegex(RuntimeError, "restoration"):
            wrapper.run(self.args)
        self.assertEqual(wrapper.read(Path(self.args.guard_output) / "summary.json")["status"], "awake_restoration_failed")

    def test_prior_and_prepared_overlap_rejected(self):
        for protected in (self.prior.parent, self.manifest.parent):
            for field in ("new_run_root", "guard_record_root"):
                with self.subTest(protected=protected, field=field):
                    saved = self.op[field]
                    self.op[field] = str(protected / "nested")
                    attr = "output" if field == "new_run_root" else "guard_output"
                    old = getattr(self.args, attr)
                    setattr(self.args, attr, self.op[field]); self.sync()
                    with self.assertRaises(ValueError):
                        wrapper.verify_operation(self.args)
                    setattr(self.args, attr, old); self.op[field] = saved; self.sync()
        self.mocks[3].assert_not_called()

    def test_changed_code_hash_rejected(self):
        self.op["operating_software_hashes"][wrapper.SOFTWARE[0]] = "0" * 64
        self.sync()
        with self.assertRaisesRegex(ValueError, "changed"):
            wrapper.verify_operation(self.args)

    def test_missing_review_and_extra_repeat_rejected(self):
        self.op["repeat_bundle_limit"] = 2; self.sync()
        with self.assertRaises(ValueError):
            wrapper.verify_operation(self.args)
        self.op["repeat_bundle_limit"] = 1
        self.op["operating_reviews"] = self.op["operating_reviews"][:2]; self.sync()
        with self.assertRaisesRegex(ValueError, "Three"):
            wrapper.verify_operation(self.args)

    def test_existing_output_not_overwritten(self):
        Path(self.args.output).mkdir()
        with self.assertRaises(ValueError):
            wrapper.run(self.args)
        self.mocks[2].assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
