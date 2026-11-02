from pathlib import Path
import hashlib
import json
import re
import unicodedata

import fitz

ROOT = Path(__file__).resolve().parents[3]
QA = ROOT / 'tmp/intro_condensed_20261101'
DATA = json.loads((Path(__file__).parent / 'content.json').read_text(encoding='utf-8-sig'))


def plain(text):
    return re.sub(r'\[([^\]]+)\]\(https?://[^)]+\)', r'\1', re.sub(r'\[\^intro\d+\]', '', text)).replace('*', '')


def norm(text):
    return re.sub(r'\s+|\u00ad|\u200b|\ufeff', '', unicodedata.normalize('NFC', text))


pdf = fitz.open(QA / 'preview.pdf')
body = []
foot = []
outside = []
for i, page in enumerate(pdf):
    page.get_pixmap(dpi=145, alpha=False).save(QA / f'page-{i+1}.png')
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            for span in line['spans']:
                if span['size'] >= 10 and span['bbox'][1] < page.rect.height - 50:
                    body.append(span['text'])
                elif 8 <= span['size'] < 9:
                    foot.append(span['text'])
                x0, y0, x1, y1 = span['bbox']
                if min(x0, y0) < -1 or x1 > page.rect.width + 1 or y1 > page.rect.height + 1:
                    outside.append({'page': i+1, 'text': span['text']})
body_text = norm(''.join(body))
foot_text = norm(''.join(foot))
missing_body = [i+1 for i, p in enumerate(DATA['paragraphs']) if norm(plain(p)) not in body_text]
missing_notes = [n['id'] for n in DATA['notes'] if norm(plain(n['text'])) not in foot_text]
assert not missing_body, missing_body
assert not missing_notes, missing_notes
assert not outside, outside
assert '선행연구와분석틀' not in body_text
result = {'status': 'text_and_layout_bounds_passed', 'pages': len(pdf), 'paragraphs': 10,
          'native_footnotes': 8, 'missing_body': missing_body, 'missing_notes': missing_notes,
          'outside_page_spans': outside, 'visual_review_required': True,
          'docx_sha256': hashlib.sha256((ROOT / 'paper/LIBERA_소논문_서론_축약본_각주포함_20261101.docx').read_bytes()).hexdigest()}
(QA / 'pdf_check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
