import json,re
from pathlib import Path
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/v63_20261027/continuation_sources'
p=OUT/'FCNTX_annual_20251231.html';s=BeautifulSoup(p.read_bytes(),'html.parser');ts=s.find_all('table')
out=[];outside=[]
for ti in [1,2,3,4]:
    for ri,tr in enumerate(ts[ti].find_all('tr')):
        c=[td.get_text(' ',strip=True) for td in tr.find_all(['td','th'],recursive=False)]
        if len(c)<3 or not c[0] or not re.fullmatch(r'[\d,]+',c[-1]) or not re.fullmatch(r'[\d,]+',c[-2]):continue
        r={'ticker':'FCNTX','holdings_as_of':'2025-12-31','source_id':'FCNTX_annual_20251231','source_table':ti,'source_row':ri,'source_text':' | '.join(c),'name_as_extracted':c[0],'shares':int(c[-2].replace(',','')),'value_usd':int(c[-1].replace(',','')),'value_unit_in_source':'USD','security_type_in_source':{1:'Common Stocks',2:'Convertible Preferred Stocks',3:'Preferred Securities',4:'Money Market Funds'}[ti],'sic':None,'ff12':None,'human_review':'user_assumed_completed'}
        # Warrants are explicitly outside the eligible ordinary-equity sleeve even if grouped within common stocks.
        r['eligible_equity']=ti==1 and r['value_usd']>0 and 'warrant' not in r['name_as_extracted'].lower()
        (out if ti==1 else outside).append(r)
summary={'source_id':'FCNTX_annual_20251231','ticker':'FCNTX','holdings_as_of':'2025-12-31','parsed_rows':len(out),'parsed_value_usd':sum(r['value_usd'] for r in out),'reported_common_stock_value_usd':168598207235,'source_nav_usd':176314376288,'source_investments_usd':176672979099,'source_other_assets_less_liabilities_usd':-358602811}
summary['common_stock_sum_matches']=summary['parsed_value_usd']==summary['reported_common_stock_value_usd'];summary['source_accounting_identity_matches']=summary['source_investments_usd']+summary['source_other_assets_less_liabilities_usd']==summary['source_nav_usd'];summary['complete_named_schedule_value_matches']=sum(r['value_usd'] for r in out+outside)==summary['source_investments_usd']
(OUT/'parsed').mkdir(exist_ok=True)
(OUT/'parsed/FCNTX_annual_20251231.json').write_text(json.dumps({'summary':summary,'rows':out,'outside_rows':outside},indent=2),encoding='utf8')
(OUT/'FCNTX_annual_20251231.txt').write_text(s.get_text('\n',strip=True),encoding='utf8')
print(json.dumps(summary,indent=2))
