"""Check final delivery files and create page previews for human layout review."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import fitz

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
PAPER = ROOT / 'paper'
VISUAL = WORK / 'visual_qa'
NAMES = ['LIBERA_소논문_최종결과반영_20261029', 'LIBERA_본실험_결과해석_20261029']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    VISUAL.mkdir(exist_ok=True)
    numeric = json.loads((WORK / 'numeric_audit.json').read_text(encoding='utf-8'))
    source_analysis = ROOT / numeric['source_analysis']['path']
    assert digest(source_analysis) == numeric['source_analysis']['sha256']
    results = []
    for doc_number, name in enumerate(NAMES, 1):
        qa = json.loads((WORK / 'document_qa' / (name + '.render_qa.json')).read_text(encoding='utf-8'))
        assert qa['status'] == 'passed' and qa['source_unchanged']
        paths = {ext: PAPER / (name + '.' + ext) for ext in ('md', 'docx', 'html', 'pdf')}
        assert qa['source_sha256'] == digest(paths['md'])
        assert qa['docx_sha256'] == digest(paths['docx'])
        assert qa['html_sha256'] == digest(paths['html'])
        assert qa['pdf_export']['sha256'] == digest(paths['pdf'])
        document = fitz.open(paths['pdf'])
        pages = []
        previews = []
        for index, page in enumerate(document):
            text = page.get_text()
            spans = [span for block in page.get_text('dict')['blocks'] if 'lines' in block
                     for line in block['lines'] for span in line['spans'] if span['text'].strip()]
            outside = [s['text'] for s in spans if s['bbox'][0] < -1 or s['bbox'][1] < -1
                       or s['bbox'][2] > page.rect.width + 1 or s['bbox'][3] > page.rect.height + 1]
            image_blocks = page.get_image_info()
            has_figure = bool(image_blocks)
            normalized = re.sub(r'\s+', '', text)
            page_info = {'page': index + 1, 'characters': len(text.strip()), 'images': len(image_blocks),
                         'text_outside_page': outside, 'a4': abs(page.rect.width - 595.28) < 2 and abs(page.rect.height - 841.89) < 2,
                         'first_text': text.strip()[:100], 'last_text': text.strip()[-100:]}
            pages.append(page_info)
            if index == 0 or has_figure or any(key in normalized for key in ('표1.분석대상', '표6.같은펀드', '표8.관측된', '참고문헌', '표A2.')):
                output = VISUAL / f'final_doc{doc_number}_page_{index+1:02d}.png'
                page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25)).save(output)
                previews.append(str(output.relative_to(ROOT)))
        source = paths['md'].read_text(encoding='utf-8')
        assert '@@' not in source and '\ufffd' not in source
        assert all(p['a4'] and not p['text_outside_page'] and (p['characters'] > 30 or p['images']) for p in pages)
        results.append({'name': name, 'page_count': len(document), 'render_status': qa['status'],
                        'files': [{'path': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size, 'sha256': digest(p)} for p in paths.values()],
                        'pages': pages, 'visual_previews': previews})
    manifest = {'status': 'passed_content_and_pdf_geometry', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'documents': results, 'visual_review': 'Page previews generated; inspect images separately.',
                'source_analysis_sha256_reverified': digest(source_analysis),
                'experiment_data_modified': False, 'new_model_experiment_calls': 0}
    target = WORK / 'final_delivery_check.json'
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': manifest['status'], 'documents': [{'name': x['name'], 'pages': x['page_count'], 'previews': x['visual_previews']} for x in results]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
