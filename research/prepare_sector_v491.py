"""Prepare public D0 requests offline; never invoke a model or invent a draft.

Run from any directory with Python plus the recorded numpy/jsonschema versions.
The manifest is controller metadata, never an additional model input. Identical
late-arm D0 inputs still require separate executions for every planned case.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re

from sector_v491_contract import (
    CONTRACT_VERSION, build_draft_messages, canonical_json, evidence_ids,
    select_public_inputs, strict_json,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "plan/LIBERA_실험설정_v4.9.1_20261019.json"
DEFAULT_OUTPUT = ROOT / "data/sector_protocol/v491_design_20261019/prepared"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def workspace_path(value: str | Path) -> Path:
    path = Path(value)
    path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError("preparation inputs/outputs must remain inside the repository") from exc
    return path


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read(path: str | Path, expected_sha: str | None = None) -> tuple[dict, dict]:
    path = workspace_path(path)
    raw = path.read_bytes()
    digest = sha(raw)
    if expected_sha is not None and expected_sha != digest:
        raise ValueError("input hash differs from configuration: " + relative(path))
    value = strict_json(raw.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("preparation input must be a JSON object")
    return value, {"path": relative(path), "sha256": digest, "bytes": len(raw)}


def prepare(config_path: str | Path = DEFAULT_CONFIG,
            output_dir: str | Path = DEFAULT_OUTPUT) -> dict:
    """Validate all requests before writing, with no outcomes or model calls."""
    output_dir = workspace_path(output_dir)
    config, config_ref = read(config_path)
    if config.get("protocol_version") != "4.9.1" or config.get("arms") != ["E", "L"] or config.get("stages") != ["D0", "F0"]:
        raise ValueError("configuration must declare the v4.9.1 E/L D0/F0 design")
    data = config["data"]
    candidate, candidate_ref = read(data["compact_candidate"]["path"], data["compact_candidate"]["sha256"])
    context, context_ref = read(data["common_context"]["path"], data["common_context"]["sha256"])
    prompt, prompt_ref = read(config["prompt_contract_path"])
    schema, schema_ref = read(config["schema_path"])
    if context != candidate.get("common_context") or config.get("task") != context.get("operating_brief"):
        raise ValueError("standalone, aggregate and configured common operating context must agree")
    if prompt.get("protocol_version") != "4.9.1":
        raise ValueError("prompt version differs from the declared protocol")
    source_plan = config["sources"]
    if set(source_plan) != {"pilot", "main"} or any(len(source_plan[s]) != 2 for s in source_plan):
        raise ValueError("exactly two source documents per split are required")
    source_ids = [sid for split in ("pilot", "main") for sid in source_plan[split]]
    if len(set(source_ids)) != 4 or set(source_ids) != set(candidate["public_source_packets"]):
        raise ValueError("source plan and four-packet public corpus differ")
    if any(not re.fullmatch(r"[a-zA-Z0-9_-]+", sid) for sid in source_ids):
        raise ValueError("source identifiers must be safe fixed filename components")
    public_packet_tokens = source_ids + [p.get("issuer", "") for p in candidate["public_source_packets"].values()]
    public_packet_tokens = [token for token in public_packet_tokens if token]
    common_keys = ("common_context", "common_market", "public_numeric_fact_index", "response_schema")
    common_hashes = None
    late_request_hashes = set()
    planned, pending = [], []
    for split in ("pilot", "main"):
        for source_id in source_plan[split]:
            inputs = select_public_inputs(candidate, source_id)
            packet = inputs["assigned_packet"]
            if packet.get("split") != split:
                raise ValueError("packet split differs from configured case split")
            for arm in config["arms"]:
                messages = build_draft_messages(arm=arm, **inputs, common_context=context,
                                                prompt_contract=prompt, response_schema=schema)
                payload = strict_json(messages[1]["content"])
                hashes = {key: sha(canonical_json(payload[key]).encode("utf-8")) for key in common_keys}
                if common_hashes is None:
                    common_hashes = hashes
                elif common_hashes != hashes:
                    raise ValueError("common blocks differ between planned cases")
                content = canonical_json(messages)
                if arm == "L":
                    if "institution_document" in payload or any(token in content for token in public_packet_tokens):
                        raise ValueError("late draft contains source identity or source packet")
                    late_request_hashes.add(sha(content.encode("utf-8")))
                elif payload.get("institution_document") != packet:
                    raise ValueError("early draft does not contain exactly its assigned packet")
                if any(sid in content for sid in source_ids if sid != source_id):
                    raise ValueError("request contains an unassigned source identity")
                if any(key in payload for key in ("case_id", "arm", "source_id", "split", "public_source_packets", "evaluator_only")):
                    raise ValueError("controller-only metadata entered a model payload")
                case_id = split + "/" + source_id + "__" + arm
                path = output_dir / split / (source_id + "__" + arm + "__D0_messages.json")
                raw = (json.dumps(messages, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
                visible = evidence_ids(context) | evidence_ids(inputs["public_numeric_fact_index"])
                if arm == "E":
                    visible |= evidence_ids(packet)
                planned.append({"case_id": case_id, "split": split, "assigned_source_id": source_id,
                                "arm": arm, "stage": "D0", "path": relative(path),
                                "sha256": sha(raw), "file_bytes": len(raw),
                                "canonical_messages_sha256": sha(content.encode("utf-8")),
                                "canonical_messages_utf8_bytes": len(content.encode("utf-8")),
                                "message_content_utf8_bytes": sum(len(m["content"].encode("utf-8")) for m in messages),
                                "visible_evidence_count": len(visible), "separate_generation_required": True,
                                "model_calls": 0, "common_block_hashes": hashes})
                pending.append((path, raw))
    if len(planned) != 8 or len({item["case_id"] for item in planned}) != 8 or len(late_request_hashes) != 1:
        raise ValueError("expected eight distinct cases and identical late-arm D0 requests")
    module = ROOT / "research/sector_v491_contract.py"
    preparer = Path(__file__).resolve()
    manifest = {
        "protocol_version": "4.9.1", "status": "offline_D0_preparation_passed_no_generation",
        "model_calls": 0, "pilot_model_calls": 0, "main_model_calls": 0,
        "not_an_execution_or_readiness_certificate": True,
        "manifest_visibility": "controller_metadata_never_model_input",
        "inputs": {"configuration": config_ref, "public_aggregate_never_sent": candidate_ref,
                   "common_context": context_ref, "prompt_contract": prompt_ref, "response_schema": schema_ref,
                   "contract_implementation": {"path": relative(module), "sha256": sha(module.read_bytes())},
                   "preparer_implementation": {"path": relative(preparer), "sha256": sha(preparer.read_bytes())}},
        "runtime_dependencies": {name: importlib.metadata.version(name) for name in ("numpy", "jsonschema")},
        "contract_version": CONTRACT_VERSION, "prepared_cases": planned,
        "checks": {"eight_unique_case_identifiers": True, "four_cases_per_split": True,
                   "all_common_blocks_identical": True, "all_late_D0_messages_identical": True,
                   "late_D0_has_no_source_identity_or_packet": True,
                   "unassigned_sources_absent": True, "controller_metadata_outside_messages": True,
                   "configuration_input_hashes_verified": True,
                   "standalone_and_aggregate_context_equal": True},
        "common_block_hashes": common_hashes,
        "counts": {"pilot_D0": 4, "main_D0": 4, "prepared_D0": 8, "prepared_F0": 0},
        "late_draft_execution_rule": "Identical inputs do not authorize sharing one generated draft. Every case requires its own isolated generation and log.",
        "F0_not_prepared_reason": "F0 depends on the exact actual D0 response and arithmetic calculated from that response. No synthetic draft or fabricated calculator feedback is stored.",
        "run_order": "This inventory order is not the frozen execution order.",
        "byte_measurement_scope": "UTF-8 bytes only; no token, memory, latency or completion claim.",
        "remaining_requirements": ["exact served-backend full-history token and memory check", "four-case pilot",
                                   "independent human source/meaning review", "frozen runtime settings and order"],
    }
    for path, raw in pending:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    manifest_path = output_dir / "preparation_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf-8", newline="\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = prepare(args.config, args.output_dir)
    print(json.dumps({"status": manifest["status"], "prepared_D0": len(manifest["prepared_cases"]),
                      "model_calls": 0, "manifest": relative(workspace_path(args.output_dir) / "preparation_manifest.json")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
