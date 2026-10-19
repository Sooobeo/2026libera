"""Render-only D0 sizing and independent archived-counter cross-checks.

No inference/generation requests. Optional requests target a caller-owned local
Ollama service; it may load the model to render, so root coordinates that service.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.request

from sector_v491_tokenizer import NativeTokenizer, sha_file
from sector_v48_transport import validate_render
from local_sector_single_case import OPTIONS, MODEL

ROOT = Path(__file__).resolve().parent.parent


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def audit(origin, target):
    target = target.resolve()
    if target.exists():
        raise FileExistsError("Use a new evidence directory")
    target.mkdir(parents=True)
    save(target / "invocation.json", {"utc": datetime.now(timezone.utc).isoformat(),
         "purpose": "render_only_and_exact_vocabulary_tokenization",
         "origin": origin, "generation_requests": 0,
         "context_tokens": 65536, "output_reserve": 8192,
         "scope": "D0 only; no invented bound for unseen F0 history"})
    manifest = load(ROOT / "data/sector_protocol/v491_design_20261019/prepared/preparation_manifest.json")
    cases, crosschecks = [], []
    with NativeTokenizer() as tokenizer:
        for case in manifest["prepared_cases"]:
            path = ROOT / case["path"]
            if sha_file(path) != case["sha256"]:
                raise ValueError("Prepared D0 hash mismatch")
            messages = load(path)
            folder = target / case["case_id"]
            body = {"model": MODEL, "messages": messages, "stream": False,
                    "think": False, "truncate": False, "shift": False,
                    "keep_alive": 0, "options": OPTIONS | {"num_gpu": 0},
                    "_debug_render_only": True}
            save(folder / "request.json", {"path": "/api/chat", "body": body,
                 "purpose": "render_only_not_generation"})
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            started = time.monotonic()
            request = urllib.request.Request(origin + "/api/chat", data=payload,
                      headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read()
            (folder / "response_body.bin").write_bytes(raw)
            rendered_response = json.loads(raw)
            save(folder / "response.json", rendered_response)
            if rendered_response.get("eval_count", 0) or rendered_response.get("message", {}).get("content"):
                raise ValueError("Unexpected generation in debug render-only response")
            validation = validate_render(rendered_response, messages, messages[0]["content"])
            save(folder / "render_validation.json", validation)
            rendered = rendered_response["_debug_info"]["rendered_template"]
            (folder / "rendered_prompt.txt").write_bytes(rendered.encode("utf-8"))
            count = tokenizer.count(rendered)
            save(folder / "token_count.json", count)
            cases.append({"case_id": case["case_id"], "stage": "D0",
                "input_file_sha256": case["sha256"], **count,
                "output_reserve": 8192, "context_tokens": 65536,
                "required_tokens": count["token_count"] + 8192,
                "fits_with_output_reserve": count["token_count"] + 8192 <= 65536,
                "renderer_validation_pass": True,
                "render_wall_seconds": time.monotonic() - started,
                "generation_requests": 0})
        old = ROOT / "data/local_sector_runtime/pilot_v48_guarded_20261019/fidelity_q2_2026__R1"
        for stage in ["stage1", "stage2", "stage3", "C0", "C1"]:
            rendered = old / stage / "render_only/rendered_prompt.txt"
            result = old / stage / "http_0001_generation/result.json"
            if not rendered.is_file() or not result.is_file():
                continue
            observed = load(result).get("metrics", {}).get("prompt_eval_count")
            if observed is None:
                continue
            count = tokenizer.count(rendered.read_bytes().decode("utf-8"))
            crosschecks.append({"stage": stage,
                "archived_render_sha256": sha_file(rendered),
                "archived_result_sha256": sha_file(result),
                "native_exact_count": count["token_count"],
                "archived_provider_prompt_eval_count": observed,
                "matches": count["token_count"] == observed,
                "no_replay": True})
    result = {"status": "pass" if all(c["fits_with_output_reserve"] for c in cases)
              and all(c["matches"] for c in crosschecks) else "requires_review",
              "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "generation_requests": 0, "render_only_requests": len(cases),
              "cases": cases, "archived_counter_crosschecks": crosschecks,
              "exact_D0_token_range": [min(c["token_count"] for c in cases),
                                        max(c["token_count"] for c in cases)],
              "F0_capacity_universally_proven": False,
              "F0_policy": "Render the actual retained D0 and computed feedback, exact-tokenize, then require tokens+8192<=num_ctx before the single final generation. Stop and record failure if insufficient; do not truncate.",
              "limitations": ["D0 fit is not full two-stage runtime feasibility.",
                "Unbounded strings/arrays and feedback echoes preclude a claimed generic F0 bound from these D0 counts.",
                "Exact vocabulary tokenization does not measure inference RAM, latency or semantic quality.",
                "Independent native tokenizer uses same binary/GGUF as installed runner, not an independent algorithm implementation."]}
    save(target / "summary.json", result)
    files = [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha_file(p), "bytes": p.stat().st_size}
             for p in sorted(target.rglob("*")) if p.is_file()]
    save(target / "manifest.json", {"files": files})
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--origin", default="http://127.0.0.1:11435")
    p.add_argument("--target", type=Path, required=True)
    args = p.parse_args()
    if not args.origin.startswith("http://127.0.0.1:"):
        raise ValueError("Only loopback caller-owned service allowed")
    result = audit(args.origin, args.target)
    print(json.dumps({k: result[k] for k in ["status", "render_only_requests", "generation_requests",
         "exact_D0_token_range", "archived_counter_crosschecks"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
