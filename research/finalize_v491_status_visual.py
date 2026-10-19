"""Record actual visual inspection of the new status page, without editing it."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research/artifacts/v491_runtimeprep_20261019'


def ref(path):
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    capture_path=OUT/'status_capture_receipt.json'
    capture=json.loads(capture_path.read_text(encoding='utf-8'))
    assert ref(ROOT/capture['source']['path'])==capture['source']
    assert len(capture['captures'])==2
    for row in capture['captures']:
        p=ROOT/row['image']['path']
        assert ref(p)==row['image']
        width,height=struct.unpack('>II',p.read_bytes()[16:24])
        assert [width,height]==[int(x) for x in row['viewport'].split(',')]
        assert not row['cleanup']['remaining_pids']
    assert len(capture['local_link_checks'])==6 and all(x['exists_inside_workspace'] for x in capture['local_link_checks'])
    prior=json.loads((ROOT/'research/v491_handoff_20261019.json').read_text(encoding='utf-8'))
    assert all(ref(ROOT/r['path'])['sha256']==r['sha256'] for r in prior['exact_delivery_files'])
    result={'status':'PASS','reviewed_at_utc':datetime.now(timezone.utc).isoformat(),'source':capture['source'],'capture_receipt':ref(capture_path),'inspected_images':[r['image'] for r in capture['captures']],'visual_review_completed':True,'checks':[
        {'name':'desktop_actual_page','pass':True,'observation':'Title, research-generation-zero notice, preparation explanation, three-row CPU table, human-review instructions and topic/scope footer are visible without clipping or overlap.'},
        {'name':'600px_actual_page','pass':True,'observation':'Inspected original-resolution 600px capture. Korean text and links wrap within page; all five table columns and all three values are legible; no horizontal clipping or overlapping blocks.'},
        {'name':'numbers_and_scope_visible','pass':True,'observation':'Displayed long-input times are 876.4 and 465.0 seconds; both are explicitly supervisor total time. CPU 8 threads is a provisional pilot candidate. Synthetic 32-output-token tests are distinguished from the task allowance of 8192 and from zero research generations.'},
        {'name':'reader_next_step','pass':True,'observation':'Two separate reviewer links and pilot-first instructions are clear; source checks do not ask humans to invent target portfolio weights. Main fields can remain blank for pilot.'},
        {'name':'six_local_links','pass':True,'observation':'Both reviewer pages, evaluation protocol, existing plan, pre-experiment paper and machine report all resolve to existing files inside workspace.'},
        {'name':'owned_browser_cleanup','pass':True,'observation':'Exact profile-scoped cleanup finished with no remaining Chrome PIDs. Initial immediate cleanup check stopped conservatively during termination; existing desktop capture retained and subsequent bounded poll confirmed cleanup.'},
        {'name':'original_files_preserved','pass':True,'observation':'New status source hash unchanged during capture and review; all 69 prior delivery files retain exact original hashes.'},
    ],'model_calls':0,'human_source_review_completed':False,'scope_limits':['Screen layout and local-link validation of this status page only; not a browser click-through study, PDF pagination review, or human semantic source review.','The initial cleanup observation is preserved in capture receipt; no model or experiment calls were made during visual inspection.']}
    target=OUT/'status_visual_review.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'status':'PASS','checks':len(result['checks']),'images':2,'links':6,'review_sha256':ref(target)['sha256']}))


if __name__=='__main__':main()
