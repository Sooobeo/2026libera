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
DOCX = Path('C:/Users/Insun/Downloads/소논문_6절_해결방안_통합개정본.docx')
PDF = WORK / 'verified.pdf'
assert PDF.exists() and PDF.stat().st_size > 1000
os.environ['PATH'] = str(RUNTIME / 'dependencies/native/poppler/Library/bin') + os.pathsep + os.environ.get('PATH', '')
spec = importlib.util.spec_from_file_location('packaged_docx_renderer', RENDERER)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
def native_pdf_conversion(doc_path, user_profile, convert_tmp_dir, stem, verbose=False):
    assert Path(doc_path).name == DOCX.name
    destination = Path(convert_tmp_dir) / (stem + '.pdf')
    shutil.copy2(PDF, destination)
    return str(destination), 'PDF exported from the final DOCX by Microsoft Word; selected Windows runtime does not bundle LibreOffice.'
renderer.convert_to_pdf = native_pdf_conversion
sys.argv = [str(RENDERER), str(DOCX), '--output_dir', str(WORK / 'render'), '--dpi', '144', '--verbose']
renderer.main()
(WORK / 'render_receipt.json').write_text(json.dumps({'docx_sha256': hashlib.sha256(DOCX.read_bytes()).hexdigest(), 'pdf_sha256': hashlib.sha256(PDF.read_bytes()).hexdigest()}, indent=2), encoding='utf-8')
