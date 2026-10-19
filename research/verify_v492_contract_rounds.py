"""Record three offline checks; no Ollama or other network access."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import sector_v491_contract as old
import sector_v492_contract as new
import test_sector_v491_contract as fixtures

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def main():
    fixture = fixtures.ContractTests()
    fixture.setUp()
    candidate, context, prompt, schema = fixture.real_v491_inputs()
    prompt = copy.deepcopy(prompt)
    prompt["F0_instruction"] = "SYNTHETIC TEST CONTRACT: review your actual draft and feedback. If an institutional document is supplied, interpret it; otherwise state that none was supplied."
    tests = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", "-m", "unittest",
         "test_sector_v492_contract.Contract492Tests", "-v"],
        cwd=ROOT / "research", capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if tests.returncode:
        raise AssertionError(tests.stdout + tests.stderr)
    assert "Ran 16 tests" in tests.stderr
    equivalences = []
    late = []
    for source_id in candidate["public_source_packets"]:
        selected = old.select_public_inputs(candidate, source_id)
        packet = selected["assigned_packet"]
        for arm in ("E", "L"):
            args = dict(arm=arm, **selected, common_context=context,
                        prompt_contract=prompt, response_schema=schema)
            before, after = old.build_draft_messages(**args), new.build_draft_messages(**args)
            assert old.canonical_json(before) == new.canonical_json(after)
            if arm == "L":
                late.append(after)
            obj = fixture.response(arm == "E")
            obj["source_id"] = source_id if arm == "E" else None
            obj["context_assessment"]["evidence_ids"] = ["CTX:task"]
            for row in obj["sectors"]:
                row["weight"] = 0.1  # deliberate invalid raw sum, never repaired
                row["source_label"] = packet["rating_vocabulary"][0] if arm == "E" else None
                row["source_evidence_ids"] = [sorted(new.evidence_ids(packet))[0]] if arm == "E" else []
                row["decision_evidence_ids"] = ["M:baseline_weights:" + row["sector_code"]]
            raw = "\r\n" + json.dumps(obj, ensure_ascii=False, indent=2) + "\r\n"
            final_args = dict(draft_messages=before, raw_draft=raw, assigned_packet=packet,
                              prompt_contract=prompt, response_schema=schema)
            prior_final, current_final = old.build_final_messages(**final_args), new.build_final_messages(**final_args)
            assert prior_final["ready"] and current_final["ready"]
            assert current_final["messages"][:3] == prior_final["messages"][:3]
            prior_payload = old.strict_json(prior_final["messages"][3]["content"])
            current_payload = new.strict_json(current_final["messages"][3]["content"])
            current_payload["actual_draft_calculator_feedback"]["lineage"]["contract_version"] = old.CONTRACT_VERSION
            assert old.canonical_json(prior_payload) == new.canonical_json(current_payload)
            assert current_final["source_packet_sha256"] == prior_final["source_packet_sha256"]
            assert not current_final["draft_feedback"]["allocation"]["valid"]
            assert current_final["visible_evidence_ids_for_final"] == prior_final["visible_evidence_ids_for_final"]
            equivalences.append({"source_id": source_id, "arm": arm, "D0_identical": True,
                                 "F0_identical_except_declared_contract_version": True,
                                 "raw_invalid_sum_retained": True})
    control = new.build_draft_messages(arm="C", **new.select_public_inputs(candidate, None),
        common_context=context, prompt_contract=prompt, response_schema=schema)
    assert len(late) == 4 and all(control == messages for messages in late)
    source_ids = set().union(*(new.evidence_ids(packet) for packet in candidate["public_source_packets"].values()))
    assert not (source_ids & new.evidence_ids(new.strict_json(control[1]["content"])))
    original = read("research/v491_handoff_20261019.json")["exact_delivery_files"]
    unchanged = [{"path": entry["path"], "unchanged": sha(entry["path"]) == entry["sha256"]}
                 for entry in original]
    assert all(item["unchanged"] for item in unchanged)
    files = ["research/sector_v492_contract.py", "research/test_sector_v492_contract.py",
             "research/verify_v492_contract_rounds.py", "research/sector_v491_contract.py",
             "research/sector_engine.py", "research/test_sector_v491_contract.py"]
    report = {
        "artifact_kind": "v492_contract_offline_three_stage_verification",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS", "model_calls": 0, "network_calls": 0,
        "synthetic_outputs_only": True, "independent_human_review": False,
        "round1": {"kind": "16_adversarial_contract_tests", "returncode": tests.returncode,
                   "stdout": tests.stdout, "stderr": tests.stderr},
        "round2": {"kind": "real_public_inputs_old_E_L_regression_with_synthetic_drafts",
                   "cases": equivalences},
        "round3": {"kind": "source_free_control_and_prior_artifact_integrity",
                   "C_D0_equals_four_L_inputs": True, "institution_evidence_ids_in_C": [],
                   "prior_delivery_files_unchanged": unchanged},
        "source_refs": [{"path": path, "sha256": sha(path)} for path in files],
        "limits": ["Three process checks are not independent human judgments.",
                   "Contract construction does not authenticate caller-supplied D0 provenance; runtime separately binds persisted same-case artifacts.",
                   "Source and schema gates enforce declared inputs; semantic support remains unvalidated AI-assisted evaluation.",
                   "No pilot or main generation was performed by this verification."],
    }
    path = ROOT / "research/v492_contract_verification_20261019.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"path": str(path.relative_to(ROOT)), "sha256": sha(path.relative_to(ROOT)),
                      "status": "PASS", "tests": 16, "real_E_L_regressions": 8,
                      "prior_unchanged": len(unchanged)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
