"""Sequential Chrome screenshots of the actual review page and an expanded section."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/artifacts/v491_runtimeprep_20261019'
SOURCE = ROOT / 'research/v491_human_review_pack_20261019_R1.html'


def ref(path):
    return {'path':str(path.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    chrome=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    tmp=ROOT/'tmp/v491_visual'/('human_pack_'+stamp)
    tmp.mkdir(parents=True,exist_ok=False)
    before=ref(SOURCE)
    soup=BeautifulSoup(SOURCE.read_text(encoding='utf-8'),'html.parser')
    section=soup.find(id='fidelity_q2_2026')
    section.select('.source-row')[0]['open']=''
    preview=tmp/'expanded_pilot_section.html'
    preview.write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+str(soup.find('style'))+'<main><p>실제 R1 검토 페이지에서 추출 · pilot 첫 산업 펼침</p>'+str(section)+'</main></html>',encoding='utf-8',newline='\n')
    captures=[]
    for name,path,size in [
        ('human_R1_top_desktop',SOURCE,'1360,1200'),
        ('human_R1_top_narrow',SOURCE,'600,1600'),
        ('human_R1_pilot_desktop',preview,'1360,1600'),
        ('human_R1_pilot_narrow',preview,'600,2000'),
    ]:
        target=OUT/(name+'.png')
        reused=name.startswith('human_R1_top_') and target.exists()
        if not reused:
            cmd=[str(chrome),'--headless','--disable-gpu','--disable-background-networking','--no-first-run','--no-default-browser-check','--hide-scrollbars','--force-device-scale-factor=1','--run-all-compositor-stages-before-draw','--virtual-time-budget=1500','--window-size='+size,'--user-data-dir='+str(tmp/(name+'_profile')),'--screenshot='+str(target),path.as_uri()]
            process=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            deadline=time.monotonic()+40
            stable=0; previous_size=None
            try:
                while time.monotonic()<deadline:
                    if target.exists():
                        size_now=target.stat().st_size
                        stable=stable+1 if size_now==previous_size and size_now>0 else 0
                        previous_size=size_now
                        if stable>=4:
                            break
                    time.sleep(.25)
                if stable<4:
                    raise RuntimeError('Screenshot failed: '+name)
            finally:
                # Only this script's explicitly spawned browser and its descendants.
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
                process.wait(timeout=10)
        captures.append({'name':name,'viewport':size,'image':ref(target),'original_source':before,'render_source':ref(path),'extracted_section_only':path==preview,'expanded_first_source_row_for_inspection':path==preview,'reused_top_capture_from_initial_attempt':reused})
    if ref(SOURCE)!=before:
        raise RuntimeError('Original HTML changed during rendering')
    receipt={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'source':before,'captures':captures,'headless_instances_in_parallel':1,'browser_gpu_disabled':True,'profile_root':str(tmp.relative_to(ROOT)).replace('\\','/'),'visual_review_completed':False,'research_model_calls':0,'initial_attempt_incident':'Both top images were produced from the unchanged original HTML. Second Chrome did not close within 45 seconds; subprocess pipes delayed timeout return. Only owned headless processes under tmp/v491_visual/human_pack_20261019T060514Z were terminated. Remaining section renders use DEVNULL and terminate only their own process tree after a stable image file.'}
    (OUT/'human_pack_capture_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'captures':len(captures),'source_sha256':before['sha256']}))


if __name__=='__main__':
    main()
