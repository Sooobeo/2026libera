"""Synthetic transport-artifact tests. Never call an actual model or HTTP API."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from research.v63.ollama_transport import OllamaTransport, packed, digest_bytes
from research.v63.recovery import RecoveryClient, RecoveryInterruption


def fixture(tmp_path,count=1):
    history=tmp_path/'prior';history.mkdir()
    freeze=dict(model='pinned:test',model_sha256='a'*64,engine_revision='0.35.1',
                chat_template_sha256=digest_bytes(b'template'),quantization_level='Q4_K_M',
                temperature=0,output_tokens=64,context_tokens=4096,request_timeout=90,
                think=None,seed_support='supported',seed=7,
                allowed_response_schema_sha256=[digest_bytes(packed({'type':'object'}))])
    request=packed(dict(model=freeze['model'],messages=[{'role':'user','content':'same exact prompt'}],
                        temperature=0,max_output_tokens=64,stream=False,seed=7,
                        response_schema={'type':'object'},expected_prompt_tokens=100))
    for i in range(1,count+1):save_attempt(history/f'attempt_{i:06d}',freeze,request)
    return history,freeze,request


def save_attempt(folder,freeze,request):
    folder.mkdir()
    (folder/'runner_request.bin').write_bytes(request)
    (folder/'attempt_receipt.json').write_bytes(packed(dict(generation_requests=1,
        runner_request_sha256=digest_bytes(request),model_sha256=freeze['model_sha256'],completed_at_utc='2026-10-27T00:01:00+00:00')))
    adapter=object.__new__(OllamaTransport);adapter.freeze=freeze
    body=adapter._translate(request)
    for prefix in ['before','after']:
        exchange(folder,prefix+'_version','/api/version',b'',{'version':'0.35.1'})
        exchange(folder,prefix+'_tags','/api/tags',b'',{'models':[{'name':freeze['model'],'digest':freeze['model_sha256']}]})
        exchange(folder,prefix+'_show','/api/show',packed({'model':freeze['model']}),
                 {'template':'template','details':{'quantization_level':'Q4_K_M'},'capabilities':['completion']})
    exchange(folder,'generation','/api/chat',body,dict(model=freeze['model'],message={'content':'{"answer":42}'},
             done=True,done_reason='stop',prompt_eval_count=100,eval_count=7,total_duration=99),generation=True)


def exchange(folder,label,path,body,response,*,generation=False):
    raw=packed(response)
    (folder/(label+'.request.bin')).write_bytes(body)
    (folder/(label+'.response.bin')).write_bytes(raw)
    receipt=dict(url='http://127.0.0.1:11435'+path,method='POST' if body else 'GET',
        request_sha256=digest_bytes(body),response_sha256=digest_bytes(raw),response_bytes=len(raw),
        generation_endpoint=generation,http_status=200,elapsed_seconds=12.5 if generation else .01,
        started_at_utc='2026-10-27T00:00:00+00:00')
    (folder/(label+'.receipt.json')).write_bytes(packed(receipt))


class Live:
    def __init__(self,freeze):self.freeze=deepcopy(freeze);self.calls=[]
    def __call__(self,request):
        self.calls.append(request)
        return dict(content='{}',model_sha256=self.freeze['model_sha256'],finish_reason='stop',transport_generation_requests=1)


def test_verified_response_replayed_then_new_request_sent_once(tmp_path):
    history,freeze,request=fixture(tmp_path);live=Live(freeze)
    client=RecoveryClient(history,freeze,live,history_quiescent=True)
    r=client(request)
    assert r['content']=='{"answer":42}' and r['usage']['eval_count']==7
    assert r['replayed'] and r['source_elapsed_seconds']==12.5
    assert r['transport_generation_requests']==1 and r['new_generation_requests']==0 and live.calls==[]
    fresh=request.replace(b'same exact prompt',b'next prompt')
    assert client(fresh)['new_generation_requests']==1
    assert live.calls==[fresh]
    receipt=client.recovery_receipt()
    assert receipt['replayed_attempts']==[str(history.resolve()/'attempt_000001')]
    assert receipt['freeze_status_modified'] is False and receipt['new_live_calls']==1


def test_live_continuation_requires_explicit_campaign_quiescence(tmp_path):
    history,freeze,request=fixture(tmp_path);live=Live(freeze);client=RecoveryClient(history,freeze,live)
    assert client(request)['replayed']
    with pytest.raises(RecoveryInterruption) as e:client(request)
    assert not e.value.retryable and e.value.new_generation_requests==0
    assert not e.value.generation_attempted and live.calls==[]


def test_exact_request_bytes_not_semantic_json_equivalence(tmp_path):
    history,freeze,request=fixture(tmp_path);live=Live(freeze);client=RecoveryClient(history,freeze,live,history_quiescent=True)
    equivalent=json.dumps(json.loads(request),indent=2).encode()
    with pytest.raises(RecoveryInterruption):client(equivalent)
    assert live.calls==[]
    with pytest.raises(RecoveryInterruption):client(request) # permanently halted


@pytest.mark.parametrize('problem',['partial','after_missing','hash_tampered','model_drift','template_drift','prompt_count'])
def test_uncertain_or_drifted_attempts_never_generate_again(tmp_path,problem):
    history,freeze,request=fixture(tmp_path);p=history/'attempt_000001'
    if problem=='after_missing':(p/'after_show.response.bin').unlink()
    elif problem=='hash_tampered':(p/'generation.response.bin').write_bytes(b'{}')
    elif problem in ['model_drift','template_drift']:
        label='after_tags' if problem=='model_drift' else 'after_show'
        obj=json.loads((p/(label+'.response.bin')).read_bytes())
        if problem=='model_drift':obj['models'][0]['digest']='b'*64
        else:obj['template']='changed template'
        body=(p/(label+'.request.bin')).read_bytes()
        exchange(p,label,'/api/tags' if problem=='model_drift' else '/api/show',body,obj)
    else:
        obj=json.loads((p/'generation.response.bin').read_bytes())
        if problem=='partial':obj['done']=False
        else:obj['prompt_eval_count']=99
        exchange(p,'generation','/api/chat',(p/'generation.request.bin').read_bytes(),obj,generation=True)
    live=Live(freeze);client=RecoveryClient(history,freeze,live,history_quiescent=True)
    with pytest.raises(RecoveryInterruption) as e:client(request)
    assert e.value.generation_attempted and e.value.new_generation_requests==0 and live.calls==[]


def test_verified_prefix_replays_before_ambiguous_tail_stops(tmp_path):
    history,freeze,request=fixture(tmp_path,count=2)
    (history/'attempt_000002'/'attempt_receipt.json').unlink()
    live=Live(freeze);client=RecoveryClient(history,freeze,live,history_quiescent=True)
    assert client(request)['replayed']
    with pytest.raises(RecoveryInterruption):client(request)
    assert live.calls==[]


def test_explicitly_unsent_tail_can_continue_but_generation_file_conflict_cannot(tmp_path):
    history,freeze,request=fixture(tmp_path);p=history/'attempt_000001'
    for f in p.glob('generation.*'):f.unlink()
    receipt=json.loads((p/'attempt_receipt.json').read_bytes());receipt['generation_requests']=0
    (p/'attempt_receipt.json').write_bytes(packed(receipt))
    live=Live(freeze);client=RecoveryClient(history,freeze,live,history_quiescent=True)
    assert not client(request)['replayed'] and live.calls==[request]
    (p/'generation.request.bin').write_bytes(b'uncertain dispatch')
    live2=Live(freeze);blocked=RecoveryClient(history,freeze,live2,history_quiescent=True)
    with pytest.raises(RecoveryInterruption):blocked(request)
    assert live2.calls==[]


def test_prior_history_mutation_halts_even_valid_replay(tmp_path):
    history,freeze,request=fixture(tmp_path);live=Live(freeze);client=RecoveryClient(history,freeze,live,history_quiescent=True)
    (history/'late_writer_marker').write_text('writer still active')
    with pytest.raises(RecoveryInterruption):client(request)
    assert live.calls==[]


def test_valid_hashes_do_not_allow_changed_translated_generation_request(tmp_path):
    history,freeze,request=fixture(tmp_path);p=history/'attempt_000001'
    body=json.loads((p/'generation.request.bin').read_bytes());body['options']['temperature']=.5
    exchange(p,'generation','/api/chat',packed(body),json.loads((p/'generation.response.bin').read_bytes()),generation=True)
    live=Live(freeze);client=RecoveryClient(history,freeze,live,history_quiescent=True)
    with pytest.raises(RecoveryInterruption):client(request)
    assert live.calls==[]


def test_history_gaps_and_live_output_reuse_rejected(tmp_path):
    history,freeze,request=fixture(tmp_path)
    (history/'attempt_000001').rename(history/'attempt_000002')
    with pytest.raises(RecoveryInterruption):RecoveryClient(history,freeze,Live(freeze),history_quiescent=True)
    (history/'attempt_000002').rename(history/'attempt_000001')
    live=Live(freeze);live.logs=history
    with pytest.raises(RecoveryInterruption):RecoveryClient(history,freeze,live,history_quiescent=True)
