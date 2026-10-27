"""Source-preserving semantic units for the two long Vanguard source rules.

Profiles remain immutable. Units carry the same underlying evidence ID, so
splitting never increases the gold denominator. No model generation is used.
"""
from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone
from research.v63.exact_tokenizer import NativeTokenizer

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/v63_20261027'
SRC=DATA/'continuation_sources'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def text_sha(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)

def split_rules(profiles, lines):
    records=[]
    for profile in profiles['profiles']:
        if profile['fund_id']!='F02' or profile['period'] not in ['A_B','C']:continue
        for rule in profile['mandatory_constraints']:
            eid=rule['evidence_id']
            if eid not in ['VPMCX_BORROWING_COVER','VPMCX_LENDING']:continue
            continuation=''
            if eid=='VPMCX_BORROWING_COVER':
                texts=lines[195:198]
                locators=[[196,196],[197,197],[198,198]]
                assert ' '.join(texts)==rule['source_excerpt']
            else:
                original=' '.join(lines[504:509])
                assert original==rule['source_excerpt']
                # The immutable source selection ends with 'See'. Retain it
                # and append the actual adjacent source text to close the
                # original cross-reference sentence, rather than deleting it.
                assert original.endswith(' See')
                continuation=' '.join(lines[509:511])
                boundary=original.index(' Loan arrangements made by a fund')
                texts=[original[:boundary],original[boundary+1:]]
                locators=[[505,509],[509,511]]
                assert all(s in texts[0] for s in ['33 1 ⁄ 3 %','(1)','(2)','(3)','(4)','100%'])
            scope=f"F02 VPMCX; period={profile['period']}; {eid}; source=VPMCX_SAI_20260325, 2026-03-25. Original mandatory rule; applicable from stage 1 to every arm; not a new outlook."
            units=[];cursor=0
            for i,(t,loc) in enumerate(zip(texts,locators)):
                # Preserve separating whitespace in the preceding slice.
                raw=t+(' ' if i<len(texts)-1 else '')
                assert rule['source_excerpt'][cursor:cursor+len(raw)]==raw
                units.append(dict(unit_id=f'{eid}/U{i+1:02d}',evidence_ids=[eid],text=raw,
                    shared_context=('See '+continuation if continuation and i==len(texts)-1 else ''),
                    original_start=cursor,original_end=cursor+len(raw),
                    source_line_start=loc[0],source_line_end=loc[1]))
                cursor+=len(raw)
            assert ''.join(u['text'] for u in units)==rule['source_excerpt']
            records.append(dict(fund_id='F02',ticker='VPMCX',period=profile['period'],evidence_id=eid,
                source_document_id=rule['source_document_id'],source_url=rule['source_url'],
                original_source_excerpt=rule['source_excerpt'],source_excerpt_sha256=text_sha(rule['source_excerpt']),source_continuation=continuation,
                continuation_reason='Complete the original See Tax Status cross-reference sentence without changing the frozen profile.' if continuation else None,
                common_scope_text=scope,units=units,original_excerpt_preserved_exactly=True,
                reconstruction='concatenate unit text exactly = original_source_excerpt; final unit shared_context contains the adjacent original cross-reference sentence when needed',
                all_parts_required_for_complete_rule=True,gold_count_per_rule=1))
    assert len(records)==4
    return records

def main():
    profile_path=SRC/'profiles_v2.json';source_path=SRC/'VPMCX_SAI_20260325_text.txt'
    records=split_rules(read(profile_path),source_path.read_text(encoding='utf-8-sig').splitlines())
    tok=NativeTokenizer(read(DATA/'continuation/deployment/local_windows/tokenizer_config.json'))
    try:
        for record in records:
            for unit in record['units']:
                exact=canonical(dict(evidence_id=record['evidence_id'],source_document_id=record['source_document_id'],source_excerpt_part=unit['text'],shared_context=unit['shared_context']))
                unit['token_receipt']=tok.receipt(exact)
                assert unit['token_receipt']['token_count']<=340
        result=dict(schema_version='v2',status='semantic_source_units_with_exact_scope_token_check',
            recorded_at_utc=datetime.now(timezone.utc).isoformat(),generation_calls=0,
            tokenizer_identity=tok.identity,profiles_path=str(profile_path.relative_to(ROOT)),
            profiles_sha256=sha(profile_path),source_path=str(source_path.relative_to(ROOT)),
            source_sha256=sha(source_path),script_sha256=sha(Path(__file__)),profiles=records,
            token_rendering='canonical JSON with evidence_id, source_document_id, source_excerpt_part, shared_context; <=340 exact tokens, leaving at least 60 tokens for runtime header',
            limitation='Runtime must recheck its exact final header, chunk construction and overlap against 400 tokens.')
        out=SRC/'mandate_atomic_units_v2.json';out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'path':str(out),'sha256':sha(out),'units':sum(len(x['units']) for x in records),
                          'max_tokens':max(u['token_receipt']['token_count'] for r in records for u in r['units'])}))
    finally:tok.close()

if __name__=='__main__':main()
