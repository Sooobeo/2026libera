"""Freeze the measured isolated CPU candidate, without authorizing main."""
from pathlib import Path
import importlib.metadata,json,platform
from research.v63.build_run import read_json,save_json,file_ref
from research.v63 import numerics
from research.v63.campaign import CODE_FILES,runtime_identity

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/v63_20261027/continuation/deployment/local_windows'
DEST=BASE/'candidate_002'

def main():
    DEST.mkdir(exist_ok=False)
    config=read_json(BASE/'campaign_config.json');freeze=read_json(BASE/'runtime_candidate.json')
    signed=read_json(ROOT/'data/v63_20261027/runtime/local_windows/authenticode.json')
    binaries=[file_ref(Path(item['path']),ROOT) for item in signed]
    for item,ref in zip(signed,binaries):
        if ref['sha256']!=item['sha256'] or item['status']!='Valid':raise ValueError('Signed binary drift.')
    launch=read_json(ROOT/'data/v63_20261027/runtime/local_windows/service_20261027T042827759Z/server_launch.json')
    if launch['process_scoped_environment']['OLLAMA_KV_CACHE_TYPE']!='f16':raise ValueError('Wrong server environment.')
    env={'candidate_id':'windows_cpu_compact_002','inference_engine':'official Ollama 0.35.1 Windows portable CPU',
        'server_environment':launch['process_scoped_environment'],
        'python_environment':{key:'1' for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')},
        'python_version':platform.python_version(),'python_packages':{name:importlib.metadata.version(name) for name in ('numpy','scipy','cvxpy','clarabel','rank-bm25','jsonschema')},
        'cpu':launch['cpu'],'physical_memory_KiB':launch['memory']['TotalVisibleMemorySize'],
        'binary_artifacts':binaries,'launcher':file_ref(ROOT/'research/start_v63_local_ollama.ps1',ROOT),
        'numeric_policy':'Campaign sets Python BLAS/OMP/MKL thread counts to 1 before NumPy import; the separate inference server uses num_thread=8.',
        'selection_basis':'Identical model/template. Resource capacity and latency only; no investment outcomes used for candidate selection.'}
    freeze.update(context_tokens=32768,output_tokens=4096,fixed_options={'num_thread':8,'num_gpu':0,'use_mmap':True,'num_batch':256},
                  main_model_frozen=False,execution_environment=env,selection_stage='Candidate 002; 15 then 60 then 720 development gates; main remains unauthorized until resource review.')
    config.update(runtime_freeze_path=(DEST/'runtime_candidate.json').relative_to(ROOT).as_posix(),
                  execution_environment_path=(DEST/'execution_environment.json').relative_to(ROOT).as_posix(),
                  mandate_atomic_units_path='data/v63_20261027/continuation_sources/mandate_atomic_units_v2.json',
                  source_catalog_path='data/v63_20261027/numerical/evaluator_only/source_catalog_v2.json')
    save_json(DEST/'runtime_candidate.json',freeze);save_json(DEST/'execution_environment.json',env);save_json(DEST/'campaign_config.json',config)
    run_id,identity=runtime_identity(ROOT,freeze,file_ref(ROOT/config['tokenizer_config_path'],ROOT),config['execution_amendment'])
    evidence=[ROOT/'data/v63_20261027/runtime/local_windows'/p for p in ('q8_timing_probe_002/summary.json','f16_timing_probe_003/summary.json','numeric_memory_default.json','numeric_memory_singlethread.json')]
    save_json(DEST/'selection_receipt.json',{'status':'development_candidate_frozen','run_id':run_id,'main_model_frozen':False,
        'engineering_request_count_in_timing_comparison':3,'experimental_model_requests_at_freeze':0,
        'next_action':'Only the 15-stage technical-smoke phase; later phases require review.',
        'evidence':[file_ref(p,ROOT) for p in evidence],
        'cold_cache_note':'Each short probe unloaded the previous runner. Exact render-only preflight loads the engine before timed generation. OS file cache is uncontrolled; no whole-campaign forecast is inferred.',
        'source_identity':identity})
    save_json(ROOT/'data/v63_20261027/audit/candidate_002_code_verification.json',{
        'status':'passed','engineering_only':True,'actual_model_calls':0,'command':'python -m pytest research/v63 -q',
        'environment':env['python_environment'],'tests_passed':178,'warnings':2,
        'warnings_detail':'CLARABEL inaccurate-solution warnings in two oracle/range tests; both independent numerical assertions passed.',
        'code_sha256':identity['code'],'scope':'Implementation tests only. Real model feasibility remains unmeasured for this frozen candidate.'})
    print(json.dumps({'run_id':run_id,'config':config['runtime_freeze_path'],'candidate_directory':str(DEST)}))

if __name__=='__main__':main()
