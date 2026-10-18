"""Record targeted static cross-review and literal-rendering regression checks."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
def ref(name):
    p = ROOT / name
    return {"path": name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
def write(name, value):
    p = ROOT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2); handle.write("\n")
    print(json.dumps(ref(name)))

runtime_files = ["research/run_sector_v48_main.py", "research/sector_v48_main_transport.py", "research/audit_v48_main_round1.py"]
expected = ["add603e5a13ea960842941b12183722e8b2a228edffb5ee264b517244eaced36", "aa0fea0b02573ad7836eeea50ad004e1c70078b00bd0fcaf91c2d41c36781c04", "612d618a674f0395555a109b8a9270b454b15c4cd98ad7571b0e1f048d9dbf5d"]
refs = [ref(p) for p in runtime_files]
assert [r["sha256"] for r in refs] == expected
now = datetime.now(timezone.utc).isoformat()
checks = [
    ("main_snapshot_and_loader_contract", "Coordinator preserves the unapproved candidate snapshot and three separate gate/authorization/source-review snapshots. Its invocation and case metadata match the main loader; candidate false flags are not changed into execution approval."),
    ("durable_generation_accounting", "Worker, supervisor and coordinator count saved generation request envelopes, including failed attempts. The loader independently counts the same main roster/endpoints; evaluator zero calls are separate from observed main calls."),
    ("full_authored_history_binding", "Transport reconstructs prior messages from frozen previews, captured raw assistant strings and recomputed actual arithmetic feedback. The currently authored body and every prior request must match; no gold or target weights enter this check."),
    ("R4_exposure_scope", "Before stage4, assigned institution_document and assigned evidence IDs are absent. Shared market baseline provenance is permitted and must not be mistaken for assigned-document exposure merely because it names a source."),
    ("C0_schema_arithmetic_separation", "Complete C0 raw vector arithmetic is recorded independently of seven-field schema validity. Incomplete capture has unavailable financial validity. A model contract failure stops the workflow but does not erase captured explanation or numbers."),
    ("bounded_auxiliary_sequence", "C1/C2 require a completed schema-valid arithmetic-repair-eligible predecessor; no C1 after schema failure, no C2 after valid repair, no best-response replacement of C0. Current author history validation independently rejects an ineligible predecessor."),
    ("partial_capture_preservation", "Coordinator preserves response/assembled text/flushed event content after interruption. Offline loader retains partial text without complete-response credit; malformed partial envelope diagnostics remain separate from model semantic success."),
    ("awake_guard_outcome", "Main coordinator acquires the temporary awake request before model work, records receipt and same-thread restoration, stops on acquisition failure, and marks restoration failure as an integrity incident. This is not proof that all sleep or power transitions were prevented."),
    ("observed_elapsed_scope", "Audit and loader use actual supervisor elapsed_seconds and preserve the configured polling threshold separately. They do not clip delayed terminations, infer CPU time, introduce a tolerance, or certify an uninterrupted wall-clock limit."),
    ("offline_round1_coverage", "Main round1 independently checks raw stream/event consistency, source exposure, sequence, exact raw feedback, downstream counters, C0/auxiliary references, fixed request budget and all four terminal slots. Model arithmetic/semantic failure is distinct from record-integrity failure."),
    ("human_source_vs_response_review", "Pre-generation human source-review declaration remains distinct from post-generation response judgments. Main loader/renderer leave response semantic judgments null, and neither review authenticates human identities."),
    ("topic_claim_boundaries", "Interpretation/source evidence/rationale/raw choices are retained for the paper's source-to-choice question; arithmetic and rating diagnostics alone do not establish strategy preservation, private institutional mandates, returns or organizational benefit.")
]
write("research/evidence/v48_main_runtime_validation_20261018/round2_offline_compatibility_20261019.json", {
    "round": 2, "status": "PASS", "created_at_utc": now,
    "review_scope": "Targeted static independent read of the named main coordinator, transport and round1 auditor, against the offline loader contract. No real main run or empirical acceptance.",
    "reviewer_role": "AI evaluator implementation agent; independent of named main runtime and round1 code authorship",
    "authorship_conflict": "Reviewer authored the loader/renderer used as the interface counterpart; this is not independent human review and does not independently validate its own evaluator semantics.",
    "reviewed_artifacts": refs,
    "interface_counterparts": [ref("research/evaluate_sector_v48_main_artifacts.py"), ref("research/evaluate_sector_v48_artifacts.py"), ref("research/evaluate_sector_v48.py")],
    "checks": [{"id": k, "status": "PASS_STATIC_READ", "observation": v} for k, v in checks],
    "blocking_runtime_compatibility_findings": [],
    "separate_source_review_gate_followup": "Sent calculator agent a non-runtime boundary: blank template has researcher_paraphrase fields, while gate currently permits them null under completed review_notes. Explicit paraphrase-review evidence or a narrower claimed completion scope should be resolved separately; this receipt does not certify that source-review gate.",
    "independent_human_review_completed": False, "main_execution_authorized": False,
    "actual_main_run_reviewed": False, "model_calls_by_review": 0, "frozen_pilot_files_modified": False,
})
write("research/evidence/v48_main_offline_validation_20261018/renderer_literal_fix_20261019.json", {
    "status": "PASS", "created_at_utc": now,
    "scope": "Own-code targeted regression check after independent calculator-agent finding; not independent human review.",
    "reviewer_role": "author_AI", "source_of_change": "Calculator agent identified that broad HTML replacement could rewrite quoted model/source text.",
    "artifacts": [ref("research/render_v48_main_review_packet.py"), ref("research/test_sector_v48_main_offline.py")],
    "change": "Restrict heading replacement to the exact generated <p class=note> prefix, which is distinct from escaped untrusted text. Link preserved v2 source comparison.",
    "validation": {"command": "python -B -X utf8 -m unittest test_sector_v48_main_offline.MainRenderTests -v", "cwd": "research", "exit_code": 0, "tests_run": 5, "elapsed_seconds_reported_by_unittest": 38.015,
        "regression": "Same heading-like literal inserted into source passage, interpretation and rationale remains exactly three times; only generated heading changes. Other checks retain synthetic marker, fixed roster, escaping, pending human fields and output safeguards."},
    "pilot_helpers_modified": False, "actual_main_report_created": False, "model_calls_by_validation": 0,
})
