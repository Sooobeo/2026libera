"""Extract acquired evidence and produce an explicit, unsatisfied v6.3 data gate.

Parsed holdings are audit candidates, never an executable h or human gold table.
"""
from __future__ import annotations
import csv, hashlib, html as html_escape, json, re
from datetime import datetime, timezone
from pathlib import Path
import pdfplumber
from pypdf import PdfReader
from lxml import html

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/v63_20261027'

def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def register_browser_files():
    for identifier,role,period in [('DODGX_NCSR_20251231_browser','NCSR','2025-12-31'),('DODGX_QH1_20260331_browser','QH1','2026-03-31'),('DODGX_QH3_20250930_browser','QH3','2025-09-30')]:
        p=OUT/'raw'/(identifier+'.pdf'); receipt=OUT/'receipts'/(identifier+'.json')
        if p.exists() and not receipt.exists():
            dump(receipt,{'id':identifier,'requested_url':'https://connect.rightprospectus.com/DodgeandCox/TVT/256219106/'+role+'?site=Funds',
                'status':'downloaded','http_status':None,'download_method':'official_manager_link_to_distributor_browser_UI_download',
                'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'bytes':p.stat().st_size,'sha256':sha(p),
                'local_path':p.relative_to(ROOT).as_posix(),'metadata':{'ticker':'DODGX','role':role,'report_as_of_observed':period,'discovered_from':'DODGX_manager_documents'},
                'human_review':'pending','historical_eligibility':'unverified','attempts':1})

def extract_sources():
    sources=[]
    for p in sorted((OUT/'receipts').glob('*.json')):
        rec=json.loads(p.read_text(encoding='utf-8')); raw=ROOT/rec.get('local_path','__missing__')
        text=''; validation='http_error' if rec['status']=='http_error' else 'not_extracted'
        if raw.exists() and rec['status']=='downloaded':
            if raw.suffix=='.pdf':
                reader=PdfReader(raw); rec['page_count']=len(reader.pages)
                text='\n\n'.join('PAGE '+str(i+1)+'\n'+(page.extract_text() or '') for i,page in enumerate(reader.pages))
                validation='readable_pdf' if len(text)>100 else 'pdf_requires_ocr'
            elif raw.suffix=='.json':
                json.loads(raw.read_text(encoding='utf-8')); validation='valid_json_metadata'
            else:
                tree=html.fromstring(raw.read_bytes())
                for e in tree.xpath('//script|//style'): e.drop_tree()
                text='\n'.join(x.strip() for x in tree.text_content().splitlines() if x.strip())
                validation='readable_html'
                if any(x in text.lower() for x in ['page temporarily unavailable','page unavailable','service unavailable','akamai reference']): validation='semantic_error_page'
                elif len(text)<150: validation='javascript_shell_or_incomplete'
            if text:
                dest=OUT/'extracted'/(rec['id']+'.txt'); dest.parent.mkdir(exist_ok=True); dest.write_text(text,encoding='utf-8')
                rec.update({'extracted_text_path':dest.relative_to(ROOT).as_posix(),'extracted_text_sha256':sha(dest),'characters':len(text)})
        rec['content_validation']=validation
        rec['eligible_for_experiment']=False
        rec['eligibility_reason']='Source identity, complete holdings, historical publication/version and two independent human reviews remain unverified.'
        if rec['id'] in ['DODGX_manager_holdings_current','TRBCX_manager_portfolio_update_current','TRBCX_manager_quarterly_review_current','TRBCX_manager_q3_holdings_mutable','VPMCX_current_factbook','VPMCX_manager_factbook_current']:
            rec['observed_report_dates']=['2026-09-30']; rec['eligibility_reason']='Current retrieved bytes are dated 2026-09-30, after all requested cutoffs.'
        elif rec['id']=='VPMCX_manager_financial_statements_2025':
            rec['observed_report_dates']=['2026-03-31']; rec['eligibility_reason']='Mutable URL indexed as 2025 now contains March 2026 semiannual statements for the registrant. Target PRIMECAP begins at PDF page 2; other series must be excluded.'
        elif rec['id']=='VPMCX_manager_holdings_dec2025': rec['observed_report_dates']=['2025-12-31']
        elif rec['id']=='TRBCX_manager_q4_holdings_mutable': rec['observed_report_dates']=['2025-12-31']
        elif rec['id']=='TRBCX_manager_q1_holdings_mutable': rec['observed_report_dates']=['2026-03-31']
        elif rec['id'].startswith('DODGX_') and 'browser' in rec['id']: rec['observed_report_dates']=[rec['metadata']['report_as_of_observed']]
        elif rec['id']=='VPMCX_summary_20260128': rec['observed_cover_date']='2026-01-28'
        elif rec['id']=='TRBCX_full_20260301': rec['observed_cover_date']='2026-03-01'
        elif rec['id'].startswith('DODGX_2025_review') or rec['id']=='DODGX_manager_2025_review': rec['observed_report_dates']=['2025-12-31'];rec['publication_label']='February 2026 (official web page; exact original bytes date not verified)'
        sources.append(rec)
    return sources

def parse_vanguard(identifier,pages,period):
    reader=PdfReader(OUT/'raw'/(identifier+'.pdf')); rows=[]; stopped=False
    for pi in pages:
        lines=(reader.pages[pi].extract_text() or '').splitlines()
        for li,line in enumerate(lines,1):
            if re.search(r'T\s*otal Common Stocks',line): stopped=True
            if stopped: continue
            if re.search(r'\b(?:As of |January|February|March|April|May|June|July|August|September|October|November|December)\b',line): continue
            m=re.match(r'^(.*?)\s+([\d,]+)\s+([\d,]+)\s*$',line.strip())
            if not m: continue
            name,shares,value=m.groups()
            if not re.search('[A-Za-z]',name): continue
            rows.append({'ticker':'VPMCX','holdings_as_of':period,'source_id':identifier,'source_page':pi+1,'source_line':li,'source_text':line,
                         'name_as_extracted':name,'shares':int(shares.replace(',','')),'value_usd':int(value.replace(',',''))*1000,
                         'value_unit_in_source':'USD thousands','security_type_in_source':'Common Stocks','sic':None,'sic_source_url':None,'ff12':None,'human_review':'pending'})
    return rows

def parse_trbcx(identifier,period):
    reader=PdfReader(OUT/'raw'/(identifier+'.pdf'));rows=[]
    for pi,page in enumerate(reader.pages):
        for li,line in enumerate((page.extract_text() or '').splitlines(),1):
            m=re.match(r'^(.*?)\s+([\d,]+)\s+([\d,]+)\s+([\d.]+)%\s*$',line)
            if not m: continue
            name,shares,value,weight=m.groups()
            rows.append({'ticker':'TRBCX','holdings_as_of':period,'source_id':identifier,'source_page':pi+1,'source_line':li,'source_text':line,
                         'name_as_extracted':name,'shares_or_par':int(shares.replace(',','')),'value_usd':int(value.replace(',','')),
                         'source_weight_pct':float(weight),'security_type_in_source':'not_explicitly_classified_in_this_table','sic':None,'sic_source_url':None,'ff12':None,'human_review':'pending'})
    return rows

def parse_dodge(identifier,period,pages):
    rows=[];stopped=False;buffer=[]
    with pdfplumber.open(OUT/'raw'/(identifier+'.pdf')) as pdf:
        for pi in pages:
            page=pdf.pages[pi]
            for ci in [0,1]:
                crop=page.crop((ci*page.width/2,30,(ci+1)*page.width/2,page.height-30))
                for li,line in enumerate((crop.extract_text() or '').splitlines(),1):
                    compact=re.sub(r'\s+','',line)
                    if 'TotalCommonStocks' in compact: stopped=True
                    if stopped: continue
                    if re.search(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s*\d',line):
                        buffer=[];continue
                    if not line.strip() or re.match(r'^[\d,$.\s]+$',line) or '%' in line or any(x in line for x in ['Shares Value','Portfolio of Investments','Common Stocks (continued)','CommonStocks(continued)','DODGE & COX','DODGE&COX']):
                        buffer=[];continue
                    m=re.match(r'^(.*?)\s+([\d,]+)\s+\$?\s*([\d,]+)\s*$',line)
                    if m:
                        name,shares,value=m.groups(); name=' '.join(buffer+[name]); buffer=[]
                        if not re.search('[A-Za-z]',name): continue
                        rows.append({'ticker':'DODGX','holdings_as_of':period,'source_id':identifier,'source_page':pi+1,'source_column':ci+1,'source_line':li,'source_text':name+' | '+shares+' | '+value,
                                     'name_as_extracted':name,'shares':int(shares.replace(',','')),'value_usd':int(value.replace(',','')),
                                     'value_unit_in_source':'USD','security_type_in_source':'Common Stocks','sic':None,'sic_source_url':None,'ff12':None,'human_review':'pending'})
                    elif re.search('[A-Za-z]',line): buffer.append(line)
    return rows

def parse_all():
    specs=[
      ('VPMCX_manager_holdings_dec2025','VPMCX','2025-12-31',74997601000,75698348000,76069363000,-371015000,'vanguard',[0,1,2,3]),
      ('VPMCX_manager_financial_statements_2025','VPMCX','2026-03-31',71633199000,72370674000,72302419000,68255000,'vanguard',[3,4,5,6]),
      ('TRBCX_manager_q4_holdings_mutable','TRBCX','2025-12-31',None,68783761207,68757425667,None,'trbcx',[]),
      ('TRBCX_manager_q1_holdings_mutable','TRBCX','2026-03-31',None,58825376504,58707508498,None,'trbcx',[]),
      ('DODGX_NCSR_20251231_browser','DODGX','2025-12-31',118237496481,119131415085,119675751633,-544336548,'dodge',[1,2]),
      ('DODGX_QH1_20260331_browser','DODGX','2026-03-31',113277538279,114748286307,114373779771,374506536,'dodge',[0,1]),
      ('DODGX_QH3_20250930_browser','DODGX','2025-09-30',118579261881,120315519626,120297445267,18074359,'dodge',[0,1])]
    all_rows=[];summary=[]
    for identifier,ticker,period,common,nav,investments,other,kind,pages in specs:
        rows=parse_vanguard(identifier,pages,period) if kind=='vanguard' else parse_trbcx(identifier,period) if kind=='trbcx' else parse_dodge(identifier,period,pages)
        total=sum(r['value_usd'] for r in rows)
        s={'source_id':identifier,'ticker':ticker,'holdings_as_of':period,'parsed_rows':len(rows),'parsed_value_usd':total,
           'reported_common_stock_value_usd':common,'source_nav_usd':nav,'source_investments_usd':investments,'source_other_assets_less_liabilities_usd':other,
           'common_stock_sum_matches':total==common if common is not None else None,
           'source_accounting_identity_matches':investments+other==nav if all(v is not None for v in [investments,other,nav]) else None,
           'sic_mapped_rows':0,'sic_coverage':None,'complete_holdings_certified':False,'h_created':False,'human_review':'pending'}
        if kind=='trbcx':
            s['concealed_miscellaneous_securities_usd']=809579209 if period=='2025-12-31' else 971565937
            s['named_plus_concealed_matches_investments']=total+s['concealed_miscellaneous_securities_usd']==investments
            s['named_plus_concealed_minus_investments_usd']=total+s['concealed_miscellaneous_securities_usd']-investments
            s['display_rounding_bound_usd']=(len(rows)+2)*0.5
            s['within_individual_dollar_rounding_bound']=abs(total+s['concealed_miscellaneous_securities_usd']-investments)<=(len(rows)+2)*0.5
            s['issues']=['Names of miscellaneous securities are intentionally concealed.','Source states non-GAAP presentation can differ from regulatory holdings.','Do not infer security eligibility or SIC from issuer name.']
        dump(OUT/'parsed'/(identifier+'.json'),{'status':'unaudited_extraction_only','summary':s,'rows':rows})
        all_rows.extend(rows);summary.append(s)
    dump(OUT/'holdings_parse_summary.json',{'status':'unaudited_extraction_only','rows':summary,'total_parsed_rows':len(all_rows),'h_created':False})
    columns=['ticker','holdings_as_of','source_id','source_page','name_as_extracted','value_usd','security_type_in_source','sic','sic_source_url','ff12','reviewer_1','reviewer_2','review_resolution']
    p=OUT/'human_audit/holdings_mapping_review_template.csv';p.parent.mkdir(exist_ok=True)
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(all_rows)
    working=OUT/'human_audit/holdings_mapping_review.csv'
    if not working.exists(): working.write_bytes(p.read_bytes())
    return summary

def build_readiness(sources,parsed):
    periods=[('development','2025-09-30','2025-12-31'),('A_B','2025-12-31','2026-03-31'),('C','2026-03-31','2026-06-30')]
    rows=[]
    for fundid,ticker in [('F01','FCNTX'),('F02','VPMCX'),('F03','DODGX'),('F04','TRBCX')]:
        for period,date,cutoff in periods:
            evidence=[x['source_id'] for x in parsed if x['ticker']==ticker and x['holdings_as_of']==date]
            issues=['발행인 식별자와 시점별 공식 SIC 연결 미완료','90% 분류율 검증 미완료','당시 유효한 의무규칙 및 보충문서 이력 감사 미완료','두 명의 독립 사람 감사 미완료','원문 바이트의 최초 공개시점과 원공시 동일성 미확인']
            if not evidence: issues.insert(0,'해당 시점의 전체 보유 원문 미확보')
            if ticker=='TRBCX' and evidence: issues.insert(0,'일부 증권명 비공개인 보유요약표이므로 완전한 보유자료가 아님')
            if ticker=='VPMCX' and date=='2025-12-31': issues.insert(0,'공식 공급자 PDF NAV와 SEC 검색추출 NAV가 달라 원공시·수정본 대조 필요')
            if ticker=='TRBCX' and date=='2025-12-31': issues.insert(0,'보유요약 PDF NAV와 SEC 검색추출 NAV 차이 해결 필요')
            local=next((x for x in parsed if x['source_id'] in evidence),{})
            rows.append({'fund_id':fundid,'ticker':ticker,'period':period,'holdings_as_of':date,'publication_cutoff':cutoff,
                         'complete_holdings':False,'source_bytes_present':bool(evidence),'publication_verified':False,
                         'source_internal_accounting_matches':local.get('source_accounting_identity_matches'),
                         'sic_coverage':None,'nav_reconciled':False,'human_review_complete':False,'ready':False,
                         'issues':issues,'evidence_ids':evidence})
    counts={'expected_fund_periods':12,'source_bytes_present_fund_periods':sum(x['source_bytes_present'] for x in rows),'ready_fund_periods':0,
            'parsed_holdings_rows':sum(x['parsed_rows'] for x in parsed),'sources_attempted':len(sources),
            'http_success_receipts':sum(x.get('http_status')==200 for x in sources),'browser_downloads':sum(x.get('download_method') is not None for x in sources),
            'readable_pdf_sources':sum(x['content_validation']=='readable_pdf' for x in sources),
            'unique_readable_pdf_hashes':len({x['sha256'] for x in sources if x['content_validation']=='readable_pdf'}),
            'valid_json_metadata_sources':sum(x['content_validation']=='valid_json_metadata' for x in sources),
            'http_errors':sum(x['content_validation']=='http_error' for x in sources),'semantic_error_pages':sum(x['content_validation']=='semantic_error_page' for x in sources),
            'javascript_shells':sum(x['content_validation']=='javascript_shell_or_incomplete' for x in sources),'h_created':False,'model_calls':0}
    result={'protocol_version':'6.3-design','as_of_date':'2026-10-27','status':'blocked_on_source_completeness_mapping_and_human_audit','summary':counts,'rows':rows}
    dump(OUT/'readiness.json',result)
    fields=['fund_id','ticker','period','holdings_as_of','publication_cutoff','source_bytes_present','complete_holdings','publication_verified','sic_coverage','nav_reconciled','human_review_complete','ready','evidence_ids','issues']
    with (OUT/'readiness.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader()
        for r in rows: writer.writerow({**r,'evidence_ids':'; '.join(r['evidence_ids']),'issues':'; '.join(r['issues'])})
    return result

def audit_pack(sources,readiness,parsed):
    E=html_escape.escape
    checks=[('원본과 공개시점','원문 PDF/XML과 SEC accession을 대조하고, 보고기준일·최초 공개일·수정일·취득일을 각각 기록한다. 표지 날짜만으로 적격 처리하지 않는다.'),
      ('전체 보유와 분모','보통주·REIT·ADR·외국주를 식별하고 비공개·매핑불가 주식도 분류율 분모에 보존한다. 현금·채권·펀드지분·기타자산·부채를 삭제하지 않는다. 순자산, 총자산, 순자산+차입은 각각 보존한다.'),
      ('발행인과 SIC','발행인 식별자를 공식 원공시에 연결하고 시점별 SIC를 확보한다. 이름·현대 GICS·LLM 상식으로 SIC를 채우지 않는다. 동일 발행인 클래스와 ADR 경제권리 중복 여부를 감사한다.'),
      ('제약','규칙의 분모·적용조건·예외를 그대로 기록한다. FF12만으로 정확히 계산할 수 없는 규칙을 숨은 산업상한으로 바꾸지 않는다.'),
      ('검토와 승인','설계는 모든 펀드의 적격성·제약에 두 명의 독립 사람 검토를 요구한다. 아래 비어 있는 검토란은 AI가 서명하지 않는다. 불일치 조정 후 서명과 날짜를 기록한다.')]
    issue_rows=[]
    for r in readiness['rows']:
        issue_rows.append('<tr><td>'+E(r['ticker'])+'</td><td>'+E(r['holdings_as_of'])+'</td><td>'+('원문 후보 확보' if r['source_bytes_present'] else '미확보')+'</td><td>'+E('; '.join(r['issues']))+'</td></tr>')
    source_rows=[]
    for s in sources:
        link='../'+str(Path(s.get('local_path','')).relative_to('data/v63_20261027')).replace('\\','/') if s.get('local_path') else ''
        source_rows.append('<tr><td>'+E(s['id'])+'</td><td>'+E(s['content_validation'])+'</td><td>'+E(', '.join(s.get('observed_report_dates',[])))+'</td><td><a href="'+E(link)+'">저장 원문</a> · <a href="'+E(s['requested_url'])+'">공식 URL</a></td></tr>')
    content='''<!doctype html><html lang="ko"><meta charset="utf-8"><title>v6.3 자료 감사 패키지</title><style>body{max-width:1200px;margin:36px auto;padding:0 24px;font:16px/1.7 "Malgun Gothic",sans-serif;color:#202b3b}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:9px;border:1px solid #ccd3df;vertical-align:top;overflow-wrap:anywhere}th{background:#edf2f7}h1{font-size:28px}.status{background:#fff4dc;padding:16px}a{color:#174bb4}code{font-size:13px}</style><h1>v6.3 공식 자료 감사 패키지</h1><p>2026-10-27 · 원문 수집·기계 추출 결과. 사람 검토 완료나 본실험 완료를 뜻하지 않습니다.</p><p class="status">12개 펀드·기간 중 실행 적격으로 인증된 자료는 0개입니다. 보유 후보 원문이 있는 기간은 '''+str(readiness['summary']['source_bytes_present_fund_periods'])+'''개입니다. h와 정답표를 만들지 않았고 모델 요청도 하지 않았습니다.</p><p><a href="holdings_mapping_review.csv">보유행·SIC 매핑 검토 CSV</a> · <a href="review_decisions.json">검토기록 입력 양식</a> · <a href="../readiness.json">12행 준비상태 JSON</a> · <a href="../holdings_parse_summary.json">파싱·합계 검산</a></p>'''
    for title,text in checks: content+='<h2>'+E(title)+'</h2><p>'+E(text)+'</p>'
    content+='<h2>자료별 미해결 사항</h2><table><tr><th>펀드</th><th>보유일</th><th>후보 원문</th><th>남은 검증</th></tr>'+''.join(issue_rows)+'</table>'
    content+='<h2>특정 불일치</h2><p>TRBCX 본기 요약 PDF는 순자산 68,783,761,207달러와 이름이 가려진 증권 809,579,209달러를 기록합니다. SEC NPORT 검색 추출은 순자산 68,745,843,881.999985달러를 표시했습니다. VPMCX 본기 PDF는 순자산 75,698,348,000달러, SEC NPORT 검색 추출은 76,019,104,196.27달러를 표시했습니다. 검색 추출만으로 어느 쪽을 채택하거나 오류를 고치지 않았습니다. 원공시와 정정·평가기준을 대조해야 합니다.</p><p>DODGX 세 기간의 공식 보유표는 운용사가 공개적으로 연결한 문서 공급자 화면에서 다운로드했습니다. SEC 접근 오류를 우회하지 않았습니다. 표내 합계 검산 성공은 역사적 동일성·SIC·규칙 적격성 검증을 대신하지 않습니다.</p>'
    content+='<h2>취득 원문과 실패 기록</h2><table><tr><th>ID</th><th>내용 확인</th><th>관찰된 보고일</th><th>근거</th></tr>'+''.join(source_rows)+'</table></html>'
    (OUT/'human_audit/index.html').write_text(content,encoding='utf-8')
    decisions=OUT/'human_audit/review_decisions.json'
    if not decisions.exists():
        dump(decisions,{'schema_version':'v63-source-audit-1','status':'pending_human_review','AI_review_is_not_human_review':True,
            'reviewers':[{'reviewer_id':'human_1','name':None,'signed_at':None},{'reviewer_id':'human_2','name':None,'signed_at':None}],
            'fund_period_reviews':[{'fund_id':r['fund_id'],'holdings_as_of':r['holdings_as_of'],'source_version_verified':None,'publication_verified':None,'holdings_complete':None,'issuer_SIC_mapping_verified':None,'coverage_numerator_usd':None,'coverage_denominator_usd':None,'NAV_and_fixed_assets_reconciled':None,'constraints_verified':None,'reviewer_1_decision':None,'reviewer_2_decision':None,'adjudication':None} for r in readiness['rows']]})

def main():
    register_browser_files();sources=extract_sources();parsed=parse_all();readiness=build_readiness(sources,parsed)
    dump(OUT/'source_manifest.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),'client_date':'2026-10-27','protocol_version':'6.3-design',
        'purpose':'Official source acquisition and unaudited extraction, not a frozen eligible corpus',
        'sources':sources,'summary':readiness['summary'],'historical_eligibility_verified':False,'human_review_complete':False,'holdings_ready':False,
        'SEC_access_note':'Archives HTTP 403 failures retained. No proxy, identity rotation or access-control bypass. Official manager-linked browser PDF downloads used where available.',
        'pre_script_probe_note':'Four exploratory HTTP requests preceded the archived collector: FCNTX NPORT XML 403/4819 bytes; FCNTX submissions JSON 200/137638 bytes; Vanguard sp59 PDF 200/76124 bytes; Dodge & Cox current holdings PDF 200/273936 bytes. Responses were not saved in those probes. Subsequent archived acquisitions are separately counted. Counts here are receipt counts, not all browser or search network requests.'})
    audit_pack(sources,readiness,parsed)
    print(json.dumps(readiness['summary'],ensure_ascii=False,indent=2))
    for r in parsed: print(r['ticker'],r['holdings_as_of'],r['parsed_rows'],r['common_stock_sum_matches'],r.get('named_plus_concealed_matches_investments'))

if __name__=='__main__':main()
