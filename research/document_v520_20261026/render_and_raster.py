"""Attempt the skill renderer or raster the isolated Word-rendered PDF."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
DEP = Path('C:/Users/Insun/.cache/codex-runtimes/codex-primary-runtime/dependencies')
SKILL = Path('C:/Users/Insun/.codex/plugins/cache/openai-primary-runtime/documents/26.1020.11348/skills/documents')
DOCX = ROOT / 'paper/LIBERA_소논문_시각화포함_v5.2_20261026.docx'


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['packaged', 'raster'])
    ap.add_argument('--run', default='word_r1')
    args = ap.parse_args()
    if args.mode == 'packaged':
        out = WORK / 'qa/packaged'
        out.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PATH'] = os.pathsep.join(str(x) for x in [DEP / 'python', DEP / 'bin/override', DEP / 'native/poppler/Library/bin', Path('C:/Windows/System32')])
        cmd = [sys.executable, str(SKILL / 'render_docx.py'), str(DOCX), '--output_dir', str(out), '--emit_pdf', '--dpi', '144', '--verbose']
        with (out / 'render.log').open('w', encoding='utf-8') as log:
            result = subprocess.run(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        manifest = json.loads((DEP.parent / 'runtime.json').read_text(encoding='utf-8'))
        receipt = {'command': cmd, 'exit_code': result.returncode, 'bundled_libreoffice': manifest['libreOfficeVersion'], 'desktop_libreoffice_allowed': False, 'docx_sha256': digest(DOCX), 'log': str(out / 'render.log')}
        (out / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        print((out / 'render.log').read_text(encoding='utf-8')[-4500:])
        return result.returncode
    from pypdf import PdfReader
    from pdf2image import convert_from_path
    out = WORK / 'qa' / args.run
    pdf = out / 'manuscript.pdf'
    pages = []
    for i, page in enumerate(PdfReader(str(pdf)).pages, 1):
        text = page.extract_text() or ''
        (out / f'page-{i}.txt').write_text(text, encoding='utf-8')
        pages.append({'page': i, 'characters': len(text), 'start': text[:130], 'end': text[-130:]})
    paths = convert_from_path(str(pdf), dpi=144, fmt='png', thread_count=2, poppler_path=str(DEP / 'native/poppler/Library/bin'), output_folder=str(out), paths_only=True, output_file='raster')
    for i, p in enumerate(paths, 1):
        Path(p).rename(out / f'page-{i}.png')
    receipt = {'renderer': 'isolated Microsoft Word PDF and bundled Poppler', 'docx_sha256': digest(DOCX), 'pdf_sha256': digest(pdf), 'dpi': 144, 'pages': pages, 'pngs': [str(out / f'page-{i}.png') for i in range(1, len(paths)+1)], 'visual_review': 'pending', 'python': sys.executable}
    (out / 'raster_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'pages': len(paths), 'out': str(out)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
