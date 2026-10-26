"""Read current on-disk pilot progress; never infer live execution from a stale label."""
from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "data/local_sector_runtime/v494_pilot_20261025"
REPORTS = ROOT / "research/recovery_20261025/new_pilot"
CASES = [s + "__" + a for s in ("fidelity_q2_2026", "ubs_june_2026") for a in ("E", "L")] + ["common_market_only__C"]


def read_if(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else None
    except (OSError, ValueError):
        return {"unreadable_or_write_in_progress": True}


def status():
    rows = []
    for case in CASES:
        for stage in ("D0", "F0"):
            folder = RUN / (case + "__" + stage)
            transport = read_if(folder / "transport_result.json")
            review = read_if(folder / "stage_review.json")
            stream = folder / "http_0001_generation/events.jsonl"
            row = {"case_id": case, "stage": stage,
                   "request_envelope_exists": (folder / "http_0001_generation/request.json").is_file(),
                   "response_exists": (folder / "http_0001_generation/response.json").is_file(),
                   "transport_status": (transport or {}).get("status"),
                   "instrument_review_pass": (review or {}).get("instrument_integrity_pass"),
                   "raw_sum": (review or {}).get("diagnostics", {}).get("raw_sum_decimal"),
                   "arithmetic_valid": (review or {}).get("diagnostics", {}).get("arithmetic_valid"),
                   "stream_bytes": stream.stat().st_size if stream.exists() else 0,
                   "last_stream_write_utc": datetime.fromtimestamp(stream.stat().st_mtime, timezone.utc).isoformat() if stream.exists() else None}
            rows.append(row)
    try:
        with urllib.request.urlopen("http://127.0.0.1:11435/api/ps", timeout=2) as response:
            service = json.load(response)
    except OSError as exc:
        service = {"unavailable": type(exc).__name__}
    return {"observed_at_utc": datetime.now(timezone.utc).isoformat(), "run_exists": RUN.exists(),
            "planned_cases": 5, "planned_stage_slots": 10,
            "attempted_request_envelopes": sum(r["request_envelope_exists"] for r in rows),
            "saved_responses": sum(r["response_exists"] for r in rows),
            "final_responses": sum(r["response_exists"] for r in rows if r["stage"] == "F0"),
            "stage_records": rows, "terminal_summary": read_if(RUN / "pilot_summary.json"),
            "coordinator_receipt": read_if(REPORTS / "terminal_receipt.json"),
            "service_observation": service,
            "scope": "Read-only file and service snapshot. Missing terminal record alone does not prove a running process; no semantic success inferred."}


if __name__ == "__main__":
    print(json.dumps(status(), ensure_ascii=False, indent=2, allow_nan=False))
