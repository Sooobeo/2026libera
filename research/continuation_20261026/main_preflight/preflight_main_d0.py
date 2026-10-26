"""Five main-candidate D0 render-only checks; no generation or main execution."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "d0_capacity_r1"
CANDIDATE = ROOT / "data/sector_protocol/v495_main_candidate_20261025"
MANIFEST = CANDIDATE / "prepared/preparation_manifest.json"
RUNTIME = HERE.parent / "runtime_candidate.json"
ORIGIN = "http://127.0.0.1:11435"
CASES = ("fidelity_q3_2026__E", "fidelity_q3_2026__L", "ubs_july_2026__E", "ubs_july_2026__L", "common_market_only__C")
sys.path.insert(0, str(ROOT / "research"))
import sector_v494_runtime as runtime
from sector_v491_tokenizer import NativeTokenizer


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def ref(path):
    path = Path(path).resolve()
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def get(endpoint):
    with urllib.request.urlopen(ORIGIN + endpoint, timeout=15) as response:
        return json.load(response)


def host_snapshot():
    script = """$ErrorActionPreference='Stop'
$listeners=@(Get-NetTCPConnection -State Listen -LocalPort 11435 | Select-Object LocalAddress,LocalPort,OwningProcess)
if($listeners.Count -ne 1){throw 'One owned listener required'}
$owner=Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $listeners[0].OwningProcess)
[pscustomobject]@{at_utc=[DateTime]::UtcNow.ToString('o');listeners=$listeners;process=@{pid=$owner.ProcessId;executable=$owner.ExecutablePath;command_line=$owner.CommandLine;created_at_utc=$owner.CreationDate.ToUniversalTime().ToString('o')};binary_sha256=(Get-FileHash -LiteralPath $owner.ExecutablePath -Algorithm SHA256).Hash.ToLowerInvariant()}|ConvertTo-Json -Depth 5"""
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True,
        capture_output=True, text=True, encoding="utf-8", timeout=20,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return json.loads(result.stdout)


def snapshot(service):
    host = host_snapshot()
    pin = runtime.bench.observe(ORIGIN, runtime.base.MODEL)
    runtime.base.assert_pin(pin)
    state = get("/api/ps")
    process = host["process"]
    created = datetime.fromisoformat(process["created_at_utc"].replace("Z", "+00:00"))
    expected = datetime.fromisoformat(service["process_created_at_utc"].replace("Z", "+00:00"))
    require(process["pid"] == service["pid"] and Path(process["executable"]).resolve() == Path(service["executable"]).resolve(), "Service PID/path changed")
    require(abs((created - expected).total_seconds()) <= 0.001 and host["binary_sha256"] == service["executable_sha256"], "Service creation/binary identity changed")
    require(host["listeners"] == [{"LocalAddress": "127.0.0.1", "LocalPort": 11435, "OwningProcess": service["pid"]}], "Listener ownership differs")
    require(process["command_line"].rstrip().endswith("serve") and state.get("models") == [], "Service must remain idle")
    return {"at_utc": now(), "host": host, "pin": pin, "ps": state, "read_only_metadata_calls": True}


def main():
    OUTPUT.mkdir()
    summary = {"version": "v495_main_D0_render_only_preflight_1", "status": "RUNNING", "started_at_utc": now(),
        "generation_requests_sent": 0, "main_model_generation_calls": 0, "render_requests_attempted": 0,
        "render_requests_completed": 0, "case_reviews": [], "main_execution_authorized_by_preflight": False}
    selected, service = None, None
    try:
        selected = read(RUNTIME)
        runtime.validate_runtime(selected)
        service_reference = selected["backend_evidence"][0]
        service_path = runtime.prepare.workspace_path(service_reference["path"])
        require(ref(service_path)["sha256"] == service_reference["sha256"], "Service receipt changed")
        service = read(service_path)
        require(service["origin"] == ORIGIN and service["pid"] == 10920, "Only current root-owned service is assigned")
        manifest = read(MANIFEST)
        require(ref(MANIFEST)["sha256"] == "feb0b889331bf20fc04595ee1395b1c61f41b2663b9ba4c0207397d023ba06b1", "Prepared main manifest changed")
        require(manifest["case_order"] == list(CASES) and [c["case_id"] for c in manifest["prepared_cases"]] == list(CASES), "Exactly five main candidate cases required")
        refs = [ref(MANIFEST), ref(RUNTIME), ref(service_path), ref(Path(__file__))]
        for reference in manifest["artifact_refs"] + manifest["input_refs"]:
            path = runtime.prepare.workspace_path(reference["path"])
            require(ref(path)["sha256"] == reference["sha256"], "Pinned candidate input changed: " + str(path))
            refs.append(ref(path))
        public = read(CANDIDATE / "public_inputs.json")
        prompt = read(CANDIDATE / "prompt_contract.json")
        schema_path = ROOT / "data/sector_protocol/v491_design_20261019/response_schema.json"
        schema = read(schema_path)
        common = {"common_context": public["common_context"], "common_market": public["common_market"],
                  "public_numeric_fact_index": public["public_numeric_fact_index"], "response_schema": schema}
        require(public["common_market"]["cutoff_exclusive"] == "2026-07-17"
                and public["common_market"]["last_observation_date"] == "2026-07-16", "Main common market task cutoff changed")
        require(ref(CANDIDATE / "prompt_contract.json")["sha256"] == ref(ROOT / "data/sector_protocol/v494_design_20261025/prompt_contract.json")["sha256"], "Prompt differs from reviewed v494 wording")
        cases, source_free = [], []
        all_source_ids = ("fidelity_q2_2026", "ubs_june_2026", "fidelity_q3_2026", "ubs_july_2026")
        for prepared in manifest["prepared_cases"]:
            path = runtime.prepare.workspace_path(prepared["path"])
            messages = read(path)
            source, arm = prepared["source_id"], prepared["arm"]
            assigned = runtime.contract.select_public_inputs(public, source)
            rebuilt = runtime.contract.build_draft_messages(arm=arm, **assigned, common_context=public["common_context"],
                                                           prompt_contract=prompt, response_schema=schema)
            payload = runtime.contract.strict_json(messages[1]["content"])
            text = runtime.contract.canonical_json(messages)
            visible = runtime.contract.evidence_ids(public["common_context"]) | runtime.contract.evidence_ids(public["public_numeric_fact_index"])
            if arm == "E":
                visible |= runtime.contract.evidence_ids(assigned["assigned_packet"])
            checks = {"prepared_message_hash_matches": ref(path)["sha256"] == prepared["sha256"],
                "exact_reconstruction_matches": messages == rebuilt,
                "canonical_message_hash_matches": runtime.value_sha(messages) == prepared["canonical_messages_sha256"],
                "all_common_blocks_and_schema_preserved": all(runtime.value_sha(payload[key]) == runtime.value_sha(value) == manifest["common_block_hashes"][key] for key, value in common.items()),
                "source_timing_matches": ("institution_document" in payload) == (arm == "E"),
                "assigned_source_exact": payload.get("institution_document") == (assigned["assigned_packet"] if arm == "E" else None),
                "unassigned_source_ids_absent": not any(s in text for s in all_source_ids if s != source or arm != "E"),
                "controller_metadata_absent": not bool(set(payload) & {"case_id", "arm", "source_id", "split", "public_source_packets", "evaluator_only"}),
                "visible_evidence_ids_match_manifest": sorted(visible) == prepared["visible_evidence_ids"],
                "main_D0_identity": prepared["split"] == "main" and prepared["stage"] == "D0"}
            require(all(checks.values()), "Main input boundary failed: " + prepared["case_id"] + str(checks))
            cases.append((prepared, messages, checks))
            if arm in ("L", "C"):
                source_free.append(messages)
        require(len(source_free) == 3 and all(m == source_free[0] for m in source_free), "L/L/C must have identical source-free D0 messages")
        before = snapshot(service)
        save(OUTPUT / "before.json", before)
        save(OUTPUT / "runtime_used.json", selected)
        for filename in ("sector_v494_runtime.py", "sector_v48_transport.py", "sector_v491_tokenizer.py", "sector_v492_contract.py", "sector_v491_contract.py"):
            refs.append(ref(ROOT / "research" / filename))
        with NativeTokenizer(selected["tokenizer_config"]) as tokenizer:
            for prepared, messages, checks in cases:
                folder = OUTPUT / prepared["case_id"]
                folder.mkdir()
                save(folder / "input_boundary.json", checks)
                body = runtime.request_body(selected, messages, schema)
                session = SimpleNamespace(target=folder, origin=ORIGIN, timeout_seconds=60)
                summary["render_requests_attempted"] += 1
                runtime.prior.render_call(session, body, messages[0]["content"])
                summary["render_requests_completed"] += 1
                rendered = (folder / "render_only/rendered_prompt.txt").read_bytes().decode("utf-8")
                tokens = tokenizer.count(rendered)
                capacity = runtime.check_token_capacity(tokens, rendered, selected)
                save(folder / "tokenizer_receipt.json", tokens)
                save(folder / "context_capacity.json", capacity)
                summary["case_reviews"].append({"case_id": prepared["case_id"], "status": "PASS", "input_boundary_checks": checks,
                    "prepared_messages_ref": ref(ROOT / prepared["path"]), "capacity": capacity,
                    "headroom_after_full_output_allowance": 65536 - capacity["total_required_tokens"],
                    "request_ref": ref(folder / "render_only/request_body.bin"), "response_ref": ref(folder / "render_only/response_body.bin"),
                    "render_validation_ref": ref(folder / "render_only/validation.json"), "tokenizer_ref": ref(folder / "tokenizer_receipt.json")})
        after = snapshot(service)
        save(OUTPUT / "after.json", after)
        for reference in refs:
            require(ref(ROOT / reference["path"]) == reference, "Input changed during render-only preflight")
        summary.update(status="PASS", completed_at_utc=now(), input_refs=refs, before_ref=ref(OUTPUT / "before.json"),
            after_ref=ref(OUTPUT / "after.json"), source_free_L_L_C_identical=True, common_schema_source_boundaries_preserved=True,
            output_reserve_tokens=8192, context_tokens=65536, F0_capacity="PENDING: exact own actual completed D0 history must be rendered and counted before each future F0; no guessed F0 used here.",
            source_limits=manifest["source_limits"],
            review_axes={"errors": {"pass": True, "reason": "Five existing render validators report zero evaluation/content; exact native tokens plus8192 reserve fit65536. No generation request or response repair."},
                "consistency": {"pass": True, "reason": "Main manifest and prepared bytes, reconstructed E packets, common schema/market, L/L/C identity, pinned model/template/engine and before/after owned idle service all match."},
                "paper_topic": {"pass": True, "reason": "Prospective main E/L/C source timing and sector-allocation task are preserved. Two declared wording repairs remain bound, dates/availability caveats retained; no outcome or semantic-success claim."}},
            limitations=["This is input/render capacity verification, not main execution authorization, generation feasibility or semantic validation.",
                "F0 capacity depends on each actual future D0 and remains pending.", "October retrieval does not prove identical source bytes were available at the July task cutoff."])
    except BaseException as exc:
        summary.update(status="FAIL", completed_at_utc=now(), error_type=type(exc).__name__, error=str(exc))
        if service is not None:
            try:
                save(OUTPUT / "after_failure.json", snapshot(service))
            except BaseException as observation_error:
                summary["after_failure_observation_error"] = str(observation_error)
        raise
    finally:
        saved_results = list(OUTPUT.glob("*/render_only/result.json"))
        summary["unexpected_generation_evidence_observed"] = any(read(p).get("unexpected_generation_evidence") is True for p in saved_results)
        save(OUTPUT / "summary.json", summary)
    print(json.dumps({"status": summary["status"], "render_requests": summary["render_requests_completed"],
        "generation_requests_sent": 0, "tokens": {c["case_id"]: c["capacity"]["prompt_tokens"] for c in summary["case_reviews"]}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
