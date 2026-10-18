"""Bind the third cross-review and its forward-only delta to exact pilot files."""
import argparse
from pathlib import Path
import run_sector_v48 as runner


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();manifest=Path(args.manifest).resolve();runner.verify_manifest(manifest)
    draft=runner.ROOT/'research/v48_implementation_round3_draft_20261018.json'
    delta=runner.ROOT/'research/evidence/v48_legacy_cancel_investigation/investigation_and_round3_delta.json'
    reviews=[runner.read(draft),runner.read(delta)]
    if any(r.get('status')!='PASS' or r.get('round')!=3 for r in reviews): raise ValueError('Cross review or delta missing')
    latest={}
    for review in reviews:
        for item in review['reviewed_files']: latest[item['path']]=item
    for item in latest.values():
        if runner.ref(runner.ROOT/item['path'])!=item: raise ValueError('Reviewed source changed: '+item['path'])
    for item in reviews[0]['frozen_design_integrity']:
        if runner.sha(runner.ROOT/item['path'])!=item['sha256']: raise ValueError('Frozen design changed')
    report={'round':3,'status':'PASS','created_at_utc':runner.now(),'manifest_sha256':runner.sha(manifest),
            'reviewed_files':[runner.ref(runner.ROOT/'research'/x) for x in runner.SOFTWARE],
            'source_reviews':[runner.ref(draft),runner.ref(delta)],
            'cross_reviewed_source_files':list(latest.values()),
            'reviewer_disclosure':reviews[0]['independence_disclosure'],
            'binding_role':'Root verifies the complete executable hash inventory against the prepared manifest; actual cross-review scope and authorship remain as stated in the linked reviews.',
            'checks':{'initial_cross_review':17,'forward_delta':12,'reviewed_hashes_current':True,'frozen_design_unchanged':True},
            'topic_alignment':reviews[0]['paper_to_implementation_mapping'],
            'historical_failure':'The older expanded 113-test run remains FAIL. This binds only the new v4.8 execution path, not the retired one-case workflow.',
            'main_authorized':False,'model_calls':0,'independent_human_review_completed':False}
    path=Path(args.output)
    if path.exists(): raise FileExistsError(path)
    runner.save(path,report)
    print(str(path))


if __name__=='__main__': main()
