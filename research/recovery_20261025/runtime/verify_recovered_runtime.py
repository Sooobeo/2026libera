"""Verify recovered bytes, model and exact vocabulary tokenizer; never generate."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
PORTABLE = ROOT / "tmp/libera_ollama0351_20261025/portable"
MODEL_ROOT = Path.home() / ".ollama/models"
ORIGIN = "http://127.0.0.1:11435"
sys.path.insert(0, str(ROOT / "research"))
from sector_v491_tokenizer import NativeTokenizer, MODEL_DIGEST, GGUF_SHA256, TEMPLATE_SHA256


def sha(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def api(endpoint: str, body: dict | None = None):
    request = urllib.request.Request(
        ORIGIN + endpoint,
        data=None if body is None else json.dumps(body).encode(),
        headers={} if body is None else {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    output = EVIDENCE / "verification_receipt.json"
    if output.exists():
        raise RuntimeError("Verification receipt already exists; preserve it")
    report = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "running", "generation_requests": 0,
        "purpose": "Restore byte-identical original runtime without changing research treatments or outcomes",
        "origin": ORIGIN,
        "limitations": [
            "Read-only API checks and vocabulary-only tokenization do not demonstrate inference placement or completion.",
            "Caller must preserve model, request options, source material, schema, output allowance and research design.",
        ],
    }
    try:
        binary = PORTABLE / "ollama.exe"
        expected_cli = "3cc17c238b081adf2bd3a206e52a063b637af1bf283d95b4ffd73a2bdec8b027"
        assert sha(binary) == expected_cli, "Recovered CLI pin differs"
        report["binary"] = {"path": str(binary), "sha256": expected_cli}
        version = api("/api/version")
        assert version["version"] == "0.35.1", "Live engine version differs"
        report["version"] = version
        tags = api("/api/tags")
        matches = [model for model in tags["models"] if model["name"] == "qwen3.5:4b-q4_K_M"]
        assert len(matches) == 1 and matches[0]["digest"] == MODEL_DIGEST, "Live model digest differs"
        report["model"] = matches[0]
        manifest = MODEL_ROOT / "manifests/registry.ollama.ai/library/qwen3.5/4b-q4_K_M"
        assert sha(manifest) == MODEL_DIGEST, "Manifest bytes differ"
        report["manifest"] = {"path": str(manifest), "sha256": sha(manifest)}
        metadata = json.loads(manifest.read_bytes())
        blobs = []
        for layer in [metadata["config"], *metadata["layers"]]:
            blob = MODEL_ROOT / "blobs" / layer["digest"].replace(":", "-", 1)
            digest = sha(blob)
            assert digest == layer["digest"].split(":", 1)[1], "Model layer digest differs"
            assert blob.stat().st_size == layer["size"], "Model layer size differs"
            blobs.append({"path": str(blob), "media_type": layer["mediaType"], "sha256": digest, "bytes": layer["size"]})
        report["model_blobs"] = blobs
        show = api("/api/show", {"model": "qwen3.5:4b-q4_K_M"})
        template_sha = hashlib.sha256(show["template"].encode()).hexdigest()
        assert template_sha == TEMPLATE_SHA256, "Live template differs"
        report["template_sha256"] = template_sha
        report["model_show_capabilities"] = show.get("capabilities", [])
        config = {"library_dir": str(PORTABLE / "lib/ollama"),
                  "gguf_path": str(MODEL_ROOT / "blobs" / ("sha256-" + GGUF_SHA256))}
        report["tokenizer_config"] = config
        with NativeTokenizer(config) as tokenizer:
            assert tokenizer.tokens("<|im_start|>") == [248045]
            assert tokenizer.tokens("<|im_end|>") == [248046]
            assert tokenizer.tokens("") == []
            assert not tokenizer.add_bos and not tokenizer.add_eos
            sample = '<|im_start|>user\n한국 시장 배분과 인용 정합성\r\n<|im_end|>'
            first = tokenizer.count(sample)
            assert first == tokenizer.count(sample), "Repeated tokenization differs"
            assert first["rendered_utf8_sha256"] == hashlib.sha256(sample.encode()).hexdigest()
            assert len(tokenizer.tokens("hello\0 world after null")) > len(tokenizer.tokens("hello"))
            report["tokenizer_sample"] = first
            historical = ROOT / "data/local_sector_runtime/pilot_v48_guarded_20261019/fidelity_q2_2026__R1/stage1"
            if not historical.exists():
                raise RuntimeError("Historical actual-runtime counter evidence missing")
            rendered_path = historical / "render_only/rendered_prompt.txt"
            provider_path = historical / "http_0001_generation/result.json"
            rendered = rendered_path.read_bytes().decode("utf-8")
            provider = json.loads(provider_path.read_text(encoding="utf-8"))
            counted = tokenizer.count(rendered)
            assert counted["token_count"] == provider["metrics"]["prompt_eval_count"], "Historical provider counter differs"
            report["historical_tokenizer_crosscheck"] = {
                "rendered_prompt": str(rendered_path), "rendered_prompt_sha256": sha(rendered_path),
                "provider_result": str(provider_path), "provider_result_sha256": sha(provider_path),
                "count": counted["token_count"], "provider_prompt_eval_count": provider["metrics"]["prompt_eval_count"],
                "equal": True,
            }
        residency = api("/api/ps")
        assert residency["models"] == [], "Unexpected resident model during read-only verification"
        report["resident_models"] = []
        report["cpu_library_hashes"] = {
            file.name: sha(file) for file in sorted((PORTABLE / "lib/ollama").glob("*.dll"))
        }
        report["status"] = "passed_read_only_no_inference"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
        raise
    finally:
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "receipt": str(output),
                      "historical_token_count": report["historical_tokenizer_crosscheck"]["count"],
                      "generation_requests": 0}))


if __name__ == "__main__":
    main()
