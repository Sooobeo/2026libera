"""Pinned vocabulary-only llama.cpp tokenizer, Linux/Windows AMD64.

ABI source: https://raw.githubusercontent.com/ggml-org/llama.cpp/6f767fe96/include/llama.h
The actual model and shared libraries are hash-pinned in a deployment config.
No inference context or tensor weights are loaded. Run the CLI in a subprocess
on a new deployment before importing into a long-lived campaign.
"""
from __future__ import annotations
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import struct

ABI_ID='llama.cpp-6f767fe96-model-params-80-amd64'

class ModelParams(C.Structure):
    _fields_=[('devices',C.c_void_p),('tensor_buft_overrides',C.c_void_p),('n_gpu_layers',C.c_int32),
              ('split_mode',C.c_int),('load_mode',C.c_int),('lazy_mode',C.c_int),('main_gpu',C.c_int32),
              ('tensor_split',C.c_void_p),('progress_callback',C.c_void_p),('progress_callback_user_data',C.c_void_p),
              ('kv_overrides',C.c_void_p),('vocab_only',C.c_bool),('check_tensors',C.c_bool),('use_extra_bufts',C.c_bool),
              ('no_host',C.c_bool),('no_alloc',C.c_bool),('load_mtp',C.c_bool)]

def file_sha(path):
    digest=hashlib.sha256()
    with open(path,'rb') as handle:
        for chunk in iter(lambda:handle.read(8*1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

class NativeTokenizer:
    def __init__(self,config):
        if C.sizeof(C.c_void_p)!=8 or C.sizeof(ModelParams)!=80 or config.get('abi_identity')!=ABI_ID:
            raise ValueError('Tokenizer ABI must be explicitly pinned to the supported 64-bit header.')
        self.config=dict(config)
        self.hashes={}
        for item in [*config['libraries'],{'path':config['gguf_path'],'sha256':config['gguf_sha256']}]:
            path=Path(item['path']).resolve()
            actual=file_sha(path)
            if actual!=item['sha256']:raise ValueError('Tokenizer/model binary hash mismatch: '+str(path))
            self.hashes[str(path)]=actual
        if not any(Path(x['path']).resolve()==Path(config['library_path']).resolve() for x in config['libraries']):
            raise ValueError('Main libllama shared library must appear in the hash-pinned library list.')
        self.dll_cookie=os.add_dll_directory(str(Path(config['library_path']).parent)) if os.name=='nt' else None
        self.handles=[]
        for item in config['libraries']:
            self.handles.append(C.CDLL(str(Path(item['path']).resolve()),mode=getattr(C,'RTLD_GLOBAL',0)))
        self.dll=C.CDLL(str(Path(config['library_path']).resolve()))
        signatures={
            'llama_model_default_params':([],ModelParams),
            'llama_model_load_from_file':([C.c_char_p,ModelParams],C.c_void_p),
            'llama_model_free':([C.c_void_p],None),
            'llama_model_get_vocab':([C.c_void_p],C.c_void_p),
            'llama_vocab_n_tokens':([C.c_void_p],C.c_int32),
            'llama_vocab_get_add_bos':([C.c_void_p],C.c_bool),
            'llama_vocab_get_add_eos':([C.c_void_p],C.c_bool),
            'llama_tokenize':([C.c_void_p,C.c_char_p,C.c_int32,C.POINTER(C.c_int32),C.c_int32,C.c_bool,C.c_bool],C.c_int32)}
        for name,(args,restype) in signatures.items():
            function=getattr(self.dll,name);function.argtypes=args;function.restype=restype
        params=self.dll.llama_model_default_params();params.vocab_only=True;params.n_gpu_layers=0;params.use_extra_bufts=False
        self.model=self.dll.llama_model_load_from_file(str(Path(config['gguf_path']).resolve()).encode('utf-8'),params)
        if not self.model:raise RuntimeError('Pinned vocabulary-only load failed.')
        self.vocab=self.dll.llama_model_get_vocab(self.model)
        self.vocabulary_size=int(self.dll.llama_vocab_n_tokens(self.vocab))
        self.add_bos=bool(self.dll.llama_vocab_get_add_bos(self.vocab));self.add_eos=bool(self.dll.llama_vocab_get_add_eos(self.vocab))
        if config.get('vocabulary_size') is not None and config['vocabulary_size']!=self.vocabulary_size:
            raise ValueError('Unexpected vocabulary size.')
        self.identity='native:'+config['gguf_sha256']+':'+config['model_sha256']

    def tokens(self,text,*,add_special=True):
        raw=text.encode('utf-8')
        needed=self.dll.llama_tokenize(self.vocab,raw,len(raw),None,0,add_special,True)
        if needed==0:return []
        if needed>0:raise RuntimeError('Unexpected tokenizer sizing response.')
        buffer=(C.c_int32 * -needed)()
        actual=self.dll.llama_tokenize(self.vocab,raw,len(raw),buffer,-needed,add_special,True)
        if actual!=-needed:raise RuntimeError('Tokenizer size changed.')
        return list(buffer)

    def count(self,text):return len(self.tokens(text))

    def receipt(self,text):
        ids=self.tokens(text)
        return {'method':'exact_installed_libllama_vocab_only','abi_identity':ABI_ID,'token_count':len(ids),
                'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
                'token_ids_sha256':hashlib.sha256(struct.pack('<'+'i'*len(ids),*ids)).hexdigest(),
                'model_sha256':self.config['model_sha256'],'gguf_sha256':self.config['gguf_sha256'],
                'vocabulary_size':self.vocabulary_size,'library_hashes':self.hashes,
                'add_bos':self.add_bos,'add_eos':self.add_eos,'generation_calls':0,'vocab_only':True}

    def close(self):
        if getattr(self,'model',None):self.dll.llama_model_free(self.model);self.model=None
        if self.dll_cookie:self.dll_cookie.close();self.dll_cookie=None

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();config=json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    tokenizer=NativeTokenizer(config)
    samples=['Hello, world.','forecast -0.0123456789; precision r=0.5','<|im_start|>user\nReturn JSON.\n<|im_end|>']
    result={'status':'native_vocab_loaded_and_counted','samples':[tokenizer.receipt(t) for t in samples],
            'provider_count_crosscheck':False,'generation_calls':0}
    Path(args.output).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');tokenizer.close()
    print(json.dumps({'status':result['status'],'sample_counts':[x['token_count'] for x in result['samples']]}))
