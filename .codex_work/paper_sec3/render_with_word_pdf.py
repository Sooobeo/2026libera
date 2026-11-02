from pathlib import Path
import importlib.util
import os
import shutil
import sys

WORK = Path(__file__).parent
RUNTIME = Path('C:/Users/Insun/.cache/codex-runtimes/codex-primary-runtime')
RENDERER = Path('C:/Users/Insun/.codex/plugins/cache/openai-primary-runtime/documents/26.1026.10807/skills/documents/render_docx.py')
os.environ['PATH'] = str(RUNTIME / 'dependencies/native/poppler/Library/bin') + os.pathsep + os.environ.get('PATH', '')
spec = importlib.util.spec_from_file_location('packaged_docx_renderer', RENDERER)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
docx = Path(sys.argv[1])
pdf = Path(sys.argv[2])
outdir = Path(sys.argv[3])

def word_pdf_conversion(doc_path, user_profile, convert_tmp_dir, stem, verbose=False):
    destination = Path(convert_tmp_dir) / (stem + '.pdf')
    shutil.copy2(pdf, destination)
    return str(destination), 'PDF exported by Microsoft Word on Windows; LibreOffice is not bundled on this platform.'

renderer.convert_to_pdf = word_pdf_conversion
sys.argv = [str(RENDERER), str(docx), '--output_dir', str(outdir), '--dpi', '144']
renderer.main()
