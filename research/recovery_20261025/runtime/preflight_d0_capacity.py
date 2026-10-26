"""Five exact v4.9.4 D0 render-only/native-token checks; no generation."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
OUTPUT = EVIDENCE / "preflight_d0_r2"
sys.path.insert(0, str(ROOT / "research"))
import sector_v494_runtime as runtime
from sector_v491_tokenizer import NativeTokenizer


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, obj):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def ref(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def get(endpoint):
    with urllib.request.urlopen("http://127.0.0.1:11435" + endpoint, timeout=15) as response:
        return json.load(response)


def host_snapshot():
    command = """$os = Get-CimInstance Win32_OperatingSystem
$listener = @(Get-NetTCPConnection -State Listen -LocalPort 11435 | Select-Object LocalAddress,LocalPort,OwningProcess)
$owner = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $listener[0].OwningProcess)
[ordered]@{recorded_at_utc=[DateTime]::UtcNow.ToString('o'); total_physical_memory_kib=$os.TotalVisibleMemorySize; free_physical_memory_kib=$os.FreePhysicalMemory; listeners=$listener; process=@{pid=$owner.ProcessId; executable=$owner.ExecutablePath; command_line=$owner.CommandLine; created_at_utc=$owner.CreationDate.ToUniversalTime().ToString('o')}} | ConvertTo-Json -Depth 6"""
    result = subprocess.run(["powershell", "-NoProfile", "-Command", command], check=True,
                            capture_output=True, text=True, encoding="utf-8")
    return json.loads(result.stdout)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    OUTPUT.mkdir()
    summary = {"receipt_version": "v494_render_only_capacity_preflight_1", "status": "RUNNING",
               "started_at_utc": now(), "generation_requests": 0, "render_requests_attempted": 0,
               "render_requests_completed": 0, "case_reviews": []}
    try:
        handoff_path = EVIDENCE / "handoff.json"
        handoff = json.loads(handoff_path.read_text(encoding="utf-8-sig"))
        old_path = ROOT / "research/v492_runtime_candidate_20261019.json"
        old = json.loads(old_path.read_text(encoding="utf-8-sig"))
        service_path = EVIDENCE / "service_ready/service_receipt.json"
        evidence = copy.deepcopy(old["backend_evidence"])
        evidence[0] = {"role": "cpu_service", "path": service_path.relative_to(ROOT).as_posix(),
                       "sha256": ref(service_path)["sha256"]}
        selected = runtime.candidate_runtime(backend="cpu", num_ctx=65536,
            tokenizer_config=handoff["tokenizer_config"], backend_evidence=evidence, num_thread=8)
        runtime.validate_runtime(selected)
        root_candidate_path = ROOT / "research/recovery_20261025/runtime_candidate.json"
        root_candidate = json.loads(root_candidate_path.read_text(encoding="utf-8-sig"))
        require(selected == root_candidate, "Coordinator candidate differs from independently reconstructed runtime")
        require(selected["options"] == old["options"], "Request options changed from historical CPU candidate")
        save(OUTPUT / "candidate_runtime.json", selected)
        before = {"host": host_snapshot(), "version": get("/api/version"), "ps": get("/api/ps")}
        require(before["host"]["process"]["pid"] == handoff["pid"], "Owned service PID differs")
        require(before["host"]["process"]["executable"] == handoff["executable"], "Owned executable differs")
        require(before["version"]["version"] == "0.35.1" and before["ps"]["models"] == [], "Service must be pinned and idle")
        save(OUTPUT / "before.json", before)
        loaded, cases = runtime.load_bundle()
        manifest, _ = runtime.prepare.read(runtime.MANIFEST)
        previous_loaded, previous_cases = runtime.inherited.load_bundle()
        previous_payload = runtime.contract.strict_json(previous_cases[0]["messages"][1]["content"])
        common_keys = ("common_context", "common_market", "public_numeric_fact_index", "response_schema")
        expected_common = {key: runtime.contract.canonical_json(previous_payload[key]) for key in common_keys}
        source_free_messages = []
        input_refs = [ref(handoff_path), ref(old_path), ref(root_candidate_path), ref(service_path), ref(runtime.MANIFEST),
                      ref(ROOT / "research/sector_v494_runtime.py"), ref(Path(__file__))]
        with NativeTokenizer(selected["tokenizer_config"]) as tokenizer:
            for case, prepared in zip(cases, manifest["prepared_cases"]):
                folder = OUTPUT / case["case_id"]
                folder.mkdir()
                payload = runtime.contract.strict_json(case["messages"][1]["content"])
                checks = {
                    "case_order_matches_prepared_manifest": case["case_id"] == prepared["case_id"],
                    "common_context_same_as_historical": runtime.contract.canonical_json(payload["common_context"]) == expected_common["common_context"],
                    "market_same_as_historical": runtime.contract.canonical_json(payload["common_market"]) == expected_common["common_market"],
                    "numeric_fact_index_same_as_historical": runtime.contract.canonical_json(payload["public_numeric_fact_index"]) == expected_common["public_numeric_fact_index"],
                    "output_schema_same_as_historical": runtime.contract.canonical_json(payload["response_schema"]) == expected_common["response_schema"],
                    "source_timing_matches_design": ("institution_document" in payload) == (case["arm"] == "E"),
                    "institution_packet_exact": payload.get("institution_document") == (case["assigned_packet"] if case["arm"] == "E" else None),
                }
                require(all(checks.values()), "Input boundary differs: " + case["case_id"])
                if case["arm"] != "E":
                    source_free_messages.append(case["messages"])
                body = runtime.request_body(selected, case["messages"], loaded["response_schema"])
                session = SimpleNamespace(target=folder, origin=handoff["origin"], timeout_seconds=60)
                summary["render_requests_attempted"] += 1
                runtime.prior.render_call(session, body, case["messages"][0]["content"])
                summary["render_requests_completed"] += 1
                rendered = (folder / "render_only/rendered_prompt.txt").read_bytes().decode("utf-8")
                token_receipt = tokenizer.count(rendered)
                capacity = runtime.check_token_capacity(token_receipt, rendered, selected)
                save(folder / "tokenizer_receipt.json", token_receipt)
                save(folder / "context_capacity.json", capacity)
                save(folder / "input_boundary.json", checks)
                summary["case_reviews"].append({"case_id": case["case_id"], "arm": case["arm"],
                    "status": "PASS", "input_boundary_checks": checks, "capacity": capacity,
                    "headroom_after_full_output_allowance": 65536 - capacity["total_required_tokens"],
                    "render_ref": ref(folder / "render_only/validation.json"),
                    "tokenizer_ref": ref(folder / "tokenizer_receipt.json"),
                    "request_ref": ref(folder / "render_only/request_body.bin"),
                    "response_ref": ref(folder / "render_only/response_body.bin")})
                input_refs.append(ref(ROOT / prepared["path"]))
        require(len(source_free_messages) == 3 and all(m == source_free_messages[0] for m in source_free_messages),
                "Two L plus C D0 messages must be identical")
        after = {"host": host_snapshot(), "version": get("/api/version"), "ps": get("/api/ps")}
        require(after["host"]["process"]["pid"] == handoff["pid"] and after["ps"]["models"] == [],
                "Owned PID or idle state changed during preflight")
        save(OUTPUT / "after.json", after)
        summary.update(status="PASS", completed_at_utc=now(), input_refs=input_refs,
            source_free_D0_inputs_identical=True, all_five_common_inputs_preserved=True,
            output_reserve_tokens=8192, context_tokens=65536, candidate_runtime_ref=ref(OUTPUT / "candidate_runtime.json"),
            prior_preflight_attempt={"ref": ref(EVIDENCE / "preflight_d0/summary.json"), "render_requests": 0,
                "generation_requests": 0, "cause": "Local checker compared absolute and relative receipt path spelling; corrected to coordinator relative-path representation, hashes/options unchanged."},
            smoke_evidence_scope="Prior October 19 exact large-input CPU smoke reused under byte-identical engine and settings; no new inference smoke performed. Initial pilot D0 will provide actual current-host generation evidence.",
            before_ref=ref(OUTPUT / "before.json"), after_ref=ref(OUTPUT / "after.json"),
            F0_capacity="Unknown until actual D0; runtime must render and count full actual D0 plus final instruction before F0 generation",
            review_axes={
                "errors": {"pass": True, "reason": "All five read-only responses passed exact render validation and byte-bound native token counting; every request retains all 8192 output tokens within context 65536. No model generation or repair occurred."},
                "consistency": {"pass": True, "reason": "Input manifest reconstruction, unchanged common blocks/schema/model/request options, exact E institution packet, source-free L/C identity, pinned service ownership and idle state all passed."},
                "paper_topic": {"pass": True, "reason": "Only the common instruction clarification distinguishes the prospective pilot. Institutional evidence timing E/L, C control, sector allocation task and original evidence/rubric remain; preflight introduces no substantive institution labels or scoring changes."}},
            limitations=["Render-only and token counts do not prove generation completes under current memory/load.",
                         "No future F0 input was guessed, truncated or shortened.",
                         "Topic-boundary preservation is not an outcome-level semantic-support verdict."])
    except BaseException as exc:
        summary.update(status="FAIL", completed_at_utc=now(), error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        save(OUTPUT / "summary.json", summary)
    print(json.dumps({"status": summary["status"], "generation_requests": 0,
        "render_requests": summary["render_requests_completed"], "summary": str(OUTPUT / "summary.json"),
        "tokens": {case["case_id"]: case["capacity"]["prompt_tokens"] for case in summary["case_reviews"]}}))


if __name__ == "__main__":
    main()
