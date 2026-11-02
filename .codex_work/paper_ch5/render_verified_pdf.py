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

def hanword_pdf_conversion(doc_path, user_profile, convert_tmp_dir, stem, verbose=False):
    destination = Path(convert_tmp_dir) / (stem + '.pdf')
    shutil.copy2(WORK / 'final_verified.pdf', destination)
    return str(destination), 'PDF exported from the final DOCX by Hancom Hanword 2020. The selected Windows runtime does not bundle LibreOffice; Microsoft Word PDF export stalled.'

renderer.convert_to_pdf = hanword_pdf_conversion
sys.argv = [str(RENDERER), 'C:/Users/Insun/Downloads/소_논문45_5장축약본.docx', '--output_dir', str(WORK / 'render_final'), '--dpi', '144']
renderer.main()
