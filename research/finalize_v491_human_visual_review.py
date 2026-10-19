"""Record four inspected captures and their bounded rendering incident."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/artifacts/v491_runtimeprep_20261019'


def ref(path):
    p=ROOT/path
    return {'path':path,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}


def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


def main():
    source=ref('research/v491_human_review_pack_20261019_R1.html')
    assert source['sha256']=='ab578b188f79203bd6278af3336d097fe58611d8687226958d996da2c86d6286'
    caps=[]
    for name,viewport,section in [('human_R1_top_desktop','1360,1200',False),('human_R1_top_narrow','600,1600',False),('human_R1_pilot_desktop','1360,1600',True),('human_R1_pilot_narrow','600,2000',True)]:
        caps.append({'name':name,'viewport':viewport,'image':ref('research/artifacts/v491_runtimeprep_20261019/'+name+'.png'),'original_source':source,'extracted_section_only':section,'expanded_first_source_row_for_inspection':section,'original_html_unchanged':True})
    incident=[
        'Initial 20261019T060514Z attempt produced both top images, but the second headless Chrome did not close within 45 seconds; subprocess inherited pipes delayed return. Only owned headless profiles under that exact task directory were terminated.',
        'Second 20261019T060717Z attempt produced both pilot section images using DEVNULL and a stable image-size check. The final owned process tree was terminated, but process.wait exceeded 10 seconds before cleanup completed. A subsequent exact-profile process inventory found no remaining owned Chrome processes.',
        'The renderer helper exit code 1 was a cleanup timeout after valid image production. It is retained as an engineering incident; it was not a model call or experiment failure. No real user Chrome session was targeted.',
    ]
    receipt={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'source':source,'captures':caps,'headless_instances_in_parallel':1,'browser_gpu_disabled':True,'profiles':['tmp/v491_visual/human_pack_20261019T060514Z','tmp/v491_visual/human_pack_20261019T060717Z'],'rendering_incidents':incident,'capture_artifacts_complete':True,'visual_review_completed':True,'research_model_calls':0}
    save('human_pack_capture_receipt.json',receipt)
    review={'status':'PASS_scoped_visual_inspection','reviewed_at_utc':datetime.now(timezone.utc).isoformat(),'source':source,'capture_receipt':ref('research/artifacts/v491_runtimeprep_20261019/human_pack_capture_receipt.json'),'inspected_images':[x['image'] for x in caps],'checks':[
        {'name':'desktop_top','pass':True,'observation':'Korean title, pilot-first 129/99-field guidance, navigation, independence notice and JSON save/import controls are legible without clipping or overlap.'},
        {'name':'600px_top','pass':True,'observation':'Long guidance and navigation wrap inside viewport; save/import/progress wrap to multiple rows without overlap. First identity field remains within page width.'},
        {'name':'desktop_pilot_section','pass':True,'observation':'Original PDF link, SHA, page locators and first sector paraphrase are visible. Expanded sector exposes two blank text areas and one blank select with associated labels.'},
        {'name':'600px_pilot_section','pass':True,'observation':'Source title, evidence ID, paragraph and labels wrap; all first-row controls fit viewport. All 11 sector headings are present in the inspected capture.'},
    ],'scope_limit':['Top of actual R1 page plus first pilot document section extracted from the same exact HTML; section capture opens the first sector disclosure for inspection.','Not a full-page screenshot audit of every row, browser automation of save/import, PDF print pagination, or visual inspection of R2. R2 has identical layout/content except reviewer slot and export metadata; export/import logic was separately executed in Node checks.','No human source interpretation or evaluation was completed by this visual inspection.'],'rendering_incidents_retained':True}
    save('human_pack_visual_review.json',review)
    audit={'status':'PASS','reviewed_at_utc':datetime.now(timezone.utc).isoformat(),'files':[ref('research/sector_v491_human_gate.py'),ref('research/test_sector_v491_human_gate.py')],'independent_checks':['Exact final blank-form SHA pins and split-specific scope match delivered reviewer pack.','Metadata, shared anchors, all 22 source rows and all 11 source comparisons required for pilot; 99 main-only answer fields may remain null.','Independent original named submissions, explicit attestations and input/submission hashes preserved.','Completion <= export <= reconciliation UTC ordering checked; null original SHA cannot bypass integrity checks.','All original comparison decisions retained, disagreements explicitly preserved; uncertainty, similarity and noncomparability remain permitted.','Material input/rubric revisions prevent approval; runtime cannot infer or certify human identity or semantic correctness.'],'test_command':'python -B -X utf8 -m unittest -v test_sector_v491_human_gate','tests_passed':10,'tests_failed':0,'fixture_scope':'Temporary synthetic fixtures only; no genuine human review answers created or completed.','remaining_human_gate':'pending; original R1/R2 answers remain null'}
    save('human_gate_independent_review.json',audit)
    print(json.dumps({'captures':4,'visual_review':review['status'],'human_gate_tests_passed':10,'human_review_completed':False}))


if __name__=='__main__':main()
