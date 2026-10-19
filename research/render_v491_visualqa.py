"""Capture actual HTML and its extracted context section with headless Chrome."""
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import subprocess
from bs4 import BeautifulSoup
from build_v491_context_plan import ROOT, PLAN, PAPER, ref, save


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision',choices=['r1','r2'],default='r2')
    args=parser.parse_args()
    out=ROOT/'research/artifacts/v491_visual_20261019'
    if args.revision=='r2':out=out/'r2'
    out.mkdir(parents=True,exist_ok=True)
    chrome=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
    tmp=ROOT/'tmp/v491_visual'
    tmp.mkdir(parents=True,exist_ok=True)
    s=BeautifulSoup(PLAN.read_text('utf-8'),'html.parser')
    preview=tmp/'context_section.html'
    preview.write_text('<!doctype html><html lang="ko">'+str(s.head)+'<body><main>'+str(s.find(id='context'))+'</main></body></html>',encoding='utf-8')
    refs=[ref(PLAN),ref(PAPER)]
    captures=[]
    for name,path,size in [('plan_top',PLAN,'1360,1000'),('context_table',preview,'1360,2000'),
                            ('plan_narrow',PLAN,'600,1400'),('paper_top',PAPER,'1360,1200')]:
        target=out/(name+'.png')
        cmd=[str(chrome),'--headless','--disable-gpu','--no-first-run','--no-default-browser-check',
             '--hide-scrollbars','--force-device-scale-factor=1','--run-all-compositor-stages-before-draw',
             '--virtual-time-budget=2000','--window-size='+size,'--user-data-dir='+str(tmp/(name+'_'+args.revision+'_profile')),
             '--screenshot='+str(target),path.as_uri()]
        done=subprocess.run(cmd,capture_output=True,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
        if done.returncode or not target.exists():
            raise RuntimeError('HTML render failed: '+name)
        captures.append({'name':name,'viewport':size,'image':ref(target),'source':ref(PLAN if path==preview else path),
                         'extracted_section_only':path==preview})
    assert refs==[ref(PLAN),ref(PAPER)]
    save(out/'capture_receipt.json',{'checked_at_utc':datetime.now(timezone.utc).isoformat(),'documents':refs,
        'captures':captures,'visual_review_completed':False,'model_calls':0})
    print(json.dumps({'captures':len(captures),'out':str(out)}))


if __name__=='__main__':main()
