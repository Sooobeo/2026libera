"""Build source-preserving A/C original-section corpus, without LLM summaries.

Run with the existing system Python (BeautifulSoup/PyMuPDF). Exact model token
counts are deliberately left to build_run and the pinned remote tokenizer.
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
import fitz

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/v63_20261027'
SRC=DATA/'continuation_sources'
OUTLOOK=SRC/'outlook'
PROTOCOL_PATH=next((ROOT/'plan').glob('*v6.3*.json'))
FUNDS=json.loads(PROTOCOL_PATH.read_text(encoding='utf-8-sig'))['data_contract']['funds']
BY_TICKER={f['ticker']:f for f in FUNDS}
BY_ID={f['fund_id']:f for f in FUNDS}

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def clean(text):return re.sub(r'\s+',' ',text).strip()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def sentence_units(text,limit=780):
    """Contiguous source text; split only at sentence ends, never inside a row.

    An unusually long indivisible sentence is rejected for explicit resolution.
    Joining the result with spaces reconstructs normalized source text exactly.
    """
    text=clean(text)
    bits=re.split(r'(?<=[.!?])\s+(?=[A-Z“"(])',text)
    if any(len(x)>limit for x in bits):
        raise ValueError('Oversized source sentence: '+max(bits,key=len)[:100])
    out=[];pending=''
    for bit in bits:
        if pending and len(pending+' '+bit)>limit:out.append(pending);pending=''
        pending=(pending+' '+bit).strip()
    if pending:out.append(pending)
    assert clean(' '.join(out))==text
    return out

def doc(identifier,fund,period,date,url,path,role,asof,publication_evidence):
    return dict(document_id=identifier,fund_id=fund,period=period,
        publication_date=date,source_eligibility_verified=True,
        text_is_original_eligible_section=True,role=role,
        header=f'{identifier}; fund={fund}; source date={asof}; unit: as stated in each original section. Official original text.',
        source_url=url,source_path=str(Path(path).relative_to(ROOT)),source_bytes_sha256=digest(path),
        source_as_of=asof,publication_evidence=publication_evidence,units=[],
        ticker=BY_ID[fund]['ticker'] if fund!='COMMON' else None,
        source_owner=BY_ID[fund]['name'] if fund!='COMMON' else 'Federal Open Market Committee',
        human_review_status='assumed_complete_by_explicit_user_instruction; no actual independent signatures asserted')

def add_text(d,text,catalog,locator,*,facts=None,atomic=False):
    parts=[clean(text)] if atomic else sentence_units(text)
    if atomic and len(parts[0])>1500:raise ValueError('Oversized intact numeric bundle')
    for i,part in enumerate(parts):
        eid=f"{d['document_id']}/E{len(d['units'])+1:03d}"
        unit=dict(text=f'[evidence_id={eid}]\n'+part,evidence_ids=[eid],source_locator=locator,
                  original_normalized_text=part,original_text_sha256=hashlib.sha256(part.encode()).hexdigest())
        d['units'].append(unit)
        entry=dict(document_id=d['document_id'],fund_id=d['fund_id'],period=d['period'],
            ticker=d['ticker'],source_owner=d['source_owner'],
            publication_date=d['publication_date'],date=d['source_as_of'],source_url=d['source_url'],
            source_bytes_sha256=d['source_bytes_sha256'],source_locator=locator,source_text=part,
            semantic_review_required=True)
        # Only a registered, exactly present source fact receives numeric gold.
        matched=[f for f in (facts or []) if f['source_literal'] in part]
        if matched:entry['facts']=[{k:v for k,v in f.items() if k!='source_literal'} for f in matched]
        catalog[eid]=entry

def fomc(period,stamp,catalog):
    date=f'{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}'
    path=OUTLOOK/f'FOMC_{stamp}.html';soup=BeautifulSoup(path.read_bytes(),'html.parser')
    url=f'https://www.federalreserve.gov/monetarypolicy/fomcprojtabl{stamp}.htm'
    d=doc(f'{period}-COMMON-FOMC-{stamp}','COMMON',period,date,url,path,'common_economic_outlook',date,
          {'kind':'explicit official release timestamp','date':date,'local_receipt':str((OUTLOOK/f'FOMC_{stamp}_receipt.json').relative_to(ROOT))})
    selected=[]
    h=next(x for x in soup.find_all('h4') if x.get_text(strip=True)=='Summary of Economic Projections')
    summary=clean(h.find_next_sibling('p').get_text(' ',strip=True));selected.append(summary)
    add_text(d,summary,catalog,'Summary of Economic Projections: complete introductory paragraph')
    block=soup.find(id='xt1').parent
    title=clean(block.find('h4').get_text(' ',strip=True))
    add_text(d,title,catalog,'Table 1 title')
    table=block.find('table');last_variable=''
    notes=clean(next(p for p in block.find_all('p') if p.get_text(strip=True).startswith('Note:')).get_text(' ',strip=True))
    sentences=re.split(r'(?<=[.!?])\s+(?=[A-Z])',notes)
    group_notes={g:clean(block.find(id=f'xt1p1f{n}').get_text(' ',strip=True)).replace(' Return to table','') for g,n in [('Median',1),('Central Tendency',2),('Range',3)]}
    for rowno,tr in enumerate(table.find('tbody').find_all('tr')):
        cells=tr.find_all(['td','th'],recursive=False)
        if len(cells)!=13:
            label=clean(tr.get_text(' ',strip=True))
            if label:add_text(d,label,catalog,f'Table 1 row {rowno+1} spanning label')
            continue
        label=clean(cells[0].get_text(' ',strip=True))
        if 'projection' not in label.lower():last_variable=label
        label_context=label if 'projection' not in label.lower() else last_variable+' — '+label
        # Original row serialized in three intact original column groups. All
        # 12 cells, including blanks, are retained. Repeat original headers.
        for group,offset in [('Median',1),('Central Tendency',5),('Range',9)]:
            values=[clean(c.get_text(' ',strip=True)) for c in cells[offset:offset+4]]
            raw=f'{label_context} | {group} | Percent | 2026: {values[0]} | 2027: {values[1]} | 2028: {values[2]} | Longer run: {values[3]}'
            facts=[]
            for year,val in zip(['2026','2027','2028','Longer run'],values):
                if not val:continue
                numeric=float(val) if re.fullmatch(r'-?\d+(?:\.\d+)?',val) else val
                facts.append(dict(value=numeric,unit='percent',date=date,variable=label_context,statistic=group,target_period=year,source_literal=f'{year}: {val}'))
            context=[group_notes[group]]
            if 'GDP' in last_variable or 'inflation' in last_variable:context.append(sentences[0])
            if 'inflation' in last_variable:context.append(next(t for t in sentences if t.startswith('PCE inflation and')))
            if 'Unemployment' in last_variable:context.append(next(t for t in sentences if t.startswith('Projections for the unemployment')))
            if 'Federal funds' in last_variable:context.append(next(t for t in sentences if t.startswith('The projections for the federal funds')))
            if 'Core PCE' in last_variable:context.append(clean(block.find(id='xt1p1f4').get_text(' ',strip=True)).replace(' Return to table',''))
            else:context.append(next(t for t in sentences if t.startswith('Longer-run projections')))
            add_text(d,raw+'\n'+' '.join(context),catalog,f'Table 1 row {rowno+1}, {group}, all four columns plus repeated original applicable notes',facts=facts,atomic=True)
    # Every source note and footnote in the selected table section is retained.
    for p in block.find_all('p'):
        text=clean(p.get_text(' ',strip=True))
        if text:add_text(d,text,catalog,'Table 1 original unit/note/footnote')
    h=next(x for x in soup.find_all('h4') if x.get_text(strip=True)=='Forecast Uncertainty')
    for sibling in h.find_next_siblings():
        if sibling.name in ['h3','h4']:break
        if sibling.name=='p':
            text=clean(sibling.get_text(' ',strip=True))
            if text and text not in ['Return to top']:
                selected.append(text);add_text(d,text,catalog,'Forecast Uncertainty: complete prose section')
    d['eligible_section_scope']=['Complete Summary of Economic Projections introduction','Complete Table 1 with all columns, prior projections, notes and footnotes','Complete Forecast Uncertainty prose section']
    d['repeated_original_context']='Applicable original period definitions and statistic footnotes are repeated inside each atomic numeric row group, so retrieval cannot separate a number from its definitions.'
    d['omitted_sections']='Figures 1–5 and Table 2 are outside the prespecified prose/main-table section scope; not removed after observing model outputs.'
    return d

def fund_documents(catalog):
    out=[]
    path=SRC/'FCNTX_A_shareholder_report.html';soup=BeautifulSoup(path.read_bytes(),'html.parser')
    for x in soup.find_all('ix:header'):x.decompose()
    for x in list(soup.find_all(style=True)):
        if x.attrs and 'display:none' in x.get('style','').replace(' ','').lower():x.decompose()
    text=clean(soup.get_text(' ',strip=True))
    match=re.search(r'Fidelity® Contrafund®\s*:\s*FCNTX',text);assert match
    tail=text[match.start():]
    start=tail.index("What affected the Fund's performance this period?")
    end=tail.index('How did the Fund perform over the past 10 years?',start)
    section=tail[start:end].strip()
    assert '176,314,376,288' in tail[:12000] and 'K6' not in section
    d=doc('A-F01-FCNTX-2025-REVIEW','F01','A','2026-02-20',
        'https://www.sec.gov/Archives/edgar/data/24238/000002423826000023/filing10969.htm',path,
        'fund_historical_performance_commentary','2025-12-31',{'kind':'SEC accession filing date','accession':'0000024238-26-000023','date':'2026-02-20'})
    add_text(d,section,catalog,'FCNTX C000016601: complete What affected the Fund performance section')
    d['eligible_section_scope']=['Complete FCNTX performance commentary; other series and share classes excluded'];out.append(d)
    d['source_owner_evidence']={'source_literal':match.group(),'source_locator':'SEC visible shareholder-report heading, after hidden iXBRL header removal'}

    path=SRC/'VPMCX_annual_20250930_browser_dom.json';capture=read(path);text=capture['dom_snapshot']
    start=text.index('- heading "How did the Fund perform during the reporting period?"')
    end=text.index('- heading "How did the Fund perform over the past 10 years?"',start)
    lines=text[start:end].splitlines();paras=[x.split('- paragraph: ',1)[1] for x in lines if '- paragraph: ' in x]
    assert len(paras)==4
    d=doc('A-F02-VPMCX-2025-REVIEW','F02','A','2025-11-28',capture['source_url'],path,
        'fund_historical_performance_commentary','2025-09-30',{'kind':'SEC annual report filing date; verify accession receipt','accession':'0001104659-25-116918','date':'2025-11-28'})
    for p in paras:add_text(d,p,catalog,'Investor Shares VPMCX: complete annual reporting-period performance section')
    d['eligible_section_scope']=['Complete Investor Shares performance commentary'];out.append(d)
    assert 'Investor Shares (VPMCX)' in text and 'Vanguard PRIMECAP Fund' in text
    d['source_owner_evidence']={'source_literal':'Vanguard PRIMECAP Fund / Investor Shares (VPMCX)','source_locator':'Official shareholder report DOM heading'}

    path=OUTLOOK/'TRBCX_annual_2025.pdf';pdf=fitz.open(path);text=clean(pdf[0].get_text())
    assert 'Blue Chip Growth Fund' in text and 'Investor Class (TRBCX)' in text
    start=text.index('What drove fund performance during the past 12 months?');end=text.index('How has the fund performed?',start)
    fund=BY_TICKER['TRBCX']['fund_id']
    d=doc(f'A-{fund}-TRBCX-2025-REVIEW',fund,'A','2026-02-28',read(OUTLOOK/'TRBCX_annual_2025_receipt.json')['source_url'],path,
        'fund_historical_performance_commentary','2025-12-31',{'kind':'conservative month-end upper bound','printed_publication_label':'2/26','date_precision':'month','pdf_created':'2026-02-10'})
    add_text(d,text[start:end],catalog,'Investor Class TRBCX: complete What drove fund performance section')
    d['eligible_section_scope']=['Complete Investor Class performance commentary'];out.append(d)
    d['source_owner_evidence']={'source_literal':'Blue Chip Growth Fund / Investor Class (TRBCX)','source_locator':'Official annual PDF page1 title'}

    path=DATA/'raw/DODGX_2025_review_transcript.pdf';pdf=fitz.open(path)
    assert 'Dodge & Cox Stock Fund' in clean(pdf[3].get_text()) and 'Class I' in clean(pdf[3].get_text())
    url='https://www.dodgeandcox.com/content/dam/web/documents/insights/2025-annual-investment-reviews/dc-us-on-demand-audio-transcript-us-equity-4Q2025.pdf'
    fund=BY_TICKER['DODGX']['fund_id']
    d=doc(f'A-{fund}-DODGX-2025-REVIEW',fund,'A','2026-02-28',url,path,'fund_investment_outlook','2025-12-31',
          {'kind':'conservative month-end upper bound','official_landing_page_publication_label':'February 2026','pdf_cover_label':'January 2026','date_precision':'month','source_manifest':'data/v63_20261027/source_manifest.json'})
    facts=[dict(value=14.6,unit='times earnings',date='2025-12-31',source_literal='14.6 times earnings'),
           dict(value=0.86,unit='beta against S&P 500',date='2025-12-31',source_literal='beta is low at 0.86'),
           dict(value=13.7,unit='percent',date='2025-12-31',source_literal='13.7%')]
    original_blocks=[];decorative=[]
    for page_i,page in enumerate(pdf):
        # PDF content-stream reading order preserves both columns; text blocks
        # are sentence-split without rewriting. Entire 4-page transcript retained.
        for block in page.get_text('blocks'):
            if len(block)>6 and block[6]!=0:continue
            value=clean(block[4]);locator=f'PDF page {page_i+1}; block {block[5]}'
            if not value:continue
            if value.startswith('2025 ANNUAL U.S. EQUIT Y REVIEW') or value.startswith('ON-DEMAND AUDIO TRANSCRIPT') or value=='January 2026':
                decorative.append(dict(text=value,source_locator=locator));continue
            if original_blocks and not re.search(r'[.!?]$',original_blocks[-1][0]) and re.match(r'[a-z0-9]',value):
                prior,where=original_blocks.pop();original_blocks.append((prior+' '+value,where+'; continuation '+locator))
            else:original_blocks.append((value,locator))
    for value,locator in original_blocks:add_text(d,value,catalog,locator,facts=facts)
    d['eligible_section_scope']=['Entire four-page official transcript body, including source footnotes and qualifications; decorative title and running page furniture stored separately']
    d['source_page_furniture']=decorative
    d['source_owner_evidence']={'source_literal':'Dodge & Cox Stock Fund — Class I','source_locator':'Official transcript PDF page4 performance disclosure'}
    d['header']+=' DODGX Stock Fund Class I; transcript cover January 2026, published by February 2026.'
    out.append(d)
    return out

def main():
    catalog={};documents=[fomc('A','20260318',catalog),fomc('C','20260617',catalog)]+fund_documents(catalog)
    for d in documents:
        assert d['units'] and d['publication_date']<=('2026-03-31' if d['period']=='A' else '2026-06-30')
        if d['period']=='C':assert d['publication_date']>'2026-03-31'
        if d['role']=='fund_historical_performance_commentary':
            gold=[e for u in d['units'] for e in u['evidence_ids']]
        else:gold=[e for u in d['units'] for e in u['evidence_ids'] if catalog[e].get('facts')]
        d['retrieval_gold_evidence_ids']=gold
        d['retrieval_gold_scope']='All intact numeric projection row groups and manually registered numerical fund facts; for short historical performance sections, all source narrative units. Header/footnote/disclaimer-only units are not retrieval gold. This is a prespecified mechanical/source-fact recall diagnostic, not exhaustive semantic-outlook recall.'
    corpus=dict(status='prepared_for_exact_tokenizer_validation',documents=documents,
        construction_policy='Original full selected sections, whitespace normalization only; HTML tables serialized with all cells and repeated original headers. No LLM summaries.',
        corpus_scope_frozen_before_model_outputs=True,
        C_scope_limitation='C contains new common FOMC economic projections. No historically eligible own-fund new outlook bytes were recovered; no claim of four fund-specific new-outlook coverage.',
        excluded=[dict(source='mutable Fidelity/TRowePrice/DodgeCox quarterly-review PDFs',reason='Retrieved current bytes dated September 2026; search-index old dates are not historical source verification.'),
                  dict(source='GICS11 prior public-sector corpus',reason='Protocol forbids combining with French12 experiment'),
                  dict(source='existing mandatory rules',reason='Provided in baseline to all arms; not counted as new outlook retrieval')])
    write(SRC/'documents_v2.json',corpus)
    write(DATA/'numerical/evaluator_only/source_catalog_v2.json',catalog)
    verification=dict(documents=len(documents),evidence_units=len(catalog),numeric_fact_units=sum(bool(v.get('facts')) for v in catalog.values()),
        authoritative_protocol_path=str(PROTOCOL_PATH.relative_to(ROOT)),authoritative_protocol_sha256=digest(PROTOCOL_PATH),
        fund_attribution=[dict(document_id=d['document_id'],fund_id=d['fund_id'],ticker=d['ticker'],source_owner=d['source_owner'],source_owner_evidence=d.get('source_owner_evidence')) for d in documents],
        corpus_sha256=digest(SRC/'documents_v2.json'),source_catalog_sha256=digest(DATA/'numerical/evaluator_only/source_catalog_v2.json'),
        source_files=[dict(document_id=d['document_id'],path=d['source_path'],sha256=d['source_bytes_sha256'],units=len(d['units']),max_unit_characters=max(len(u['text']) for u in d['units'])) for d in documents],
        exact_model_tokenizer_status='pending root build_run; character length is diagnostic only',
        human_review='assumed by user instruction, distinct from actual automatic checks',
        source_catalog_is_evaluator_only=True,script_sha256=digest(__file__))
    write(SRC/'documents_v2_verification.json',verification)
    print(json.dumps(verification,ensure_ascii=True,indent=2))

if __name__=='__main__':main()
