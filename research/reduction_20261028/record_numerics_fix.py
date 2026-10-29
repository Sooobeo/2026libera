"""Preserve the stopped preflight and refresh the handoff before dispatch."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET

from research.v63.campaign import runtime_identity
from research.v63.build_run import file_ref

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "실험참고자료_20261027"
HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def ref(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests", required=True)
    parser.add_argument("--diagnostic", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--description", required=True)
    args = parser.parse_args()
    tests_path = ROOT / args.tests
    diagnostic_source = ROOT / args.diagnostic
    state_path = BUNDLE / "현재실험상태_20261028.json"
    state = read(state_path)
    old_id = state["run_id"]
    config = read(ROOT / state["config"]["path"])
    new_id, identity = runtime_identity(ROOT, read(ROOT / config["runtime_freeze_path"]),
                                      file_ref(ROOT / config["tokenizer_config_path"], ROOT), config["execution_amendment"], config)
    if new_id == old_id:
        raise RuntimeError("No new source identity; handoff already refreshed or fix missing.")
    out = ROOT / config["output_root"]
    old_phase = out / "phases" / old_id / "B-main"
    if (old_phase / "records.json").exists() or any((out / "runs" / old_id).rglob("http")):
        raise RuntimeError("Old run has response or dispatch artifacts; inspect before amending.")
    tests = ET.parse(tests_path).getroot()
    suites = [tests] if tests.tag == "testsuite" else list(tests.iter("testsuite"))
    if not suites or any(int(s.get("failures", 0)) or int(s.get("errors", 0)) for s in suites):
        raise RuntimeError("Focused validation has not passed.")
    stamp = datetime.now(timezone.utc)
    archive = BUNDLE / "history" / ("before_numerics_fix_" + stamp.strftime("%Y%m%dT%H%M%SZ"))
    manifest_path = BUNDLE / "현재자료목록_20261028.json"
    manifest = read(manifest_path)
    active_pages = [BUNDLE / name for name in manifest["active_html"]]
    resumes = [BUNDLE / "README.txt", ROOT / "research/device_migration_20261027/RESUME.txt", ROOT / "research/v63/RESUME_20261027.txt"]
    audit_path = HERE / "direct_main_call_audit.json"
    locator_path = ROOT / "research/device_migration_20261027/current_execution.json"
    plan_path = HERE / "execution_plan_20261028.json"
    wrapper = HERE / "run_selected_main_timed.py"
    for path in [*active_pages, *resumes, state_path, locator_path, manifest_path, audit_path, plan_path, wrapper]:
        destination = archive / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    diagnostic = HERE / (Path(args.receipt).stem + "_diagnostic.json")
    shutil.copyfile(diagnostic_source, diagnostic)
    receipt_path = HERE / args.receipt
    prior_process_path = Path(read(out / "active_execution.json")["receipt_path"])
    prior_process = read(prior_process_path)
    if prior_process["run_id"] != old_id or prior_process["status"] != "stopped_incomplete":
        raise RuntimeError("Most recent process is not the expected stopped preflight.")
    receipt = {
        "schema": "libera_preflight_numerics_fix_v1", "recorded_at_utc": stamp.isoformat(),
        "previous_run_id": old_id, "new_run_id": new_id,
        "previous_numerics_fix": state.get("numerics_fix"),
        "previous_process_receipt": ref(prior_process_path),
        "old_numerics": ref(old_phase / "source_snapshot/numerics.py"),
        "new_numerics": ref(ROOT / "research/v63/numerics.py"),
        "execution_source_guard": ref(ROOT / "research/v64_reduced/design.py"),
        "change": args.description,
        "design_and_model_configuration_unchanged": True,
        "previous_generation_requests": 0, "model_calls_in_fix_validation": 0,
        "focused_test_count": sum(int(s.get("tests", 0)) for s in suites),
        "focused_tests": ref(tests_path),
        "selected_input_diagnostic": ref(diagnostic),
        "exact_vertex_verification": ref(HERE / "vertex_exact_verification.json"),
        "coordinate_failure_input": ref(HERE / "coordinate_failure_input.json"),
        "archive": archive.relative_to(ROOT).as_posix(),
    }
    write(receipt_path, receipt)
    audit = read(audit_path)
    audit.update(recorded_at_utc=stamp.isoformat(), runtime_id_if_started_with_current_sources=new_id, numerics_fix=ref(receipt_path))
    write(audit_path, audit)
    state.update(recorded_at_utc=stamp.isoformat(), status="prepared_main_after_numerics_fix", run_id=new_id,
                 progress_path=f"{config['output_root'].replace(chr(92), '/')}/phases/{new_id}/B-main/progress.json",
                 call_audit=ref(audit_path), numerics_fix=ref(receipt_path),
                 previous_preflight_execution={"run_id": old_id, "generation_requests": 0, "elapsed_seconds": prior_process["elapsed_seconds"]})
    write(state_path, state)
    write(locator_path, state)
    note = f'<div class="box status"><strong>추가 수치 사전검사 수정</strong><p>직전 실행은 {prior_process["elapsed_seconds"]:.6f}초 후 수치 검증에서 중단됐으며 모델 요청은 0회였습니다. 기존 제약·허용오차를 유지하며 기준해 계산을 수정했습니다. 새 소스는 아래 새 실행 ID로 구분합니다. <a href="../research/reduction_20261028/{receipt_path.name}">수정·검증 기록</a></p></div>'
    for path in active_pages:
        text = path.read_text(encoding="utf-8").replace(old_id, new_id)
        text = re.sub(r"갱신 2026-10-28 \d{2}:\d{2} KST", "갱신 " + stamp.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST"), text)
        path.write_text(text.replace("<main>", "<main>" + note, 1), encoding="utf-8", newline="\n")
    for path in resumes:
        text = path.read_text(encoding="utf-8").replace(old_id, new_id)
        path.write_text(text + f"\n추가 수치 사전검사 수정 기록: research/reduction_20261028/{receipt_path.name}\n직전 실행은 {prior_process['elapsed_seconds']:.6f}초 후 생성 0회로 중단. 기존 검증 기준 유지.\n", encoding="utf-8", newline="\n")
    wrapper.write_text(wrapper.read_text(encoding="utf-8").replace(old_id, new_id), encoding="utf-8", newline="\n")
    plan = read(plan_path)
    plan["expected_run_id"] = new_id
    plan["efficiency"]["frozen_experiment_sources_modified"] = True
    plan["numerics_fix"] = ref(receipt_path)
    write(plan_path, plan)
    manifest["recorded_at_utc"] = stamp.isoformat()
    manifest["generated_files"] = [{"copy": row["copy"], **ref(BUNDLE / row["copy"])} for row in manifest["generated_files"]]
    paths = {ROOT / row["path"] for row in manifest["workspace_files"]}
    paths.update([receipt_path, diagnostic, tests_path, plan_path, wrapper])
    paths.update([HERE / "vertex_exact_verification.json", HERE / "coordinate_failure_input.json"])
    manifest["workspace_files"] = [ref(path) for path in sorted(paths)]
    write(manifest_path, manifest)
    print(json.dumps({"new_run_id": new_id, "focused_tests": receipt["focused_test_count"], "generation_requests": 0}))


if __name__ == "__main__":
    main()
