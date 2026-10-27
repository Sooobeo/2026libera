"""Verify saved source integrity and extraction accounting, not human eligibility."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/v63_20261027'

def main():
    manifest=json.loads((OUT/'source_manifest.json').read_text(encoding='utf-8'))
    readiness=json.loads((OUT/'readiness.json').read_text(encoding='utf-8'))
    parsed=json.loads((OUT/'holdings_parse_summary.json').read_text(encoding='utf-8'))
    checks=[]
    def check(name,condition,detail=None): checks.append({'name':name,'passed':bool(condition),'detail':detail})
    for source in manifest['sources']:
        if source.get('local_path'):
            p=ROOT/source['local_path']
            check('raw_hash:'+source['id'],p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==source['sha256'])
        if source.get('extracted_text_path'):
            p=ROOT/source['extracted_text_path']
            check('text_hash:'+source['id'],p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==source['extracted_text_sha256'])
    check('exactly_twelve_fund_periods',len(readiness['rows'])==12 and len({(x['fund_id'],x['holdings_as_of']) for x in readiness['rows']})==12)
    check('no_unaudited_case_ready',all(not x['ready'] and not x['human_review_complete'] for x in readiness['rows']))
    check('h_not_created',not manifest['summary']['h_created'])
    check('no_model_calls_by_data_pipeline',manifest['summary']['model_calls']==0)
    for row in parsed['rows']:
        p=OUT/'parsed'/(row['source_id']+'.json'); data=json.loads(p.read_text(encoding='utf-8'))
        check('parsed_count:'+row['source_id'],len(data['rows'])==row['parsed_rows'])
        check('raw_value_sum:'+row['source_id'],sum(x['value_usd'] for x in data['rows'])==row['parsed_value_usd'])
        if row['ticker'] in ['VPMCX','DODGX']:
            check('common_stock_total:'+row['source_id'],row['common_stock_sum_matches'])
            check('source_accounting:'+row['source_id'],row['source_accounting_identity_matches'])
        else:
            check('printed_dollar_rounding:'+row['source_id'],row['within_individual_dollar_rounding_bound'],{'difference_usd':row['named_plus_concealed_minus_investments_usd'],'bound_usd':row['display_rounding_bound_usd']})
        check('SIC_not_invented:'+row['source_id'],all(x['sic'] is None and x['ff12'] is None for x in data['rows']))
    result={'status':'pass' if all(c['passed'] for c in checks) else 'fail','checks_passed':sum(c['passed'] for c in checks),'checks_total':len(checks),'scope':'Source bytes, extraction arithmetic, and fail-closed data readiness. Not historical source certification or human review.','checks':checks}
    (OUT/'official_data_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['status','checks_passed','checks_total','scope']},ensure_ascii=False))
    if result['status']!='pass': raise SystemExit(1)

if __name__=='__main__':main()
