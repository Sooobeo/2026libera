"""One authorized, isolated GPU engineering probe; no campaign or retries."""
from __future__ import annotations

import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"

from research.v63.exact_tokenizer import NativeTokenizer
from research.v63.ollama_transport import OllamaTransport, packed

MODEL = "qwen3:1.7b"
MODEL_SHA = "8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7"
RUN_ID = "00b7955a968c13547e6fcc857485a62c6d27a6ecc008c3c3cee4f32d981e5a0d"
ORIGIN = "http://127.0.0.1:11436"
MIN_AVAILABLE = 2 * 1024**3
STAGING = ROOT / "tmp/v63_vulkan_probe_20261027"
PINS = {
    "concrt140.dll": "efa54bfeb12377e0bad3bdd1f7ebbcc59187e15734f14d330793798616c440e0",
    "ggml-vulkan.dll": "fbb05873c1c3ee119bb2db1c4f6b574700434d03e47a4cfadf117af17c1f2396",
    "msvcp140.dll": "9c640e0bf7e58b95cf3a6a035f4d13f78018774f00f54adbcabc75e611a6c6b8",
    "msvcp140_1.dll": "26c8f6dba94a988b8fab3db935ba77351be1d84888444de0fb9f6e3793dcad09",
    "msvcp140_2.dll": "9ccb42c714f9bf2b1bc3959f49435666a582445f2cda7f87e933f4a9e6a9595a",
    "msvcp140_atomic_wait.dll": "218d06e4eb3577390e7def2baa4754274c032c68e0bf68e431a439f4cde35653",
    "msvcp140_codecvt_ids.dll": "ab7da0a11a87e6ef9b891e959772b9a42408ca446d5f734b036966ac1526df2f",
    "vccorlib140.dll": "5252a8f26a88f60b3ed3abfd2b9d4c25dde6a1862ac210f5e8b2e4b451f0b02a",
    "vcruntime140.dll": "6cfea5ab8ba8976e90af22dd9fd0cd4ac6d92c60671c17dc4a81653e182b591e",
    "vcruntime140_1.dll": "7c78d78e413a46db5fdbb89dbe863696cc386e45f33d85ab697d3f7e26e8c667",
    "vcruntime140_threads.dll": "97f36ae9c12e0f4550a443c8b5bc1991b874d47f28ca915210e1f1d0ad39adb8",
}
MICROSOFT = {"msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def memory():
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    ("total_phys", ctypes.c_ulonglong), ("available_phys", ctypes.c_ulonglong),
                    ("total_page", ctypes.c_ulonglong), ("available_page", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong)]
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return {"utc": now(), "physical_total_bytes": status.total_phys,
            "physical_available_bytes": status.available_phys, "memory_load_percent": status.load}


def read_only_api(origin, path):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(origin + path, timeout=5) as response:
        return json.loads(response.read())


def stage(out):
    STAGING.mkdir(exist_ok=False)
    candidate = load(ROOT / "data/v63_20261027/continuation/deployment/local_windows/candidate_004/runtime_candidate.json")
    binaries = []
    for entry in candidate["execution_environment"]["binary_artifacts"]:
        source = ROOT / entry["path"]
        relative = Path(entry["path"]).relative_to("tmp/v63_local_ollama")
        binaries.append((source, STAGING / relative, entry["sha256"], "Ollama"))
    for name, expected in PINS.items():
        source = ROOT / "tmp/v63_local_ollama/non_cpu_assets/lib/ollama/vulkan" / name
        binaries.append((source, STAGING / "portable/lib/ollama/vulkan" / name, expected,
                         "Microsoft Windows" if name in MICROSOFT else "Ollama"))
    records = []
    for source, target, expected, publisher in binaries:
        assert sha(source) == expected, source
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(source, target)
        records.append({"source": str(source), "path": str(target), "sha256": expected,
                        "expected_publisher_substring": publisher, "bytes": target.stat().st_size})
    write(out / "binary_manifest.json", records)
    signature_script = out / "verify_signatures.ps1"
    signature_script.write_text("""param([string]$Manifest,[string]$Output)
$ErrorActionPreference='Stop'
$entries=Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
$checks=foreach($entry in $entries){
  $signature=Get-AuthenticodeSignature -LiteralPath $entry.path
  $hash=(Get-FileHash -LiteralPath $entry.path -Algorithm SHA256).Hash.ToLowerInvariant()
  $passed=($signature.Status -eq 'Valid' -and $signature.SignerCertificate.Subject -like ('*'+$entry.expected_publisher_substring+'*') -and $hash -eq $entry.sha256)
  [ordered]@{path=$entry.path;sha256=$hash;signature=$signature.Status.ToString();publisher=$signature.SignerCertificate.Subject;passed=$passed}
}
$checks | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $Output -Encoding UTF8
if(@($checks|Where-Object{-not $_.passed}).Count -gt 0){throw 'Pinned file hash/publisher verification failed'}
""", encoding="utf-8-sig")
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(signature_script),
                    "-Manifest", str(out / "binary_manifest.json"), "-Output", str(out / "binary_signatures.json")],
                   check=True, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
    model_source = ROOT / "tmp/v63_local_ollama/models"
    model_target = STAGING / "models"
    manifest_relative = Path("manifests/registry.ollama.ai/library/qwen3/1.7b")
    assert sha(model_source / manifest_relative) == MODEL_SHA
    (model_target / manifest_relative).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(model_source / manifest_relative, model_target / manifest_relative)
    manifest = load(model_source / manifest_relative)
    (model_target / "blobs").mkdir()
    blobs = []
    for entry in [manifest["config"], *manifest["layers"]]:
        name = entry["digest"].replace(":", "-")
        source = model_source / "blobs" / name
        assert sha(source) == entry["digest"].removeprefix("sha256:")
        target = model_target / "blobs" / name
        os.link(source, target)
        blobs.append({"source": str(source), "path": str(target), "bytes": target.stat().st_size, "sha256": sha(target)})
    write(out / "model_manifest.json", {"digest": MODEL_SHA, "blobs": blobs, "shared_source_mutations": 0})
    return candidate


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = ROOT / "data/v63_20261027/runtime/local_windows" / ("vulkan_probe_" + stamp)
    out.mkdir(parents=True, exist_ok=False)
    summary = {"started_at_utc": now(), "evidence_directory": str(out), "engineering_only": True,
               "experimental_generation_requests": 0, "engineering_generation_requests": 0,
               "max_generation_requests": 1, "max_output_tokens": 128, "timeout_seconds": 600,
               "retries": 0, "model": MODEL, "model_sha256": MODEL_SHA, "origin": ORIGIN,
               "selection_criteria": "speed, complete prompt coverage, memory, provider token agreement only",
               "investment_content_evaluated_for_selection": False, "models_unloaded_at_end": None}
    write(out / "started.json", summary)
    (out / "probe_script.py").write_bytes(Path(__file__).read_bytes())
    server = None
    transport = None
    tokenizer = None
    samples = []
    stop = threading.Event()
    monitor = None
    service_log = None
    try:
        with socket.socket() as check:
            assert check.connect_ex(("127.0.0.1", 11436)) != 0, "11436 is already occupied"
        user_before = {"version": read_only_api("http://127.0.0.1:11434", "/api/version"),
                       "ps": read_only_api("http://127.0.0.1:11434", "/api/ps")}
        write(out / "user_service_before.json", user_before)
        assert memory()["physical_available_bytes"] >= MIN_AVAILABLE
        candidate = stage(out)
        print("Stage and signature verification completed", flush=True)
        overrides = {
            "OLLAMA_HOST": "127.0.0.1:11436", "OLLAMA_MODELS": str(STAGING / "models"),
            "OLLAMA_NO_CLOUD": "1", "OLLAMA_NOPRUNE": "1", "OLLAMA_VULKAN": "1",
            "OLLAMA_IGPU_ENABLE": "1", "GGML_VK_VISIBLE_DEVICES": "0", "OLLAMA_LLM_LIBRARY": "",
            "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_MAX_LOADED_MODELS": "1",
            "OLLAMA_CONTEXT_LENGTH": "32768", "OLLAMA_FLASH_ATTENTION": "1",
            "OLLAMA_KV_CACHE_TYPE": "f16", "OLLAMA_KEEP_ALIVE": "10m", "OLLAMA_LOAD_TIMEOUT": "180s",
            "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
        }
        environment = os.environ.copy()
        environment.update(overrides)
        service_log = (out / "server.stderr.log").open("wb")
        server_stdout = (out / "server.stdout.log").open("wb")
        server = subprocess.Popen([str(STAGING / "portable/ollama.exe"), "serve"], cwd=ROOT, env=environment,
                                  stdout=server_stdout, stderr=service_log, creationflags=subprocess.CREATE_NO_WINDOW)
        server_stdout.close()
        summary["server_pid"] = server.pid
        write(out / "server_launch.json", {"pid": server.pid, "started_at_utc": now(), "origin": ORIGIN,
                                           "binary": str(STAGING / "portable/ollama.exe"), "environment": overrides,
                                           "persistent_environment_changes": 0, "user_service_changes": 0})
        for _ in range(100):
            assert server.poll() is None, "Probe service exited during startup"
            try:
                version = read_only_api(ORIGIN, "/api/version")
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("Probe service did not become ready within 20 seconds")
        assert version["version"] == "0.35.1"
        ownership_script = out / "verify_listener.ps1"
        ownership_script.write_text("""param([int]$ExpectedPid,[string]$Output)
$connections=@(Get-NetTCPConnection -LocalPort 11436 -State Listen -ErrorAction Stop | Select-Object LocalAddress,LocalPort,OwningProcess)
$connections|ConvertTo-Json|Set-Content -LiteralPath $Output -Encoding UTF8
if($connections.Count -ne 1 -or $connections[0].LocalAddress -ne '127.0.0.1' -or $connections[0].OwningProcess -ne $ExpectedPid){throw 'Probe listener ownership mismatch'}
""", encoding="utf-8-sig")
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ownership_script),
                        "-ExpectedPid", str(server.pid), "-Output", str(out / "listener_ownership.json")],
                       check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        source = ROOT / f"data/v63_20261027/local_campaign_results/runs/{RUN_ID}/B-development/development-001__F03__R0__1/http/attempt_000001/runner_request.bin"
        source_raw = source.read_bytes()
        (out / "source_runner_request.bin").write_bytes(source_raw)
        request = json.loads(source_raw)
        request["max_output_tokens"] = 128
        request.pop("expected_prompt_tokens", None)
        freeze = dict(candidate)
        freeze.update(output_tokens=128, request_timeout=600,
                      allowed_response_schema_sha256=[hashlib.sha256(packed(request["response_schema"])).hexdigest()])
        freeze["fixed_options"] = {"num_thread": 8, "num_gpu": -1, "use_mmap": True, "num_batch": 256}
        write(out / "engineering_runtime_freeze.json", freeze)
        write(out / "engineering_source_mapping.json", {"source_path": str(source), "source_sha256": hashlib.sha256(source_raw).hexdigest(),
                                                        "source_candidate": "004", "source_run_id": RUN_ID,
                                                        "message_bytes_unchanged": True, "response_schema_unchanged": True,
                                                        "changes": ["output cap 4096 to 128", "num_gpu 0 to -1", "port 11436", "Vulkan enabled"]})
        transport = OllamaTransport(ORIGIN, freeze, out / "http")
        transport._identity(out, "preflight_identity")
        def monitor_memory():
            while not stop.is_set():
                sample = memory()
                samples.append(sample)
                with (out / "memory_samples.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(sample) + "\n")
                stop.wait(1)
        monitor = threading.Thread(target=monitor_memory, daemon=True)
        monitor.start()
        options = {**freeze["fixed_options"], "num_ctx": 32768, "num_predict": 128, "temperature": 0, "seed": 1001}
        print("Loading same model on isolated Vulkan service at 32768 context", flush=True)
        loaded = json.loads(transport._http(out, "administrative_load", "/api/generate",
                            packed({"model": MODEL, "stream": False, "keep_alive": "10m", "options": options}), generation=False))
        assert not loaded.get("response") and not loaded.get("eval_count", 0), "Unexpected output during administrative load"
        assert memory()["physical_available_bytes"] >= MIN_AVAILABLE, "Below 2 GiB available after load; generation withheld"
        ps = json.loads(transport._http(out, "loaded_ps", "/api/ps"))
        models = [item for item in ps.get("models", []) if item.get("name") == MODEL]
        assert len(models) == 1 and models[0].get("digest") == MODEL_SHA
        assert models[0].get("size_vram", 0) > 0, "No actual GPU allocation; generation withheld"
        assert models[0].get("context_length") == 32768, "Unexpected loaded context length"
        server_log = (out / "server.stderr.log").read_text(encoding="utf-8", errors="replace")
        assert "Vulkan" in server_log and "offload" in server_log.lower(), "Missing Vulkan/offload evidence"
        summary["loaded_model"] = {key: models[0].get(key) for key in ("name", "digest", "size", "size_vram", "context_length")}
        summary["memory_after_load"] = memory()
        tokenizer = NativeTokenizer(load(ROOT / "data/v63_20261027/continuation/deployment/local_windows/candidate_004/tokenizer_config.json"))
        print("Rendering frozen stage-1 prompt and counting exact tokens", flush=True)
        count = transport.render_and_count(request, tokenizer)
        assert count + 128 <= 32768, "Prompt plus bounded output exceeds context"
        summary["exact_prompt_tokens"] = count
        summary["source_expected_prompt_tokens"] = json.loads(source_raw).get("expected_prompt_tokens")
        assert count == json.loads(source_raw)["expected_prompt_tokens"], "Prompt renderer changed token count"
        request["expected_prompt_tokens"] = count
        (out / "engineering_runner_request.bin").write_bytes(packed(request))
        assert memory()["physical_available_bytes"] >= MIN_AVAILABLE, "Below 2 GiB available before generation; withheld"
        assert not (out / "generation_authorization_used.json").exists()
        summary["engineering_generation_requests"] = 1
        write(out / "generation_authorization_used.json", {"used_at_utc": now(), "generation_requests_upper_bound": 1,
                                                           "max_output_tokens": 128, "retries": 0, "timeout_seconds": 600})
        print("Dispatching the only authorized generation, output cap 128, timeout 600 seconds", flush=True)
        started = time.perf_counter()
        try:
            response = transport(packed(request))
            summary["http_wall_seconds"] = time.perf_counter() - started
            summary["provider_metrics"] = response.get("usage", {})
            summary["finish_reason"] = response.get("finish_reason")
            summary["status"] = "engineering_generation_completed"
        finally:
            summary["http_wall_seconds"] = time.perf_counter() - started
        metrics = summary["provider_metrics"]
        summary["provider_token_count_matches_exact"] = metrics.get("prompt_eval_count") == count
        for label, tokens, duration in [("prefill_tokens_per_second", "prompt_eval_count", "prompt_eval_duration"),
                                        ("decode_tokens_per_second", "eval_count", "eval_duration")]:
            summary[label] = metrics.get(tokens, 0) / (metrics[duration] / 1e9) if metrics.get(duration) else None
        assert metrics.get("eval_count", 0) <= 128
        transport._identity(out, "completed_identity")
    except Exception as exc:
        summary.update(status="failed_no_retry", error_type=type(exc).__name__, error=str(exc))
        print(json.dumps({"status": summary["status"], "error_type": type(exc).__name__, "error": str(exc)}), flush=True)
    finally:
        if tokenizer is not None:
            tokenizer.close()
        if transport is not None and server is not None and server.poll() is None:
            try:
                transport._http(out, "administrative_unload", "/api/generate", packed({"model": MODEL, "keep_alive": 0}), generation=False)
                final_ps = json.loads(transport._http(out, "after_unload_ps", "/api/ps"))
                summary["models_unloaded_at_end"] = not final_ps.get("models")
            except Exception as exc:
                summary["unload_error"] = str(exc)
        stop.set()
        if monitor is not None:
            monitor.join(timeout=3)
        summary["minimum_available_memory_bytes"] = min((x["physical_available_bytes"] for x in samples), default=memory()["physical_available_bytes"])
        summary["memory_after"] = memory()
        summary["server_left_running"] = server is not None and server.poll() is None
        summary["ended_at_utc"] = now()
        try:
            user_after = {"version": read_only_api("http://127.0.0.1:11434", "/api/version"), "ps": read_only_api("http://127.0.0.1:11434", "/api/ps")}
            write(out / "user_service_after.json", user_after)
            summary["user_service_preserved"] = user_after == load(out / "user_service_before.json")
        except Exception as exc:
            summary["user_service_after_check_error"] = str(exc)
        write(out / "summary.json", summary)
        write(ROOT / "research/device_migration_20261027/gpu_probe_summary.json", summary)
        write(out / "artifact_manifest.json", {"recorded_at_utc": now(), "files": [
            {"path": str(path.relative_to(out)), "bytes": path.stat().st_size, "sha256": sha(path),
             "mutable_while_service_running": path.name in {"server.stdout.log", "server.stderr.log"}}
            for path in sorted(out.rglob("*")) if path.is_file() and path.name != "artifact_manifest.json"]})
        if service_log is not None:
            service_log.close()
        print(json.dumps({key: summary.get(key) for key in ("status", "engineering_generation_requests", "experimental_generation_requests",
                         "exact_prompt_tokens", "decode_tokens_per_second", "models_unloaded_at_end", "server_pid", "evidence_directory")}), flush=True)


if __name__ == "__main__":
    main()
