"""Offline representation audit only: no generation or experiment mutation."""
from copy import deepcopy
from decimal import Decimal,localcontext,ROUND_HALF_EVEN
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,struct
from research.v63.exact_tokenizer import NativeTokenizer

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'data/v63_20261027/audit/candidate_002_render_capacity_01'
OUT=ROOT/'data/v63_20261027/audit/covariance_representation_audit.json'

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def bits(value):return struct.pack('<d',value).hex()
def flat(matrix):return [x for row in matrix for x in row]
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def baseline(label):
    trace=read(SOURCE/'captured_engineering_only'/label/'trace.json')
    return json.loads(trace['messages'][1]['content'].split('\n',1)[1])

def main():
    original=baseline('B-development__F01');sigma=flat(original['Sigma']);prior=flat(original['V0']);common=flat(original['Omega0'])
    naive=[s/12.0 for s in sigma];recipe=[float(format(s/12.0,'.12g')) for s in sigma]
    with localcontext() as context:
        context.prec=12;context.rounding=ROUND_HALF_EVEN
        decimal_recipe=[float(Decimal(str(s))/Decimal(12)) for s in sigma]
    def differences(values):
        return {'unequal_binary64_cells':sum(bits(x)!=bits(y) for x,y in zip(values,prior)),
            'max_absolute_error':max(abs(x-y) for x,y in zip(values,prior)),
            'max_relative_error':max(abs(x-y)/abs(y) for x,y in zip(values,prior))}
    assert differences(recipe)['unequal_binary64_cells']==0
    assert all(bits(x)==bits(y) for x,y in zip(common,prior))
    candidates={
        'Omega0_exact_alias_only':{'Omega0':'V0 (exact same matrix)'},
        'V0_exact_binary64_roundtrip_and_Omega0_alias':{
            'V0':"For each i,j: float(format(float(Sigma[i][j])/12.0,'.12g')). float is IEEE-754 binary64, nearest-even; format rounds to 12 significant decimal digits. Same industries order as Sigma.",
            'Omega0':'V0 (exact same matrix)'},
    }
    config_path=ROOT/'data/v63_20261027/continuation/deployment/local_windows/tokenizer_config.json'
    native=NativeTokenizer(read(config_path));report=read(SOURCE/'capacity_report.json');measurements=[];tool_rows=[]
    try:
        for index,row in enumerate(report['rows']):
            if not row['module'].startswith('B'):continue
            label=row['module']+'__'+row['fund_id'];base=baseline(label)
            assert base['Sigma']==original['Sigma'] and base['V0']==original['V0'] and base['Omega0']==original['Omega0']
            render_path=SOURCE/'render_http'/f'render_{index*3+2:06d}'/'rendered_prompt.txt'
            rendered=render_path.read_text(encoding='utf-8');needle='COMMON BASELINE\n'+canonical(base)
            assert rendered.count(needle)==1
            before=native.count(rendered);assert before==row['baseline_plus_FULL_render_tokens']
            for name,changes in candidates.items():
                changed={**deepcopy(base),**changes}
                modified=rendered.replace(needle,'COMMON BASELINE\n'+canonical(changed))
                after=native.count(modified)
                measurements.append({'module':row['module'],'fund_id':row['fund_id'],'candidate':name,
                    'original_verified_render_tokens':before,'transformed_same_template_native_tokens':after,
                    'saved_tokens':before-after,'same_role_template_reconstruction_not_new_API_render':True,
                    'new_baseline_sha256':hashlib.sha256(canonical(changed).encode()).hexdigest(),
                    'stage3_headroom_if_each_prior_output_1024_and_output_reserve4096':{
                        str(c):row['headroom_assumptions'][1]['headroom_by_context'][str(c)]+before-after for c in report['contexts']}})
            response=read(SOURCE/'tool_outputs'/f'{label}.json')['calculator_response'];cov=response['covariance']
            symmetric=all(bits(cov[i][j])==bits(cov[j][i]) for i in range(12) for j in range(12));assert symmetric
            encoded={'format':'symmetric_upper_triangle_row_major_including_diagonal','dimension':12,
                     'industry_order':'same as baseline industries','values':[cov[i][j] for i in range(12) for j in range(i,12)]}
            restored=[[None]*12 for _ in range(12)];iterator=iter(encoded['values'])
            for i in range(12):
                for j in range(i,12):restored[i][j]=restored[j][i]=next(iterator)
            assert all(bits(x)==bits(y) for x,y in zip(flat(restored),flat(cov)))
            compact={**response,'covariance':encoded}
            naive_full=[x/2.5 for x in prior] # all representative cases have r=0.5
            tool_rows.append({'module':row['module'],'fund_id':row['fund_id'],'full_observation_precision':0.5,
                'covariance_symmetric_bitwise':symmetric,'upper_triangle_roundtrip_bitwise':True,
                'original_tool_response_tokens':native.count(canonical(response)),
                'upper_triangle_object_response_tokens':native.count(canonical(compact)),
                'saved_tokens_if_versioned_tool_contract_changed':native.count(canonical(response))-native.count(canonical(compact)),
                'covariance_equals_V0_div_2_plus_r_bitwise':all(bits(x)==bits(y) for x,y in zip(flat(cov),naive_full)),
                'max_abs_error_from_naive_V0_div_2_plus_r':max(abs(x-y) for x,y in zip(flat(cov),naive_full)),
                'covariance_sha256':hashlib.sha256(canonical(cov).encode()).hexdigest()})
        result={'status':'read_only_representation_audit_completed','recorded_at_utc':datetime.now(timezone.utc).isoformat(),
            'generation_calls':0,'render_API_calls':0,'core_or_candidate_files_modified':False,
            'scope':'Future candidate assessment only; existing 15/60/development experiment identities remain unchanged.',
            'authoritative_recipe':"Sigma=displayed_covariance(LedoitWolf.covariance_); V0=float(format(Sigma_float64/12.0,'.12g')) elementwise; Omega0=V0.copy().",
            'Omega0_V0_bitwise_identical_cells':144,'cell_count':144,'naive_divide_only':differences(naive),
            'decimal_divide_round_12_half_even':differences(decimal_recipe),'exact_binary64_format_recipe':differences(recipe),
            'decimal_recipe_mismatch_examples':[{'row':i//12,'column':i%12,'displayed_Sigma':sigma[i],
                'V0_original':prior[i],'decimal_recipe':decimal_recipe[i],'float_recipe':recipe[i]}
                for i in range(144) if bits(decimal_recipe[i])!=bits(prior[i])],
            'tested_lossless_candidate_fields':candidates,'native_tokenizer_identity':native.identity,
            'max_saving_among_tested_baseline_representations':max(r['saved_tokens'] for r in measurements),
            'baseline_measurements':measurements,'posterior_tool_measurements':tool_rows,
            'protocol_assessment':[
                'Exact Omega0 alias preserves every current common-covariance bit; V0 needs the precise binary64 division then .12g roundtrip, not just Sigma/12 or decimal-half-even division.',
                'All matrices/rules must remain common to every arm from stage1. Keep numeric callbacks on the identical dense binary64 arrays; decode rules and test equality before use.',
                'The plan permits precision/covariance rules in atomic documents and lists V0/Omega0 as common baseline fields, without expressly requiring dense display. This supports an exact rule representation as an implementation interpretation, not permission to silently alter an already frozen candidate.',
                'Equivalent information does not guarantee identical model behavior: changing dense matrices to a recipe changes prompt length and computation demands. A new candidate/input/code identity and complete staged development checks are required.',
                'Posterior covariance is symmetric and can be encoded losslessly by 78 original upper-triangle values. This changes covariance from matrix to object, so it is not a drop-in preservation of the current response type; a documented versioned tool-output decoder/schema and every-arm-consistent implementation are needed.',
                'An exact reference may reuse an identical covariance already delivered in the same retained trajectory, identified by a content hash. Never reference another fund/run or an unseen result. A first covariance still needs a visible definition.',
                'V0/(2+r) is not bitwise equal to the actual rounded-covariance/linear-solve posterior even in complete-observation representative cases; partial observations also require selection-matrix updates.',
                'Measured savings are maxima among the explicit tested representations, not a claim of globally optimal compression. A/C baselines contain neither V0 nor Omega0 and receive no savings from this proposal.',
                'Counts use exact native tokenization of a literal baseline-content replacement within the prior verified rendered template; no new renderer or generation request was sent. Future candidate must repeat real render gates.'
            ],'source_files':[{'path':str(p),'sha256':digest(p)} for p in [Path(__file__),ROOT/'plan/LIBERA_실험설정_v6.3_20261027.json',
                ROOT/'research/v63/numerics.py',ROOT/'research/v63/build_run.py',ROOT/'research/v63/runtime.py',config_path,SOURCE/'capacity_report.json']]}
        OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        text='Read-only covariance representation audit; no model generation, no new render API request, no candidate mutation.\n'
        text+=f"Omega0 equals V0 bit-for-bit: 144/144. Divide-only mismatches: {differences(naive)}. Decimal 12-significant-digit division mismatches: {differences(decimal_recipe)}. Exact binary64/.12g recipe: {differences(recipe)}.\n"
        for row in measurements:text+=f"{row['module']} {row['fund_id']} {row['candidate']}: {row['original_verified_render_tokens']} -> {row['transformed_same_template_native_tokens']}; save {row['saved_tokens']}.\n"
        text+='\n'+'\n'.join(result['protocol_assessment'])+'\n'
        OUT.with_suffix('.txt').write_text(text,encoding='utf-8')
        print(json.dumps({'max_baseline_saving':result['max_saving_among_tested_baseline_representations'],
            'baseline_savings':sorted(set((r['candidate'],r['saved_tokens']) for r in measurements)),
            'tool_upper_triangle_savings':sorted(set(r['saved_tokens_if_versioned_tool_contract_changed'] for r in tool_rows))}))
    finally:native.close()

if __name__=='__main__':main()
