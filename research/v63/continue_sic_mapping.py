"""Official issuer SIC acquisition; no SIC is inferred from company names."""
import json,re,hashlib,time,sys
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/v63_20261027/continuation_sources'
OUT.mkdir(parents=True,exist_ok=True)
def norm(s):
    s=s.lower().replace('&','and')
    s=re.sub(r'^[*,\d\s]+','',s)
    s=re.sub(r'/.*$','',s)
    s=re.sub(r'\([^)]*\)|\bclass\s*[abc]\b|\badr\b|\badr\s*\d+\b','',s)
    s=re.sub(r'[^a-z0-9]','',s)
    if s.startswith('the'):s=s[3:]
    s=s.replace('reit','')
    for suf in ['commonstock','classa','classb','classc','spnsradr','sponsoredadr','adr','holdingcompany','holdingsinc','holdingscorp','corporation','incorporated','limited','company','holdings','holding','inc','corp','plc','ltd','co','sa','nv','ag']:
        if s.endswith(suf):s=s[:-len(suf)]
    return s
def index():
    entries={}
    for p in OUT.glob('company_tickers_web_*.txt'):
        t=re.sub(r'\nL\d+:\s*',' ',p.read_text(encoding='utf8'))
        for v in re.findall(r'\{"cik_str":\d+,"ticker":"[^"]+","title":"[^"]+"\}',t):
            d=json.loads(v);entries[d['ticker']]=d
    (OUT/'issuer_identifier_candidates.json').write_text(json.dumps(list(entries.values()),indent=2),encoding='utf8')
    return entries
def proposals():
    entries=index();ns={}
    for d in entries.values():ns.setdefault(norm(d['title']),[]).append(d)
    names={}
    for p in list((ROOT/'data/v63_20261027/parsed').glob('*.json'))+list((OUT/'parsed').glob('*.json')):
        for r in json.loads(p.read_text(encoding='utf8'))['rows']:
            names.setdefault(r['name_as_extracted'],0);names[r['name_as_extracted']]+=r['value_usd']
    out=[]
    for name,value in sorted(names.items(),key=lambda x:-x[1]):
        matches=ns.get(norm(name),[])
        cikset={d['cik_str'] for d in matches}
        out.append({'name':name,'normal_form':norm(name),'aggregate_value':value,'matches':matches,'confirmed_cik':next(iter(cikset)) if len(cikset)==1 else None,'identity_method':'exact_legal_name_normalization' if len(cikset)==1 else None})
    (OUT/'issuer_match_proposals.json').write_text(json.dumps(out,indent=2),encoding='utf8')
    print('entries',len(entries),'names',len(out),'exact',sum(r['confirmed_cik'] is not None for r in out))
    print('\n'.join(r['name'] for r in out if not r['confirmed_cik']))
def acquire():
    proposals=json.loads((OUT/'issuer_match_proposals.json').read_text())
    overrides=json.loads((OUT/'issuer_identity_overrides.json').read_text()) if (OUT/'issuer_identity_overrides.json').exists() else {}
    receipts=[]
    for r in proposals:
        r.update(overrides.get(r['name'],{}))
    ciks=sorted({r['confirmed_cik'] for r in proposals if r['confirmed_cik']})
    rd=OUT/'issuer_submissions';rd.mkdir(exist_ok=True)
    for i,cik in enumerate(ciks):
        url=f'https://data.sec.gov/submissions/CIK{cik:010d}.json';p=rd/f'CIK{cik:010d}.json';rec=p.with_suffix('.receipt.json')
        if rec.exists():receipts.append(json.loads(rec.read_text()));continue
        try:
            res=requests.get(url,headers={'User-Agent':'LIBERA academic research data collection contact research@example.com','Accept':'application/json'},timeout=25)
            p.write_bytes(res.content)
            d={'cik':cik,'url':url,'status':res.status_code,'bytes':len(res.content),'sha256':hashlib.sha256(res.content).hexdigest(),'path':str(p.relative_to(ROOT)),'retrieved_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
            if res.status_code==200:
                j=res.json();d.update({'official_name':j.get('name'),'sic':j.get('sic'),'sicDescription':j.get('sicDescription'),'tickers':j.get('tickers'),'sic_temporal_basis':'current_SEC_issuer_record; historical continuity not yet certified'})
        except Exception as e:d={'cik':cik,'url':url,'error':str(e)}
        rec.write_text(json.dumps(d,indent=2),encoding='utf8');receipts.append(d);time.sleep(.15)
        if i%20==0:print('acquired',i+1,'/',len(ciks),flush=True)
    (OUT/'issuer_sic_manifest.json').write_text(json.dumps({'receipts':receipts},indent=2),encoding='utf8')
    bycik={r['cik']:r for r in receipts}
    for r in proposals:
        rec=bycik.get(r['confirmed_cik'],{});r['official_sic']=rec.get('sic');r['sic_source_url']=rec.get('url');r['sic_evidence_sha256']=rec.get('sha256');r['official_name']=rec.get('official_name')
    (OUT/'issuer_sic_mapping.json').write_text(json.dumps(proposals,indent=2),encoding='utf8')
if __name__=='__main__':
    if '--acquire' in sys.argv:acquire()
    else:proposals()
