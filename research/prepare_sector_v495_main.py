"""Prepare a separately versioned, offline main-input candidate; no inference.

Only the two reviewed source-paraphrase fields change. The common evidence,
schema and actual v494 instruction strings stay fixed. No runtime, F0 response,
token preflight or main-run adapter is created by this preparer.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path

import sector_v492_contract as contract
from v49_compaction_review_20261019 import compact_packet, restore_packet

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/sector_protocol/v495_main_candidate_20261025"
REVIEW = ROOT / "research/recovery_20261025/main_candidate_preparation"
VERSION = "v495_main_offline_candidate_preparer_1"
SOURCES = ("fidelity_q3_2026", "ubs_july_2026")
CASE_ORDER = tuple(source + "__" + arm for source in SOURCES for arm in ("E", "L")) + ("common_market_only__C",)
PINS = {
    "data/sector_documents/packets/main/fidelity_q3_2026.json": "3f84c5d1e1302238fd270b41f1b9bcf86e3ae5c8c44a74f7a49a19941407d297",
    "data/sector_documents/packets/main/ubs_july_2026.json": "49f47f8c628b53231cdfb09fa90eabfa0a5d271fb6a439e75360bdb97db29d30",
    "data/sector_protocol/v491_design_20261019/public_compact_candidate.json": "afe810b2bfb69ae4bfa372e65fa587bc6253eecf8028d5fde39cf3ec395bcb8d",
    "data/sector_context/v491_20261019/common_context.json": "67d94bdee3d38854097970cdfb74f40e2557a11e22b016e9a68374e6f13cb96f",
    "data/sector_protocol/v491_design_20261019/response_schema.json": "944a232de9f4a1e9ae672b172196aa906077ee03c3f6bf2ab06ad032d6d0b147",
    "data/sector_protocol/v494_design_20261025/prompt_contract.json": "7d75828866825af1f7051a528defc92c88f2beac3f42a66f5d5223c4fb714362",
    "research/v492_evaluation_protocol_20261019_r2.json": "807def444cc36d4a702321401a52e653b3f9a304383911e13f3c0389183086f1",
    "research/recovery_20261025/main_readiness_source_review_20261025.json": "50572a99534574693a8e87180e3f0f158fa80f79a3aa0d11ad1f7b963c781605",
    "research/recovery_20261025/main_packet_precision_candidate.json": "d4fc6a832dfe3abd4a9e29ae696783e5f85e4d5395fefeffe1b9bd2858258422",
    "research/recovery_20261025/stage02_method_preparation_review.json": "f78183fd2bc0177f23713fd7bdd7d8174a84c96dfa2fb71bce23d98fdb495d3a",
    "research/recovery_20261025/allocation_finalization_amendment.json": "009f90b89a6185f1af9c63fd6be47d01f9662d959fd13b9938295f5943156031",
    "research/recovery_20261025/allocation_finalization_acceptance.json": "402ad49fc81c3732d1266a0449859c1a0ca2fe26150efc96c2d5900733c7066a",
    "research/recovery_20261025/allocation_finalization_acceptance_r2.json": "0232232baeb7e251aa0dee42bc9a1969f66615a1df4d303bccb67dd938b47d9e",
    "research/recovery_20261025/derived_final_allocation_policy_review_20261025.json": "7355b0de7466edac93187133ca2156a3cd31f2c852a0e0351193320ee0687c3d",
    "research/recovery_20261025/pilot_freeze.json": "8f8f95c4b90583e5bd97f2b80168c51aa9efec92a958b8235a9baecdfb7001cf",
    "research/finalize_sector_allocation.py": "54bf904de34dad83b1b504241f8a8b54158105fa9f740b1d2717f73ceaf048d3",
    "research/v49_compaction_review_20261019.py": "5e9f41215f2e96b13b8241e03be3cd8bd1b409b12712b5541e08e59917405850",
    "research/sector_v492_contract.py": "f77d1ddec9630a4c7edbf3928d298b7b05094345996ece1cf53d91fc40171a21",
    "research/sector_v491_contract.py": "de5bfab83726e6f9b8f93a4203296d8a5cc93630d9c4412df3532c0441d80397",
    "research/sector_engine.py": "507eb352fc3b8b61ad92be31e4697e48deb0e8cc233fae5e230aecb7a0c9649c",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return contract.canonical_json(value)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def reference(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("reference_outside_workspace")
    raw = path.read_bytes()
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(raw), "bytes": len(raw)}


def verify_pins(pins):
    refs = []
    for name, expected in pins.items():
        item = reference(ROOT / name)
        if item["sha256"] != expected:
            raise ValueError("input_pin_changed:" + name)
        refs.append(item)
    return refs


def load(name):
    return contract.strict_json((ROOT / name).read_text(encoding="utf-8-sig"))


def changed_paths(left, right, path=""):
    if type(left) is not type(right):
        return [path]
    if isinstance(left, dict):
        if set(left) != set(right):
            return [path]
        return [change for key in left for change in changed_paths(left[key], right[key], path + "/" + key)]
    if isinstance(left, list):
        if len(left) != len(right):
            return [path]
        return [change for i, value in enumerate(left) for change in changed_paths(value, right[i], path + "/" + str(i))]
    return [] if left == right else [path]


def frozen_refs():
    freeze = load("research/recovery_20261025/pilot_freeze.json")
    refs = freeze["code_refs"] + [freeze[name] for name in (
        "input_protocol_ref", "evaluation_protocol_ref", "source_review_ref", "method_review_ref",
        "prompt_contract_ref", "prepared_manifest_ref", "runtime_ref")]
    return verify_pins({r["path"]: r["sha256"] for r in refs})


def prepare():
    if OUTPUT.exists() or (REVIEW / "build_review.json").exists():
        raise FileExistsError("A new candidate and unused build review are required; no overwrite or resume")
    started = now()
    input_refs = verify_pins(PINS)
    protected_before = frozen_refs()
    aggregate = load("data/sector_protocol/v491_design_20261019/public_compact_candidate.json")
    context = load("data/sector_context/v491_20261019/common_context.json")
    schema = load("data/sector_protocol/v491_design_20261019/response_schema.json")
    prompt_path = ROOT / "data/sector_protocol/v494_design_20261025/prompt_contract.json"
    prompt = load(prompt_path)
    r2 = load("research/v492_evaluation_protocol_20261019_r2.json")
    precision = load("research/recovery_20261025/main_packet_precision_candidate.json")
    amendment = load("research/recovery_20261025/allocation_finalization_amendment.json")
    acceptance = load("research/recovery_20261025/allocation_finalization_acceptance_r2.json")
    if (acceptance.get("status") != "PASS" or not any(
            item.get("path") == "research/finalize_sector_allocation.py"
            and item.get("sha256") == PINS["research/finalize_sector_allocation.py"]
            for item in acceptance.get("refs", []))):
        raise ValueError("current_finalizer_acceptance_binding_required")
    if (r2["expected_cases_per_split"] != 5 or r2["expected_sector_rows_per_final_split"] != 55
            or r2["design"]["main_maximum_generation_calls"] != 10
            or r2["design"]["main_cells"] != ["Fidelity E", "Fidelity L", "UBS E", "UBS L", "common no-institution C"]):
        raise ValueError("reviewed_r2_five_case_design_required")
    if canonical(context) != canonical(aggregate["common_context"]):
        raise ValueError("common_context_binding_mismatch")
    if (context["operating_brief"]["decision_reference_date"] != "2026-07-17"
            or context["operating_brief"]["information_cutoff_exclusive"] != "2026-07-17"
            or aggregate["common_market"]["cutoff_exclusive"] != "2026-07-17"
            or aggregate["common_market"]["last_observation_date"] != "2026-07-16"):
        raise ValueError("reviewed_common_task_market_cutoff_changed")
    if prompt["protocol_version"] != "4.9.4":
        raise ValueError("exact_v494_prompt_required")
    changes = precision["changes"]
    if [c["source_id"] for c in changes] != list(SOURCES) or len(changes) != 2:
        raise ValueError("exact_two_reviewed_source_changes_required")
    pending, packet_checks, compact_packets = [], [], {}
    for change in changes:
        source = change["source_id"]
        name = change["packet_path"]
        if name != "data/sector_documents/packets/main/" + source + ".json" or PINS[name] != change["precondition_packet_sha256"]:
            raise ValueError("packet_change_precondition_mismatch")
        original = load(name)
        if changed_paths(original, restore_packet(aggregate["public_source_packets"][source])):
            raise ValueError("old_compact_packet_not_lossless:" + source)
        replacement = copy.deepcopy(original)
        pointer = change["affected_field"]["json_pointer"]
        expected_pointer = "/evidence_passages/7/text" if source == SOURCES[0] else "/evidence_passages/11/text"
        if pointer != expected_pointer:
            raise ValueError("unexpected_reviewed_change_pointer")
        index = int(pointer.split("/")[2])
        row = replacement["evidence_passages"][index]
        if row["evidence_id"] != change["affected_field"]["evidence_id"] or row["text"] != change["original_text"]:
            raise ValueError("reviewed_text_or_evidence_identity_mismatch")
        row["text"] = change["replacement_text"]
        if changed_paths(original, replacement) != [pointer]:
            raise ValueError("packet_changes_exceed_one_reviewed_text_field")
        if (replacement["source_id"] != source or replacement["split"] != "main"
                or contract.evidence_ids(original) != contract.evidence_ids(replacement)):
            raise ValueError("packet_identity_split_or_evidence_set_changed")
        compact = compact_packet(replacement)
        if changed_paths(replacement, restore_packet(compact)):
            raise ValueError("new_packet_compaction_roundtrip_failed")
        compact_packets[source] = compact
        packet_path = OUTPUT / "packets/main" / (source + ".json")
        pending.append((packet_path, encoded(replacement)))
        packet_checks.append({"source_id": source, "original_ref": reference(ROOT / name),
            "changed_paths": [pointer], "evidence_id": row["evidence_id"],
            "before": change["original_text"], "after": row["text"],
            "all_other_values_preserved": True, "lossless_compaction_roundtrip": True,
            "source_review_erratum_applied": source == SOURCES[1]})
    fidelity_dates = compact_packets[SOURCES[0]]["dates"]
    if fidelity_dates["sector_view_as_of_raw"] != "6/31/26" or fidelity_dates["sector_view_as_of_normalized"] is not None:
        raise ValueError("unresolved_printed_fidelity_date_must_be_preserved")
    public = {"status": "controller_only_offline_main_candidate_never_sent_whole",
        "common_market": copy.deepcopy(aggregate["common_market"]),
        "public_numeric_fact_index": copy.deepcopy(aggregate["public_numeric_fact_index"]),
        "common_context": copy.deepcopy(context), "public_source_packets": compact_packets,
        "meaning": "Allowlist one assigned main packet, or none for C. This aggregate and metadata never enter model messages."}
    pending.append((OUTPUT / "public_inputs.json", encoded(public)))
    pending.append((OUTPUT / "prompt_contract.json", prompt_path.read_bytes()))
    planned, no_source, common_hashes = [], [], None
    all_original_source_ids = tuple(aggregate["public_source_packets"])
    for case_id in CASE_ORDER:
        source, arm = (None, "C") if case_id == "common_market_only__C" else case_id.rsplit("__", 1)
        selected = contract.select_public_inputs(public, source)
        messages = contract.build_draft_messages(arm=arm, **selected, common_context=context,
                                                prompt_contract=prompt, response_schema=schema)
        payload = contract.strict_json(messages[1]["content"])
        blocks = {name: digest(canonical(payload[name]).encode("utf-8")) for name in
                  ("common_context", "common_market", "public_numeric_fact_index", "response_schema")}
        if common_hashes is None:
            common_hashes = blocks
        elif common_hashes != blocks:
            raise ValueError("common_blocks_differ_between_main_cases")
        for name, expected in (("common_context", context), ("common_market", aggregate["common_market"]),
                               ("public_numeric_fact_index", aggregate["public_numeric_fact_index"]), ("response_schema", schema)):
            if canonical(payload[name]) != canonical(expected):
                raise ValueError("common_evidence_or_schema_changed:" + name)
        content = canonical(messages)
        if arm in ("L", "C"):
            if "institution_document" in payload or any(s in content for s in all_original_source_ids):
                raise ValueError("institution_identity_leaked_into_source_free_D0")
            no_source.append(messages)
        elif payload.get("institution_document") != compact_packets[source]:
            raise ValueError("early_main_packet_binding_mismatch")
        if any(s in content for s in all_original_source_ids if s != source):
            raise ValueError("unassigned_source_identity_leaked_into_D0")
        if set(payload) & {"case_id", "arm", "source_id", "split", "public_source_packets", "evaluator_only"}:
            raise ValueError("controller_metadata_leaked_into_D0")
        visible = contract.evidence_ids(context) | contract.evidence_ids(public["public_numeric_fact_index"])
        if arm == "E":
            visible |= contract.evidence_ids(compact_packets[source])
        target = OUTPUT / "prepared" / (case_id + "__D0_messages.json")
        raw = encoded(messages)
        pending.append((target, raw))
        planned.append({"case_id": case_id, "split": "main", "source_id": source, "arm": arm, "stage": "D0",
            "path": target.relative_to(ROOT).as_posix(), "sha256": digest(raw), "file_bytes": len(raw),
            "canonical_messages_sha256": digest(content.encode("utf-8")), "common_block_hashes": blocks,
            "visible_evidence_ids": sorted(visible), "separate_generation_required": True,
            "model_calls": 0, "response_not_generated": True})
    if len(no_source) != 3 or any(messages != no_source[0] for messages in no_source):
        raise ValueError("three_independent_source_free_main_D0_inputs_must_be_identical")
    if [item["case_id"] for item in planned] != list(CASE_ORDER) or len(pending) != 9:
        raise ValueError("five_case_main_input_inventory_mismatch")
    source_limits = {
        "task_market_cutoff_exclusive": "2026-07-17", "price_last_observation": "2026-07-16",
        "task_scope": "Retrospective documentary task, not a point-in-time trading replay.",
        "source_availability": "Publication/view metadata is retained as reviewed. October retrieval and pinned caches do not independently prove historical July availability of identical bytes or vendor vintages.",
        "fidelity": "Use the pinned Q3 cache, not refreshed mutable Q4 URL metadata; invalid printed 6/31/26 stays raw with null normalized date.",
        "ubs": "The review addendum supersedes any earlier company-subset inference: some AI exposure is a degree qualifier, not an identified company subset.",
        "common_benchmark": "Comparison-only reported99.9% benchmark normalization is unchanged and separate from model-output finalization.",
    }
    finalizer_binding = {
        "scope": "Bind adopted exact math to prospective main inputs; do not execute pilot-only run finalizer on main IDs.",
        "pure_implementation_ref": reference(ROOT / "research/finalize_sector_allocation.py"),
        "pure_entry_point": "finalize_content", "rule": copy.deepcopy(amendment["rule"]),
        "same_rule_all_main_conditions": True, "integer_units": 10000,
        "raw_r2_endpoint_and_errors_retained": True, "derived_allocation_labeled_separately": True,
        "historical_acceptance": "allocation_finalization_acceptance.json binds117301...; it is not acceptance of current54bf... artifact guards.",
        "current_implementation_acceptance_ref": reference(ROOT / "research/recovery_20261025/allocation_finalization_acceptance_r2.json"),
        "current_implementation_acceptance": "PASS for current54bf implementation:47 pure/artifact tests and completed-stage/terminal-pilot integration; not a main adapter validation",
        "main_artifact_adapter": "not_prepared; requires separately versioned manifest-bound main adapter before any main run",
        "model_explanations_or_citations_rewritten": False,
    }
    if verify_pins(PINS) != input_refs or frozen_refs() != protected_before:
        raise ValueError("protected_input_changed_during_preparation")
    implementation = reference(Path(__file__))
    manifest = {"version": VERSION, "protocol_version": "4.9.5-main-candidate", "created_at_utc": now(),
        "status": "offline_main_candidate_prepared_not_runtime_ready", "source_prompt_version": "4.9.4",
        "input_protocol_version": "4.9.1", "evaluation_protocol_version": "4.9.2-r2",
        "model_calls": 0, "main_model_calls": 0, "pilot_model_calls": 0,
        "main_execution_allowed": False, "runtime_prepared": False, "token_preflight_performed": False,
        "prepared_F0": 0, "synthetic_drafts_created": 0, "input_refs": input_refs,
        "preparer_ref": implementation, "runtime_dependencies": {name: importlib.metadata.version(name) for name in ("numpy", "jsonschema")},
        "case_order": list(CASE_ORDER), "prepared_cases": planned, "packet_change_checks": packet_checks,
        "denominators": {"planned_cases": 5, "planned_final_sector_rows": 55, "source_conditioned_final_rows": 44,
            "no_source_control_final_rows": 11, "planned_stage_slots": 10, "maximum_generation_requests": 10,
            "shared_C_count": 1, "unavailable_outcomes_retained": True, "pilot_outputs_counted_as_main": False},
        "source_timing": "E assigned main packet at D0 and F0; L first at F0; C never receives institution packet. Every case retains its own actual raw D0 and unchanged calculator feedback.",
        "F0_construction": "Only after actual own D0 using reviewed conditional F0 instruction; no fabricated final history or feedback prepared.",
        "checks": {"exactly_two_reviewed_packet_text_changes": True, "lossless_packet_roundtrips": True,
            "common_evidence_and_schema_unchanged": True, "same_v494_prompt_bytes": True,
            "five_unique_cases": True, "three_L_L_C_D0_messages_identical": True,
            "no_unassigned_source_or_controller_metadata_leak": True, "frozen_pilot_refs_unchanged": True},
        "common_block_hashes": common_hashes, "source_limits": source_limits,
        "allocation_finalizer": finalizer_binding,
        "development_disclosure": "Held-out source documents are preselected but source packets are researcher-prepared. Two source-wording repairs and the previously developed v494 prompt are declared before any main generation. Deterministic finalization was adopted during development; pilot outcomes are not main evidence.",
        "pending_before_any_main_generation": ["independent review of this candidate", "future separately scheduled native-token render-only D0 capacity checks; not performed by this preparation", "separately reviewed main runtime, no-retry order and manifest-bound finalizer adapter", "prospective main freeze binding all exact inputs and code"],
        "artifact_refs": [{"path": p.relative_to(ROOT).as_posix(), "sha256": digest(raw), "bytes": len(raw)} for p, raw in pending],
    }
    pending.append((OUTPUT / "prepared/preparation_manifest.json", encoded(manifest)))
    OUTPUT.mkdir(parents=True, exist_ok=False)
    for path, raw in pending:
        if not path.resolve().is_relative_to(OUTPUT):
            raise ValueError("output_path_escaped_dedicated_candidate")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
    actual_refs = [reference(path) for path, raw in pending]
    if any(ref["sha256"] != digest(raw) for ref, (_, raw) in zip(actual_refs, pending)):
        raise ValueError("written_artifact_hash_mismatch")
    if verify_pins(PINS) != input_refs or frozen_refs() != protected_before or reference(Path(__file__)) != implementation:
        raise ValueError("protected_input_or_preparer_changed_while_writing")
    review = {"version": "v495_main_candidate_build_review_1", "status": "PASS_OFFLINE_BUILD_CHECKS_INDEPENDENT_REVIEW_PENDING",
        "started_at_utc": started, "completed_at_utc": now(), "preparer_ref": implementation,
        "input_refs": input_refs, "output_refs": actual_refs, "frozen_pilot_refs_verified": protected_before,
        "prior_failed_attempt_refs": [reference(path) for path in sorted(REVIEW.glob("attempt*.json"))],
        "review_axes": {
            "errors": {"pass": True, "evidence": "Exact source precondition hashes/text/IDs and two changed JSON paths checked; compaction roundtrips, schema construction, output hashes and all frozen pilot refs verified before/after."},
            "consistency": {"pass": True, "evidence": "Five r2 main cases, common blocks/schema and v494 prompt bytes preserved; L/L/C D0 identical and separately declared, assigned-source visibility checked, finalizer math and current code hash explicitly distinguished from prior acceptance."},
            "paper_topic": {"pass": True, "evidence": "E/L source timing, one common C, raw model diagnostics and evidence-to-allocation interpretation remain separate from deterministic100% arithmetic. Source conditions/uncertainty are restored without new ratings, institutional target weights, gold, numeric constraints or performance claims."}},
        "packet_changes": packet_checks, "source_limits": source_limits,
        "checks_executed": [str(len(PINS)) + " pinned input/source/code hashes", str(len(protected_before)) + " frozen pilot reference hashes before and after", "two exact one-field packet diffs", "two old and new lossless packet roundtrips", "five message constructions using existing schema-validating contract", "five common-block equivalence checks", "three source-free message equality checks", "source/controller visibility checks", "exclusive new output writes and byte-hash verification"],
        "model_calls": 0, "network_calls": 0, "tokenizer_or_service_calls": 0,
        "new_runtime_or_process_changes": 0, "F0_inputs_created": 0, "source_or_frozen_files_modified": False,
        "independent_review_completed": False, "source_PDFs_reread_by_this_builder": False,
        "limitations": manifest["pending_before_any_main_generation"] + ["Build checks are not semantic validation, main-run feasibility certification or source-availability proof. Current source review plus precision addendum remain the evidence basis."]}
    REVIEW.mkdir(parents=True, exist_ok=True)
    with (REVIEW / "build_review.json").open("xb") as stream:
        stream.write(encoded(review))
    return {"status": manifest["status"], "prepared_cases": len(planned), "model_calls": 0,
            "manifest": reference(OUTPUT / "prepared/preparation_manifest.json"),
            "review": reference(REVIEW / "build_review.json")}


if __name__ == "__main__":
    print(json.dumps(prepare(), ensure_ascii=False, allow_nan=False))
