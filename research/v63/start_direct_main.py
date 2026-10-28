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
    config=json.loads(base.read_text(encoding="utf-8-sig"))
    config.update(
        workspace_root=str(Path.cwd()),
        output_root=str(output),
        direct_main_no_preliminary_validation=True,
        main_direct_design={"precision_levels":[0.5,2.0],"samples_per_precision":5,"replicates":1},
        weight_policy="normalize_nonnegative_then_recheck",
    )
    config["phase_budgets"]["B-main"]={"max_generation_requests":5400,"max_wall_seconds":259200}
    destination=output/"direct_main_config.json"
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(config,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return destination


def main() -> int:
    parser=argparse.ArgumentParser()
    default_candidate=Path("data/v63_20261027/continuation/deployment/local_windows/candidate_005/campaign_config.json")
    fallback=Path("data/v63_20261027/continuation/deployment/campaign_config.json")
    parser.add_argument("--base",type=Path,default=default_candidate if default_candidate.is_file() else fallback)
    parser.add_argument("--output",type=Path,default=Path("data/v63_20261027/direct_main_results"))
    args=parser.parse_args()
    config=build_config(args.base,args.output)
    import sys
    sys.argv=["research.v63.campaign",str(config),"--phase","B-main"]
    return campaign_main()


if __name__=="__main__":
    raise SystemExit(main())
