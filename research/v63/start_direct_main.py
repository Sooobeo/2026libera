"""Start only the reduced B-main experiment requested on 2026-10-28.

This launcher intentionally schedules no smoke, feasibility, or development
phase. Runtime failures are recorded by campaign.py rather than converted into
preliminary experiments.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.v63.campaign import main as campaign_main


def build_config(base: Path, output: Path) -> Path:
    from research.v64_reduced.design import make_main_only_design, validate_design
    manifest_path=Path('research/reduction_20261028/main_only_no_full_approved.json')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    design=validate_design(manifest['design'])
    if manifest.get('status')!='USER_SCOPE_CONFIRMED' or design!=make_main_only_design():
        raise ValueError('The selected four-condition main scope must be recorded first.')
    config=json.loads(base.read_text(encoding="utf-8-sig"))
    config.update(
        workspace_root=str(Path.cwd()),
        output_root=str(output),
        direct_main_no_preliminary_validation=True,
        main_direct_design={"precision_levels":[0.5,2.0],"samples_per_precision":5,"replicates":1,
                            "arms":["R0","R1","R2","R3"]},
        design_manifest_path=manifest_path.as_posix(),
        weight_policy="normalize_nonnegative_then_recheck",
        skip_duplicate_render_identity=True,
        allow_infrastructure_retries=False,
    )
    # Three required stages, at most two optional calculator round trips in
    # each stage; no infrastructure retries and no preliminary model calls.
    config["phase_budgets"]={"B-main":{"max_generation_requests":1440,"max_wall_seconds":259200}}
    destination=output/"direct_main_config.json"
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(config,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return destination


def main() -> int:
    parser=argparse.ArgumentParser()
    default_candidate=Path("data/v63_20261027/continuation/deployment/local_windows/candidate_005/campaign_config.json")
    fallback=Path("data/v63_20261027/continuation/deployment/campaign_config.json")
    parser.add_argument("--base",type=Path,default=default_candidate if default_candidate.is_file() else fallback)
    parser.add_argument("--output",type=Path,default=Path("data/v64_20261028/main_only_results"))
    parser.add_argument("--prepare-only",action="store_true",help="Write the selected config without loading or calling a model.")
    args=parser.parse_args()
    config=build_config(args.base,args.output)
    if args.prepare_only:
        print(json.dumps({'status':'prepared_no_model_calls','config':str(config),
                          'trajectories':160,'planned_output_slots':480}))
        return 0
    import sys
    sys.argv=["research.v63.campaign",str(config),"--phase","B-main"]
    return campaign_main()


if __name__=="__main__":
    raise SystemExit(main())
