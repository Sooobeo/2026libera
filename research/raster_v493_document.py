"""Render the Word-exported QA PDF using the managed Poppler binary."""
from pathlib import Path
import json,hashlib,sys
from pdf2image import convert_from_path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]
qadir=ROOT/'research/artifacts/v493_manuscript_qa/word_r1'
pdf=qadir/'manuscript.pdf'
poppler='C:/Users/Insun/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin'
reader=PdfReader(str(pdf))
pages=[]
for i,page in enumerate(reader.pages,1):
    text=page.extract_text() or ''
    pages.append({'page':i,'characters':len(text),'start':text[:180],'end':text[-180:]})
    (qadir/f'page-{i}.txt').write_text(text,encoding='utf-8')
imgs=convert_from_path(str(pdf),dpi=140,fmt='png',thread_count=1,poppler_path=poppler)
for i,img in enumerate(imgs,1):img.save(qadir/f'page-{i}.png')
r={'pages':len(pages),'renderer':'Microsoft Word PDF plus managed Poppler','pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'page_text_summary':pages,'dpi':140,'pngs':[str(qadir/f'page-{i}.png') for i in range(1,len(pages)+1)],'visual_review':'pending'}
(ROOT/'research/v493_render_inventory_20261019.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'pages':len(pages),'pngs':len(imgs),'output':str(qadir)},ensure_ascii=False))
