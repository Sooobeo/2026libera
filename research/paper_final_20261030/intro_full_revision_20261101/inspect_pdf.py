"""Inspect the native Word PDF; DOCX authoring is handled by the .NET script."""
from pathlib import Path
import hashlib
import json
import re
import unicodedata

import fitz

ROOT = Path(__file__).resolve().parents[3]
TASK = Path(__file__).resolve().parent
QA = ROOT / 'tmp/intro_full_revision_20261101/qa'
STAGE = QA.parent / 'staged'
STEM = 'LIBERA_소논문_최종결과반영_20261030'
data = json.loads((TASK / 'content.json').read_text(encoding='utf-8-sig'))


def normalized(text):
    return re.sub(r'\s+|\u200b|\ufeff|\u00ad', '', unicodedata.normalize('NFC', text))


def plain(text):
    text = re.sub(r'\[\^intro\d+\]', '', text)
    return re.sub(r'\[([^\]]+)\]\(https?://[^)]+\)', r'\1', text).replace('*', '')


pdf = fitz.open(STAGE / (STEM + '.pdf'))
body_parts = []
foot_parts = []
outside = []
intro_pages = []
pages = []
QA.mkdir(parents=True, exist_ok=True)
for index, page in enumerate(pdf):
    spans = []
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            for span in line['spans']:
                spans.append(span)
                if span['size'] >= 10 and span['bbox'][1] < page.rect.height - 50:
                    body_parts.append(span['text'])
                elif 8 <= span['size'] < 9:
                    foot_parts.append(span['text'])
                x0, y0, x1, y1 = span['bbox']
                if x0 < -1 or y0 < -1 or x1 > page.rect.width + 1 or y1 > page.rect.height + 1:
                    outside.append({'page': index + 1, 'text': span['text'], 'bbox': span['bbox']})
    target = QA / f'page-{index + 1:02d}.png'
    page.get_pixmap(dpi=130, alpha=False).save(target)
    if any('GenAI' in s['text'] for s in spans) and index < 8:
        intro_pages.append(index + 1)
    pages.append({'page': index + 1, 'image': str(target.relative_to(ROOT)), 'text_chars': len(page.get_text()), 'image_count': len(page.get_images())})

body = normalized(''.join(body_parts))
foot = normalized(''.join(foot_parts))
missing_paragraphs = [i + 1 for i, p in enumerate(data['paragraphs']) if normalized(plain(p)) not in body]
missing_notes = [n['id'] for n in data['notes'] if normalized(plain(n['text'])) not in foot]
report = {'status': 'passed' if not (outside or missing_paragraphs or missing_notes) else 'needs_review',
          'pages': len(pdf), 'introduction_paragraphs_checked': len(data['paragraphs']),
          'missing_introduction_paragraphs': missing_paragraphs, 'missing_footnotes': missing_notes,
          'outside_page_spans': outside, 'page_images': pages,
          'pdf_sha256': hashlib.sha256((STAGE / (STEM + '.pdf')).read_bytes()).hexdigest(),
          'visual_review_required': True}
(QA / 'pdf_check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in report.items() if k != 'page_images'}, ensure_ascii=False))
