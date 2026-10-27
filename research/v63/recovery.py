"""Read-only replay of verified Ollama attempts, then explicitly safe live work.

An absent/partial response is never permission to send the old request again.
The campaign must hold its run lock and assert history_quiescent before this
wrapper may generate anything. This module never authorizes or changes a model
freeze, repairs a response, writes prior artifacts, or retries an interruption.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

from research.v63.ollama_transport import OllamaTransport, packed, digest_bytes
from research.v63.transport_errors import InfraFailure, ProtocolViolation


class RecoveryInterruption(InfraFailure):
    def __init__(self,message,*,generation_attempted=True):
        super().__init__('Recovery interrupted: '+message,retryable=False,
                         partial_content=None,generation_attempted=generation_attempted)
        self.new_generation_requests=0
        self.recovery_interrupted=True


def _read_json(path):
    value=json.loads(path.read_bytes())
    if not isinstance(value,dict):raise ValueError('Expected JSON object: '+path.name)
    return value


def _tree_snapshot(folder):
    result={}
    for p in sorted(folder.rglob('*')):
        if p.is_symlink():raise ValueError('History symlinks are not accepted.')
        if p.is_file():result[p.relative_to(folder).as_posix()]=digest_bytes(p.read_bytes())
    return result


def _http_exchange(folder,label,*,path,body,method,generation,origin=None):
    receipt=_read_json(folder/(label+'.receipt.json'))
    request=(folder/(label+'.request.bin')).read_bytes()
    raw=(folder/(label+'.response.bin')).read_bytes()
    if request!=body or receipt.get('request_sha256')!=digest_bytes(request):
        raise ValueError(label+' request bytes/hash differ from the frozen request.')
    if receipt.get('response_sha256')!=digest_bytes(raw) or receipt.get('response_bytes')!=len(raw):
        raise ValueError(label+' response bytes/hash mismatch.')
    if receipt.get('http_status')!=200 or receipt.get('method')!=method or receipt.get('generation_endpoint') is not generation:
        raise ValueError(label+' is not a successful complete expected HTTP exchange.')
    url=urlsplit(receipt.get('url',''))
    if url.scheme not in {'http','https'} or not url.hostname or url.username or url.password or url.path!=path or url.query or url.fragment:
        raise ValueError(label+' HTTP endpoint differs from the expected endpoint.')
    this_origin=url.scheme+'://'+url.netloc
    if origin is not None and this_origin!=origin:raise ValueError('Mixed HTTP origins in one prior attempt.')
    elapsed=receipt.get('elapsed_seconds')
    if isinstance(elapsed,bool) or not isinstance(elapsed,(int,float)) or not math.isfinite(elapsed) or elapsed<0:
        raise ValueError(label+' has no valid elapsed-time receipt.')
    return raw,receipt,this_origin


def _identity(folder,prefix,freeze,origin=None):
    version,_,origin=_http_exchange(folder,prefix+'_version',path='/api/version',body=b'',method='GET',generation=False,origin=origin)
    tags,_,_=_http_exchange(folder,prefix+'_tags',path='/api/tags',body=b'',method='GET',generation=False,origin=origin)
    show,_,_=_http_exchange(folder,prefix+'_show',path='/api/show',body=packed({'model':freeze['model']}),method='POST',generation=False,origin=origin)
    version,tags,show=map(json.loads,(version,tags,show))
    if not all(isinstance(x,dict) for x in (version,tags,show)) or not isinstance(tags.get('models'),list):
        raise ValueError('Malformed prior identity envelopes.')
    if version.get('version')!=freeze['engine_revision']:raise ValueError('Prior engine revision differs from freeze.')
    models=[m for m in tags['models'] if isinstance(m,dict) and (m.get('name')==freeze['model'] or m.get('model')==freeze['model'])]
    if len(models)!=1 or models[0].get('digest')!=freeze['model_sha256']:raise ValueError('Prior model digest differs from freeze.')
    if digest_bytes(show.get('template','').encode('utf-8'))!=freeze['chat_template_sha256']:
        raise ValueError('Prior chat template differs from freeze.')
    if show.get('details',{}).get('quantization_level')!=freeze['quantization_level']:
        raise ValueError('Prior quantization differs from freeze.')
    if freeze['think'] is not None and 'thinking' not in show.get('capabilities',[]):
        raise ValueError('Prior model did not declare the pinned thinking capability.')
    return origin


@dataclass
class _Attempt:
    folder: Path
    request: bytes|None
    response: dict|None=None
    safe_unsent: bool=False
    error: str|None=None
    generation_attempted: bool=True


def _verify_attempt(folder,freeze,*,last):
    request=None;attempted=True
    try:
        request=(folder/'runner_request.bin').read_bytes()
        envelope=_read_json(folder/'attempt_receipt.json')
        if envelope.get('runner_request_sha256')!=digest_bytes(request) or envelope.get('model_sha256')!=freeze['model_sha256']:
            raise ValueError('Prior runner request/model receipt hash mismatch.')
        if not isinstance(envelope.get('completed_at_utc'),str) or not envelope['completed_at_utc']:
            raise ValueError('Prior attempt has no completed receipt.')
        count=envelope.get('generation_requests')
        if type(count) is not int or count not in (0,1):raise ValueError('Prior generation-attempt count is not explicit.')
        # Use the exact transport translator without constructing an HTTP client
        # or creating output folders. This validates all frozen request fields.
        adapter=object.__new__(OllamaTransport);adapter.freeze=deepcopy(freeze)
        body=adapter._translate(request)
        if count==0:
            # The adapter sets generation_started before creating any generation
            # artifacts. Both a completed zero receipt and absence of such files
            # are required. A zero attempt in the middle is not a replayable call.
            if any(folder.glob('generation.*')):raise ValueError('Zero-generation receipt conflicts with generation artifacts.')
            attempted=False
            if not last:raise ValueError('An unsent attempt is followed by other history; cannot safely align replay.')
            return _Attempt(folder,request,safe_unsent=True,generation_attempted=False)
        origin=_identity(folder,'before',freeze)
        raw,receipt,_=_http_exchange(folder,'generation',path='/api/chat',body=body,method='POST',generation=True,origin=origin)
        _identity(folder,'after',freeze,origin)
        result=json.loads(raw)
        if not isinstance(result,dict) or result.get('done') is not True or not isinstance(result.get('message'),dict) or not isinstance(result['message'].get('content'),str):
            raise ValueError('Prior model response is incomplete or malformed.')
        if result.get('model')!=freeze['model']:raise ValueError('Prior returned model name differs from freeze.')
        expected=json.loads(request).get('expected_prompt_tokens')
        if expected is not None and result.get('prompt_eval_count')!=expected:
            raise ValueError('Prior provider prompt tokens differ from exact preflight.')
        reason=result.get('done_reason','stop')
        if not isinstance(reason,str) or reason=='incomplete':raise ValueError('Prior finish reason is incomplete/malformed.')
        response=dict(content=result['message']['content'],model_sha256=freeze['model_sha256'],finish_reason=reason,
            usage={k:result.get(k) for k in ('prompt_eval_count','eval_count','total_duration','prompt_eval_duration','eval_duration','load_duration')},
            transport_generation_requests=1,transport_log=str(folder),replayed=True,
            source_elapsed_seconds=receipt['elapsed_seconds'],new_generation_requests=0)
        return _Attempt(folder,request,response=response)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,ProtocolViolation) as exc:
        return _Attempt(folder,request,error=f'{folder.name}: {type(exc).__name__}: {exc}',generation_attempted=attempted)


class RecoveryClient:
    def __init__(self,previous_http_dir,freeze,live_client,*,history_quiescent=False):
        self.previous=Path(previous_http_dir).resolve()
        if not self.previous.is_dir():raise RecoveryInterruption('Prior HTTP history directory is missing.')
        self.freeze=deepcopy(freeze);self.live_client=live_client
        self.history_quiescent=history_quiescent is True
        self.cursor=0;self.replayed_attempts=[];self.new_calls=0;self.blocked=None
        if hasattr(live_client,'freeze') and live_client.freeze!=freeze:
            raise RecoveryInterruption('Live transport configuration differs from recovery freeze.',generation_attempted=False)
        if hasattr(live_client,'logs'):
            dest=Path(live_client.logs).resolve()
            if dest==self.previous or self.previous in dest.parents:
                raise RecoveryInterruption('Live transport must use a separate output history directory.',generation_attempted=False)
        try:
            self.snapshot=_tree_snapshot(self.previous)
            folders=sorted(p for p in self.previous.iterdir() if p.name.startswith('attempt_'))
            for i,p in enumerate(folders,1):
                if not p.is_dir() or p.name!=f'attempt_{i:06d}':
                    raise ValueError('Prior attempt numbering is malformed or has gaps.')
            self.attempts=[_verify_attempt(p,self.freeze,last=i==len(folders)-1) for i,p in enumerate(folders)]
            if _tree_snapshot(self.previous)!=self.snapshot:raise ValueError('Prior history changed during validation.')
        except (OSError,ValueError) as exc:
            raise RecoveryInterruption(str(exc)) from exc
        self.history_sha256=digest_bytes(packed(self.snapshot))

    def _interrupt(self,message,*,attempted=True):
        self.blocked=message
        raise RecoveryInterruption(message,generation_attempted=attempted)

    def __call__(self,raw_request):
        if self.blocked:self._interrupt('This recovery client was already interrupted: '+self.blocked)
        if not isinstance(raw_request,bytes):self._interrupt('Canonical request must be bytes.',attempted=False)
        try:current=_tree_snapshot(self.previous)
        except (OSError,ValueError) as exc:self._interrupt(str(exc))
        if current!=self.snapshot:self._interrupt('Prior history changed after validation; no further replay or sending is allowed.')
        if self.cursor<len(self.attempts):
            old=self.attempts[self.cursor]
            if old.error:self._interrupt(old.error,attempted=old.generation_attempted)
            if raw_request!=old.request:self._interrupt('Reconstructed request differs byte-for-byte from '+old.folder.name,attempted=old.generation_attempted)
            if old.response is not None:
                self.cursor+=1;self.replayed_attempts.append(str(old.folder))
                return deepcopy(old.response)
            if not old.safe_unsent:self._interrupt('Prior attempt has no safely reusable outcome.')
            # A proven-unsent tail is consumed only after explicit quiescence.
            if not self.history_quiescent:self._interrupt('Live continuation requires campaign lock/quiescence confirmation.',attempted=False)
            self.cursor+=1
        if not self.history_quiescent:self._interrupt('Live continuation requires campaign lock/quiescence confirmation.',attempted=False)
        if self.live_client is None:self._interrupt('No live transport supplied.',attempted=False)
        # Check freeze once more: a mutable live client must not drift after init.
        if hasattr(self.live_client,'freeze') and self.live_client.freeze!=self.freeze:
            self._interrupt('Live transport freeze changed after validation.',attempted=False)
        self.new_calls+=1
        result=self.live_client(raw_request)
        if not isinstance(result,dict):self._interrupt('Live transport returned a malformed normalized response.')
        result=deepcopy(result)
        result.update(replayed=False,new_generation_requests=result.get('transport_generation_requests',1))
        return result

    def recovery_receipt(self):
        return dict(previous_http_dir=str(self.previous),history_sha256=self.history_sha256,
                    history_file_hashes=deepcopy(self.snapshot),history_quiescent=self.history_quiescent,
                    prior_attempts=len(self.attempts),replayed_attempts=list(self.replayed_attempts),
                    consumed_prior_attempts=self.cursor,new_live_calls=self.new_calls,
                    interrupted=self.blocked,freeze_status_modified=False,
                    model_sha256=self.freeze['model_sha256'])
