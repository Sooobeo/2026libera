"""Independent accounting, mapping, provenance and source integrity checks."""
import json,hashlib,datetime,math,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'data/v63_20261027';OUT=BASE/'continuation_sources'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
checks=[]
def check(name,passed,detail=None):checks.append({'check':name,'passed':bool(passed),'detail':detail})
old=read(BASE/'source_manifest.json')
for s in old['sources']:
 if s.get('local_path') and s.get('sha256'):
  p=ROOT/s['local_path'];check('original_source_unchanged:'+s['id'],p.exists() and sha(p)==s['sha256'])
profiles=read(OUT/'profiles_v2.json')['profiles'];rows=read(OUT/'holdings_mapped_v2.json')['rows'];sicreceipts=read(OUT/'issuer_sic_manifest.json')['receipts'];sics={r['cik']:r for r in sicreceipts}
for r in sicreceipts:
 p=ROOT/r['path'];check('issuer_source_hash:'+str(r['cik']),p.exists() and sha(p)==r['sha256'])
 if p.exists():
  d=read(p);check('issuer_sic_matches_official:'+str(r['cik']),str(d.get('sic'))==str(r.get('sic')) and int(d['cik'])==int(r['cik']))
ff=read(ROOT/'data/french/sic_definitions_ff12.json')['industries']
def ff12(s):
 if not str(s).isdigit() or int(s) in (0,8880,9995) or not 0<int(s)<=9999:return None
 for d in ff[:11]:
  if any(v['low']<=int(s)<=v['high'] for v in d['sic_intervals_inclusive']):return d['id']
 return 12
check('exactly_12_fund_periods',len(profiles)==12 and len({(p['fund_id'],p['period']) for p in profiles})==12)
profile_audit=[]
for p in profiles:
 key=p['ticker']+'_'+p['period'];rr=[r for r in rows if (r['fund_id'],r['period'])==(p['fund_id'],p['period'])];d=read(ROOT/p['source_parser_path']);s=d['summary'];hs=[0.]*12
 for r in rr:
  if r['ff12']:
   check('mapped_source:'+key+':'+r['name_as_extracted'],r['eligible_equity'] and ff12(r['sic'])==r['ff12'] and r['issuer_cik'] in sics and r['sic_evidence_sha256']==sics[r['issuer_cik']]['sha256'])
   hs[r['ff12']-1]+=r['value_usd']
 mapped=sum(hs);eligible=sum(r['value_usd'] for r in rr if r['eligible_equity']);den=eligible+s.get('concealed_miscellaneous_securities_usd',0)+s.get('coverage_uncertainty_addition_usd',0)
 check('h_unit_nonnegative:'+key,len(p['h'])==12 and all(math.isfinite(x) and x>=0 for x in p['h']) and abs(sum(p['h'])-1)<1e-12)
 check('h_recomputed:'+key,max(abs(a-b/mapped) for a,b in zip(p['h'],hs))<1e-12)
 check('q_nav_recomputed:'+key,abs(p['q_NAV']-mapped/s['source_nav_usd'])<1e-12)
 check('coverage_recomputed:'+key,abs(p['coverage']-mapped/den)<1e-12 and p['coverage']>=.9)
 check('nav_same_source:'+key,p['source_NAV_usd']==s['source_nav_usd'] and s['source_accounting_identity_matches'])
 check('full_schedule:'+key,bool(s.get('common_stock_sum_matches') or s.get('complete_nport_position_schedule')))
 check('source_cutoff:'+key,p['publication_verified'] and p['publication_date']<=p['publication_cutoff'])
 check('human_override_not_fake_signatures:'+key,p['human_review_mode']=='user_assumed_completed' and p['actual_independent_signatures'] is None)
 check('mandate_rules_ready:'+key,p['mandatory_rules_verified'] and len(p['mandatory_constraints'])>0)
 check('source_gate_ready:'+key,p['scientific_ready'])
 check('sic_vintage_disclosed:'+key,'current official' in p['mapping_vintage'] and 'retrospective' in p['mapping_vintage'])
 if p['ticker']=='TRBCX':
  check('fund_shares_excluded:'+key,all(not r['eligible_equity'] for r in rr if r.get('issuer_type')=='Fund'))
 profile_audit.append({k:p[k] for k in ['fund_id','ticker','period','holdings_as_of','publication_date','publication_cutoff','source_NAV_usd','mapped_equity_value_usd','coverage_denominator_usd','coverage','q_NAV','h','complete_holdings','nav_reconciled','scientific_ready','source_evidence_ids','source_caveats']})
check('minimum_coverage',min(p['coverage'] for p in profiles)>=.9)
check('no_artificial_numerical_caps',all(p['A']==[] and p['b']==[] for p in profiles))
result={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':checks,'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks),'all_passed':all(x['passed'] for x in checks),'rows':len(rows),'mapped_rows':sum(bool(r['ff12']) for r in rows),'issuer_records':len(sicreceipts),'profiles':profile_audit}
(OUT/'data_verification_v2.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
audit={'human_review_mode':'user_assumed_completed','actual_independent_signatures':None,'meaning':'User instructed that human audit be treated as done. No independent human signatures or actual double-review event is asserted. Scientific checks above were still executed.','verification_file':'data_verification_v2.json','fund_period_evidence':profile_audit,'limitations':['Current official issuer SIC is explicitly retrospective fallback, not a historical SIC certification.','Security-level, liquidity, country, currency, transaction and source-industry rules remain semantic; FF12 reallocation is not a security-level legal compliance certificate.','TRBCX development uses a conservative coverage denominator adding the entire $641934811.73 B.2 miscellaneous aggregate as potential equity uncertainty, while source assets/NAV count all named positions only once. The equality to two named ETFs supports but does not directly prove aggregate linkage.','FCNTX development browser capture uses its complete dom_snapshot. Its truncated rendered_html field is not used.','Older mutable or ineligible source downloads and failed requests remain unchanged and are not silently substituted into the active data.'],'pending_independent_signatures':None,'original_human_forms_preserved':True}
(OUT/'human_audit_assumption_v2.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8')
print({k:v for k,v in result.items() if k not in ['checks','profiles']});print([c for c in checks if not c['passed']][:30])
