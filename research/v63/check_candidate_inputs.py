"""Build every real profile/corpus with exact native vocabulary, without inference."""
from pathlib import Path
from research.v63 import numerics
from research.v63.build_run import read_json,save_json,b_input,actual_document_input,load_mandate_units
from research.v63.exact_tokenizer import NativeTokenizer
from research.v63.retrieval import TokenCounter

def main():
    root=Path(__file__).resolve().parents[2];data=root/'data/v63_20261027'
    native=NativeTokenizer(read_json(data/'continuation/deployment/local_windows/tokenizer_config.json'))
    rows=[]
    try:
        counter=TokenCounter(native.identity,native.count,True);cal=numerics.calibrate(root)
        scenarios={block:numerics.generate_scenarios(cal,block)[0][0] for block in ('development','main')}
        partitions=load_mandate_units(data/'continuation_sources/mandate_atomic_units_v2.json')
        for p in read_json(data/'continuation_sources/profiles_v2.json')['profiles']:
            module='B' if p['period'] in ('development','A_B') else 'C'
            case=b_input(p,cal,scenarios['development' if p['period']=='development' else 'main'],counter,mandate_units=partitions)
            r=case['retrieval']
            rows.append({'fund_id':p['fund_id'],'period':p['period'],'case':'mandates_and_B_corpus',
                         'baseline_tokens':native.count(__import__('json').dumps(case['baseline'],sort_keys=True,ensure_ascii=False,separators=(',',':'))),
                         'packet_tokens':r['packet']['tokens'],'full_tokens':r['full']['tokens'],
                         'diagnostics':r['diagnostics_evaluator_only']})
            if p['period']!='development':
                module='A' if p['period']=='A_B' else 'C'
                case=actual_document_input(p,cal,module,data/'continuation_sources/documents_v2.json',counter)
                r=case['retrieval'];rows.append({'fund_id':p['fund_id'],'period':p['period'],'case':module,
                    'packet_tokens':r['packet']['tokens'],'full_tokens':r['full']['tokens'],'diagnostics':r['diagnostics_evaluator_only']})
        result={'status':'passed','engineering_only':True,'model_calls':0,'cases':len(rows),'tokenizer_identity':native.identity,
                'source_sha256':{p.name:numerics.sha256(p) for p in [data/'continuation_sources/profiles_v2.json',data/'continuation_sources/documents_v2.json',data/'continuation_sources/mandate_atomic_units_v2.json']},
                'scope':'Actual retrieval builders include atomic chunk headers and overlap; model-rendered full-history capacity remains a live development gate.',
                'rows':rows}
        save_json(data/'audit/candidate_002_input_capacity.json',result)
        print({'status':result['status'],'cases':len(rows),'max_full_tokens':max(r['full_tokens'] for r in rows),'model_calls':0})
    finally:native.close()

if __name__=='__main__':main()
