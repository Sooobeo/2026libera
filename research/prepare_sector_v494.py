"""Prepare a prospective development pilot after the interrupted v4.9.2 run.

Only the reviewed common instruction clarification changes. Source packets,
market, schema, E/L timing, C control and raw first-attempt policy are retained.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import prepare_sector_v491 as paths
import prepare_sector_v492 as previous
import sector_v492_contract as contract
import sector_v492_runtime as previous_runtime

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "data/sector_protocol/v494_design_20261025"
MANIFEST = DESIGN / "prepared/preparation_manifest.json"
PROMPT_CANDIDATE = ROOT / "research/recovery_20261025/method_prompt_candidate.json"
CASE_ORDER = list(previous_runtime.CASES)


def reviewed_prompt():
    value = json.loads(PROMPT_CANDIDATE.read_text(encoding="utf-8-sig"))
    return value.get("prompt_contract", value)


def prepare(output_root=DESIGN):
    output_root = paths.workspace_path(output_root)
    if output_root.exists():
        raise FileExistsError("New preparation never overwrites: " + str(output_root))
    loaded, cases = previous_runtime.load_bundle()
    old_manifest, _ = paths.read(previous.MANIFEST)
    prompt = reviewed_prompt()
    if prompt.get("protocol_version") != "4.9.4":
        raise ValueError("Reviewed prospective v4.9.4 instruction required")
    common = None
    no_source = []
    pending, planned = [], []
    for case in cases:
        messages = contract.build_draft_messages(
            arm=case["arm"], assigned_packet=case["assigned_packet"],
            common_market=case["common_market"], public_numeric_fact_index=case["public_numeric_fact_index"],
            common_context=loaded["common_context"], prompt_contract=prompt,
            response_schema=loaded["response_schema"])
        payload = contract.strict_json(messages[1]["content"])
        old_payload = contract.strict_json(case["messages"][1]["content"])
        keys = ("common_context", "common_market", "public_numeric_fact_index", "response_schema")
        blocks = {key: contract.canonical_json(payload[key]) for key in keys}
        if any(blocks[key] != contract.canonical_json(old_payload[key]) for key in keys):
            raise ValueError("Common evidence or output schema changed")
        if payload.get("institution_document") != old_payload.get("institution_document"):
            raise ValueError("Institution evidence/timing changed")
        if common is None:
            common = blocks
        elif common != blocks:
            raise ValueError("Common blocks differ by condition")
        if case["arm"] in ("L", "C"):
            if "institution_document" in payload or any(s in contract.canonical_json(messages) for s in previous_runtime.PILOT_SOURCES):
                raise ValueError("Source-free draft contains institution identity")
            no_source.append(messages)
        path = output_root / "prepared" / (case["case_id"] + "__D0_messages.json")
        raw = (json.dumps(messages, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        planned.append({"case_id": case["case_id"], "split": "pilot", "arm": case["arm"],
                        "source_id": case["source_id"], "stage": "D0", "path": path.relative_to(ROOT).as_posix(),
                        "sha256": previous.hashlib.sha256(raw).hexdigest(),
                        "separate_generation_required": True, "model_calls": 0})
        pending.append((path, raw))
    if len(no_source) != 3 or any(m != no_source[0] for m in no_source):
        raise ValueError("All three source-free D0 inputs must be identical")
    prompt_path = output_root / "prompt_contract.json"
    pending.append((prompt_path, (json.dumps(prompt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")))
    for path, raw in pending:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
    inputs = copy.deepcopy(old_manifest["inputs"])
    inputs.update(previous_preparation_manifest=previous.ref(previous.MANIFEST),
                  prompt_contract=previous.ref(prompt_path),
                  preparer_implementation=previous.ref(__file__),
                  reviewed_prompt_candidate=previous.ref(PROMPT_CANDIDATE))
    manifest = {"protocol_version": "4.9.4", "input_protocol_version": "4.9.1", "model_calls": 0,
                "status": "prospective_development_preparation_complete", "prepared_cases": planned,
                "inputs": inputs,
                "checks": {"five_unique_cases": [x["case_id"] for x in planned] == CASE_ORDER,
                           "common_evidence_and_schema_unchanged": True, "source_packets_and_timing_unchanged": True,
                           "L_and_C_D0_identical": True, "no_source_leakage": True},
                "development_disclosure": "Prompt clarification selected after inspecting old pilot failures; not an untouched replication. Both runs retained. No improvement guaranteed.",
                "evaluation": "Unchanged v4.9.2 r2 descriptive arithmetic and evidence-linked semantic rubric; invalid outcomes remain in denominator."}
    target = output_root / "prepared/preparation_manifest.json"
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return manifest


if __name__ == "__main__":
    result = prepare()
    print(json.dumps({"status": result["status"], "case_count": len(result["prepared_cases"])}))
