"""Attempt packaged rendering with managed tools and preserve its exact receipt."""
from pathlib import Path
import json, os, subprocess, sys, hashlib
ROOT=Path(__file__).resolve().parents[2]
QA=ROOT/'research/solution_revision_20261026/qa'
DEP=Path('C:/Users/Insun/.cache/codex-runtimes/codex-primary-runtime/dependencies')
SKILL=Path('C:/Users/Insun/.codex/plugins/cache/openai-primary-runtime/documents/26.1020.11348/skills/documents')
DOCX=ROOT/'paper/LIBERA_소논문_실험해석과대응설계_v5.1_20261026.docx'

def main():
    QA.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
    # A restricted search path ensures the user's installed LibreOffice is never selected.
    env['PATH']=os.pathsep.join(str(x) for x in [DEP/'python',DEP/'bin/override',DEP/'native/poppler/Library/bin',Path('C:/Windows/System32')])
    cmd=[sys.executable,str(SKILL/'render_docx.py'),str(DOCX),'--output_dir',str(QA/'packaged_r1'),'--dpi','120','--emit_pdf','--verbose']
    with (QA/'packaged_render.log').open('w',encoding='utf-8') as log:
        result=subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    runtime=json.loads((DEP.parent/'runtime.json').read_text(encoding='utf-8'))
    receipt={'command':cmd,'exit_code':result.returncode,'bundled_libreoffice':None,'runtime_manifest_libreoffice_version':runtime.get('libreOfficeVersion'),'desktop_libreoffice_allowed':False,'path':env['PATH'],'log':str(QA/'packaged_render.log'),'status':'completed' if result.returncode==0 else 'failed_missing_managed_libreoffice','docx_sha256':hashlib.sha256(DOCX.read_bytes()).hexdigest()}
    (QA/'packaged_render_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False))
    print((QA/'packaged_render.log').read_text(encoding='utf-8')[-2500:])
    return result.returncode
if __name__=='__main__':raise SystemExit(main())
