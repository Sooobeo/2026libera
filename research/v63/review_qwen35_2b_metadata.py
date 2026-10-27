"""Read saved official metadata; no weight downloads, model calls or mutations."""
from pathlib import Path
import hashlib,json
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'data/v63_20261027/runtime/local_windows/architecture_options'
OUT=BASE/'qwen35_2b_review'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ref(p):return {'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size}


def main():
    hf=read(OUT/'hf_config.json');text=hf['text_config'];tokenizer=read(OUT/'hf_tokenizer_config.json')
    manifest=read(OUT/'ollama_q4_manifest.json');config=read(OUT/'ollama_q4_config.json')
    original=read(BASE/'Qwen3-1.7B.json');original=original.get('text_config',original)
    current_path=ROOT/'data/v63_20261027/continuation/deployment/local_windows/runtime_candidate.json'
    current=read(current_path)
    full=text['layer_types'].count('full_attention');linear=text['layer_types'].count('linear_attention')
    assert full==6 and linear==18 and text['num_hidden_layers']==24
    bytes_per_token=2*full*text['num_key_value_heads']*text['head_dim']*2
    old_bytes=2*original['num_hidden_layers']*original['num_key_value_heads']*original['head_dim']*2
    state_floats=text['linear_num_value_heads']*text['linear_value_head_dim']*text['linear_key_head_dim']
    conv_floats=(text['linear_conv_kernel_dim']-1)*(text['linear_num_value_heads']*text['linear_value_head_dim']+2*text['linear_num_key_heads']*text['linear_key_head_dim'])
    memory=[{'context_tokens':n,'full_attention_F16_KV_bytes':n*bytes_per_token,'full_attention_F16_KV_MiB':n*bytes_per_token/2**20,'Qwen3_1_7B_F16_KV_MiB':n*old_bytes/2**20} for n in [8192,16384,32768,65536,131072,262144]]
    size=sum(x['size'] for x in manifest['layers'])+manifest['config']['size']
    result={
      'status':'read_only_architecture_resource_review_not_execution_authorization',
      'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
      'candidate':'Qwen3.5-2B','official_ollama_tag':'qwen3.5:2b-q4_K_M',
      'scope':{'alternatives_reviewed':1,'new_model_inference_calls':0,'model_weight_downloads':0,'server_changes':0,'benchmark_scores_used_for_selection':False,'experiment_effects_or_pvalues_used_for_selection':False},
      'hf_revision':'15852e8c16360a2fea060d615a32b45270f8a8fc',
      'architecture':{'model_type':hf['model_type'],'text_model_type':text['model_type'],'layers':24,'full_attention_layers':full,'linear_attention_layers':linear,'hidden_size':text['hidden_size'],'attention_heads':text['num_attention_heads'],'KV_heads':text['num_key_value_heads'],'head_dim':text['head_dim'],'maximum_position_embeddings':text['max_position_embeddings']},
      'memory_estimates':{'kind':'analytical estimates, not measured allocations','full_attention_KV_formula':'tokens * full_attention_layers * KV_heads * head_dim * 2 (K,V) * 2 bytes (F16)','full_attention_KV_bytes_per_token':bytes_per_token,'full_attention_KV_reduction_relative_to_Qwen3_1_7B_F16':1-bytes_per_token/old_bytes,'by_context':memory,'linear_state_single_cell_F32_bytes':linear*4*(state_floats+conv_floats),'linear_state_single_cell_F32_MiB':linear*4*(state_floats+conv_floats)/2**20,'linear_state_formula':'18 * 4 bytes * (16*128*128 + (4-1)*(16*128 + 2*16*128))','linear_state_caveat':'llama.cpp allocates mem_size * (1+n_rs_seq) rows. The stated 19.265625 MiB is one F32 recurrent/conv state cell across 18 layers, not the total engine allocation. Actual dtype, sequences, rollback snapshots and workspace must be read from loader logs.','excludes':['model weights','vision projector','compute workspace','batch and microbatch buffers','allocator alignment','recurrent-state cell/snapshot multipliers','OS/engine overhead','any optional MTP model or cache']},
      'download':{'manifest_sha256':sha(OUT/'ollama_q4_manifest.json'),'manifest_config':manifest['config'],'layers':manifest['layers'],'total_bytes_including_config':size,'decimal_GB':size/1e9,'GiB':size/2**30,'note':'Official tag is a llamacpp GGUF manifest. Its default pull includes the approximately 671 MB BF16 vision projector even though this experiment uses text. Text-only actual projector residency is unmeasured. The unqualified :2b tag currently advertises Q8_0; explicitly pin the q4 tag and full manifest digest if later approved.'},
      'runtime_support':{'official_tag_requires_ollama':config['requires'],'current_recorded_ollama_revision':current['engine_revision'],'current_runtime_record':ref(current_path),'minimum_version_satisfied':tuple(map(int,current['engine_revision'].split('.')))>=tuple(map(int,config['requires'].split('.'))),'manifest_format':config['model_format'],'model_family':config['model_family'],'quantization':config['file_type'],'renderer':config['renderer'],'parser':config['parser'],'bundled_llama_cpp_pin':(OUT/'LLAMA_CPP_VERSION').read_text().strip(),'source_support_verified':True,'source_evidence':['0.35.1 model/renderers/qwen35.go implements the qwen3.5 renderer including think selection.','0.35.1 llm/llama_server.go contains qwen35 compatibility handling.','0.35.1 pins llama.cpp b11232; src/models/qwen35.cpp explicitly classifies 24 layers and hidden size 2048 as 2B.'],'actual_2B_load_verified':False,'actual_GPU_offload_verified':False,'actual_latency_verified':False,'native_vocabulary_loader_verified':False},
      'tokenizer':{'class':tokenizer['tokenizer_class'],'vocab_size_from_model':text['vocab_size'],'model_max_length':tokenizer['model_max_length'],'add_bos_token':tokenizer['add_bos_token'],'bos_token':tokenizer['bos_token'],'eos_token':tokenizer['eos_token'],'pad_token':tokenizer['pad_token'],'pretokenize_regex':tokenizer['pretokenize_regex'],'hf_chat_template_sha256':hashlib.sha256(tokenizer['chat_template'].encode()).hexdigest(),'model_text_eos_token_id':text['eos_token_id'],'tokenizer_endoftext_id':248044,'tokenizer_im_end_id':248046,'note':'Use exact deployed GGUF vocabulary and Ollama-rendered chat bytes. Do not reuse Qwen3-1.7B token counts or assume the HF template is byte-identical to Ollama renderer. HF tokenizer EOS and model text_config EOS IDs differ; retain their distinct source meanings and verify deployed stop handling.'},
      'judgment':{'resource_plausibility':'Plausible single alternative for a measured technical check: far fewer full-attention KV layers can reduce context-dependent memory and attention work.','not_established':'No claim that CPU prefill, full-history wall time, VRAM/RAM or throughput will improve. Eighteen recurrent layers still perform computation; batch, backend, state snapshots, larger vocabulary and projector can offset the memory benefit.','speedup_estimate':None,'selection_recommendation_based_on_effects':None},
      'required_future_checks_if_root_authorizes':['Pin model manifest/blob digests and verify actual GGUF metadata, recurrent-state/attention allocation, CPU/GPU placement and peak working set on the installed 0.35.1 engine.','Verify vocabulary-only NativeTokenizer can load this exact GGUF; freeze binary/tokenizer/template hashes and rebuild every token-limited source unit without truncation.','Verify renderer preserves each message and all previous outputs, think=false handling, JSON schema and tool round trips on the same protocol.','Measure cold and reused full-history prefill/decode at representative 16K/32K settings; do not infer speed from parameter count or official quality benchmarks.','Treat any model/context/quantization/renderer change as a new candidate identity. Repeat authorized same-version 15/60/FULL measurements before a root resource review, then the development pilot. Keep main N=60 and do not combine earlier candidate trajectories.'],
      'sources':[{'title':'Official Qwen2B config','url':'https://huggingface.co/Qwen/Qwen3.5-2B/blob/15852e8c16360a2fea060d615a32b45270f8a8fc/config.json'},{'title':'Official tokenizer config','url':'https://huggingface.co/Qwen/Qwen3.5-2B/blob/15852e8c16360a2fea060d615a32b45270f8a8fc/tokenizer_config.json'},{'title':'Official Q4 Ollama tag','url':'https://ollama.com/library/qwen3.5:2b-q4_K_M'},{'title':'Official tag registry manifest','url':'https://registry.ollama.ai/v2/library/qwen3.5/manifests/2b-q4_K_M'},{'title':'Official tag runtime config','url':'https://registry.ollama.ai/v2/library/qwen3.5/blobs/'+manifest['config']['digest']},{'title':'Pinned bundled qwen35 loader','url':'https://github.com/ggml-org/llama.cpp/blob/b11232/src/models/qwen35.cpp'}],
      'evidence_files':[ref(p) for p in sorted(OUT.iterdir()) if p.is_file() and not p.name.startswith('qwen35_2b_resource_review')],
    }
    dest=OUT/'qwen35_2b_resource_review.json'
    if dest.exists():raise ValueError('Preserve prior review; create a new version')
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    convenience=BASE/'Qwen3.5-2B.json'
    if not convenience.exists():convenience.write_bytes((OUT/'hf_config.json').read_bytes())
    print(json.dumps({'review':str(dest),'F16_KV_16K_MiB':memory[1]['full_attention_F16_KV_MiB'],'F16_KV_32K_MiB':memory[2]['full_attention_F16_KV_MiB'],'download_bytes':size,'Ollama_requires':config['requires'],'actual_model_calls':0}))

if __name__=='__main__':main()
