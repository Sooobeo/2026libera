"""No-inference numeric/tokenizer process-memory receipt for launcher settings."""
import ctypes,json,os,sys
from pathlib import Path
from research.v63 import numerics
from research.v63.build_run import read_json,save_json
from research.v63.exact_tokenizer import NativeTokenizer
from research.v63.retrieval import canonical,sha

class COUNTERS(ctypes.Structure):
    _fields_=[('cb',ctypes.c_ulong),('page_fault_count',ctypes.c_ulong)]+[(name,ctypes.c_size_t) for name in
       ('peak_working_set','working_set','quota_peak_paged_pool','quota_paged_pool','quota_peak_nonpaged_pool','quota_nonpaged_pool','pagefile_usage','peak_pagefile_usage','private_usage')]

def main():
    root=Path(__file__).resolve().parents[1];out=Path(sys.argv[1])
    if out.exists():raise ValueError('Refuse to overwrite probe receipt.')
    native=NativeTokenizer(read_json(root/'data/v63_20261027/continuation/deployment/local_windows/tokenizer_config.json'))
    try:
        cal=numerics.calibrate(root)
        state=COUNTERS();state.cb=ctypes.sizeof(state)
        ctypes.windll.kernel32.GetCurrentProcess.restype=ctypes.c_void_p
        ctypes.windll.psapi.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong]
        if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),ctypes.byref(state),state.cb):raise OSError('Process counters unavailable.')
        result={'status':'completed','engineering_only':True,'model_generation_requests':0,'pid':os.getpid(),
          'environment':{key:os.environ.get(key) for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')},
          'process_memory_bytes':{name:getattr(state,name) for name,_ in state._fields_ if name not in ('cb','page_fault_count')},
          'calibration_array_sha256':sha(canonical(numerics.jsonable({k:cal[k] for k in ('m0','V0','Omega0','Sigma')}))),
          'native_sample_tokens':native.count('Return exactly the JSON object {"ok":true}.')}
        save_json(out,result);print(json.dumps(result))
    finally:native.close()

if __name__=='__main__':main()
