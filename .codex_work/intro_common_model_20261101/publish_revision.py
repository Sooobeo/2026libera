from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
STEM = 'LIBERA_소논문_최종결과반영_20261030'
receipt = json.loads((WORK / 'revision_receipt.json').read_text(encoding='utf-8'))
assert receipt['pdf_body_only_changed_by_addition']
assert not receipt['pdf_outside_page_issues']

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

for ext in ['.md', '.docx', '.html', '.pdf']:
    current = ROOT / 'paper' / (STEM + ext)
    assert sha(current) == receipt['originals'][current.name], 'Source changed during review'

composer = ROOT / 'research/paper_final_20261030/compose_final_paper.py'
composer_before = composer.read_text(encoding='utf-8')
anchor = '공통 모델에 대한 의존은 최종 배분을 자동화하기 전부터 형성될 수 있다.'
assert composer_before.count(anchor) == 1
shutil.copy2(composer, WORK / 'before' / composer.name)
composer.write_text(composer_before.replace(anchor, receipt['addition'] + '\n\n' + anchor, 1), encoding='utf-8', newline='\n')

for ext in ['.md', '.docx', '.html', '.pdf']:
    destination = ROOT / 'paper' / (STEM + ext)
    shutil.copy2(WORK / 'stage' / destination.name, destination)

index = ROOT / 'paper/README.txt'
shutil.copy2(index, WORK / 'before' / 'README.txt')
index_text = index.read_text(encoding='utf-8')
note = '2026-11-01 부분 수정: 서론 첫 문단 뒤에 실무자의 성능 선호가 동일 모델 선택의 집중으로 이어질 수 있다는 출발 가정 세 문장을 추가했다. Word·PDF·HTML·본문 원본에 동일하게 반영했다.'
assert note not in index_text
index.write_text(index_text.replace('2026년 10월 30일\n', '2026년 10월 30일\n\n' + note + '\n', 1), encoding='utf-8', newline='\n')

receipt.update({
    'status': 'verified_and_published',
    'review': 'All 36 rendered pages visually inspected; original PDF body preserved except the three-sentence addition.',
    'published_at_utc': datetime.now(timezone.utc).isoformat(),
    'artifacts': [{'path': str((ROOT / 'paper' / (STEM + ext)).relative_to(ROOT)),
                   'sha256': sha(ROOT / 'paper' / (STEM + ext))} for ext in ['.md', '.docx', '.html', '.pdf']],
})
(WORK / 'revision_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
(ROOT / 'research/paper_final_20261030/intro_revision_20261101.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'status': receipt['status'], 'artifacts': [a['path'] for a in receipt['artifacts']]}, ensure_ascii=False))
