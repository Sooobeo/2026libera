"""One-request resource diagnostic, separate from pilot and main experiments.

No pull, server configuration, calculator, gold access, or strategic scoring.
Use --dry-run to inspect the exact saved request without contacting Ollama.
Create a file named CANCEL in the current artifact directory for cooperative
cancellation; Ctrl+C also preserves the already received chunks.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import http.client
import json
import math
from pathlib import Path
import platform
import re
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "data/sector_runtime"
PILOT_TEMPLATE = ROOT / "data/sector_protocol/prompt_templates/fidelity_q2_2026__R1.json"
PAPER = "https://arxiv.org/html/2605.27887v6#S3.SS1"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    # Output directory creation is exclusive; each final file is also new-only.
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def new_directory(run_id):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", run_id):
        raise ValueError("run-id must be 1-80 letters/digits/underscore/dot/hyphen, starting alphanumeric")
    root = OUTPUT_ROOT.resolve()
    target = (root / run_id).resolve()
    if target.parent != root:
        raise ValueError("Output must remain directly under data/sector_runtime")
    root.mkdir(parents=True, exist_ok=True)
    target.mkdir()  # Existing output is never overwritten or resumed.
    return target


def connection(base_url, timeout):
    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("base-url must be an HTTP(S) origin")
    if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ("", "/"):
        raise ValueError("base-url must be an origin without credentials, path or query")
    cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    return cls(parts.hostname, parts.port, timeout=timeout)


def metadata_request(base_url, path, body=None, timeout=3):
    conn = connection(base_url, timeout)
    try:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        conn.request("GET" if body is None else "POST", path, payload,
                     {"Content-Type": "application/json"})
        response = conn.getresponse()
        raw = response.read()
        parsed = json.loads(raw)
        return {"observed_at_utc": utc_now(), "http_status": response.status, "value": parsed}
    except Exception as exc:
        return {"observed_at_utc": utc_now(), "error_type": type(exc).__name__, "error": str(exc)}
    finally:
        conn.close()


class MemoryStatusEx(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


class PerformanceInformation(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong)] + [(name, ctypes.c_size_t) for name in (
        "CommitTotal", "CommitLimit", "CommitPeak", "PhysicalTotal", "PhysicalAvailable",
        "SystemCache", "KernelTotal", "KernelPaged", "KernelNonpaged", "PageSize")] + [
        ("HandleCount", ctypes.c_ulong), ("ProcessCount", ctypes.c_ulong), ("ThreadCount", ctypes.c_ulong)]


PROCESS_NAMES = frozenset(("ollama.exe", "ollama app.exe", "ollama_llama_server.exe", "llama-server.exe",
                           "ollama", "llama-server"))


def is_runtime_process(name):
    return isinstance(name, str) and name.casefold() in PROCESS_NAMES


class ProcessEntry32W(ctypes.Structure):
    _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong),
                ("th32ProcessID", ctypes.c_ulong), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", ctypes.c_ulong), ("cntThreads", ctypes.c_ulong),
                ("th32ParentProcessID", ctypes.c_ulong), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", ctypes.c_ulong), ("szExeFile", ctypes.c_wchar * 260)]


class ProcessMemoryCountersEx(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
        (name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
            "PrivateUsage")]


def native_windows_process_memory():
    """Enumerate in memory; retain only allowlisted runtime names and their stats.

    PrivateUsage is committed private bytes, not resident working set. See
    https://learn.microsoft.com/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex
    """
    result = {"source": "windows_ctypes_Toolhelp32_GetProcessMemoryInfo", "status": "ok", "processes": []}
    if sys.platform != "win32":
        result["status"] = "not_windows"
        return result
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
    kernel.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    for name in ("Process32FirstW", "Process32NextW"):
        function = getattr(kernel, name)
        function.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry32W)]
        function.restype = ctypes.c_int
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessMemoryCountersEx), ctypes.c_ulong]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if snapshot in (None, ctypes.c_void_p(-1).value):
        result.update(status="snapshot_failed", winerror=ctypes.get_last_error())
        return result
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(entry)
        present = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while present:
            if is_runtime_process(entry.szExeFile):
                row = {"pid": int(entry.th32ProcessID), "name": entry.szExeFile,
                       "memory_info_source": result["source"]}
                # Modern Windows requires only query-limited access for PSAPI stats.
                process = kernel.OpenProcess(0x1000, False, entry.th32ProcessID)
                if not process:
                    row["winerror"] = ctypes.get_last_error()
                    row["status"] = "open_failed_or_process_exited"
                else:
                    try:
                        counters = ProcessMemoryCountersEx()
                        counters.cb = ctypes.sizeof(counters)
                        if psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), ctypes.sizeof(counters)):
                            row["status"] = "ok"
                            row["memory_info"] = {
                                "working_set_bytes": counters.WorkingSetSize,
                                "private_bytes": counters.PrivateUsage,
                                "peak_working_set_bytes": counters.PeakWorkingSetSize,
                                "page_fault_count": counters.PageFaultCount,
                                "peak_private_commit_bytes": counters.PeakPagefileUsage,
                            }
                            row["interpretation"] = "Working set is resident pageable memory; private bytes are committed, not resident. Peaks cover process lifetime."
                        else:
                            row.update(status="memory_query_failed_or_process_exited", winerror=ctypes.get_last_error())
                    finally:
                        kernel.CloseHandle(process)
                result["processes"].append(row)
            # No other process name, PID, command line, or metadata is retained.
            present = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        error = ctypes.get_last_error()
        if error not in (0, 18):  # ERROR_NO_MORE_FILES
            result.update(status="enumeration_incomplete", winerror=error)
    finally:
        kernel.CloseHandle(snapshot)
    return result


def memory_snapshot():
    result = {"observed_at_utc": utc_now(), "platform": sys.platform}
    if sys.platform == "win32":
        state = MemoryStatusEx()
        state.dwLength = ctypes.sizeof(state)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatusEx)]
        kernel.GlobalMemoryStatusEx.restype = ctypes.c_int
        if kernel.GlobalMemoryStatusEx(ctypes.byref(state)):
            result["global_memory_status_ex"] = {
                "memory_load_percent": state.dwMemoryLoad,
                "total_physical_bytes": state.ullTotalPhys,
                "available_physical_bytes": state.ullAvailPhys,
                "total_page_file_budget_bytes": state.ullTotalPageFile,
                "available_page_file_budget_bytes": state.ullAvailPageFile,
                "total_virtual_bytes": state.ullTotalVirtual,
                "available_virtual_bytes": state.ullAvailVirtual,
            }
        else:
            result["global_memory_status_error"] = ctypes.get_last_error()
        performance = PerformanceInformation()
        performance.cb = ctypes.sizeof(performance)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetPerformanceInfo.argtypes = [ctypes.POINTER(PerformanceInformation), ctypes.c_ulong]
        psapi.GetPerformanceInfo.restype = ctypes.c_int
        if psapi.GetPerformanceInfo(ctypes.byref(performance), ctypes.sizeof(performance)):
            result["system_performance_info"] = {
                "committed_bytes": performance.CommitTotal * performance.PageSize,
                "commit_limit_bytes": performance.CommitLimit * performance.PageSize,
                "commit_peak_since_boot_bytes": performance.CommitPeak * performance.PageSize,
                "physical_available_bytes": performance.PhysicalAvailable * performance.PageSize,
                "page_size_bytes": performance.PageSize,
            }
        else:
            result["system_performance_info_error"] = ctypes.get_last_error()
    else:
        result["global_memory_status_ex"] = None
    # Optional corroboration; Windows system memory above needs only stdlib.
    try:
        import psutil
        processes = []
        for process in psutil.process_iter(["pid", "name"]):
            if is_runtime_process(process.info["name"]):
                try:
                    processes.append({"pid": process.pid, "name": process.info["name"],
                                      "memory_info_source": "psutil.Process.memory_info",
                                      "memory_info": process.memory_info()._asdict()})
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        result["ollama_process_memory"] = processes
        result["process_memory_source"] = "psutil.Process.memory_info"
        result["psutil_system_virtual_memory"] = psutil.virtual_memory()._asdict()
    except ImportError:
        if sys.platform == "win32":
            native = native_windows_process_memory()
            result["ollama_process_memory"] = native.pop("processes")
            result["process_memory_source"] = native["source"]
            result["native_process_memory_status"] = native
            result["optional_process_memory_status"] = "psutil_not_installed_native_windows_fallback"
        else:
            result["optional_process_memory_status"] = "psutil_not_installed_no_windows_fallback"
    except Exception as exc:
        result["optional_process_memory_error"] = str(exc)
    return result


def build_request(mode, model, num_ctx, keep_alive):
    hashes = {"probe_script": sha256(__file__)}
    if mode == "health":
        messages = [
            {"role": "system", "content": "This is a synthetic runtime health check. Reply with one JSON object only."},
            {"role": "user", "content": 'Compute 2 + 3 and return {"sum": 5}. No finance task is involved.'},
        ]
        cap = 256
    else:
        template = json.loads(PILOT_TEMPLATE.read_text(encoding="utf-8-sig"))
        stage = template["stages"][0]
        if stage.get("role") != "user" or json.loads(stage["content"]).get("stage") != 1:
            raise ValueError("Expected the saved Fidelity Q2 R1 first-stage template")
        messages = [{"role": "system", "content": template["system"]}, stage]
        hashes["pilot_static_prompt_template"] = sha256(PILOT_TEMPLATE)
        cap = 8192
    request = {"model": model, "messages": messages, "think": True, "format": "json", "stream": True,
               "options": {"temperature": 0, "num_predict": cap, "num_ctx": num_ctx},
               "keep_alive": 0 if keep_alive == "0" else keep_alive}
    upper_bound = sum(len(json.dumps(m, ensure_ascii=False).encode("utf-8")) + 256 for m in messages)
    # This is conservative engineering validation, not an actual tokenizer count.
    if upper_bound + cap > num_ctx:
        raise ValueError(f"Conservative input-byte bound {upper_bound} + output allowance {cap} exceeds context {num_ctx}; do not truncate")
    return request, hashes, upper_bound


def remaining(deadline):
    value = deadline - time.monotonic()
    if value <= 0:
        raise TimeoutError("Total inference deadline exceeded")
    return value


def capture_stream(base_url, request, output, timeout_seconds):
    """Exactly one POST /api/chat; caller owns cleanup. No automatic retry."""
    started = time.monotonic()
    deadline = started + timeout_seconds
    conn = connection(base_url, remaining(deadline))
    terminal = None
    response = None
    first_chunk = first_thinking = first_content = None
    thinking_parts, content_parts = [], []
    status, error, http_status = "incomplete", None, None
    received_lines = 0
    network_done = threading.Event()
    interruption = {}
    watcher = None
    try:
        payload = json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8")
        conn.connect()
        sock = conn.sock
        def watch_request():
            while not network_done.wait(0.1):
                if (output / "CANCEL").exists():
                    interruption["status"] = "cancelled"
                elif time.monotonic() >= deadline:
                    interruption["status"] = "timeout"
                else:
                    continue
                # Wake a blocked read without sending an extra model/server request.
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except (OSError, AttributeError):
                    pass
                return
        watcher = threading.Thread(target=watch_request, daemon=True)
        watcher.start()
        sock.settimeout(remaining(deadline))
        conn.request("POST", "/api/chat", payload, {"Content-Type": "application/json"})
        sock.settimeout(remaining(deadline))
        response = conn.getresponse()
        http_status = response.status
        save(output / "http_response.json", {"status": response.status, "headers": response.getheaders()})
        with (output / "raw_stream.ndjson").open("xb") as raw_file, (output / "stream_events.jsonl").open("x", encoding="utf-8") as events:
            while True:
                sock.settimeout(remaining(deadline))
                raw_line = response.readline()
                if not raw_line:
                    break
                elapsed = time.monotonic() - started
                raw_file.write(raw_line)
                raw_file.flush()
                received_lines += 1
                if first_chunk is None:
                    first_chunk = elapsed
                try:
                    value = json.loads(raw_line)
                except (ValueError, UnicodeError) as exc:
                    raise ValueError("Non-JSON stream line retained in raw_stream.ndjson") from exc
                events.write(json.dumps({"elapsed_seconds": elapsed, "chunk": value}, ensure_ascii=False, allow_nan=False) + "\n")
                events.flush()
                if not isinstance(value, dict):
                    raise ValueError("Stream chunk is not an object")
                if value.get("error"):
                    raise RuntimeError(str(value["error"]))
                message = value.get("message", {})
                if not isinstance(message, dict):
                    raise ValueError("Stream message is not an object")
                thinking, content = message.get("thinking", ""), message.get("content", "")
                if not isinstance(thinking, str) or not isinstance(content, str):
                    raise ValueError("Stream thinking/content must be strings")
                if thinking:
                    if first_thinking is None:
                        first_thinking = elapsed
                    thinking_parts.append(thinking)
                if content:
                    if first_content is None:
                        first_content = elapsed
                    content_parts.append(content)
                if value.get("done") is True:
                    terminal = value
                    status = "output_limit_reached" if value.get("done_reason") == "length" else "completed_generation"
                    break
        if http_status != 200:
            status = "http_error"
        elif terminal is None:
            status = "incomplete_stream"
    except KeyboardInterrupt:
        status, error = "cancelled", {"type": "KeyboardInterrupt", "message": "Client cancellation; partial chunks retained"}
    except (TimeoutError, socket.timeout) as exc:
        status, error = "timeout", {"type": type(exc).__name__, "message": str(exc)}
    except Exception as exc:
        status, error = "request_error", {"type": type(exc).__name__, "message": str(exc)}
    finally:
        network_done.set()
        if watcher is not None:
            watcher.join(timeout=1)
        if response is not None:
            response.close()
        conn.close()
    if interruption:
        status = interruption["status"]
        error = {"type": "CooperativeCancellation" if status == "cancelled" else "TotalDeadline",
                 "message": "Connection closed; received raw chunks retained. Server cancellation is not independently confirmed."}
    content, thinking = "".join(content_parts), "".join(thinking_parts)
    return {"status": status, "error": error, "http_status": http_status,
            "client_inference_wall_seconds": time.monotonic() - started,
            "first_stream_chunk_seconds": first_chunk,
            "first_thinking_chunk_seconds": first_thinking, "first_answer_chunk_seconds": first_content,
            "first_generated_text_seconds": min(x for x in (first_thinking, first_content) if x is not None)
            if first_thinking is not None or first_content is not None else None,
            "received_stream_lines": received_lines, "terminal_response": terminal,
            "message": {"role": "assistant", "content": content, "thinking": thinking},
            "thinking_character_count": len(thinking), "answer_character_count": len(content)}


def metrics(result):
    final = result.get("terminal_response") or {}
    keys = ("total_duration", "load_duration", "prompt_eval_count", "prompt_eval_cached_count",
            "prompt_eval_duration", "eval_count", "eval_duration", "done_reason", "model")
    values = {key: final.get(key) for key in keys}
    for key in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
        value = values[key]
        values[key + "_seconds"] = value / 1e9 if isinstance(value, (int, float)) and value >= 0 else None
    def rate(count, duration):
        if isinstance(count, (int, float)) and isinstance(duration, (int, float)) and count >= 0 and duration > 0:
            return count * 1e9 / duration
        return None
    values["generation_tokens_per_second"] = rate(values["eval_count"], values["eval_duration"])
    values["prompt_reported_tokens_per_second"] = rate(values["prompt_eval_count"], values["prompt_eval_duration"])
    count, cached = values["prompt_eval_count"], values["prompt_eval_cached_count"]
    uncached = count - cached if isinstance(count, int) and isinstance(cached, int) and 0 <= cached <= count else None
    values["uncached_prompt_tokens_per_second"] = rate(uncached, values["prompt_eval_duration"])
    values["censored_without_terminal_response"] = result.get("terminal_response") is None
    values["interpretation"] = "Generation count includes provider-reported output, not final-answer-only tokens. Missing terminal metrics stay null. Prompt total/count rate is not pure prefill when cached tokens exist."
    return values


def monitor(stop, base_url, output, interval):
    start = time.monotonic()
    try:
        with (output / "resource_samples.jsonl").open("x", encoding="utf-8") as handle:
            while not stop.is_set():
                sample = {"elapsed_seconds": time.monotonic() - start, "memory": memory_snapshot(),
                          "ollama_ps": metadata_request(base_url, "/api/ps", timeout=min(2, interval))}
                handle.write(json.dumps(sample, ensure_ascii=False, allow_nan=False) + "\n")
                handle.flush()
                stop.wait(interval)
    except Exception as exc:
        save(output / "monitor_error.json", {"type": type(exc).__name__, "message": str(exc)})


def resource_summary(output):
    path = output / "resource_samples.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    available = [r["memory"].get("global_memory_status_ex", {}).get("available_physical_bytes")
                 for r in rows if isinstance(r["memory"].get("global_memory_status_ex"), dict)]
    available = [n for n in available if isinstance(n, int)]
    committed = [r["memory"].get("system_performance_info", {}).get("committed_bytes") for r in rows]
    committed = [n for n in committed if isinstance(n, int)]
    return {"sample_count": len(rows), "sampled_minimum_available_physical_bytes": min(available) if available else None,
            "sampled_maximum_system_committed_bytes": max(committed) if committed else None,
            "interpretation": "Sampled observations, not exact peaks. Shared GPU memory is system RAM and must not be added as extra capacity or blindly added to RSS. /api/ps residency is not proof of an active request."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("health", "stage1"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model", default="qwen3.6:35b")
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--num-ctx", type=int, default=131072)
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--sample-seconds", type=float, default=1)
    parser.add_argument("--keep-alive", default="0")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.num_ctx <= 0 or not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        parser.error("Context and timeout must be positive and finite")
    if not math.isfinite(args.sample_seconds) or args.sample_seconds < 0.1:
        parser.error("sample-seconds must be finite and at least 0.1")
    connection(args.base_url, 1).close()  # Validate syntax without opening a socket.
    request, hashes, upper = build_request(args.mode, args.model, args.num_ctx, args.keep_alive)
    output = new_directory(args.run_id)
    save(output / "request.json", request)
    save(output / "diagnostic_manifest.json", {
        "created_at_utc": utc_now(), "mode": args.mode, "base_url": args.base_url,
        "scope": "One-request load diagnostic; neither pilot nor main experiment; no performance/strategy scoring",
        "paper_basis": PAPER, "paper_settings": {"temperature": 0, "thinking": True, "max_output_tokens": 8192},
        "diagnostic_overrides": {"output_cap": 256 if args.mode == "health" else None,
                                 "context": args.num_ctx, "streaming": True, "keep_alive": args.keep_alive,
                                 "timeout_seconds": args.timeout_seconds, "sample_seconds": args.sample_seconds},
        "context_classification": "128K candidate" if args.num_ctx == 131072 else "Reduced/alternative context engineering diagnostic, not the current main candidate",
        "input_upper_bound_bytes_plus_overhead": upper, "input_is_not_truncated": True,
        "input_hashes": hashes, "host": {"platform": platform.platform(), "machine": platform.machine()},
        "no_gold_or_main_runner_read": True, "dry_run": args.dry_run,
        "history_caveat": "Single stage does not test all four stages or preserve_thinking semantics.",
        "cooperative_cancel_file": str(output / "CANCEL"),
        "output_counting": "All generated thinking/content counts toward this one diagnostic; do not merge it into pilot/main case denominators."
    })
    if args.dry_run:
        save(output / "summary.json", {"status": "dry_run", "model_requests_attempted": 0})
        print(json.dumps({"status": "dry_run", "output": str(output), "input_upper_bound": upper}))
        return 0
    save(output / "before.json", {"memory": memory_snapshot(), "version": metadata_request(args.base_url, "/api/version"),
                                  "tags": metadata_request(args.base_url, "/api/tags"),
                                  "show": metadata_request(args.base_url, "/api/show", {"model": args.model}),
                                  "ps": metadata_request(args.base_url, "/api/ps")})
    stop = threading.Event()
    sampler = threading.Thread(target=monitor, args=(stop, args.base_url, output, args.sample_seconds), daemon=True)
    sampler.start()
    print(json.dumps({"status": "starting_one_diagnostic_request", "output": str(output)}, ensure_ascii=False), flush=True)
    try:
        result = capture_stream(args.base_url, request, output, args.timeout_seconds)
    finally:
        stop.set()
        sampler.join(timeout=5)
    save(output / "assembled_response.json", result)
    save(output / "after.json", {"memory": memory_snapshot(), "ps": metadata_request(args.base_url, "/api/ps")})
    summary = {k: v for k, v in result.items() if k not in ("message", "terminal_response")}
    summary.update({"model_requests_attempted": 1, "experiment_calls_counted": 0,
                    "provider_metrics": metrics(result), "resources": resource_summary(output),
                    "no_retry": True, "strategy_scoring_performed": False})
    save(output / "summary.json", summary)
    print(json.dumps({"status": summary["status"], "output": str(output),
                      "generation_tokens_per_second": summary["provider_metrics"]["generation_tokens_per_second"],
                      "wall_seconds": summary["client_inference_wall_seconds"]}, ensure_ascii=False), flush=True)
    return 0 if result["status"] == "completed_generation" else (130 if result["status"] == "cancelled" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
