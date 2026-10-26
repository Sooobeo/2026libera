from pathlib import Path
from PIL import Image, ImageChops
import json
import argparse

WORK = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--prior', default='word_r1')
parser.add_argument('--run', default='word_r3')
args = parser.parse_args()
prior, final = WORK / 'qa' / args.prior, WORK / 'qa' / args.run
same, changed = [], []
for path in sorted(final.glob('page-*.png'), key=lambda p: int(p.stem.split('-')[1])):
    n = int(path.stem.split('-')[1])
    before = prior / path.name
    identical = False
    if before.exists():
        with Image.open(before) as a, Image.open(path) as b:
            identical = a.size == b.size and ImageChops.difference(a.convert('RGB'), b.convert('RGB')).getbbox() is None
    (same if identical else changed).append(n)
result = {'prior': args.prior, 'run': args.run, 'pixel_identical_to_reviewed_prior': same, 'changed_pages_to_review': changed}
(final / 'render_comparison.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result))
