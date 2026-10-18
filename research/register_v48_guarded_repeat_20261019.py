"""Record one user-requested operational repeat; retain original failure reviews."""
import argparse
import copy
from pathlib import Path

import run_sector_v48_guarded_pilot as wrapper

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-round2", required=True)
    parser.add_argument("--prior-round3", required=True)
    args = parser.parse_args()
    original = ROOT / "data/sector_protocol/v48_pilot_registration_20261018.json"
    registration = copy.deepcopy(wrapper.read(original))
    manifest = wrapper.checked(registration["manifest"])
    prior_summary = ROOT / "data/local_sector_runtime/pilot_v48_20261018/summary.json"
    operation_path = ROOT / "data/sector_protocol/v48_pilot_guarded_addendum_20261019.json"
    registration_path = ROOT / "data/sector_protocol/v48_pilot_registration_guarded_20261019.json"
    if operation_path.exists() or registration_path.exists():
        raise FileExistsError("Do not overwrite a registration")
    prior_audits = [ROOT / "research/evidence/v48_actual_pilot_20261018/round1_with_environment.json",
                    wrapper.resolve(args.prior_round2), wrapper.resolve(args.prior_round3)]
    old_reviews = [wrapper.read(p) for p in prior_audits]
    if [x["round"] for x in old_reviews] != [1, 2, 3] or any(x["status"] not in ("PASS", "FAIL") for x in old_reviews):
        raise ValueError("Preserved actual preceding-run reviews required; failures must remain failures")
    for item in old_reviews[1:]:
        if wrapper.checked(item["provenance"]["manifest"]) != manifest:
            raise ValueError("Review belongs to another manifest")
    if wrapper.checked(old_reviews[2]["provenance"]["run_summary"]) != prior_summary:
        raise ValueError("Round3 belongs to another run")
    operating_reviews = [ROOT / "research/evidence/v48_guarded_repeat_20261019/round1/review.json",
        ROOT / "research/evidence/v48_guarded_repeat_20261019/round2/review.json",
        ROOT / "research/evidence/v48_actual_pilot_20261018/guarded_wrapper_round3.json"]
    software = {name: wrapper.ref(ROOT / "research" / name)["sha256"] for name in wrapper.SOFTWARE}
    for i, path in enumerate(operating_reviews, 1):
        review = wrapper.read(path)
        if review["round"] != i or review["status"] != "PASS" or review["reviewed_software"] != software:
            raise ValueError("Operating review not bound to final files")
    operation = {"kind": "one_explicit_sleep_disrupted_pilot_repeat", "registered_at_utc": wrapper.now(),
        "user_instruction_ko": "절전때문에 중단된거 다시 실행해봐",
        "authorization_scope": "One fresh fixed four-case development bundle; no MAIN or automatic repeated bundles.",
        "manifest": wrapper.ref(manifest), "prior_registration": wrapper.ref(original),
        "prior_run_summary": wrapper.ref(prior_summary), "prior_run_reviews": [wrapper.ref(p) for p in prior_audits],
        "prior_review_statuses_retained": [x["status"] for x in old_reviews],
        "new_run_root": str(ROOT / "data/local_sector_runtime/pilot_v48_guarded_20261019"),
        "guard_record_root": str(ROOT / "data/local_sector_runtime/pilot_v48_guarded_20261019_operating"),
        "roster": list(wrapper.pilot.ROSTER), "planned_core_calls": 16, "maximum_auxiliary_calls": 8,
        "repeat_bundle_limit": 1, "automatic_retries": 0, "main_authorized": False, "main_model_calls": 0,
        "operating_software_hashes": software, "operating_reviews": [wrapper.ref(p) for p in operating_reviews],
        "environment_evidence": [wrapper.ref(ROOT / "research/evidence/v48_pilot_timing_investigation_20261018/postpilot_environmental_deviation.json")],
        "operating_change": "Acquire ES_CONTINUOUS | ES_SYSTEM_REQUIRED on the calling thread for the whole unchanged pilot.run; restore previous execution state in finally. No permanent power-plan change.",
        "unchanged": ["model and template hashes", "generation options", "public documents and market input", "case order", "prompt and full history", "900-second configured supervisor rule", "raw C0 primary endpoint", "C1/C2 eligibility and cap", "all-case and sector denominators", "evaluation definitions"],
        "interpretation": "Separate development repeat after environmental disruption. Preserve and report the first run; never pool as independent cases or select better responses across runs.",
        "scientific_basis": "No scientific parameter changed. The power request is an operating measure grounded in Microsoft API documentation, not a paper-derived strategic threshold.",
        "official_api_reference": "https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate",
        "limits": "Manual sleep/lid/power actions remain possible; API acceptance does not prove uninterrupted operation. Capture actual timing and later OS events.",
        "model_calls_by_registration": 0}
    wrapper.save_new(operation_path, operation)
    registration.update(registered_at_utc=wrapper.now(), operating_addendum=wrapper.ref(operation_path),
        prior_registration=wrapper.ref(original),
        scope="User-requested fixed pilot repeat with temporary idle-sleep request; original failure retained; no MAIN authorization.")
    wrapper.save_new(registration_path, registration)
    verify_args = argparse.Namespace(manifest=str(manifest), registration=str(registration_path),
        output=operation["new_run_root"], guard_output=operation["guard_record_root"])
    wrapper.verify_operation(verify_args)
    print(registration_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
