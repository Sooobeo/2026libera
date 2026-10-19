"""Use the packaged renderer with the isolated Windows administrative image."""
from pathlib import Path
import json,os,subprocess,sys,hashlib
ROOT=Path(__file__).resolve().parents[1]
dep=Path('C:/Users/Insun/.cache/codex-runtimes/codex-primary-runtime/dependencies')
r=json.loads((ROOT/'research/v493_portable_renderer_20261019.json').read_text(encoding='utf-8'))
out=ROOT/'research/artifacts/v493_manuscript_qa/lo_r1'
docx=ROOT/'paper/LIBERA_소논문_연구설계와진행현황_20261019.docx'
script=Path('C:/Users/Insun/.codex/plugins/cache/openai-primary-runtime/documents/26.1015.12040/skills/documents/render_docx.py')
env=os.environ.copy()
env['PATH']=str(Path(r['soffice_exe']).parent)+os.pathsep+str(dep/'native/poppler/Library/bin')+os.pathsep+env.get('PATH','')
env['PYTHONIOENCODING']='utf-8'
log=ROOT/'research/v493_packaged_render_portable_20261019.log'
with log.open('w',encoding='utf-8') as f:
    done=subprocess.run([sys.executable,str(script),str(docx),'--output_dir',str(out),'--dpi','140','--emit_pdf','--verbose'],env=env,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
if done.returncode:
    print(log.read_text(encoding='utf-8')[-5000:]);sys.exit(done.returncode)
from pypdf import PdfReader
pdf=next(out.glob('*.pdf'));reader=PdfReader(str(pdf));pages=[]
for i,p in enumerate(reader.pages,1):
    text=p.extract_text() or ''
    (out/f'page-{i}.txt').write_text(text,encoding='utf-8')
    pages.append({'page':i,'characters':len(text),'start':text[:160],'end':text[-160:]})
pngs=sorted(out.glob('page-*.png'),key=lambda p:int(p.stem.split('-')[-1]))
report={'renderer':'packaged render_docx.py with isolated official Windows LibreOffice administrative image','soffice_exe':r['soffice_exe'],'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'docx_sha256':hashlib.sha256(docx.read_bytes()).hexdigest(),'pages':len(pages),'page_text_summary':pages,'pngs':[str(p) for p in pngs],'dpi':140,'visual_review':'pending'}
(ROOT/'research/v493_render_inventory_20261019.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'pages':len(pages),'pngs':len(pngs),'output':str(out)},ensure_ascii=False))
