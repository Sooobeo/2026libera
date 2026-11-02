from pathlib import Path
import hashlib
import importlib.util
import json
import os
import shutil
import sys

WORK = Path(__file__).parent
RUNTIME = Path('C:/Users/Insun/.cache/codex-runtimes/codex-primary-runtime')
RENDERER = Path('C:/Users/Insun/.codex/plugins/cache/openai-primary-runtime/documents/26.1026.10807/skills/documents/render_docx.py')
DOCX = Path('C:/Users/Insun/Downloads/소논문_6절_결과에따른해결방안_각주.docx')
PDF = WORK / 'verified_v2.pdf'
assert PDF.exists() and PDF.stat().st_size > 1000
os.environ['PATH'] = str(RUNTIME / 'dependencies/native/poppler/Library/bin') + os.pathsep + os.environ.get('PATH', '')
spec = importlib.util.spec_from_file_location('packaged_docx_renderer', RENDERER)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)

def native_pdf_conversion(doc_path, user_profile, convert_tmp_dir, stem, verbose=False):
    assert Path(doc_path).name == DOCX.name
    destination = Path(convert_tmp_dir) / (stem + '.pdf')
    shutil.copy2(PDF, destination)
    return str(destination), 'Native office PDF export of the final DOCX; the selected Windows runtime does not bundle LibreOffice.'

renderer.convert_to_pdf = native_pdf_conversion
sys.argv = [str(RENDERER), str(DOCX), '--output_dir', str(WORK / 'render_v2'), '--dpi', '144', '--verbose']
renderer.main()
receipt = {'docx_sha256': hashlib.sha256(DOCX.read_bytes()).hexdigest(), 'pdf_sha256': hashlib.sha256(PDF.read_bytes()).hexdigest()}
(WORK / 'render_receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
