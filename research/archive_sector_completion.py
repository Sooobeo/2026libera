"""Offline archive for a terminal three-condition completion; never load a model."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import zipfile
import archive_sector_continuation as inherited
import finalize_sector_completion as completion

campaign = inherited.campaign
ROOT, RESTORE_SOURCE = inherited.ROOT, inherited.RESTORE_SOURCE
VERSION = "sector_completion_archive_1"
now, sha, read, require = inherited.now, inherited.sha, inherited.read, inherited.require
contained, checked, inventory = inherited.contained, inherited.checked, inherited.inventory
windows_activity, normalized, quiet = inherited.windows_activity, inherited.normalized, inherited.quiet
verify_bundle, restore = inherited.verify_bundle, inherited.restore
urlparse = inherited.urlparse

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
    require(purpose == "pilot_completion" and declaration.get("purpose") == purpose
            and terminal.get("purpose") == purpose, "Campaign purpose mismatch")
    require(terminal.get("status") in ("stopped_semantic_review_pending", "completed_semantic_review_pending")
            and summary.get("status") in ("stopped", "attempt_sequence_finished"), "Durable terminal records required")
    require(terminal.get("declaration_ref") == dr and terminal.get("summary_ref") == sr,
            "Terminal declaration/summary binding mismatch")
    require(contained(workspace, terminal.get("run_directory")) == run
            and contained(workspace, terminal.get("output_root")) == reports,
            "Terminal output location mismatch")
    completion.scope(declaration)
    require(summary.get("purpose") == "pilot_completion" and summary.get("case_order") == list(completion.CASES)
            and [r.get("case_id") for r in summary.get("cases", [])] == list(completion.CASES),
            "Exact completion denominator required")
    attempts = summary.get("generation_requests_attempted")
    require(type(attempts) is int and 0 <= attempts <= 6
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
    runtime, rr = checked(workspace, declaration["runtime_ref"])
    require(runtime == declaration.get("runtime"), "Declared runtime bytes differ")
    services = [r for r in runtime.get("backend_evidence", []) if isinstance(r, dict) and r.get("role") == "cpu_service"]
    require(len(services) == 1, "Exactly one runtime-bound CPU service required")
    _, expected_service_ref = checked(workspace, {key: services[0][key] for key in ("path", "sha256")})
    require(servr == expected_service_ref, "Archive service receipt differs from runtime-bound service")
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
            "refs": [dr, sr, tr, ar, er, servr, shr, rr, fr, *(r for _, r in acquisitions)]}



def verified_dependencies(workspace, entries):
    """Verify the previous ZIP and its declared dependency chain, without restoring."""
    queue, seen, dependencies, members = list(entries), {}, [], {}
    while queue:
        entry = queue.pop(0)
        manifest, mr = checked(workspace, entry["manifest_ref"])
        verification, vr = checked(workspace, entry["verification_ref"])
        key = (mr["path"], mr["sha256"])
        name = manifest.get("archive")
        require(isinstance(name, str) and Path(name).name == name, "Prior archive basename required")
        bundle = contained(workspace, Path(mr["path"]).parent / name)
        require(verification.get("archive_sha256") == manifest.get("archive_sha256")
                and verification.get("verified_files") == len(manifest["files"]), "Prior verification differs from manifest")
        archive_ref = {"path": str(bundle), "sha256": manifest["archive_sha256"]}
        if "archive_ref" in entry:
            require(contained(workspace, entry["archive_ref"]["path"]) == bundle
                    and entry["archive_ref"]["sha256"] == archive_ref["sha256"], "Nested prior archive reference differs")
        identity = (vr["path"], vr["sha256"], archive_ref["path"], archive_ref["sha256"])
        if key in seen:
            require(seen[key] == identity, "Conflicting duplicate prior dependency")
            continue
        seen[key] = identity
        restored = restore(Path(mr["path"]), workspace, write=False)
        require(restored["archive_sha256"] == verification["archive_sha256"], "Prior archive verification failed")
        dependencies.append({"manifest_ref": mr, "verification_ref": vr, "archive_ref": archive_ref})
        for row in manifest["files"]:
            require(row["path"] not in members or members[row["path"]] == row["sha256"], "Conflicting prior archive members")
            members[row["path"]] = row["sha256"]
        nested = manifest.get("previous_archive_dependencies", [])
        require(isinstance(nested, list), "Nested prior dependencies must be a list")
        queue.extend(nested)
    return dependencies, members

def archive(plan_path, *, workspace=ROOT, activity_probe=windows_activity):
    workspace = Path(workspace).resolve()
    plan_path = contained(workspace, plan_path)
    plan, plan_ref = read(plan_path)
    require(plan.get("version") == "sector_completion_archive_plan_1", "Explicit archive plan version required")
    stem = plan.get("archive_stem")
    require(isinstance(stem, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", stem), "Safe archive stem required")
    output = contained(workspace, plan["output_directory"], exists=False)
    targets = [output / (stem + suffix) for suffix in (".zip", ".manifest.json", ".verification.json", ".failure.json")]
    require(not any(path.exists() for path in targets), "Existing archive attempt is immutable; choose a new stem")
    items = plan.get("campaigns")
    require(isinstance(items, list) and len(items) == 1, "Exactly one terminal completion campaign required")
    evidence = [terminal_evidence(workspace, item) for item in items]
    purposes = [e["purpose"] for e in evidence]
    require(len(purposes) == len(set(purposes)), "Duplicate campaign purpose")
    raw_parent = contained(workspace, plan["raw_campaign_parent"])
    require(raw_parent == contained(workspace, "data/local_sector_runtime")
            and all(e["run"].parent == raw_parent for e in evidence),
            "All runs and the raw inventory scan must share the canonical campaign parent")
    main = plan.get("new_main_state", {})
    require(main.get("status") == "excluded_not_run" and plan.get("analysis_role") == "primary_exploratory"
            and isinstance(main.get("reason"), str) and main["reason"].strip(), "Explicit excluded new-main scope required")
    context = {key: set().union(*(e["context"][key] for e in evidence)) for key in evidence[0]["context"]}
    before_quiet = quiet(context, activity_probe)
    # Only after quiescence do arithmetic/accounting checks read completed responses.
    accounting = [completion.finalize_completion(e["run"]) for e in evidence]
    prior = plan.get("previous_archives")
    require(isinstance(prior, list) and prior, "Previous immutable archive references required")
    dependencies, prior_members = verified_dependencies(workspace, prior)
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
    inherited_source = contained(workspace, Path(inherited.__file__).resolve())
    inherited_relative = inherited_source.relative_to(workspace).as_posix()
    require(inherited_source in initial or prior_members.get(inherited_relative) == sha(inherited_source.read_bytes()),
            "Reused archive primitive source must be preserved exactly")
    declared = {e["run"] for e in evidence}
    for path in raw_parent.glob("*/campaign_declaration.json"):
        obj, observed = read(path)
        if obj.get("purpose") in ("pilot_continuation", "pilot_completion", "main") and path.parent.resolve() not in declared:
            relative = path.relative_to(workspace).as_posix()
            require(prior_members.get(relative) == observed["sha256"], "Unlisted new campaign cannot be hidden by archive scope")
            require(obj["purpose"] != "main", "Excluded new-main claim conflicts with an existing main declaration")
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
                    "scope": "Terminal completion of three remaining original pilot conditions, with five-condition exploratory denominators and all prior attempts preserved.",
                    "new_main_state": main, "analysis_role": "primary_exploratory", "previous_archive_dependencies": dependencies,
                    "campaign_accounting": [{"purpose": "pilot_completion", "case_order": value["segment_case_order"],
                        "segment_planned_final_allocations": value["segment_planned_final_allocations"],
                        "segment_planned_stage_slots": value["segment_planned_stage_slots"],
                        "generation_requests_attempted": value["completion_generation_requests"],
                        "all_generation_requests_including_interrupted_attempt": value["all_generation_requests_including_interrupted_attempt"],
                        "original_planned_final_allocations": value["planned_final_allocations"],
                        "logical_stage_slots": value["logical_stage_slots"],
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
