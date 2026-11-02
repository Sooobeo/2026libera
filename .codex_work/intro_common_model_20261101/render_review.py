from pathlib import Path
import importlib.util
import os
import shutil
import sys
import json
import re
import difflib

import pdfplumber
from PIL import Image, ImageDraw

WORK = Path(__file__).resolve().parent
STEM = 'LIBERA_소논문_최종결과반영_20261030'
RUNTIME = Path('C:/Users/Insun/.cache/codex-runtimes/codex-primary-runtime')
SKILL = Path('C:/Users/Insun/.codex/plugins/cache/openai-primary-runtime/documents/26.1026.10807/skills/documents')
PDF = WORK / 'stage' / (STEM + '.pdf')
DOCX = WORK / 'stage' / (STEM + '.docx')
os.environ['PATH'] = str(RUNTIME / 'dependencies/native/poppler/Library/bin') + os.pathsep + os.environ.get('PATH', '')
spec = importlib.util.spec_from_file_location('packaged_docx_renderer', SKILL / 'render_docx.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)

def native_pdf_conversion(doc_path, user_profile, convert_tmp_dir, stem, verbose=False):
    destination = Path(convert_tmp_dir) / (stem + '.pdf')
    shutil.copy2(PDF, destination)
    return str(destination), 'Native Word PDF export; selected Windows runtime has libreOfficeVersion=null.'

renderer.convert_to_pdf = native_pdf_conversion
sys.argv = [str(SKILL / 'render_docx.py'), str(DOCX), '--output_dir', str(WORK / 'render'), '--dpi', '120']
if not list((WORK / 'render').glob('page-*.png')):
    renderer.main()

document = pdfplumber.open(PDF).pages
old_document = pdfplumber.open(WORK / 'before' / (STEM + '.pdf')).pages
receipt = json.loads((WORK / 'revision_receipt.json').read_text(encoding='utf-8'))
compact = lambda t: re.sub(r'\s+', '', t)
all_text = compact(''.join(p.extract_text() for p in document))
old_text = compact(''.join(p.extract_text() for p in old_document))
addition = compact(receipt['addition'])
assert all_text.count(addition) == 1
# Word page numbers are excluded when comparing the body.
def body_text(pdf):
    return compact(''.join(p.crop((0, 0, p.width, p.height - 60)).extract_text() for p in pdf))
new_body, old_body = body_text(document), body_text(old_document)
without_addition = new_body.replace(addition, '', 1)
if without_addition != old_body:
    matcher = difflib.SequenceMatcher(None, old_body, without_addition, autojunk=False)
    differences = [{'tag': tag, 'before': old_body[max(0,i-30):j+30],
                    'after': without_addition[max(0,k-30):l+30]}
                   for tag,i,j,k,l in matcher.get_opcodes() if tag != 'equal']
    print(json.dumps(differences, ensure_ascii=False))
    (WORK / 'pdf_text_differences.json').write_text(json.dumps(differences, ensure_ascii=False, indent=2), encoding='utf-8')
    raise AssertionError('Unexpected PDF body change')
issues = []
for i, page in enumerate(document):
    for char in page.chars:
        if min(char['x0'],char['top']) < -1 or char['x1'] > page.width+1 or char['bottom'] > page.height+1:
            issues.append({'page': i+1, 'text': char['text']})
assert not issues, issues
images = sorted((WORK / 'render').glob('page-*.png'), key=lambda p: int(p.stem.split('-')[-1]))
assert len(images) == len(document)
for batch in range(0, len(images), 8):
    canvas = Image.new('RGB', (1320, 1900), '#d0d0d0')
    draw = ImageDraw.Draw(canvas)
    for n, path in enumerate(images[batch:batch+8]):
        img = Image.open(path).convert('RGB')
        img.thumbnail((640, 440))
        x, y = (n % 2) * 660 + (660-img.width)//2, (n//2) * 475 + 25
        canvas.paste(img, (x,y))
        draw.text(((n%2)*660+10, (n//2)*475+5), path.stem, fill='black')
    canvas.save(WORK / f'overview-{batch//8+1}.png')
receipt.update({'pdf_pages_before': len(old_document), 'pdf_pages_after': len(document),
                'pdf_body_only_changed_by_addition': True, 'pdf_outside_page_issues': issues})
(WORK / 'revision_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'pages':len(document), 'pdf_body_only_changed_by_addition': True}, ensure_ascii=False))
