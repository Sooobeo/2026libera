"""Offline mechanical validation of this completed C F0 review; no models/services."""
from pathlib import Path
from decimal import Decimal
from fractions import Fraction
from datetime import datetime, timezone
import hashlib, json, re
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
REVIEW=HERE/'common_market_only__C__F0_review.json'
OUT=HERE/'common_market_only__C__F0_review_validation.json'
def path(v):
 p=Path(v); return p.resolve() if p.is_absolute() else (ROOT/p).resolve()
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p): return {'path':Path(p).resolve().relative_to(ROOT).as_posix(),'sha256':digest(p)}
def read(p): return json.loads(path(p).read_text(encoding='utf-8-sig'))
def ptr(obj,p):
 for k in p.split('/')[1:]:
  k=k.replace('~1','/').replace('~0','~'); obj=obj[int(k)] if isinstance(obj,list) else obj[k]
 return obj
checks=[]
def check(name,ok,detail=None): checks.append({'check':name,'pass':bool(ok),'detail':detail})
def unique(pairs):
 obj={}
 for k,v in pairs:
  if k in obj: raise ValueError('duplicate raw key')
  obj[k]=v
 return obj
r=read(REVIEW); b=read(r['bundle_ref']['path']); raw=b['raw_final_or_draft_text']; o=json.loads(raw); exact=json.loads(raw,parse_float=Decimal,parse_int=Decimal,object_pairs_hook=unique)
old=json.loads(b['own_prior_text'],parse_float=Decimal,parse_int=Decimal,object_pairs_hook=unique)
spec=read(r['worker_spec_ref']['path']); transport=read(r['transport_ref']['path']); sr=read(r['stage_review_ref']['path']); response=read(r['response_ref']['path']); math=read(r['allocation_math_ref']['path']); nf=read(r['numeric_facts_ref']['path'])
check('review_identity',r['review_status']=='completed' and r['case_id']=='common_market_only__C' and r['stage']=='F0')
check('transport_completed',transport['status']=='completed' and type(transport['generation_requests_attempted']) is int and transport['generation_requests_attempted']==1)
check('stage_instrument',sr['instrument_integrity_pass'] is True and len(sr['checks'])==10 and all(v is True for v in sr['checks'].values()))
check('response_text_bound',response['message']['content']==raw==transport['response']['message']['content'])
check('raw_sha',hashlib.sha256(raw.encode()).hexdigest()==r['raw_response_content_sha256']==b['raw_response_content_sha256'])
check('exact_own_D0_history',len(spec['body']['messages'])==4 and spec['body']['messages'][2]=={'role':'assistant','content':b['own_prior_text']} and spec['raw_draft']==b['own_prior_text'])
initial=json.loads(spec['body']['messages'][1]['content']); final=json.loads(spec['body']['messages'][3]['content'])
check('source_free_inputs',initial.get('institution_document') is None and final.get('institution_document') is None and b['source_packet'] is None and o['source_id'] is None)
check('current_market_equality',initial['common_market']==b['common_market'] and initial['public_numeric_fact_index']==b['public_numeric_fact_index'] and initial['common_context']==b['common_context'])
check('actual_feedback',final['actual_draft_calculator_feedback']==b['actual_draft_feedback'] and final['actual_draft_calculator_feedback']['allocation']['valid'] is False)
for axis in ('errors','consistency','paper_topic'): check('review_axis_'+axis,r['review_axes'][axis]['reviewed'] is True and bool(r['review_axes'][axis]['reason']))
refs={}
def findrefs(v):
 if isinstance(v,dict):
  if isinstance(v.get('path'),str) and isinstance(v.get('sha256'),str): refs[str(path(v['path']))]=(v['path'],v['sha256'])
  for x in v.values(): findrefs(x)
 elif isinstance(v,list):
  for x in v: findrefs(x)
findrefs(r)
for p,(label,h) in refs.items(): check('sha:'+label,digest(p)==h)
codes=['10','15','20','25','30','35','40','45','50','55','60']
check('eleven_canonical_rows',[x['sector_code'] for x in exact['sectors']]==codes and [x['sector_code'] for x in old['sectors']]==codes)
w=[Fraction(x['weight']) for x in exact['sectors']]; ow=[Fraction(x['weight']) for x in old['sectors']]
check('raw_sum',sum(w)==Fraction(507,500))
check('old_sum',sum(ow)==Fraction(51,50))
check('raw_delta',[a-b for a,b in zip(w,ow)]==[Fraction(-1,500) if i in (0,1,9) else 0 for i in range(11)])
check('residual',sum(w)-1==Fraction(7,500))
def units(vec):
 shares=[x/sum(vec)*10000 for x in vec]; out=[x.numerator//x.denominator for x in shares]; order=sorted(range(11),key=lambda i:(-(shares[i]-out[i]),i))
 for i in order[:10000-sum(out)]: out[i]+=1
 return out
u,ou=units(w),units(ow)
check('derived_units',u==r['independent_math_summary']['derived_units']==[x['final_units'] for x in math['rows']])
check('D0_units',ou==r['independent_math_summary']['D0_derived_units'])
check('integer_total',sum(u)==10000==math['final_total_units'])
check('derived_delta',[a-b for a,b in zip(u,ou)]==r['independent_math_summary']['derived_delta_units'])
check('derived_TV',sum(abs(a-b) for a,b in zip(u,ou))==110)
check('sidecars_independent',nf['accepted_sidecar_comparison']['matches'] is True and nf['accepted_own_D0_sidecar_comparison']['matches'] is True)
for i,row in enumerate(r['sector_reviews']):
 for k in ('source_reading_quote','decision_reason_quote'):
  q=row[k]; check('row_quote:'+str(i)+':'+k,ptr(o,q['output_pointer'])==q['quote'])
 check('source_NA:'+str(i),row['source_fidelity_applicability']=='not_applicable_no_source_supplied' and o['sectors'][i]['source_label'] is None and o['sectors'][i]['source_stance']=='not_available' and o['sectors'][i]['source_evidence_ids']==[])
 check('raw_row:'+str(i),Fraction(str(row['raw_F0_weight']))==w[i] and Fraction(str(row['raw_D0_weight']))==ow[i] and Fraction(row['raw_delta_decimal'])==w[i]-ow[i])
for i,t in enumerate(r['top_level_reviews']): check('top_quote:'+str(i),ptr(o,t['output_pointer'])==t['quote'])
for c in r['numeric_claims']:
 t=ptr(o,c['output_pointer']);check('numeric_quote:'+c['id'],t[c['start']:c['end']]==c['quote'])
 for e in c['evidence']:
  if 'bundle_pointer' in e:check('numeric_evidence:'+c['id']+e['bundle_pointer'],ptr(b,e['bundle_pointer'])==e['value'])
  if 'current_output_pointer' in e:check('numeric_current:'+c['id'],ptr(o,e['current_output_pointer'])==e['value'])
  if 'own_D0_pointer' in e:check('numeric_prior:'+c['id'],ptr(json.loads(b['own_prior_text']),e['own_D0_pointer'])==e['value'])
 if c['kind'].startswith('percent_'):
  actual=Decimal(str(c['evidence'][0]['value']))*100; delta=abs(Decimal(str(c['asserted_percent']))-actual); close=delta<=Decimal(str(c['rounding_half_unit_percent']))
  check('numeric_metric_status:'+c['id'],close==(c['status']=='supported_at_stated_precision'))
 elif c['kind']=='volatility_percent_period_unspecified':
  close=any(abs(Decimal(str(c['asserted_percent']))-Decimal(str(e['value']))*100)<=Decimal(str(c['rounding_half_unit_percent'])) for e in c['evidence'])
  check('numeric_volatility_status:'+c['id'],not close and c['status']=='contradicted_by_supplied_input')
check('numeric_count',len(r['numeric_claims'])==61==r['coverage']['numeric_claim_occurrences_extracted_and_checked'])
visible=set()
def ids(v):
 if isinstance(v,dict):
  for k in ('evidence_id','fact_id'):
   if isinstance(v.get(k),str): visible.add(v[k])
  if isinstance(v.get('columns'),list) and isinstance(v.get('rows'),list):
   for k in ('evidence_id','fact_id'):
    if k in v['columns']:
     j=v['columns'].index(k)
     for row in v['rows']:
      if isinstance(row,list) and len(row)>j and isinstance(row[j],str):visible.add(row[j])
  for z in v.values():ids(z)
 elif isinstance(v,list):
  for z in v:ids(z)
ids(initial);ids(final)
check('visible_ID_set',visible==set(b['worker_validation']['visible_evidence_ids']) and len(visible)==79)
occ=[]
def cites(v,p=''):
 if isinstance(v,dict):
  for k,z in v.items():
   np=p+'/'+k
   if k in ('source_evidence_ids','decision_evidence_ids','evidence_ids') and isinstance(z,list):
    occ.extend({'id':x,'output_pointer':np+'/'+str(i)} for i,x in enumerate(z))
   else:cites(z,np)
 elif isinstance(v,list):
  for i,z in enumerate(v):cites(z,p+'/'+str(i))
cites(o)
check('citation_count',len(occ)==77 and len({x['id'] for x in occ})==53)
check('citation_occurrence_exact',occ==b['citation_occurrences']==[{k:x[k] for k in ('id','output_pointer')} for x in r['citation_occurrence_audit']])
for i,c in enumerate(r['citation_occurrence_audit']):check('citation_visible:'+str(i),c['visible'] is True and c['id'] in visible and ptr(o,c['output_pointer'])==c['id'])
for t in r['coverage']['numeric_token_coverage']:
 text=ptr(o,t['output_pointer']);check('token_exact:'+str(len(checks)),text[t['start']:t['end']]==t['literal'])
 check('token_covered:'+str(len(checks)),bool(t['claim_ids']) or bool(t['excluded_identifier']))
 for cid in t['claim_ids']:
  c=next(x for x in r['numeric_claims'] if x['id']==cid);check('token_in_claim:'+cid,c['output_pointer']==t['output_pointer'] and c['start']<=t['start'] and c['end']>=t['end'])
check('complete_coverage',len(r['sector_reviews'])==11 and len(r['top_level_reviews'])==9 and r['coverage']['uncovered_numeric_tokens']==0 and r['coverage']['submitted_constraints_read']==len(o['submitted_constraints'])==0)
failed=[x for x in checks if not x['pass']]
receipt={'version':'last_final_semantic_review_mechanical_validation_1','status':'PASS' if not failed else 'FAIL','completed_at_utc':datetime.now(timezone.utc).isoformat(),'case_id':r['case_id'],'stage':r['stage'],'review_ref':ref(REVIEW),'transport_ref':r['transport_ref'],'validator_ref':ref(__file__),'checks_count':len(checks),'failed_checks_count':len(failed),'unique_reference_hashes_checked':len(refs),'checks':checks,'limits':['Mechanical quote/path/hash/numeric/coverage verification; qualitative entailment judgments remain the explicitly unmasked AI review.','No model/service/raw writes or ACK publication.'],'model_calls':0,'service_calls':0,'raw_modified':False}
if failed:
 print(json.dumps({'status':'FAIL','failed':failed}));raise SystemExit(1)
with OUT.open('x',encoding='utf-8',newline='\n') as h:json.dump(receipt,h,ensure_ascii=True,indent=2,allow_nan=False);h.write('\n')
print(json.dumps({'status':'PASS','checks_count':len(checks),'refs':len(refs),'review_ref':ref(REVIEW),'validation_ref':ref(OUT)}))
