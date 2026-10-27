"""Read-only cross-audit against original SEC submission indexes and canonical fund IDs."""
import json,re,hashlib,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'data/v63_20261027';OUT=BASE/'continuation_sources'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
protected=['profiles_v2.json','mandates_v2.json','source_manifest_v2.json'];before={n:sha(OUT/n) for n in protected};checks=[]
def check(label,passed,detail=None):checks.append({'check':label,'passed':bool(passed),'detail':detail})
funds={'F01':('FCNTX',24238),'F02':('VPMCX',752177),'F03':('DODGX',29440),'F04':('TRBCX',902259)}
indexes={}
for fid,(ticker,cik) in funds.items():
 d=read(BASE/f'raw/{ticker}_SEC_submissions.json');r=d['filings']['recent'];check('SEC_index_CIK:'+fid,int(d['cik'])==cik)
 indexes[fid]={a:{k:r[k][i] for k in ['filingDate','form','primaryDocument']} for i,a in enumerate(r['accessionNumber'])}
profiles=read(OUT/'profiles_v2.json')['profiles'];mandates={(p['fund_id'],p['period']):p for p in read(OUT/'mandates_v2.json')['profiles']}
for p in profiles:
 fid=p['fund_id'];key=fid+'_'+p['period'];ticker,cik=funds[fid];m=mandates[(fid,p['period'])]
 check('canonical_profile_fund:'+key,p['ticker']==ticker)
 for kind,acc,date in [('holdings',p['publication_accession'],p['publication_date']),('mandate',m['filing_accession'],m['publication_date'])]:
  indexed=indexes[fid].get(acc);check('indexed_filing_date:'+kind+':'+key,bool(indexed) and indexed['filingDate']==date and date<=p['publication_cutoff'],{'accession':acc,'claimed_date':date,'SEC_index':indexed})
 check('unique_rule_ids:'+key,len({r['evidence_id'] for r in m['mandatory_constraints']})==len(m['mandatory_constraints']))
 for r in m['mandatory_constraints']:
  rk=key+':'+r['evidence_id'];a=re.search(r'/Archives/edgar/data/(\d+)/(\d{18})/',r['source_url']);check('rule_official_owner:'+rk,a and int(a[1])==cik)
  if a:
   digits=a[2];acc=digits[:10]+'-'+digits[10:12]+'-'+digits[12:];idx=indexes[fid].get(acc);check('rule_indexed_before_cutoff:'+rk,idx and idx['filingDate']<=p['publication_cutoff'],idx)
  src=r['source_document_id'];txt=OUT/(src+'_text.txt')
  candidates=list(OUT.glob(src+'.*'));check('rule_evidence_file_exists:'+rk,bool(candidates) or txt.exists(),src)
  if txt.exists() and r.get('source_excerpt'):
   ls=txt.read_text(encoding='utf8').splitlines();a=r['source_line'];b=r.get('source_line_end',a);excerpt=' '.join(ls[a-1:b]);check('rule_source_pointer_exact:'+rk,excerpt==r['source_excerpt'])
  check('no_business_day_rewording:'+rk,'business days' not in r['text'])
 docs=read(OUT/'documents_v2.json')['documents']
for d in docs:
 did=d['document_id'];fid=d['fund_id'];date=d['publication_date'];path=ROOT/d['source_path']
 check('corpus_original_hash:'+did,path.exists() and sha(path)==d['source_bytes_sha256'])
 check('corpus_period_date:'+did,date<='2026-03-31' if d['period']=='A' else '2026-04-01'<=date<='2026-06-30')
 if fid!='COMMON':
  ticker,cik=funds[fid];check('corpus_canonical_fund_id:'+did,ticker in did,{'canonical_ticker':ticker,'document_id':did})
  url=d['source_url'];a=re.search(r'/Archives/edgar/data/(\d+)/',url)
  check('corpus_official_owner:'+did,int(a[1])==cik if a else ('troweprice.com' in url if ticker=='TRBCX' else 'dodgeandcox.com' in url if ticker=='DODGX' else False),url)
for n in protected:check('protected_file_unchanged:'+n,before[n]==sha(OUT/n))
result={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'profile_input_sha256':before['profiles_v2.json'],'source_manifest_sha256':before['source_manifest_v2.json'],'corpus_sha256':sha(OUT/'documents_v2.json'),'checks':checks,'passed':sum(c['passed'] for c in checks),'failed':sum(not c['passed'] for c in checks),'all_passed':all(c['passed'] for c in checks),'manual_review_notes':['F01 C restrictions cite same Fidelity Contrafund Class K, not the distinct Contrafund K6 portfolio; only fund-wide investment rules are used.','VPMCX SAI 50%-basket language explicitly excludes PRIMECAP. The subsequent single-issuer 25% rule applies to each fund.','TRBCX common SAI explicitly excludes Blue Chip Growth from diversified-fund issuer caps; 25% industry rule uses NAV and provider/adviser taxonomy.','FCNTX illiquid rule changed 10% to 15% in May 15 2026 amendment; this is applied only in C.','SIC is current official issuer fallback with retrospective classification; h uses mapped eligible equity and q_NAV uses matched same-source NAV.','A historical shareholder-performance commentary is labeled historical, not relabeled forward-looking outlook; common FOMC March/June outlook serves the corresponding source-date windows.']}
(OUT/'source_cross_audit_v2.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print({k:result[k] for k in ['passed','failed','all_passed']});print([c for c in checks if not c['passed']])
