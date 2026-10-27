"""Exact vocabulary-only source capacity diagnostic; no model generation."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from research.v63.exact_tokenizer import NativeTokenizer

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/v63_20261027'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)

def main():
    tokenizer=NativeTokenizer(read(DATA/'continuation/deployment/local_windows/tokenizer_config.json'))
    source=DATA/'continuation_sources/documents_v2.json'
    profiles=DATA/'continuation_sources/profiles_v2.json'
    rows=[]
    try:
        for profile in read(profiles)['profiles']:
            for rule in profile['mandatory_constraints']:
                rows.append(dict(kind='mandatory_rule',fund=profile['fund_id'],period=profile['period'],id=rule['evidence_id'],
                    tokens=tokenizer.count(canonical({'mandatory_constraint':rule})),
                    text_tokens=tokenizer.count(rule['text']),
                    excerpt_tokens=tokenizer.count(rule.get('source_excerpt','')),
                    semantic_projection_tokens=tokenizer.count(canonical({'mandatory_constraint':{k:v for k,v in rule.items() if k not in {'source_url','source_line','source_document_id','source_excerpt'}}}))))
        for doc in read(source)['documents']:
            for unit in doc['units']:
                rows.append(dict(kind='actual_document_unit',fund=doc['fund_id'],period=doc['period'],id=unit['evidence_ids'][0],
                    tokens=tokenizer.count(doc['header']+'\n'+unit['text'])))
        result=dict(recorded_at_utc=datetime.now(timezone.utc).isoformat(),engineering_only=True,model_calls=0,
                    tokenizer_identity=tokenizer.identity,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    profile_sha256=hashlib.sha256(profiles.read_bytes()).hexdigest(),
                    scope='Unit-only diagnostic; full retrieval builder still must count the exact document/chunk headers and overlap.',
                    units=len(rows),over_400=[r for r in rows if r['tokens']>400],max_tokens=max(r['tokens'] for r in rows),rows=rows)
        (DATA/'audit/source_unit_token_capacity.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(canonical({k:v for k,v in result.items() if k!='rows'}))
    finally:tokenizer.close()

if __name__=='__main__':main()
