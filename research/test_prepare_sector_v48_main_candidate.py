"""Synthetic offline packaging tests; no actual candidate, model, HTTP or process."""
from pathlib import Path
import tempfile
import unittest

import prepare_sector_v48_main_candidate as prep


class MainCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pilot = self.root / "prepared_pilot"
        self.run = self.root / "synthetic_pilot_run"
        self.docs = self.root / "data/sector_documents"
        self.output = self.root / "synthetic_candidate_output"
        self.real = prep.ROOT
        original = self.real / "data/sector_protocol/v48_pilot_r2_20261018"
        self.pilot.mkdir(); self.run.mkdir()
        for name in prep.SHARED_INPUTS:
            self.copy(original / name, self.pilot / name)
        # Common provenance can contain the assigned source's literal name/ID;
        # this is supplied identically to both sources and is not source leakage.
        market = prep.read(self.pilot / "market_input.json")
        market["synthetic_common_baseline_provenance"] = "Fidelity Q3 / fidelity_q3_2026 public common baseline"
        self.write(self.pilot / "market_input.json", market)
        registry = prep.read(self.pilot / "public_numeric_registry.json")
        registry["source"]["sha256"] = prep.digest(self.pilot / "market_input.json")
        self.write(self.pilot / "public_numeric_registry.json", registry)
        for source in prep.PILOT_SOURCES:
            self.copy(original / "packets" / (source + ".json"), self.pilot / "packets" / (source + ".json"))
        for arm in prep.ARMS:
            for stage in range(1, 5):
                self.copy(original / f"schemas/{arm}_stage{stage}.json", self.pilot / f"schemas/{arm}_stage{stage}.json")
        self.design = self.root / "synthetic_design.json"
        self.write(self.design, {"synthetic": True, "not_a_real_research_review": True})
        self.manifest_path = self.pilot / "manifest.json"
        manifest = {"protocol_version": "4.8", "scope": "all_four_fixed_pilot_cases_only",
            "roster": prep.roster(prep.PILOT_SOURCES, "pilot"), "main_authorized": False, "main_frozen": False,
            "input_hashes": {str(p.relative_to(self.pilot)).replace("\\", "/"): prep.digest(p)
                             for p in self.pilot.rglob("*") if p.is_file()},
            "software_hashes": {name: prep.digest(self.real / "research" / name) for name in prep.PILOT_SOFTWARE},
            "design_references": [prep.ref(self.design), prep.ref(self.real / "research/v48_handoff_20261018.json")]}
        self.write(self.manifest_path, manifest)
        reviews = []
        for number in range(1, 4):
            path = self.root / f"synthetic_implementation_review_{number}.json"
            self.write(path, {"round": number, "status": "PASS", "synthetic_fixture_not_real_review": True,
                              "manifest_sha256": prep.digest(self.manifest_path)})
            reviews.append(prep.ref(path))
        self.registration_path = self.root / "synthetic_registration.json"
        registration = {"protocol_version": "4.8", "manifest": prep.ref(self.manifest_path),
                        "roster": manifest["roster"], "main_authorized": False, "reviews": reviews}
        self.write(self.registration_path, registration)
        self.write(self.run / "manifest_snapshot.json", manifest)
        self.write(self.run / "registration_snapshot.json", registration)
        self.write(self.run / "summary.json", {"synthetic_fixture_not_actual_model_run": True,
            "status": "all_planned_cases_accounted", "planned_cases": manifest["roster"],
            "main_model_calls": 0, "main_frozen": False, "human_review_completed": False,
            "core_generation_calls": 0, "auxiliary_generation_calls": 0})
        self.evaluation_path = self.root / "synthetic_evaluation.json"
        self.write(self.evaluation_path, {"scope": "pilot_only_offline_analysis", "artifact_issues": [],
            "system_integrity_incidents_present": False, "main_model_calls_by_this_evaluation": 0,
            "synthetic_fixture_not_empirical_evidence": True,
            "primary_C0_bundle": {"planned_case_count": 4, "expected_sector_count": 44,
                                  "valid_raw_allocation_count": 0, "completed_response_count": 0},
            "provenance": {"prepared_manifest": prep.ref(self.manifest_path),
                           "run_summary": prep.ref(self.run / "summary.json"),
                           "run_manifest_snapshot": prep.ref(self.run / "manifest_snapshot.json")}})
        self.audits = [self.root / f"synthetic_postpilot_round{number}.json" for number in range(1, 4)]
        self.write(self.audits[0], {"round": 1, "status": "PASS", "synthetic_fixture_not_real_audit": True,
            "manifest": prep.ref(self.manifest_path), "registration": prep.ref(self.registration_path),
            "run_root": str(self.run), "artifact_inventory": [prep.ref(p) for p in self.run.iterdir()]})
        for number in (2, 3):
            self.write(self.audits[number - 1], {"round": number, "status": "PASS", "synthetic_fixture_not_real_audit": True,
                "provenance": {"manifest": prep.ref(self.manifest_path), "evaluation": prep.ref(self.evaluation_path)}})
        source_manifest = {"sources": []}
        verification = {"all_mechanical_checks_passed": True, "artifact_sha256": {}}
        for source in prep.MAIN_SOURCES:
            path = self.docs / "packets/main" / (source + ".json")
            self.copy(self.real / "data/sector_documents/packets/main" / (source + ".json"), path)
            packet = prep.read(path)
            pdf = self.root / "synthetic_originals" / (source + ".pdf")
            pdf.parent.mkdir(parents=True, exist_ok=True)
            pdf.write_bytes(b"%PDF-SYNTHETIC FIXTURE; not a real source document\n")
            source_manifest["sources"].append({"source_id": source, "split": "main",
                "dates": packet["dates"], "url": packet["source_url"], "cache": prep.ref(pdf),
                "human_review_status": "pending", "known_source_issues": ["synthetic test fixture"]})
            verification["artifact_sha256"]["packets/main/" + source + ".json"] = prep.digest(path)
        self.write(self.docs / "source_manifest.json", source_manifest)
        verification["artifact_sha256"]["source_manifest.json"] = prep.digest(self.docs / "source_manifest.json")
        self.gold = self.docs / "evaluator_only/reference_annotations.jsonl"
        self.write(self.gold, {"synthetic_fixture_not_real_gold": "SYNTHETIC_OFFLINE_ONLY_GOLD_MARKER"})
        verification["artifact_sha256"]["evaluator_only/reference_annotations.jsonl"] = prep.digest(self.gold)
        self.write(self.docs / "verification.json", verification)
        self.technical_path=self.root/'synthetic_technical_three_review_receipt.json'
        self.technical={"artifact_kind":"v4.8_main_technical_three_review_receipt","status":"PASS",
            "candidate_bound":False,"model_calls":0,"main_model_calls":0,"independent_human_review_completed":False,
            "synthetic_fixture_not_real_review":True,
            "software_hashes":{name:prep.digest(self.real/'research'/name) for name in prep.MAIN_SOFTWARE},
            "evaluator_software_hashes":{name:prep.digest(self.real/'research'/name) for name in prep.MAIN_EVALUATOR_SOFTWARE}}
        self.technical_reviews=[]
        for number in range(1,4):
            path=self.root/f'synthetic_main_technical_round{number}.json'
            self.write(path,{"round":number,"status":"PASS","synthetic_fixture_not_real_review":True,
                "software_hashes":self.technical['software_hashes'],"evaluator_software_hashes":self.technical['evaluator_software_hashes']})
            self.technical_reviews.append(path)
        self.technical['reviews']=[prep.ref(p) for p in self.technical_reviews]
        self.write(self.technical_path,self.technical)

    def copy(self, source, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(prep.encoded(value))

    def change(self, path, change):
        obj = prep.read(path)
        change(obj)
        self.write(path, obj)

    def prepare(self):
        return prep.prepare(self.manifest_path, self.registration_path, self.evaluation_path, self.audits,
                            self.output, technical_review_receipt=self.technical_path, workspace_root=self.real, documents=self.docs)

    def test_candidate_has_four_cases_44_sectors_and_no_execution_or_freeze(self):
        receipt = self.prepare()
        candidate = prep.read(self.output / "manifest.json")
        self.assertEqual(candidate["roster"], prep.roster(prep.MAIN_SOURCES, "main"))
        self.assertEqual((candidate["planned_case_count"], candidate["expected_sector_count"]), (4, 44))
        self.assertFalse(candidate["main_authorized"])
        self.assertFalse(candidate["main_frozen"])
        self.assertFalse(candidate["human_review_completed"])
        self.assertTrue(candidate["main_runner_implemented"])
        self.assertTrue(candidate["main_artifact_evaluator_implemented"])
        self.assertEqual(candidate['technical_review']['receipt'],prep.ref(self.technical_path))
        self.assertFalse(candidate['technical_review']['main_authorization_created'])
        self.assertEqual(candidate["main_model_calls"], 0)
        self.assertEqual(receipt["model_calls"], 0)
        self.assertEqual(len(list((self.output / "schemas").glob("*.json"))), 8)
        self.assertEqual(len(list((self.output / "previews").rglob("*.json"))), 16)
        for name, expected in candidate["files"].items():
            self.assertEqual(prep.digest(self.output / name), expected)
        self.assertFalse((self.output / "registration.json").exists())
        self.assertFalse((self.output / "freeze.json").exists())
        self.assertEqual(prep.read(self.output / "packets/fidelity_q3_2026.json")["dates"]["sector_view_as_of_raw"], "6/31/26")

    def test_R4_onset_and_shared_baseline_name_are_not_confused(self):
        self.prepare()
        for source in prep.MAIN_SOURCES:
            for arm in prep.ARMS:
                observed = []
                for stage in range(1, 5):
                    payload = prep.read(self.output / f"previews/{source}__{arm}/stage{stage}_payload.json")
                    if "institution_document" in payload:
                        observed.append(stage)
                        self.assertEqual(payload["institution_document"]["source_id"], source)
                    self.assertNotIn("messages", payload)
                    self.assertNotIn("calculator_feedback", payload)
                self.assertEqual(observed, [1] if arm == "R1" else [4])
        first = prep.read(self.output / "previews/fidelity_q3_2026__R4/stage1_payload.json")
        self.assertIn("fidelity_q3_2026", first["common_market"]["synthetic_common_baseline_provenance"])
        self.assertNotIn("institution_document", first)

    def test_non_treatment_stage_conditions_are_identical(self):
        self.prepare()
        for stage in range(1, 5):
            common = []
            for case in prep.roster(prep.MAIN_SOURCES, "main"):
                payload = prep.read(self.output / f"previews/{case['case_id']}/stage{stage}_payload.json")
                payload.pop("institution_document", None)
                payload.pop("response_schema")
                common.append(payload)
            self.assertTrue(all(item == common[0] for item in common))

    def test_failed_or_reordered_audits_rejected(self):
        self.change(self.audits[1], lambda obj: obj.update(status="FAIL"))
        with self.assertRaisesRegex(ValueError, "must all PASS"):
            self.prepare()
        self.assertFalse(self.output.exists())
        self.change(self.audits[1], lambda obj: obj.update(status="PASS", round=3))
        with self.assertRaisesRegex(ValueError, "must all PASS"):
            self.prepare()

    def test_reviewed_partial_capture_diagnostic_is_retained_not_a_success_gate(self):
        diagnostic = {"case_id": "fidelity_q2_2026__R1", "kind": "partial_or_invalid_event_line",
                      "scope": "synthetic accepted terminal partial capture after a model case timeout"}
        self.change(self.evaluation_path, lambda obj: obj.update(artifact_issues=[diagnostic]))
        for path in self.audits[1:]:
            self.change(path, lambda obj: obj["provenance"].update(evaluation=prep.ref(self.evaluation_path)))
        self.prepare()
        candidate = prep.read(self.output / "manifest.json")
        self.assertEqual(candidate["prior_pilot"]["retained_evaluation_artifact_issues"], [diagnostic])
        self.assertFalse(candidate["prior_pilot"]["model_success_required"])

    def test_audit_of_another_evaluation_rejected_even_for_identical_bytes(self):
        another = self.root / "other_evaluation.json"
        self.copy(self.evaluation_path, another)
        self.change(self.audits[2], lambda obj: obj["provenance"].update(evaluation=prep.ref(another)))
        with self.assertRaisesRegex(ValueError, "another artifact"):
            self.prepare()

    def test_changed_pilot_artifacts_and_uninventoried_file_rejected(self):
        self.change(self.run / "summary.json", lambda obj: obj.update(extra="changed"))
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.prepare()

    def test_added_pilot_file_rejected(self):
        (self.run / "new_unreviewed.txt").write_text("synthetic new artifact")
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.prepare()

    def test_changed_main_packet_or_original_rejected(self):
        path = self.docs / "packets/main/fidelity_q3_2026.json"
        self.change(path, lambda obj: obj.update(title="Changed after document verification"))
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.prepare()

    def test_changed_original_pdf_rejected(self):
        path = self.root / "synthetic_originals/fidelity_q3_2026.pdf"
        path.write_bytes(b"changed source bytes")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.prepare()

    def test_missing_source_manifest_hash_rejected(self):
        self.change(self.docs / "verification.json", lambda obj: obj["artifact_sha256"].pop("source_manifest.json"))
        with self.assertRaisesRegex(ValueError, "manifest hash is missing"):
            self.prepare()

    def test_running_pilot_rejected(self):
        self.change(self.run / "summary.json", lambda obj: obj.update(status="running"))
        self.change(self.evaluation_path, lambda obj: obj["provenance"].update(run_summary=prep.ref(self.run / "summary.json")))
        with self.assertRaisesRegex(ValueError, "accounting is incomplete"):
            self.prepare()

    def test_existing_output_preserved(self):
        self.output.mkdir()
        sentinel = self.output / "sentinel.txt"
        sentinel.write_text("keep original")
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.assertEqual(sentinel.read_text(), "keep original")

    def test_missing_or_authorizing_technical_receipt_rejected(self):
        for key,value in (('status','FAIL'),('candidate_bound',True),('main_model_calls',1),
                          ('independent_human_review_completed',True)):
            record=dict(self.technical);record[key]=value;self.write(self.technical_path,record)
            with self.assertRaisesRegex(ValueError,'non-authorizing'):self.prepare()
            self.assertFalse(self.output.exists())
        self.technical_path.unlink()
        with self.assertRaises(FileNotFoundError):self.prepare()

    def test_technical_receipt_stale_code_hash_rejected(self):
        self.technical['software_hashes']['run_sector_v48_main.py']='0'*64
        self.write(self.technical_path,self.technical)
        with self.assertRaisesRegex(ValueError,'hash mismatch'):self.prepare()
        self.assertFalse(self.output.exists())
        for invalid in (None, '', True, 'A'*64):
            self.technical['software_hashes']['run_sector_v48_main.py']=invalid
            self.write(self.technical_path,self.technical)
            with self.assertRaisesRegex(ValueError,'lowercase SHA-256'):self.prepare()
            self.assertFalse(self.output.exists())

    def test_all_nine_evaluation_modules_required(self):
        self.technical['evaluator_software_hashes'].pop('audit_v48_main_round1.py')
        self.write(self.technical_path,self.technical)
        with self.assertRaisesRegex(ValueError,'inventory mismatch'):self.prepare()

    def test_technical_reviews_order_and_shared_hashes_required(self):
        self.change(self.technical_reviews[1],lambda row:row.update(round=3))
        self.technical['reviews']=[prep.ref(p) for p in self.technical_reviews]
        self.write(self.technical_path,self.technical)
        with self.assertRaisesRegex(ValueError,'PASS in order'):self.prepare()
        self.change(self.technical_reviews[1],lambda row:row.update(round=2,evaluator_software_hashes={}))
        self.technical['reviews']=[prep.ref(p) for p in self.technical_reviews]
        self.write(self.technical_path,self.technical)
        with self.assertRaisesRegex(ValueError,'identical code'):self.prepare()

    def test_technical_review_references_and_code_preserved_in_provenance(self):
        self.prepare();candidate=prep.read(self.output/'manifest.json')
        refs={item['path']:item['sha256'] for item in candidate['input_provenance']}
        for path in (self.technical_path,*self.technical_reviews,self.real/'research/audit_v48_main_round2.py'):
            self.assertEqual(refs[str(path.resolve())],prep.digest(path))
        self.assertFalse(candidate['technical_review']['candidate_bound'])
        remaining=prep.read(self.output/'remaining_requirements.json')
        self.assertTrue(remaining['main_runner_implemented'])
        self.assertFalse(remaining['main_registration_or_freeze_available'])

    def test_evaluation_materials_bound_but_not_online_payloads(self):
        self.prepare(); candidate = prep.read(self.output / "manifest.json")
        refs = candidate["evaluator_material_refs"]
        self.assertEqual(set(refs), {"reference_annotations", "source_verification", "design_handoff",
                                    "evaluation_protocol", "review_template", "source_comparison"})
        self.assertEqual(refs["reference_annotations"], prep.ref(self.gold))
        self.assertEqual(len(candidate["files"]), 32)
        provenance = {item["path"]: item["sha256"] for item in candidate["input_provenance"]}
        for value in refs.values():
            self.assertEqual(provenance[value["path"]], value["sha256"])
        for name in candidate["files"]:
            self.assertNotIn("SYNTHETIC_OFFLINE_ONLY_GOLD_MARKER", (self.output / name).read_text(encoding="utf-8"))
        for name in candidate["files"]:
            if name.startswith("previews/"):
                self.assertNotIn("evaluator_material_refs", (self.output / name).read_text(encoding="utf-8"))

    def test_annotation_bytes_must_match_original_verification_pin(self):
        self.gold.write_bytes(self.gold.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_annotation_pin_is_mandatory(self):
        self.change(self.docs / "verification.json", lambda obj: obj["artifact_sha256"].update(
            {"evaluator_only/reference_annotations.jsonl": None}))
        with self.assertRaisesRegex(ValueError, "Pinned reference annotation"):
            self.prepare()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
