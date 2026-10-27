import json,datetime,hashlib,time,requests
from pathlib import Path
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[2]; BASE=ROOT/'data/v63_20261027'; OUT=BASE/'continuation_sources'
receipts=[]
for ticker in ['FCNTX','TRBCX','DODGX']:
 d=json.loads((BASE/f'raw/{ticker}_SEC_submissions.json').read_text(encoding='utf8')); r=d['filings']['recent']
 for i,form in enumerate(r['form']):
  date=r['filingDate'][i]
  if form!='497' or not '2025-03-01'<=date<='2026-06-30':continue
  acc=r['accessionNumber'][i];doc=r['primaryDocument'][i];url=f"https://www.sec.gov/Archives/edgar/data/{int(d['cik'])}/{acc.replace('-','')}/{doc}"
  name=f'{ticker}_amendment_{date.replace("-","")}_{acc[-6:]}'
  path=OUT/(name+'.html');receipt=OUT/(name+'_receipt.json')
  if receipt.exists():receipts.append(json.loads(receipt.read_text(encoding='utf8')));continue
  q=requests.get(url,headers={'User-Agent':'Libera academic research source verification contact research@example.org'},timeout=90)
  item={'source_id':name,'ticker':ticker,'source_url':url,'filing_date':date,'accession':acc,'status':q.status_code,'acquired_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':hashlib.sha256(q.content).hexdigest(),'bytes':len(q.content)}
  if q.status_code==200:
   path.write_bytes(q.content);txt='\n'.join(' '.join(x.split()) for x in BeautifulSoup(q.content,'lxml').stripped_strings);(OUT/(name+'_text.txt')).write_text(txt,encoding='utf8');item['text_chars']=len(txt)
  receipt.write_text(json.dumps(item,indent=2),encoding='utf8');receipts.append(item);print(name,q.status_code,item.get('text_chars'));time.sleep(.12)
(OUT/'mandate_amendment_manifest.json').write_text(json.dumps(receipts,indent=2),encoding='utf8')
