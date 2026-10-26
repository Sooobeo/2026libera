"""Last-final schema adapter for the unchanged Korean renderer; no raw reads."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = Path(__file__).resolve().parent
CORE_PATH = ROOT / "research/remaining_20261026/render_plain_results.py"
CORE_SHA = "77b50b82a17ded37178f48daeda6fd76b8c24e6776a27579200c9a1996bc2128"


def guard_core():
    if hashlib.sha256(CORE_PATH.read_bytes()).hexdigest() != CORE_SHA:
        raise ValueError("Pinned original renderer changed")


guard_core()
_spec = importlib.util.spec_from_file_location("immutable_remaining_plain_renderer", CORE_PATH)
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)


def view(result):
    core.require(isinstance(result, dict) and result.get("version") == "sector_last_final_finalizer_1"
        and result.get("purpose") == "primary_exploratory_last_final_dataset", "Accepted last-final result required")
    n = result.get("last_final_generation_requests")
    core.require(type(n) is int and n in (0, 1), "Zero or one last-final request required")
    for key, expected in (("remaining_generation_requests", 4), ("completion_generation_requests", 1),
        ("prior_continuation_generation_requests", 2), ("original_generation_requests", 3),
        ("all_generation_requests_including_interrupted_attempt", 10+n),
        ("segment_planned_final_allocations", 1), ("segment_planned_stage_slots", 1)):
        core.require(type(result.get(key)) is int and result[key] == expected, "Last-final accounting differs: " + key)
    core.require(result.get("segment_case_order") == [core.CASES[-1]]
        and result.get("segment_stage_order") == [core.CASES[-1]+"__F0"], "Only final control slot allowed")
    # In-memory presentation compatibility only: never rewrite the actual result.
    projected = {**result, "version": "sector_remaining_finalizer_1", "purpose": "primary_exploratory_remaining_dataset"}
    core.validate_results(projected)
    return projected


def render_html(result, notes, *, related_links=None, provenance=None):
    guard_core()
    return core.render_html(view(result), notes, related_links=related_links, provenance=provenance)


def generate(results_path, notes_path, output):
    results_path, notes_path, output = map(core.workspace_path, (results_path, notes_path, output))
    core.require(output.is_relative_to(REPORT_ROOT) and output.suffix.lower() == ".html", "New HTML must be inside last-final report tree")
    core.require(output not in (results_path, notes_path), "Inputs cannot be output")
    if output.exists():
        raise FileExistsError("Report already exists; choose a new name")
    result, data = core.load(results_path)
    notes, note_data = core.load(notes_path)
    core.notes_validated(notes)
    references = [("통합 배분 결과(JSON)", results_path), ("관찰 요약·주의점(JSON)", notes_path)]
    for item in notes["related_files"]:
        target = core.workspace_path(item["path"])
        core.require(target.is_file(), "Related file does not exist")
        references.append((item["label"], target))
    links = [(name, quote(os.path.relpath(path, output.parent).replace("\\", "/"), safe="/")) for name, path in references]
    provenance = {"생성 시각(KST)": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
        "통합 결과 SHA256": hashlib.sha256(data).hexdigest(), "관찰 메모 SHA256": hashlib.sha256(note_data).hexdigest(),
        "보고서 어댑터 SHA256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "기존 보고서 표시 코드 SHA256": CORE_SHA, "입력 결과 형식": result.get("version", "")}
    encoded = render_html(result, notes, related_links=links, provenance=provenance).encode("utf-8")
    core.require(results_path.read_bytes() == data and notes_path.read_bytes() == note_data, "Input changed during rendering")
    guard_core()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as handle:
        handle.write(encoded)
    return {"status": "created", "output": str(output), "sha256": hashlib.sha256(encoded).hexdigest(),
        "source_result_version": result["version"], "presentation_schema_projection_only": True,
        "core_source_sha256": CORE_SHA, "model_calls": 0, "service_calls": 0, "raw_files_read": 0, "inputs_modified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("results", "notes", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(generate(args.results, args.notes, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
