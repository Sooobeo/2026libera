"""Synthetic-only gate verification. No actual review, approval or run is made."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import sector_v48_main_gate as gate


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if not path.is_file() or path.read_bytes() != data:
        path.write_bytes(data)


def ref(path):
    return {"path": str(path.resolve()), "sha256": gate.digest(path)}


class Fixture:
    """All evidence, code bytes and human identities here are fictional fixtures."""
    def __init__(self, root):
        self.root = root
        self.folder = root / "synthetic_candidate"
        self.manifest = self.folder / "manifest.json"
        self.gate_path = root / "synthetic_gate.json"
        self.human_path = root / "synthetic_human.json"
        self.auth_path = root / "synthetic_authorization.json"
        self.reviews = [root / f"synthetic_review_{n}.json" for n in range(1, 4)]
        self.files = {name: {"synthetic_fixture": name} for name in gate._candidate_names()}
        for name, value in self.files.items():
            write(self.folder / name, value)
        write(self.folder / "public_numeric_registry.json", {"source": {"sha256": gate.digest(self.folder / "market_input.json")}})
        self.candidate = {"candidate_version": "v4.8-main-candidate-1", "protocol_version": "4.8",
            "scope": "offline_main_input_candidate_not_execution_registration", "main_authorized": False,
            "main_frozen": False, "human_review_completed": False, "roster": gate.roster(),
            "planned_case_count": 4, "expected_sector_count": 44, "planned_core_calls_if_later_authorized": 16,
            "maximum_auxiliary_calls_if_later_authorized": 8, "model_calls_by_preparation": 0,
            "main_model_calls": 0, "actual_main_responses": 0,
            "files": {name: gate.digest(self.folder / name) for name in self.files}, "original_documents": []}
        self.candidate["prior_pilot"] = {key: {"path": str(root / folder / name), "sha256": "0" * 64}
            for key, folder, name in (("manifest", "synthetic_prior_inputs", "manifest.json"),
                ("registration", "synthetic_prior_inputs", "registration.json"),
                ("run_summary", "synthetic_prior_run", "summary.json"))}
        self.candidate["evaluator_material_refs"] = {key: {
            "path": str((root / "synthetic_offline_not_read" / (key + ".json")).resolve()),
            "sha256": "1" * 64} for key in gate.EVALUATOR_MATERIAL_KEYS}
        for sid in gate.MAIN_SOURCES:
            original = root / "synthetic_originals" / (sid + ".pdf")
            original.parent.mkdir(parents=True, exist_ok=True)
            data = ("SYNTHETIC NON-PDF FIXTURE: " + sid).encode()
            if not original.is_file() or original.read_bytes() != data:
                original.write_bytes(data)
            self.candidate["original_documents"].append({"source_id": sid, "original_pdf": ref(original),
                "recorded_human_review_status": "pending", "known_source_issues": ["Synthetic known date limitation"]})
        write(self.manifest, self.candidate)
        for filename in set(gate.SOFTWARE) | set(gate.EVALUATOR_SOFTWARE):
            path = root / "research" / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            data = ("# SYNTHETIC CODE BYTES, NEVER EXECUTED: " + filename).encode()
            if not path.is_file() or path.read_bytes() != data:
                path.write_bytes(data)
        self.gate = {"gate_version": gate.GATE_VERSION, "frozen": True, "main_authorized": True,
            "candidate_manifest": ref(self.manifest), "roster": gate.roster(), "maximum_generation_calls": 24,
            "authorized_run_root": str((root / "synthetic_future_run").resolve()),
            "software_hashes": {name: gate.digest(root / "research" / name) for name in gate.SOFTWARE},
            "evaluator_software_hashes": {name: gate.digest(root / "research" / name) for name in gate.EVALUATOR_SOFTWARE}}
        now = datetime.now(timezone.utc).isoformat()
        self.human = {"review_version": gate.HUMAN_REVIEW_VERSION, "review_status": "completed",
            "independent_human_review_completed": True, "completed_at_utc": now, "pending": [],
            "candidate_manifest": ref(self.manifest), "reviewer": {"reviewer_id": "fictional-test-only",
                "reviewer_role": "independent_human", "name_or_model_identity": "FICTIONAL SYNTHETIC FIXTURE",
                "independence_from_response_generation": True}, "source_materials": [], "source_difference_inventory": []}
        for original in self.candidate["original_documents"]:
            sid = original["source_id"]
            self.human["source_materials"].append({"source_id": sid, "original_pdf": original["original_pdf"],
                "packet": ref(self.folder / "packets" / (sid + ".json")), "review_status": "completed",
                "review_notes": "Synthetic fixture: source remains uncertain; no favorable conclusion.",
                "known_source_issue_dispositions": [{"issue": "Synthetic known date limitation",
                    "disposition": "accepted_limitation", "reason": "Synthetic unresolved date retained."}]})
        for sector in gate.SECTOR_CODES:
            row = {"inventory_id": "synthetic-" + sector, "created_before_main_responses": True,
                "split": "main", "sector_code": sector, "source_A_id": gate.MAIN_SOURCES[0],
                "source_B_id": gate.MAIN_SOURCES[1], "rating_definition_scope": "Synthetic incompatible definitions",
                "period_and_universe_scope": "Synthetic differing dates", "relationship": "uncertain",
                "decision_relevance_reason": "No supported implication in this synthetic example.",
                "comparability_limits": ["Synthetic uncertainty remains."], "reviewer_id": "fictional-test-only",
                "reviewer_role": "independent_human", "review_status": "completed",
                "independent_human_review_completed": True}
            for letter, material in zip(("A", "B"), self.human["source_materials"]):
                row["source_" + letter + "_literal_judgment"] = "SYNTHETIC SOURCE TEXT"
                row["source_" + letter + "_researcher_paraphrase"] = "SYNTHETIC RESEARCHER PARAPHRASE"
                row["source_" + letter + "_paraphrase_review"] = {"status": "compared", "reason": "Synthetic comparison; no positive result required."}
                row["source_" + letter + "_evidence_records"] = [{"source_path_or_url": material["original_pdf"]["path"],
                    "source_sha256": material["original_pdf"]["sha256"], "page_section_or_fact_locator": "Synthetic page 1"}]
            self.human["source_difference_inventory"].append(row)
        self.authorize()

    def authorize(self):
        """Bind fictional fixture records; never used on real workspace evidence."""
        write(self.human_path, self.human)
        self.gate["human_source_review"] = ref(self.human_path)
        for index, path in enumerate(self.reviews, 1):
            write(path, {"round": index, "status": "PASS", "reviewer": {"reviewer_id": "synthetic-program",
                "reviewer_role": "deterministic_program", "name_or_model_identity": "SYNTHETIC FIXTURE ONLY"},
                **{key: self.gate[key] for key in ("candidate_manifest", "software_hashes", "evaluator_software_hashes")}})
        self.gate["reviews"] = [ref(path) for path in self.reviews]
        self.authorization = {"authorization_version": gate.AUTHORIZATION_VERSION, "decision": "authorize_main_execution",
            "authorized_by": "FICTIONAL FIXTURE - NOT A USER APPROVAL", "authorized_at_utc": datetime.now(timezone.utc).isoformat(),
            **{key: self.gate[key] for key in ("candidate_manifest", "human_source_review", "software_hashes",
                 "evaluator_software_hashes", "reviews", "roster", "maximum_generation_calls", "authorized_run_root")}}
        self.save_authorization()

    def save_authorization(self):
        write(self.auth_path, self.authorization)
        self.gate["main_execution_authorization"] = ref(self.auth_path)
        self.save_gate()

    def save_gate(self):
        write(self.gate_path, self.gate)

    def verify(self):
        return gate.verify_main_gate(self.manifest, self.gate_path, workspace_root=self.root)


class MainGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="libera_v48_gate_synthetic_")
        cls.addClassCleanup(cls.temp.cleanup)

    def setUp(self):
        run_root = Path(self.temp.name) / "synthetic_future_run"
        if run_root.exists():
            run_root.rmdir()
        self.f = Fixture(Path(self.temp.name))

    def rejects(self):
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.f.verify()

    def test_completed_uncertain_sources_allowed_and_no_writes(self):
        before = {str(p): gate.digest(p) for p in self.f.root.rglob("*") if p.is_file()}
        values = self.f.verify()
        self.assertEqual(len(values), 8)
        self.assertFalse(values[0]["main_authorized"])
        self.assertTrue(values[5]["main_authorized"])
        self.assertEqual(values[6]["source_difference_inventory"][0]["relationship"], "uncertain")
        self.assertFalse(Path(self.f.gate["authorized_run_root"]).exists())
        self.assertEqual(before, {str(p): gate.digest(p) for p in self.f.root.rglob("*") if p.is_file()})

    def test_all_relationships_and_unassessable_issue_allowed(self):
        for index, relation in enumerate(sorted(gate.RELATIONSHIPS)):
            self.f.human["source_difference_inventory"][index]["relationship"] = relation
        self.f.human["source_materials"][0]["known_source_issue_dispositions"][0]["disposition"] = "not_assessable"
        self.f.authorize()
        self.f.verify()

    def test_specific_missing_material_reason_allowed(self):
        row = self.f.human["source_difference_inventory"][0]
        row["source_A_literal_judgment"] = None
        row["source_A_evidence_records"] = []
        row["source_A_missing_material_reason"] = "Synthetic source has no statement for this sector."
        row["relationship"] = "insufficient_evidence"
        self.f.authorize()
        self.f.verify()

    def test_paraphrase_review_must_be_explicit_but_uncertainty_is_allowed(self):
        row = self.f.human["source_difference_inventory"][0]
        row["source_A_paraphrase_review"] = None
        self.f.authorize()
        self.rejects()
        row["source_A_paraphrase_review"] = {"status": "not_assessable", "reason": "Synthetic limitation: cannot establish the paraphrase's scope."}
        row["source_A_researcher_paraphrase"] = None
        self.f.authorize()
        self.f.verify()

    def test_existing_authorized_run_directory_allowed_for_endpoint_recheck(self):
        Path(self.f.gate["authorized_run_root"]).mkdir()
        self.f.verify()

    def test_evaluator_only_materials_are_bound_but_never_read_online(self):
        self.assertTrue(all(not Path(r["path"]).exists() for r in self.f.candidate["evaluator_material_refs"].values()))
        self.f.verify()
        self.f.candidate["evaluator_material_refs"]["reference_annotations"]["sha256"] = None
        write(self.f.manifest, self.f.candidate)
        self.f.gate["candidate_manifest"] = ref(self.f.manifest)
        self.f.human["candidate_manifest"] = ref(self.f.manifest)
        self.f.authorize()
        self.rejects()

    def test_unbound_changed_candidate_file_rejected(self):
        write(self.f.folder / "runtime.json", {"changed": True})
        self.rejects()

    def test_changed_original_rejected(self):
        Path(self.f.candidate["original_documents"][0]["original_pdf"]["path"]).write_bytes(b"changed")
        self.rejects()

    def test_changed_online_or_evaluator_code_rejected(self):
        for name in (gate.SOFTWARE[0], gate.EVALUATOR_SOFTWARE[0]):
            with self.subTest(name=name):
                path = self.f.root / "research" / name
                original = path.read_bytes()
                path.write_bytes(b"changed")
                self.rejects()
                path.write_bytes(original)

    def test_exact_software_inventory_required(self):
        self.f.gate["software_hashes"]["unregistered.py"] = "0" * 64
        self.f.authorize()
        self.rejects()

    def test_all_mandatory_hash_inventories_reject_null_empty_bool_uppercase(self):
        original = tuple(copy.deepcopy(x) for x in (self.f.candidate, self.f.gate, self.f.human))
        for inventory in ("candidate_files", "software_hashes", "evaluator_software_hashes"):
            for invalid in (None, "", True, "A" * 64):
                with self.subTest(inventory=inventory, invalid=invalid):
                    self.f.candidate, self.f.gate, self.f.human = map(copy.deepcopy, original)
                    if inventory == "candidate_files":
                        self.f.candidate["files"]["runtime.json"] = invalid
                        write(self.f.manifest, self.f.candidate)
                        self.f.gate["candidate_manifest"] = ref(self.f.manifest)
                        self.f.human["candidate_manifest"] = ref(self.f.manifest)
                    else:
                        write(self.f.manifest, self.f.candidate)
                        key = next(iter(self.f.gate[inventory]))
                        self.f.gate[inventory][key] = invalid
                    self.f.authorize()
                    self.rejects()

    def test_three_distinct_bound_reviews_required(self):
        self.f.gate["reviews"][2] = self.f.gate["reviews"][0]
        self.f.authorization["reviews"] = self.f.gate["reviews"]
        self.f.save_authorization()
        self.rejects()

    def test_review_binding_mismatch_rejected(self):
        path = self.f.reviews[1]
        review = gate.read(path)
        review["software_hashes"] = {}
        write(path, review)
        self.f.gate["reviews"][1] = ref(path)
        self.f.authorization["reviews"] = self.f.gate["reviews"]
        self.f.save_authorization()
        self.rejects()

    def test_missing_explicit_authorization_rejected(self):
        self.f.authorization["decision"] = "prepare_only"
        self.f.save_authorization()
        self.rejects()

    def test_authorization_cannot_change_output_roster_or_call_budget(self):
        original = copy.deepcopy(self.f.authorization)
        for key, value in (("authorized_run_root", str(self.f.root / "different_run")),
                           ("roster", []), ("maximum_generation_calls", 25)):
            with self.subTest(key=key):
                self.f.authorization = copy.deepcopy(original)
                self.f.authorization[key] = value
                self.f.save_authorization()
                self.rejects()

    def test_source_review_cannot_be_assistant_or_pending(self):
        original = copy.deepcopy(self.f.human)
        for key, value in (("review_status", "not_started"), ("pending", ["unreviewed source"]),
                           ("independent_human_review_completed", False)):
            with self.subTest(key=key):
                self.f.human = copy.deepcopy(original)
                self.f.human[key] = value
                self.f.authorize()
                self.rejects()
        self.f.human = copy.deepcopy(original)
        self.f.human["reviewer"]["reviewer_role"] = "assistant_self_review"
        self.f.authorize()
        self.rejects()

    def test_all_eleven_source_rows_and_known_issues_required(self):
        original = copy.deepcopy(self.f.human)
        for kind in ("missing_row", "duplicate_row", "missing_issue", "wrong_pdf_locator", "blank_relationship"):
            with self.subTest(kind=kind):
                self.f.human = copy.deepcopy(original)
                rows = self.f.human["source_difference_inventory"]
                if kind == "missing_row":
                    rows.pop()
                elif kind == "duplicate_row":
                    rows[-1] = rows[0]
                elif kind == "missing_issue":
                    self.f.human["source_materials"][0]["known_source_issue_dispositions"] = []
                elif kind == "wrong_pdf_locator":
                    rows[0]["source_A_evidence_records"][0]["source_sha256"] = "0" * 64
                else:
                    rows[0]["relationship"] = None
                self.f.authorize()
                self.rejects()

    def test_naive_time_and_blank_reviewer_rejected(self):
        self.f.authorization["authorized_at_utc"] = "2026-10-18T12:00:00"
        self.f.save_authorization()
        self.rejects()
        self.f.authorize()
        self.f.human["reviewer"]["name_or_model_identity"] = " "
        self.f.authorize()
        self.rejects()

    def test_gate_and_candidate_execution_flags_are_separate(self):
        self.f.gate["frozen"] = False
        self.f.save_gate()
        self.rejects()
        self.f.gate["frozen"] = True
        self.f.candidate["main_authorized"] = True
        write(self.f.manifest, self.f.candidate)
        self.f.gate["candidate_manifest"] = ref(self.f.manifest)
        self.f.human["candidate_manifest"] = ref(self.f.manifest)
        self.f.authorize()
        self.rejects()

    def test_output_must_be_absolute_and_outside_inputs(self):
        for path in ("relative_path", str(self.f.folder / "bad_run"), str(self.f.root)):
            with self.subTest(path=path):
                self.f.gate["authorized_run_root"] = path
                self.f.authorize()
                self.rejects()

    def test_output_cannot_modify_preserved_pilot_source_or_design_trees(self):
        folders = ("synthetic_prior_inputs", "synthetic_prior_run", "synthetic_originals",
                   "data/sector_documents", "data/sector_protocol/v48_design_20261018")
        for folder in folders:
            with self.subTest(folder=folder):
                self.f.gate["authorized_run_root"] = str(self.f.root / folder / "new_main")
                self.f.authorize()
                self.rejects()

    def test_authorization_cannot_predate_source_review(self):
        self.f.authorization["authorized_at_utc"] = "2026-01-01T00:00:00+00:00"
        self.f.save_authorization()
        self.rejects()

    def test_json_duplicate_and_overflow_rejected(self):
        for raw in ('{"x":1,"x":2}', '{"x":1e309}', '{"x":NaN}'):
            self.f.gate_path.write_text(raw, encoding="utf-8")
            self.rejects()

    def test_candidate_inventory_cannot_escape(self):
        value = self.f.candidate["files"].pop("runtime.json")
        self.f.candidate["files"]["../runtime.json"] = value
        write(self.f.manifest, self.f.candidate)
        self.f.gate["candidate_manifest"] = ref(self.f.manifest)
        self.f.human["candidate_manifest"] = ref(self.f.manifest)
        self.f.authorize()
        self.rejects()


if __name__ == "__main__":
    unittest.main(verbosity=2)
