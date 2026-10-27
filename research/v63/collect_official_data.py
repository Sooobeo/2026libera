"""Acquire public official evidence without changing v6.3's source contract.

No retries, identity rotation, or replacement holdings. HTTP failures are retained.
This prepares evidence; it does not certify historical eligibility or human review.
"""
from __future__ import annotations
import argparse, hashlib, json, re, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data' / 'v63_20261027'
USER_AGENT = 'LIBERA academic research data collection'

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def acquire(identifier, url, metadata=None):
    receipt = OUT / 'receipts' / (identifier + '.json')
    if receipt.exists():
        return json.loads(receipt.read_text(encoding='utf-8'))
    result = {'id': identifier, 'requested_url': url, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
              'request_user_agent': USER_AGENT, 'metadata': metadata or {}, 'historical_eligibility': 'unverified',
              'human_review': 'pending', 'attempts': 1}
    try:
        response = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=40)
        content = response.content
        kind = 'pdf' if content.startswith(b'%PDF-') else ('json' if 'json' in response.headers.get('Content-Type', '') else ('xml' if b'<edgarSubmission' in content[:1500] else 'html'))
        path = OUT / ('raw' if response.ok else 'failed_responses') / (identifier + '.' + kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        result.update({'status': 'downloaded' if response.ok else 'http_error', 'http_status': response.status_code,
                       'final_url': response.url, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest(),
                       'content_type': response.headers.get('Content-Type'), 'server_last_modified': response.headers.get('Last-Modified'),
                       'server_date': response.headers.get('Date'), 'local_path': str(path.relative_to(ROOT)).replace('\\','/')})
    except requests.RequestException as exc:
        result.update({'status': 'request_error', 'error_type': type(exc).__name__, 'error': str(exc)})
    dump(receipt, result)
    print(json.dumps({k:result.get(k) for k in ['id','status','http_status','bytes']}, ensure_ascii=False), flush=True)
    time.sleep(.15)
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--inventory-documents', action='store_true')
    args=parser.parse_args()
    inventory=json.loads((ROOT/'data/documentary/source_inventory.json').read_text(encoding='utf-8-sig'))
    candidates=[]
    target_dates={'2025-09-30','2025-12-31','2026-03-31'}
    for fund in inventory['funds']:
        ticker=fund['ticker']; cik=fund['cik']
        rec=acquire(ticker+'_SEC_submissions','https://data.sec.gov/submissions/CIK'+cik+'.json',{'ticker':ticker,'role':'official_filing_discovery','cik':cik})
        if rec['status']=='downloaded':
            data=json.loads((ROOT/rec['local_path']).read_text(encoding='utf-8'))
            recent=data['filings']['recent']
            for i, form in enumerate(recent['form']):
                report_date=recent['reportDate'][i]
                filing_date=recent['filingDate'][i]
                if (form in ['NPORT-P','NPORT-P/A','N-CSR','N-CSRS'] and report_date in target_dates) or (form in ['497','497K','485BPOS','485APOS'] and '2025-01-01'<=filing_date<='2026-06-30'):
                    accession=recent['accessionNumber'][i]
                    base='https://www.sec.gov/Archives/edgar/data/'+str(int(cik))+'/'+accession.replace('-','')+'/'
                    candidates.append({'ticker':ticker,'target_series':fund['series'],'cik':cik,'accession':accession,'form':form,
                        'report_date':report_date,'filing_date':filing_date,'acceptance_datetime':recent['acceptanceDateTime'][i],
                        'primary_document':recent['primaryDocument'][i], 'url':base+recent['primaryDocument'][i],
                        'index_url':base+accession+'-index.htm','series_identity_checked':False,
                        'note':'Registrant may contain other series; series identifier must match inside original document.'})
        if args.inventory_documents:
            for source in fund['sources']:
                if source.get('type') or source.get('accession') or 'annual' in source['id'].lower():
                    url=source.get('retrieved_document_url') or source['url']
                    acquire(source['id'],url,{'ticker':ticker,'role':source.get('role'),'claimed_cover_date':source.get('cover_date'), 'claimed_report_as_of':source.get('report_as_of')})
    dump(OUT/'filing_candidates.json',candidates)
    extra=[
      ('DODGX_manager_holdings_current','https://www.dodgeandcox.com/content/dam/dc/us/en/pdf/PortfolioHoldings/Dodge_Cox_Stock_Fund_Portfolio_Holdings.pdf','DODGX','holdings'),
      ('TRBCX_manager_quarterly_review_current','https://www.troweprice.com/literature/public/country/us/language/en/literature-type/quarterly-review/sub-type/multi-class?currency=USD&productCode=BCG','TRBCX','outlook'),
      ('TRBCX_manager_portfolio_update_current','https://www.troweprice.com/literature/public/country/us/language/en/literature-type/portfolio-update/sub-type/portfolio-update?currency=USD&productCode=BCG','TRBCX','holdings_summary'),
      ('TRBCX_manager_q4_holdings_mutable','https://individual.troweprice.com/staticFiles/gcFiles/pdf/phbcgq4.pdf','TRBCX','holdings'),
      ('VPMCX_manager_factbook_current','https://workplace.vanguard.com/iippdf/pdfs/fundbooks/0059.pdf','VPMCX','outlook_and_summary'),
      ('FCNTX_manager_annual_2025','https://www.actionsxchangerepository.fidelity.com/ShowDocument/1049393/FaxToCDocument.htm?applicationId=SPPI&clientId=Fidelity&collectionId=1049393&criticalIndicator=N&docFormat=html&docName=CON-ANN.html&docType=ANN&extraId=1775834875244&securityId=316071109&securityIdType=CUSIP&tocIndicator=false','FCNTX','annual_holdings_report'),
    ]
    for identifier,url,ticker,role in extra:
        acquire(identifier,url,{'ticker':ticker,'role':role,'mutable_url':True})
    receipts=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((OUT/'receipts').glob('*.json'))]
    dump(OUT/'source_manifest.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'purpose':'v6.3 official source acquisition, not a certified historical corpus','sources':receipts,'filing_candidates':len(candidates),'historical_eligibility_verified':False,'human_review_complete':False,'holdings_ready':False})

if __name__=='__main__': main()
