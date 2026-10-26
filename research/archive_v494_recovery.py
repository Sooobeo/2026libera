"""Archive completed recovery evidence without altering or restoring originals."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import zipfile

from restore_research_artifacts import restore

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "research/recovery_20261025"
RUNS = [ROOT / "data/local_sector_runtime" / name for name in
        ("v492_pilot_20261019", "v494_pilot_20261025")]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(roots):
    items = {}
    for folder in roots:
        if not folder.exists() or not folder.resolve().is_relative_to(ROOT):
            raise ValueError(f"Missing or external evidence root: {folder}")
        files = ([folder] if folder.is_file() else
                 [p for p in folder.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts])
        if not files:
            raise ValueError(f"Empty evidence root: {folder}")
        for path in files:
            if not path.resolve().is_relative_to(ROOT) or path in items:
                raise ValueError(f"External or duplicate evidence path: {path}")
            stat = path.stat()
            items[path] = (stat.st_size, stat.st_mtime_ns)
    return items


def archive():
    # Do not snapshot a live run or continually changing service log.
    terminal = read(RECOVERY / "new_pilot/terminal_receipt.json")
    if terminal.get("status") not in {
            "completed_semantic_review_pending", "stopped_semantic_review_pending",
            "completed_with_errors_attention_required"}:
        raise ValueError("A recognized durable coordinator terminal receipt is required")
    shutdown = read(RECOVERY / "runtime/service_ready/service_shutdown_receipt.json")
    if (shutdown.get("status") != "owned_service_stopped"
            or shutdown.get("owned_port_closed") is not True):
        raise ValueError("Owned isolated service must have been stopped before archiving")
    helper_cleanup = []
    for helper_name in ("temporary_awake_01", "postwork_awake_01"):
        awake_folder = RECOVERY / "runtime" / helper_name
        if (awake_folder / "acquire.json").exists():
            acquired = read(awake_folder / "acquire.json")
            if (awake_folder / "release.json").exists():
                released = read(awake_folder / "release.json")
                if (released.get("status") != "released"
                        or released.get("helper_pid") != acquired.get("helper_pid")
                        or released.get("clear_flags") != 0x80000000):
                    raise ValueError(f"Awake helper release must be verified: {helper_name}")
                helper_cleanup.append({"helper": helper_name, "status": "explicit_release_verified"})
            elif helper_name == "postwork_awake_01":
                # A helper can disappear before its finally receipt is written.
                # Preserve that distinction; process absence establishes a quiet
                # writer, not a successful explicit API clear or its exit cause.
                observed = read(awake_folder / "process_exit_observation.json")
                if (observed.get("status") != "helper_process_absent_no_explicit_release_receipt"
                        or observed.get("helper_pid") != acquired.get("helper_pid")
                        or observed.get("acquire_ref", {}).get("sha256") != sha((awake_folder / "acquire.json").read_bytes())
                        or observed.get("observed_helper_pid_absent") is not True
                        or observed.get("matching_helper_command_processes") != []
                        or observed.get("explicit_api_clear_verified") is not False):
                    raise ValueError("Postwork helper absence must be bound and independently observed")
                helper_cleanup.append({"helper": helper_name, "status": observed["status"],
                                       "explicit_api_clear_verified": False})
            else:
                raise ValueError(f"Missing awake release receipt: {helper_name}")
    roots = RUNS + [ROOT / "data/sector_protocol/v494_design_20261025",
                    ROOT / "data/sector_protocol/v495_main_candidate_20261025", RECOVERY]
    # New top-level implementation files may not be committed yet. Preserve the
    # frozen code itself, not only its hash; skip files already covered by roots.
    freeze = read(RECOVERY / "pilot_freeze.json")
    code_paths = []
    for reference in freeze["code_refs"]:
        path = ROOT / reference["path"]
        if not path.resolve().is_relative_to(ROOT) or sha(path.read_bytes()) != reference["sha256"]:
            raise ValueError(f"Frozen code changed or escaped workspace: {path}")
        code_paths.append(path)
    code_paths += [Path(__file__).resolve(), ROOT / "research/start_v494_pilot.ps1",
                   ROOT / "research/read_v494_status.py",
                   ROOT / "research/restore_research_artifacts.py",
                   ROOT / "research/finalize_sector_allocation.py",
                   ROOT / "research/prepare_sector_v495_main.py",
                   ROOT / "research/test_finalize_sector_allocation.py",
                   ROOT / "research/test_finalize_sector_allocation_artifacts.py",
                   ROOT / "research/test_run_v494_recovery.py",
                   ROOT / "research/test_sector_v494_recovery.py",
                   ROOT / "tmp/pdfs/sector_documents/fidelity_q3_2026.pdf",
                   ROOT / "tmp/pdfs/sector_documents/fidelity_q3_2026_3.png",
                   ROOT / "tmp/pdfs/sector_documents/ubs_july_2026.pdf",
                   ROOT / "tmp/pdfs/sector_documents/ubs_july_2026_21.png"]
    for path in code_paths:
        if not any(path == root or path.is_relative_to(root) for root in roots):
            roots.append(path)
    initial_inventory = inventory(roots)
    files = sorted(initial_inventory)
    output = ROOT / "research/artifacts"
    output.mkdir(exist_ok=True)
    bundle_path = output / "recovery-evidence-20261025.zip"
    manifest_path = output / "recovery-evidence-20261025.manifest.json"
    verification_path = output / "recovery-evidence-20261025.verification.json"
    if any(p.exists() for p in (bundle_path, manifest_path, verification_path)):
        raise FileExistsError("Existing recovery archive evidence is immutable")
    entries = []
    # Stored compression avoids expensive recompression of already small evidence.
    # Each source is read once; a changed size/mtime aborts without claiming success.
    with zipfile.ZipFile(bundle_path, "x", compression=zipfile.ZIP_STORED) as bundle:
        for path in files:
            before = path.stat()
            data = path.read_bytes()
            after = path.stat()
            if ((before.st_size, before.st_mtime_ns) != initial_inventory[path]
                    or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
                    or len(data) != after.st_size):
                raise ValueError(f"Evidence changed while archiving: {path}")
            relative = path.relative_to(ROOT).as_posix()
            bundle.writestr(relative, data)
            entries.append({"path": relative, "bytes": len(data), "sha256": sha(data)})
    if inventory(roots) != initial_inventory:
        raise ValueError("Evidence inventory changed during archiving; no success manifest written")
    manifest = {
        "version": "v494_recovery_evidence_archive_1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "archive": bundle_path.name,
        "archive_sha256": sha(bundle_path.read_bytes()),
        "files": entries,
        "scope": "Historical interrupted run, new development pilot, offline main candidate, recovery audit records, frozen code, finalizer and preparation/launch/archive helpers. Failed/missing stages remain unchanged.",
        "excluded": "Portable binaries and model blobs are not bundled; runtime provenance records their sources and hashes. Earlier input/code artifacts retain their original repository/archive locations.",
        "original_files_modified": False,
        "whole_inventory_stable_before_and_after": True,
        "model_calls": 0,
        "terminal_status": terminal["status"],
        "awake_helper_cleanup": helper_cleanup,
        "completion_is_not_semantic_or_research_success": True,
    }
    with manifest_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    result = restore(manifest_path, ROOT, write=False)
    result.update({"verified_at_utc": datetime.now(timezone.utc).isoformat(),
                   "manifest": manifest_path.relative_to(ROOT).as_posix(),
                   "restore_performed": False, "source_files_deleted": False})
    with verification_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    return result


if __name__ == "__main__":
    print(json.dumps(archive(), ensure_ascii=False, allow_nan=False))
