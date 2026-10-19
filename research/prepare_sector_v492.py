"""Prepare five pilot inputs offline, retaining the reviewed v4.9.1 market/task.

E/L source cases and the separate never-source C case share one conditional final
instruction. Identical L/C draft messages require separate executions. This file
does not invoke a model, set a gold allocation or certify AI review completion.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

import prepare_sector_v491 as paths
import sector_v491_runtime as inherited

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "data/sector_protocol/v492_design_20261019"
MANIFEST = DESIGN / "prepared/preparation_manifest.json"
CASE_ORDER = list(inherited.CASES) + ["common_market_only__C"]


def ref(path):
    path = paths.workspace_path(path)
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def shared_prompt(original):
    result = copy.deepcopy(original)
    instruction = result["F0_instruction"].replace(
        "using the complete assigned institution packet supplied in this final message, the common market evidence in history",
        "using the common market evidence retained in history, any institution packet actually supplied in this final message")
    instruction = instruction.replace("Explain how current supplied market evidence interacts with the dated source view;",
        "When an institution packet is supplied, explain how current supplied market evidence interacts with that dated source view;")
    instruction += (" If no institution packet is supplied, institutional evidence remains unavailable. "
        "Use source_id=null, source_label=null, source_stance=not_available, and empty source_evidence_ids for every sector. "
        "Do not guess a source, issuer, rating or institutional rationale. Explain the allocation from the common evidence "
        "and actual draft feedback without attributing it to an institution.")
    result.update(protocol_version="4.9.2", F0_instruction=instruction,
        status="offline_five_case_candidate_requires_AI_review_freeze_and_live_validation",
        F0_order=["same conditional instruction", "actual own-draft calculator feedback", "assigned source packet only when provided"],
        source_selection="E D0 assigned only; L/C D0 no source identity; E/L F0 assigned only; C F0 no source identity or packet",
        implementation="research/sector_v492_contract.py",
        control_case="One separately generated C trajectory, with no institution packet at D0 or F0; not a shared L draft")
    return result


def prepare(output_root=DESIGN):
    import sector_v492_contract as contract
    output_root = paths.workspace_path(output_root)
    old_loaded, old_cases = inherited.load_bundle()
    old_manifest, _ = paths.read(inherited.MANIFEST, inherited.MANIFEST_SHA)
    prompt = shared_prompt(old_loaded["prompt_contract"])
    cases = copy.deepcopy(old_cases)
    cases.append({"case_id": "common_market_only__C", "source_id": None, "arm": "C",
                  "common_market": copy.deepcopy(cases[0]["common_market"]),
                  "public_numeric_fact_index": copy.deepcopy(cases[0]["public_numeric_fact_index"]),
                  "assigned_packet": None})
    pending, planned, common, no_source_messages = [], [], None, []
    for case in cases:
        messages = contract.build_draft_messages(arm=case["arm"], assigned_packet=case["assigned_packet"],
            common_market=case["common_market"], public_numeric_fact_index=case["public_numeric_fact_index"],
            common_context=old_loaded["common_context"], prompt_contract=prompt, response_schema=old_loaded["response_schema"])
        payload = contract.strict_json(messages[1]["content"])
        blocks = {key: contract.canonical_json(payload[key]) for key in
                  ("common_context", "common_market", "public_numeric_fact_index", "response_schema")}
        if common is None:
            common = blocks
        elif common != blocks:
            raise ValueError("Common blocks differ across five pilot conditions")
        if case["arm"] in ("L", "C"):
            if "institution_document" in payload:
                raise ValueError("Institution packet leaked into a source-free draft")
            no_source_messages.append(messages)
        if case["arm"] != "C" and messages != case["messages"]:
            raise ValueError("Existing E/L draft inputs changed unexpectedly")
        path = output_root / "prepared" / (case["case_id"] + "__D0_messages.json")
        raw = (json.dumps(messages, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        visible = contract.evidence_ids(old_loaded["common_context"]) | contract.evidence_ids(case["public_numeric_fact_index"])
        if case["arm"] == "E":
            visible |= contract.evidence_ids(case["assigned_packet"])
        planned.append({"case_id": case["case_id"], "split": "pilot", "arm": case["arm"], "source_id": case["source_id"],
            "stage": "D0", "path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(raw).hexdigest(),
            "canonical_messages_sha256": hashlib.sha256(contract.canonical_json(messages).encode()).hexdigest(),
            "message_content_utf8_bytes": sum(len(m["content"].encode("utf-8")) for m in messages),
            "visible_evidence_count": len(visible), "separate_generation_required": True, "model_calls": 0})
        pending.append((path, raw))
    if [c["case_id"] for c in planned] != CASE_ORDER or len(no_source_messages) != 3 or not all(m == no_source_messages[0] for m in no_source_messages):
        raise ValueError("Expected five unique cases and three identical but separately executed source-free drafts")
    prompt_path = output_root / "prompt_contract.json"
    pending.insert(0, (prompt_path, (json.dumps(prompt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")))
    for path, _ in pending:
        if path.exists():
            raise FileExistsError("Preparation does not overwrite existing files: " + str(path))
    manifest_path = output_root / "prepared/preparation_manifest.json"
    if manifest_path.exists():
        raise FileExistsError(str(manifest_path))
    for path, raw in pending:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(raw)
    old_inputs = old_manifest["inputs"]
    manifest = {"protocol_version": "4.9.2", "input_protocol_version": "4.9.1",
        "status": "offline_five_case_preparation_passed_no_generation", "model_calls": 0,
        "pilot_model_calls": 0, "main_model_calls": 0, "prepared_cases": planned,
        "inputs": {"input_protocol": ref(old_inputs["configuration"]["path"]),
                   "previous_preparation_manifest": ref(inherited.MANIFEST),
                   "public_aggregate_never_sent": ref(old_inputs["public_aggregate_never_sent"]["path"]),
                   "common_context": ref(old_inputs["common_context"]["path"]),
                   "response_schema": ref(old_inputs["response_schema"]["path"]),
                   "prompt_contract": ref(prompt_path),
                   "contract_implementation": ref("research/sector_v492_contract.py"),
                   "preparer_implementation": ref(Path(__file__).resolve())},
        "checks": {"five_unique_cases": True, "common_blocks_identical": True,
                   "original_four_D0_unchanged": True, "L_and_C_D0_identical": True,
                   "L_and_C_D0_exclude_institution": True, "no_generation_or_synthetic_final_prepared": True},
        "F0": "Built only from each case's own actual retained D0 and arithmetic. E/L receive assigned packet; C receives none. Same final instruction in all five.",
        "limits": "Preparation is not semantic review, feasibility certification, or proof that equal portfolios are appropriate. Five-case order and size are declared design choices, not paper-derived optima."}
    with manifest_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DESIGN)
    args = parser.parse_args()
    result = prepare(args.output_root)
    print(json.dumps({"status": result["status"], "prepared_cases": len(result["prepared_cases"]), "model_calls": 0}))
