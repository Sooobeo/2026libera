import json,copy,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/v63_20261027/continuation_sources';path=OUT/'mandates_v2.json';obj=json.loads(path.read_text(encoding='utf8'))
dev=next(p for p in obj['profiles'] if (p['fund_id'],p['period'])==('F03','development'))
ab=copy.deepcopy(dev);ab['period']='A_B';ab['version_notes']='The June 27 2025 filed prospectus/SAI, revised June 30, remains the cutoff-eligible version. SEC submission history has no later full prospectus/SAI replacement before March 31 2026; next annual replacement filed April 22 2026. Later raw HTTP recovery corroborates the retained earlier normalized evidence.'
ab['source_evidence_ids']+=['DODGX_amendment_20250627_151247','DODGX_SEC_submissions']
name='DODGX_C_full485_20260422';url='https://www.sec.gov/Archives/edgar/data/29440/000119312526169303/d21586d485bpos.htm';ls=(OUT/(name+'_text.txt')).read_text(encoding='utf8').splitlines()
c=copy.deepcopy(dev);c.update(period='C',source_url=url,source_evidence_ids=[name,'DODGX_SEC_submissions'],publication_date='2026-04-22',document_date='2026-05-01',supplement_effective_date=None,filing_accession='0001193125-26-169303',capture_method='official SEC HTTP original HTML bytes, local parsed text',evidence_sha256=hashlib.sha256((OUT/(name+'.html')).read_bytes()).hexdigest(),version_notes='May 1 2026 prospectus and SAI filed April 22 2026; SEC May 1 497J confirms definitive text unchanged from registration statement. Stock Fund sections selected explicitly.')
lines={'DODGX_EQ80':3383,'DODGX_FOREIGN20':3383,'DODGX_CURRENCY5':3383,'DODGX_INDUSTRY25':6661,'DODGX_ISSUER75':6671,'DODGX_ILLIQUID15':6676,'DODGX_TRANSACTION_SCOPE':6677,'DODGX_OTHER_RESTRICTIONS':6659,'DODGX_DEFENSIVE':3385}
for r in c['mandatory_constraints']:
 n=lines[r['evidence_id']];r.update(source_document_id=name,source_url=url,source_line=n,source_excerpt=ls[n-1])
for p in [ab,c]:
 obj['profiles']=[v for v in obj['profiles'] if (v['fund_id'],v['period'])!=('F03',p['period'])]+[p]
 (OUT/f'DODGX_{p["period"]}_mandate_evidence.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf8')
path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8');print('DODGX A_B and C mandates linked; development preserved byte-content')
