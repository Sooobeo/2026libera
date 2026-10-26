"""Archive only quiet, terminal manifest-bound campaigns; never restore or delete.

The plan is an explicit inventory contract. Preparing/importing this module does
not inspect services or create an archive. CLI execution requires --execute.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from urllib.parse import urlparse
import zipfile

import finalize_sector_campaign as campaign
from restore_research_artifacts import restore

ROOT = Path(__file__).resolve().parents[1]
RESTORE_SOURCE = Path(__file__).resolve().with_name("restore_research_artifacts.py")
VERSION = "sector_continuation_archive_1"


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return campaign.math.read_artifact(path)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def contained(workspace, value, *, exists=True):
    require(isinstance(value, (str, Path)) and str(value), "Nonempty workspace path required")
    candidate = Path(value)
    candidate = candidate if candidate.is_absolute() else workspace / candidate
    # Do not silently collapse an escaping path or dereference a symlink/junction.
    require(".." not in candidate.parts, "Parent traversal is not an evidence path")
    candidate = candidate.absolute()
    require(candidate.is_relative_to(workspace), "Evidence path escapes workspace")
    for part in (candidate, *candidate.parents):
        if part == workspace.parent:
            break
        if part.exists() or part.is_symlink():
            info = part.lstat()
            require(not stat.S_ISLNK(info.st_mode)
                    and not (getattr(info, "st_file_attributes", 0) & 0x400),
                    "Symlink or reparse-point evidence is forbidden")
    if exists:
        require(candidate.exists(), "Missing evidence path: " + str(candidate))
    require(candidate.resolve().is_relative_to(workspace), "Resolved evidence escapes workspace")
    return candidate.resolve()


def checked(workspace, reference):
    require(isinstance(reference, dict) and set(reference) == {"path", "sha256"}, "Exact artifact ref required")
    path = contained(workspace, reference["path"])
    value, actual = read(path)
    require(actual["sha256"] == reference["sha256"], "Artifact hash mismatch: " + str(path))
    return value, actual


def inventory(workspace, roots):
    paths = [contained(workspace, root) for root in roots]
    require(paths and len(paths) == len(set(paths)), "Duplicate or empty evidence roots")
    require(not any(a != b and (a.is_relative_to(b) or b.is_relative_to(a))
                    for i, a in enumerate(paths) for b in paths[i + 1:]), "Overlapping evidence roots")
    result = {}
    def visit(path):
        path = contained(workspace, path)
        if path.is_dir():
            for child in sorted(path.iterdir()):
                if child.name == "__pycache__":
                    continue
                visit(child)
        else:
            info = path.stat()
            require(stat.S_ISREG(info.st_mode), "Only regular evidence files are allowed")
            require(path not in result, "Duplicate evidence file")
            result[path] = (info.st_size, info.st_mtime_ns)
    for path in paths:
        count = len(result)
        visit(path)
        require(len(result) > count, "Empty evidence root: " + str(path))
    return result


def windows_activity(_context):
    """Read processes/listeners only. No HTTP, model, shutdown, or power calls."""
    require(os.name == "nt", "Live quiet verification requires Windows or an explicit test probe")
    script = r"""$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new()
$p=@(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine)
$l=@(Get-NetTCPConnection -State Listen | Select-Object LocalPort,OwningProcess)
@{processes=$p;listeners=$l} | ConvertTo-Json -Depth 5 -Compress
"""
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, encoding="utf-8-sig", timeout=30, check=True)
    return json.loads(result.stdout)


def normalized(value):
    return str(value).replace("\\", "/").casefold()


def quiet(context, probe):
    observed = probe(context)
    require(isinstance(observed, dict) and isinstance(observed.get("processes"), list)
            and isinstance(observed.get("listeners"), list), "Complete process/listener observation required")
    for row in observed["processes"]:
        pid = row.get("ProcessId")
        # Win32_Process includes System Idle Process (PID0), which is not a writer.
        require(type(pid) is int and pid >= 0, "Malformed process observation")
        command = normalized(row.get("CommandLine") or "")
        executable = normalized(row.get("ExecutablePath") or "")
        require(pid not in context["pids"]
                and executable not in context["service_executables"]
                and not any(marker in command for marker in context["command_markers"]),
                "Related coordinator, worker or owned service process remains active")
    for row in observed["listeners"]:
        require(type(row.get("LocalPort")) is int, "Malformed listener observation")
        require(row["LocalPort"] not in context["ports"], "Owned service port still listening")
    return {"status": "related_processes_and_ports_absent", "observed_at_utc": now(),
            "processes_observed": len(observed["processes"]), "listeners_observed": len(observed["listeners"]),
            "network_or_model_calls": 0, "unrelated_process_details_saved": False}


def terminal_evidence(workspace, item):
    require(isinstance(item, dict), "Campaign plan entry required")
    run = contained(workspace, item["run_directory"])
    reports = contained(workspace, item["reports_directory"])
    require(not run.is_relative_to(reports) and not reports.is_relative_to(run), "Separate raw/report trees required")
    declaration, dr = read(run / "campaign_declaration.json")
    summary, sr = read(run / "campaign_summary.json")
    terminal, tr = read(reports / "terminal_receipt.json")
    release, ar = read(reports / "coordinator_awake_release.json")
    started, er = read(run / "execution_started.json")
    purpose = item.get("purpose")
    require(purpose in ("pilot_continuation", "main") and declaration.get("purpose") == purpose
            and terminal.get("purpose") == purpose, "Campaign purpose mismatch")
    require(terminal.get("status") in ("stopped_semantic_review_pending", "completed_semantic_review_pending")
            and summary.get("status") in ("stopped", "attempt_sequence_finished"), "Durable terminal records required")
    require(terminal.get("declaration_ref") == dr and terminal.get("summary_ref") == sr,
            "Terminal declaration/summary binding mismatch")
    require(contained(workspace, terminal.get("run_directory")) == run
            and contained(workspace, terminal.get("output_root")) == reports,
            "Terminal output location mismatch")
    attempts = summary.get("generation_requests_attempted")
    require(type(attempts) is int and attempts >= 0
            and type(terminal.get("generation_requests_attempted")) is int
            and terminal["generation_requests_attempted"] == attempts, "Terminal attempt accounting mismatch")
    pid = declaration.get("coordinator_pid")
    require(type(pid) is int and pid > 0 and started.get("coordinator_pid") == pid
            and release.get("coordinator_pid") == pid and terminal.get("awake_release") == release,
            "Coordinator release identity/binding mismatch")
    require(release.get("status") in ("released", "no_request_acquired")
            and type(release.get("clear_flags")) is int and release["clear_flags"] == 0x80000000
            and type(release.get("owner_thread_id")) is int and release["owner_thread_id"] > 0
            and release.get("permanent_power_settings_changed") is False,
            "Explicit successful coordinator release required")
    acquisitions = []
    events = contained(workspace, reports / "events", exists=False)
    for path in events.glob("*.json"):
        event, event_ref = read(contained(workspace, path))
        if event.get("event") == "coordinator_awake_acquired":
            acquisitions.append((event, event_ref))
    if release["status"] == "no_request_acquired":
        require(attempts == 0 and not acquisitions,
                "No-request release requires zero generation attempts and no acquisition event")
    else:
        require(len(acquisitions) == 1, "Exactly one coordinator acquisition event required")
        acquired = acquisitions[0][0]
        require(type(acquired.get("coordinator_pid")) is int and acquired["coordinator_pid"] == pid
                and type(acquired.get("owner_thread_id")) is int
                and acquired["owner_thread_id"] == release["owner_thread_id"]
                and type(acquired.get("flags")) is int and acquired["flags"] == 0x80000003
                and acquired.get("helper_process_created") is False
                and acquired.get("permanent_power_settings_changed") is False,
                "Coordinator acquisition/release same-thread identity mismatch")
    service, servr = read(contained(workspace, item["service_receipt"]))
    shutdown, shr = read(contained(workspace, item["shutdown_receipt"]))
    require(service.get("status") == "ready" and type(service.get("pid")) is int
            and service["pid"] > 0 and shutdown.get("stopped_pid") == service["pid"], "Owned service identity required")
    require(shutdown.get("status") == "owned_service_stopped"
            and shutdown.get("owned_port_closed") is True
            and shutdown.get("no_resident_models_before_stop") is True
            and shutdown.get("existing_11434_listener_unchanged") is True
            and shutdown.get("persistent_environment_changed") is False,
            "Model-free verified owned-service shutdown required")
    for field in ("executable", "executable_sha256"):
        require(isinstance(service.get(field), str) and service[field]
                and shutdown.get(field) == service[field], "Shutdown service provenance mismatch")
    require(campaign.timestamp(service.get("process_created_at_utc"))
            == campaign.timestamp(shutdown.get("process_created_at_utc")), "Service PID creation time mismatch")
    origin = urlparse(service.get("origin", ""))
    require(origin.scheme == "http" and origin.hostname == "127.0.0.1" and origin.port,
            "Owned loopback service origin required")
    freeze, fr = checked(workspace, declaration["freeze_ref"])
    context = {"pids": {pid, service["pid"]}, "ports": {origin.port},
               "service_executables": {normalized(service["executable"])},
               "command_markers": {normalized(run)}}
    # Worker/supervisor identifiers are scoped to these declared raw stage files.
    def pids(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ("pid", "worker_pid", "supervisor_pid", "process_id") and type(child) is int and child > 0:
                    context["pids"].add(child)
                else:
                    pids(child)
        elif isinstance(value, list):
            for child in value:
                pids(child)
    for path in run.glob("*__*/worker_summary.json"):
        pids(read(path)[0])
    for path in run.glob("*__*/supervisor_result.json"):
        pids(read(path)[0])
    for reference in freeze.get("code_refs", []):
        name = Path(reference["path"]).name
        if name.startswith("run_sector_") or name.endswith("_runtime.py"):
            context["command_markers"].add(normalized(name))
    return {"run": run, "reports": reports, "purpose": purpose, "summary": summary,
            "declaration": declaration, "freeze": freeze, "context": context,
            "refs": [dr, sr, tr, ar, er, servr, shr, fr, *(r for _, r in acquisitions)]}


def verify_bundle(path, entries):
    names = [row["path"] for row in entries]
    require(len(names) == len(set(names)), "Duplicate manifest members")
    with zipfile.ZipFile(path) as bundle:
        require(sorted(bundle.namelist()) == sorted(names), "ZIP inventory differs")
        for row in entries:
            data = bundle.read(row["path"])
            require(len(data) == row["bytes"] and sha(data) == row["sha256"], "ZIP member checksum mismatch")
    return sha(path.read_bytes())


def archive(plan_path, *, workspace=ROOT, activity_probe=windows_activity):
    workspace = Path(workspace).resolve()
    plan_path = contained(workspace, plan_path)
    plan, plan_ref = read(plan_path)
    require(plan.get("version") == "sector_campaign_archive_plan_1", "Explicit archive plan version required")
    stem = plan.get("archive_stem")
    require(isinstance(stem, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", stem), "Safe archive stem required")
    output = contained(workspace, plan["output_directory"], exists=False)
    targets = [output / (stem + suffix) for suffix in (".zip", ".manifest.json", ".verification.json", ".failure.json")]
    require(not any(path.exists() for path in targets), "Existing archive attempt is immutable; choose a new stem")
    items = plan.get("campaigns")
    require(isinstance(items, list) and items and len(items) <= 2, "Explicit one-or-two campaign inventory required")
    evidence = [terminal_evidence(workspace, item) for item in items]
    purposes = [e["purpose"] for e in evidence]
    require(len(purposes) == len(set(purposes)), "Duplicate campaign purpose")
    raw_parent = contained(workspace, plan["raw_campaign_parent"])
    require(raw_parent == contained(workspace, "data/local_sector_runtime")
            and all(e["run"].parent == raw_parent for e in evidence),
            "All runs and the raw inventory scan must share the canonical campaign parent")
    main = plan.get("main_state", {})
    require((main.get("status") == "pending_not_run" and "main" not in purposes
             or main.get("status") == "included_terminal_main" and "main" in purposes)
            and isinstance(main.get("reason"), str) and main["reason"].strip(), "Explicit main-pending/included distinction required")
    context = {key: set().union(*(e["context"][key] for e in evidence)) for key in evidence[0]["context"]}
    before_quiet = quiet(context, activity_probe)
    # Only after quiescence do arithmetic/accounting checks read completed responses.
    accounting = [campaign.finalize_campaign(e["run"]) for e in evidence]
    prior = plan.get("previous_archives")
    require(isinstance(prior, list) and prior, "Previous immutable archive references required")
    dependencies, prior_members = [], {}
    for prior_entry in prior:
        manifest, mr = checked(workspace, prior_entry["manifest_ref"])
        verification, vr = checked(workspace, prior_entry["verification_ref"])
        archive_name = manifest.get("archive")
        require(isinstance(archive_name, str) and Path(archive_name).name == archive_name, "Prior archive basename required")
        bundle = contained(workspace, Path(mr["path"]).parent / archive_name)
        require(verification.get("archive_sha256") == manifest.get("archive_sha256")
                and verification.get("verified_files") == len(manifest["files"]), "Prior verification differs from manifest")
        restored = restore(Path(mr["path"]), workspace, write=False)
        require(restored["archive_sha256"] == verification["archive_sha256"], "Prior archive verification failed")
        dependencies.append({"manifest_ref": mr, "verification_ref": vr,
                             "archive_ref": {"path": str(bundle), "sha256": restored["archive_sha256"]}})
        for row in manifest["files"]:
            require(row["path"] not in prior_members or prior_members[row["path"]] == row["sha256"], "Conflicting prior archive members")
            prior_members[row["path"]] = row["sha256"]
    report_values = plan.get("report_roots")
    require(isinstance(report_values, list) and report_values, "Explicit report roots required")
    report_roots = [contained(workspace, value) for value in report_values]
    require(all(any(e["reports"].is_relative_to(root) for root in report_roots) for e in evidence),
            "All reports must be within explicit report roots")
    roots = [e["run"] for e in evidence] + report_roots
    roots += [contained(workspace, value) for value in plan.get("extra_roots", [])]
    for source in roots:
        require(not output.is_relative_to(source) and not source.is_relative_to(output), "Archive output/root self-cycle")
    initial = inventory(workspace, roots)
    require(plan_path in initial, "Archive plan must itself be preserved")
    require(all(Path(dep["archive_ref"]["path"]) not in initial for dep in dependencies), "Do not nest original archives in the new ZIP")
    for source in (Path(__file__).resolve(), RESTORE_SOURCE):
        require(source in initial, "Archive/restore implementation must be explicitly preserved")
    declared = {e["run"] for e in evidence}
    for path in raw_parent.glob("*/campaign_declaration.json"):
        obj, observed = read(path)
        if obj.get("purpose") in ("pilot_continuation", "main") and path.parent.resolve() not in declared:
            relative = path.relative_to(workspace).as_posix()
            require(prior_members.get(relative) == observed["sha256"], "Unlisted new campaign cannot be hidden by archive scope")
            require(not (obj["purpose"] == "main" and main["status"] == "pending_not_run"), "Main-pending claim conflicts with existing main declaration")
    bound_refs = [plan_ref, *(r for e in evidence for r in e["refs"]),
                  *(r for result in accounting for r in result["input_refs"])]
    for reference in bound_refs:
        source = contained(workspace, reference["path"])
        relative = source.relative_to(workspace).as_posix()
        require(source in initial or prior_members.get(relative) == reference["sha256"],
                "Bound artifact is absent from current or previous evidence archives: " + relative)
    for e in evidence:
        for reference in e["freeze"]["code_refs"]:
            source = contained(workspace, reference["path"])
            require(sha(source.read_bytes()) == reference["sha256"], "Frozen executable changed before archive")
            relative = source.relative_to(workspace).as_posix()
            require(source in initial or prior_members.get(relative) == reference["sha256"], "Frozen executable is not preserved")
    output.mkdir(parents=True, exist_ok=True)
    bundle_path, manifest_path, verification_path, failure_path = targets
    # Reserve this attempt before entering failure handling. A competing writer
    # that loses the exclusive create must not write our failure receipt.
    reserved_stream = bundle_path.open("xb")
    try:
        entries = []
        with reserved_stream:
            with zipfile.ZipFile(reserved_stream, "w", compression=zipfile.ZIP_STORED) as bundle:
                for path in sorted(initial):
                    info = path.stat()
                    data = path.read_bytes()
                    after = path.stat()
                    require((info.st_size, info.st_mtime_ns) == initial[path]
                            and (after.st_size, after.st_mtime_ns) == initial[path]
                            and len(data) == after.st_size, "Evidence changed during read: " + str(path))
                    relative = path.relative_to(workspace).as_posix()
                    bundle.writestr(relative, data)
                    entries.append({"path": relative, "bytes": len(data), "sha256": sha(data)})
        require(inventory(workspace, roots) == initial, "Evidence inventory changed while archiving")
        # Hash every source again: equal size/mtime does not establish equal bytes.
        for row in entries:
            require(sha((workspace / row["path"]).read_bytes()) == row["sha256"], "Evidence bytes changed after snapshot")
        after_quiet = quiet(context, activity_probe)
        campaign.unchanged(bound_refs)
        for dep in dependencies:
            campaign.unchanged(list(dep.values()))
        bundle_hash = verify_bundle(bundle_path, entries)
        bundle_size = bundle_path.stat().st_size
        manifest = {"version": VERSION, "created_at_utc": now(), "archive": bundle_path.name,
                    "archive_sha256": bundle_hash, "archive_bytes": bundle_size, "files": entries,
                    "scope": "Terminal continuation and any explicitly included terminal main; preserved failed/missing outcomes, reports and executable helpers.",
                    "main_state": main, "previous_archive_dependencies": dependencies,
                    "campaign_accounting": [{"purpose": value["purpose"], "case_order": value["case_order"],
                        "planned_final_allocations": value["planned_final_allocations"],
                        "planned_stage_slots": value["planned_stage_slots"],
                        "generation_requests_attempted": value["generation_requests_attempted"],
                        "finalized_finals": value["finalized_finals"]} for value in accounting],
                    "quiet_observations": [before_quiet, after_quiet],
                    "original_files_modified": False, "source_files_deleted": False,
                    "whole_inventory_and_bytes_stable_before_and_after": True,
                    "excluded": ["__pycache__ directories", "portable binaries/model caches outside explicit roots", "previous ZIP bytes retained as hash-bound dependencies"],
                    "model_calls": 0, "semantic_success_claimed": False, "main_execution_authorized_by_archive": False}
        encoded = (json.dumps(manifest, ensure_ascii=True, allow_nan=False, indent=2) + "\n").encode()
        with manifest_path.open("xb") as handle:
            handle.write(encoded)
        verification = {"status": "byte_verified_quiet_terminal_archive", "verified_at_utc": now(),
                        "verified_files": len(entries), "restored_files": 0, "archive_sha256": bundle_hash,
                        "archive_bytes": bundle_size,
                        "manifest": manifest_path.relative_to(workspace).as_posix(),
                        "manifest_sha256": sha(encoded), "restore_performed": False, "source_files_deleted": False,
                        "narrow_duplicate_ignore_eligible_only_for_exact_verified_members": True}
        with verification_path.open("xb") as handle:
            handle.write((json.dumps(verification, indent=2) + "\n").encode())
        return verification
    except BaseException as exc:
        # Preserve failed attempts; never delete partial ZIPs or label them verified.
        failure = {"status": "archive_attempt_failed_no_success_claim", "recorded_at_utc": now(),
                   "error_type": type(exc).__name__, "error": str(exc), "partial_zip_may_exist": bundle_path.exists(),
                   "source_files_deleted": False, "model_calls": 0}
        with failure_path.open("xb") as handle:
            handle.write((json.dumps(failure, ensure_ascii=True, indent=2) + "\n").encode())
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("Explicit --execute only after terminal accounting, release and owned-service cleanup")
    print(json.dumps(archive(args.plan), ensure_ascii=True))


if __name__ == "__main__":
    main()
