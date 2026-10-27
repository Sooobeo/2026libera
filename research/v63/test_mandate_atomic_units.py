"""Actual source reconstruction checks; not simulated model experiments."""
from pathlib import Path
import hashlib
import json
from research.v63.split_mandate_sources import split_rules

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'data/v63_20261027/continuation_sources'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))

def test_actual_slices_exactly_restore_immutable_source_excerpts():
    profiles=read(SRC/'profiles_v2.json')
    lines=(SRC/'VPMCX_SAI_20260325_text.txt').read_text(encoding='utf-8-sig').splitlines()
    rows=split_rules(profiles,lines)
    assert len(rows)==4
    for row in rows:
        excerpt=row['original_source_excerpt']
        assert ''.join(u['text'] for u in row['units'])==excerpt
        assert hashlib.sha256(excerpt.encode()).hexdigest()==row['source_excerpt_sha256']
        for unit in row['units']:
            assert unit['text']==excerpt[unit['original_start']:unit['original_end']]
        assert row['gold_count_per_rule']==1
        if row['evidence_id']=='VPMCX_LENDING':
            assert all(s in row['units'][0]['text'] for s in ['33 1 ⁄ 3 %','100%','(1)','(2)','(3)','(4)'])
            assert row['units'][-1]['shared_context']=='See '+' '.join(lines[509:511])
        else:
            first=row['units'][0]['text']
            assert all(s in first for s in ['300%','5%','three days','excluding Sundays and holidays'])
            assert 'Rule 18f-4' in row['units'][-1]['text']

def test_saved_exact_token_receipts_bind_to_rendered_parts():
    from research.v63.split_mandate_sources import canonical
    artifact=read(SRC/'mandate_atomic_units_v2.json')
    assert artifact['profiles_sha256']==hashlib.sha256((SRC/'profiles_v2.json').read_bytes()).hexdigest()
    for row in artifact['profiles']:
        for u in row['units']:
            text=canonical(dict(evidence_id=row['evidence_id'],source_document_id=row['source_document_id'],source_excerpt_part=u['text'],shared_context=u['shared_context']))
            receipt=u['token_receipt']
            assert receipt['text_sha256']==hashlib.sha256(text.encode()).hexdigest()
            assert receipt['token_count']<=340
            assert receipt['generation_calls']==0
            assert receipt['method']=='exact_installed_libllama_vocab_only'
