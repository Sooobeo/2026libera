from pathlib import Path
from zipfile import ZipFile
from lxml import etree
import hashlib
import json
import re

WORK = Path(__file__).parent
DOCX = Path('C:/Users/Insun/Downloads/소논문_6절_결과대응_해결방안_재작성.docx')
SOURCE = WORK / 'final.md'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PR = 'http://schemas.openxmlformats.org/package/2006/relationships'
NS = {'w': W, 'r': R}
markdown = SOURCE.read_text(encoding='utf-8')
body_md = re.split(r'(?m)^\[\^\d+\]:', markdown, maxsplit=1)[0].strip()
expected_body = [p.strip().removeprefix('## ') for p in body_md.split('\n\n') if p.strip()]
expected_body = [re.sub(r'\[\^\d+\]', '', p) for p in expected_body]
expected_notes = dict(re.findall(r'(?m)^\[\^(\d+)\]:\s*(.+)$', markdown))
expected_links = re.findall(r'\]\((https?://[^)]+)\)', markdown)
with ZipFile(DOCX) as z:
    body = etree.fromstring(z.read('word/document.xml'))
    notes = etree.fromstring(z.read('word/footnotes.xml'))
    rels = etree.fromstring(z.read('word/_rels/footnotes.xml.rels'))
    doc_rels = etree.fromstring(z.read('word/_rels/document.xml.rels'))
    styles = etree.fromstring(z.read('word/styles.xml'))
actual_body = [''.join(p.xpath('.//w:t/text()', namespaces=NS)) for p in body.findall('w:body/w:p', NS)]
assert actual_body == expected_body
note_ids = [n.get('{' + W + '}id') for n in body.findall('.//w:footnoteReference', NS)]
assert note_ids == list(expected_notes)
for note_id, definition in expected_notes.items():
    actual_note = notes.xpath(f'w:footnote[@w:id="{note_id}"]', namespaces=NS)
    assert len(actual_note) == 1
    actual_text = ''.join(actual_note[0].xpath('.//w:t/text()', namespaces=NS)).strip()
    expected_text = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'\1', definition).strip()
    assert actual_text == expected_text
links = {r.get('Id'): r.get('Target') for r in rels}
assert list(links.values()) == expected_links
for link in notes.findall('.//w:hyperlink', NS):
    assert link.get('{' + R + '}id') in links
assert len(links) == len(expected_links)
assert any(r.get('Type') == R + '/footnotes' and r.get('Target') == 'footnotes.xml' for r in doc_rels)
assert body.find('.//w:footnoteReference', NS) is not None
assert not styles.xpath('//w:pBdr', namespaces=NS)
audit = json.loads((WORK / 'document_audit.json').read_text(encoding='utf-8'))
assert hashlib.sha256(DOCX.read_bytes()).hexdigest() == audit['docx_sha256']
print('FINAL DOCX BODY')
for paragraph in actual_body:
    print(paragraph)
    print()
print(json.dumps({'body_matches_final_md': True, 'footnote_texts_match': True, 'word_footnote_ids': note_ids, 'source_links': len(links), 'sha256_matches_build': True}, ensure_ascii=False))
(WORK / 'package_check.json').write_text(json.dumps({'body_matches_final_md': True, 'footnote_texts_match': True, 'footnotes': len(note_ids), 'source_links': len(links), 'docx_sha256': audit['docx_sha256']}, indent=2), encoding='utf-8')
