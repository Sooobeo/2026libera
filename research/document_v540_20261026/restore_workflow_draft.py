import json
from pathlib import Path
import re

root = Path(__file__).resolve().parent
source = json.loads((root.parent.parent / 'paper/v530_manuscript_20261026.json').read_text(encoding='utf-8'))
tables = {b['caption'].split()[1]: b for b in source['blocks'] if b['type'] == 'table'}
raw = (root / 'workflow_rag_draft_restored_source.md').read_text(encoding='utf-8')
blocks = []
rendered = []
for part in raw.strip().split('\n\n'):
    if part.startswith('# '):
        blocks.append({'type': 'heading', 'level': 1, 'text': part[2:]})
        rendered.append(part)
    elif part.startswith('## '):
        blocks.append({'type': 'heading', 'level': 2, 'text': part[3:]})
        rendered.append(part)
    elif part.startswith('{{TABLE:'):
        number = re.fullmatch(r'\{\{TABLE:(\d+)\}\}', part)[1]
        table = tables[number]
        blocks.append(table)
        rows = [table['caption'], '', '| ' + ' | '.join(table['headers']) + ' |', '| ' + ' | '.join(['---'] * len(table['headers'])) + ' |']
        rows.extend('| ' + ' | '.join(str(cell).replace('\n', '<br>') for cell in row) + ' |' for row in table['rows'])
        rows.extend(['', table.get('note', '')])
        rendered.append('\n'.join(rows))
    else:
        blocks.append({'type': 'paragraph', 'text': part})
        rendered.append(part)
start = next(b['text'] for b in source['blocks'] if b.get('type') == 'heading' and b.get('text', '').startswith('8 '))
stop = next(b['text'] for b in source['blocks'] if b.get('type') == 'heading' and b.get('text', '').startswith('10 '))
result = {'source': 'paper/v530_manuscript_20261026.json', 'replace_from_heading': start, 'replace_until_before_heading': stop, 'blocks': blocks}
json_path = root / 'workflow_rag_draft.json'
md_path = root / 'workflow_rag_draft.md'
json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
md_path.write_text('\n\n'.join(rendered) + '\n', encoding='utf-8')
receipt = {}
for path in (json_path, md_path):
    text = path.read_text(encoding='utf-8')
    hangul = [c for c in text if '\uac00' <= c <= '\ud7a3']
    assert len(hangul) > 3000, (path, len(hangul))
    assert text.count('?') == 0, (path, text.count('?'))
    receipt[path.name] = {'bytes': path.stat().st_size, 'hangul_count': len(hangul), 'question_mark_count': text.count('?'), 'first_hangul_codepoint': ord(hangul[0]), 'heading_sample': next((b['text'] for b in blocks if b['type'] == 'heading'))}
assert len(blocks) == 41
for t in [b for b in blocks if b['type'] == 'table']:
    assert t == tables[t['caption'].split()[1]]
(root / 'workflow_rag_encoding_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(receipt, ensure_ascii=True))
