"""Compare every page pixel against the reviewed prior render."""
from pathlib import Path
import json
from PIL import Image, ImageChops

WORK = Path(__file__).resolve().parent
old, new = WORK / 'qa/word_r2', WORK / 'qa/word_r3'
rows = []
for p in sorted(new.glob('page-*.png'), key=lambda p: int(p.stem.split('-')[1])):
    prior = old / p.name
    same = False
    if prior.exists():
        with Image.open(prior) as a, Image.open(p) as b:
            same = a.size == b.size and ImageChops.difference(a.convert('RGB'), b.convert('RGB')).getbbox() is None
    rows.append({'page': int(p.stem.split('-')[1]), 'pixel_identical_to_reviewed_r2': same})
report = {'pages': rows, 'identical_pages': [r['page'] for r in rows if r['pixel_identical_to_reviewed_r2']], 'changed_pages': [r['page'] for r in rows if not r['pixel_identical_to_reviewed_r2']]}
(new / 'render_comparison.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report))
