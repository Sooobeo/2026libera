"""Capture final-document sections with explicit viewport measurements.

Copies retain source text and styles. Section copies avoid asynchronous smooth
fragment scrolling in headless Chrome. No delivered HTML is modified.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research/evidence/v481_delivery_20261019/visual_r2'
CHROME=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')


def ref(p): return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}


def main():
    OUT.mkdir(parents=True,exist_ok=False)
    paper=ROOT/'paper/LIBERA_텀페이퍼_초안_v4.8.1_20261019_r2.html'
    plan=ROOT/'plan/LIBERA_실험준비현황_v4.8.1_20261019_r2.html'
    inputs=[ref(paper),ref(plan)]; captures=[]
    specs=[('paper_top',paper,None,'1440,1100'),
           ('paper_results',paper,'readiness','1440,2200'),
           ('paper_observations',paper,'observations','1440,2200'),
           ('paper_implications',paper,'implications','1440,1800'),
           ('plan_narrow',plan,None,'600,2100')]
    for name,path,selection,size in specs:
        source=BeautifulSoup(path.read_text(encoding='utf-8'),'html.parser')
        if selection:
            rendered=BeautifulSoup('<!doctype html><html lang="ko"><head></head><body><main class="paper-body"></main></body></html>','html.parser')
            rendered.head.replace_with(BeautifulSoup(str(source.head),'html.parser').head)
            if selection=='observations':
                heading=source.find('h3',string='근거에서 실제 선택까지: AI 작성자의 사례 검토')
                nodes=[heading,heading.find_next_sibling('p'),heading.find_next_sibling('div')]
            else: nodes=[source.find(id=selection)]
            for node in nodes:
                if node is None: raise ValueError('Missing source section: '+name)
                rendered.main.append(BeautifulSoup(str(node),'html.parser'))
        else: rendered=source
        base=rendered.new_tag('base',href=path.parent.as_uri()+'/');rendered.head.insert(0,base)
        script=rendered.new_tag('script')
        script.string="window.addEventListener('load',()=>{document.documentElement.setAttribute('data-qa-layout',JSON.stringify({width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth}));});"
        rendered.body.append(script)
        derived=OUT/(name+'.html');derived.write_text(str(rendered),encoding='utf-8')
        image=OUT/(name+'.png')
        command=[str(CHROME),'--headless','--disable-gpu','--no-first-run','--no-default-browser-check',
                 '--hide-scrollbars','--force-device-scale-factor=1','--virtual-time-budget=3000',
                 '--window-size='+size,'--user-data-dir='+str(ROOT/'tmp/browser_profiles/v481_20261019_r2'/name),
                 '--dump-dom','--screenshot='+str(image),derived.as_uri()]
        result=subprocess.run(command,capture_output=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
        (OUT/(name+'.stdout.bin')).write_bytes(result.stdout);(OUT/(name+'.stderr.bin')).write_bytes(result.stderr)
        if result.returncode or not image.is_file():raise RuntimeError('Capture failed: '+name)
        dom=BeautifulSoup(result.stdout.decode('utf-8',errors='replace'),'html.parser')
        metrics=json.loads(dom.html['data-qa-layout'])
        captures.append({'name':name,'source':ref(path),'selection':selection or 'full_document_top',
                         'derived':ref(derived),'image':ref(image),'requested_viewport':size,
                         'actual_layout':metrics,'no_document_horizontal_overflow':metrics['scrollWidth']<=metrics['width']})
    if inputs!=[ref(paper),ref(plan)]:raise RuntimeError('Source changed')
    receipt={'at_utc':datetime.now(timezone.utc).isoformat(),'inputs':inputs,'captures':captures,
             'renderer':ref(Path(__file__)),'visual_review_completed':False,'model_calls':0,
             'scope':'Selected sections at measured desktop/narrow viewports; not every scroll position or a phone emulation.'}
    (OUT/'capture_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'captures':len(captures),'layout':[c['actual_layout'] for c in captures],'output':str(OUT)}))


if __name__=='__main__':main()
