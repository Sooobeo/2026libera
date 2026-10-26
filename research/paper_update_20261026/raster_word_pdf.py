"""Raster a verified own-Word PDF using only managed Poppler and Python."""
from pathlib import Path
from pypdf import PdfReader
from pdf2image import convert_from_path
import json, hashlib, sys
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/('research/paper_update_20261026/qa/'+(sys.argv[1] if len(sys.argv)>1 else 'word_r1'))
PDF=OUT/'manuscript.pdf'
DOCX=ROOT/'paper/LIBERA_소논문_실험결과와해결방향_v5.0_20261026.docx'
POPPLER=Path('C:/Users/Insun/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    pages=[]
    for i,p in enumerate(PdfReader(str(PDF)).pages,1):
        text=p.extract_text() or '';(OUT/f'page-{i}.txt').write_text(text,encoding='utf-8')
        pages.append({'page':i,'characters':len(text),'start':text[:180],'end':text[-180:]})
    paths=convert_from_path(str(PDF),dpi=120,fmt='png',thread_count=2,poppler_path=str(POPPLER),output_folder=str(OUT),paths_only=True,output_file='raster')
    for i,p in enumerate(paths,1):Path(p).rename(OUT/f'page-{i}.png')
    receipt={'renderer':'isolated owned Microsoft Word COM PDF plus managed Poppler; packaged renderer unavailable because managed LibreOffice absent','docx_sha256':digest(DOCX),'pdf_sha256':digest(PDF),'dpi':120,'pages':pages,'pngs':[str(OUT/f'page-{i}.png') for i in range(1,len(paths)+1)],'visual_review':'pending','runtime_python':sys.executable,'poppler':str(POPPLER)}
    (OUT/'raster_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'pages':len(paths),'out':str(OUT)}))
if __name__=='__main__':main()
