"""Ollama 0.35.1 HTTP adapter candidate; exact prompt/tokenizer still required.

This uses the runner's JSON-envelope tool loop, not Ollama native tool_calls.
The adapter never retries. Only runtime.call_with_retries owns retry policy.
Model/version/template are checked before and after every generation attempt.
Raw request/response bytes and metadata checks are saved separately per attempt.

Primary references:
https://raw.githubusercontent.com/ollama/ollama/v0.35.1/api/types.go
https://docs.ollama.com/api/chat
https://docs.ollama.com/api/tags
https://docs.ollama.com/capabilities/structured-outputs
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import http.client
import json
from pathlib import Path
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from research.v63.transport_errors import InfraFailure, ProtocolViolation
from research.v63.campaign_control import atomic_json


def packed(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def retry_after_seconds(value):
    if not value:return 0
    try:return max(0,float(value))
    except ValueError:
        try:return max(0,(parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds())
        except (ValueError,TypeError):return 0


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


class OllamaTransport:
    """freeze pins model, model_sha256, engine_revision='0.35.1',
    chat_template_sha256, quantization_level, temperature, output_tokens,
    context_tokens, request_timeout, think, seed_support, optional seed,
    allowed_response_schema_sha256, and optional fixed_options.

    Call with the canonical bytes from runtime.run_trajectory. Exact rendered
    token counting is deliberately outside this adapter; an HTTP API being
    reachable does not establish context capacity or experiment readiness.
    """
    def __init__(self,base_url,freeze,log_dir,*,opener=None):
        parsed=urllib.parse.urlsplit(base_url)
        if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'','/'}:
            raise ValueError('A plain HTTP(S) service origin without credentials/path is required.')
        required={'model','model_sha256','engine_revision','chat_template_sha256','quantization_level',
                  'temperature','output_tokens','context_tokens','request_timeout','think','seed_support',
                  'allowed_response_schema_sha256'}
        if required-set(freeze):raise ValueError('Missing transport freeze fields: '+', '.join(sorted(required-set(freeze))))
        if freeze['engine_revision']!='0.35.1':raise ValueError('This candidate is pinned to Ollama 0.35.1.')
        if freeze['seed_support']=='supported' and not isinstance(freeze.get('seed'),int):raise ValueError('Missing frozen seed.')
        if not isinstance(freeze['allowed_response_schema_sha256'],list) or not freeze['allowed_response_schema_sha256']:
            raise ValueError('Response schema hashes must be frozen before any generation.')
        self.origin=base_url.rstrip('/')
        self.freeze=deepcopy(freeze)
        self.logs=Path(log_dir)
        self.logs.mkdir(parents=True,exist_ok=True)
        self.opener=opener or urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirects())
        self.next_id=1
        while (self.logs/f'attempt_{self.next_id:06d}').exists():self.next_id+=1
        self.next_render_id=1
        while (self.logs/f'render_{self.next_render_id:06d}').exists():self.next_render_id+=1

    def render_and_count(self,request,tokenizer):
        """Use the same installed Ollama renderer without generating tokens."""
        folder=self.logs/f'render_{self.next_render_id:06d}';folder.mkdir(exist_ok=False);self.next_render_id+=1
        # Direct-main mode verifies identity immediately before and after the
        # actual generation. Repeating all three metadata queries here adds
        # no extra model response or information to that same dispatch.
        if not self.freeze.get('skip_duplicate_render_identity',False):
            self._identity(folder,'identity')
        body=json.loads(self._translate(packed(request)));body['_debug_render_only']=True
        raw=self._http(folder,'render','/api/chat',packed(body),generation=False)
        result=json.loads(raw);info=result.get('_debug_info',{})
        rendered=info.get('rendered_template')
        if result.get('model')!=self.freeze['model'] or not isinstance(rendered,str) or not rendered:
            raise ProtocolViolation('Exact render-only response is unavailable.')
        if result.get('eval_count',0) or result.get('prompt_eval_count',0) or result.get('message',{}).get('content') or result.get('message',{}).get('thinking'):
            raise ProtocolViolation('Unexpected generation during render-only preflight.',generation_attempted=True)
        position=0
        for index,message in enumerate(request['messages']):
            content=message['content'].strip(' \t\r\n')
            located=rendered.find(content,position)
            if located<0:raise ProtocolViolation(f'Renderer omitted or changed history message {index}.')
            position=located+len(content)
        (folder/'rendered_prompt.txt').write_text(rendered,encoding='utf-8',newline='')
        receipt=tokenizer.receipt(rendered)
        receipt.update(renderer_model=self.freeze['model'],chat_template_sha256=self.freeze['chat_template_sha256'],
                       expected_output_tokens=request['max_output_tokens'],context_tokens=self.freeze['context_tokens'])
        (folder/'tokenizer_receipt.json').write_bytes(packed(receipt))
        return receipt['token_count']

    def _http(self,folder,label,path,body=None,*,generation=False):
        request=urllib.request.Request(self.origin+path,data=body,headers={'Content-Type':'application/json'},method='POST' if body is not None else 'GET')
        (folder/(label+'.request.bin')).write_bytes(body or b'')
        receipt={'url':self.origin+path,'method':request.method,'request_sha256':digest_bytes(body or b''),
                 'generation_endpoint':generation,'started_at_utc':datetime.now(timezone.utc).isoformat()}
        started=time.perf_counter()
        raw=b''
        if generation:
            atomic_json(folder/'generation.dispatch_started.json',{'status':'dispatch_started_or_indeterminate_if_interrupted',
                'started_at_utc':receipt['started_at_utc'],'request_sha256':receipt['request_sha256'],'generation_requests_upper_bound':1})
        try:
            with self.opener.open(request,timeout=self.freeze['request_timeout']) as response:
                receipt['http_status']=response.status
                receipt['content_type']=response.headers.get('Content-Type')
                try:
                    raw=response.read()
                except http.client.IncompleteRead as exc:
                    raw=exc.partial
                    raise InfraFailure('Partial HTTP content; do not regenerate',retryable=False,
                                       partial_content=raw.decode('utf-8','replace'),generation_attempted=generation) from exc
                except (TimeoutError,socket.timeout) as exc:
                    # Response headers have arrived. Treat this conservatively as
                    # an incomplete attempt, not a fresh pre-content retry.
                    raise InfraFailure('Timeout after response headers',retryable=False,partial_content='',generation_attempted=generation) from exc
        except urllib.error.HTTPError as exc:
            raw=exc.read()
            receipt.update(http_status=exc.code,retry_after=exc.headers.get('Retry-After'))
            raise InfraFailure(f'HTTP {exc.code}',retryable=exc.code==429 or 500<=exc.code<600,
                               retry_after=retry_after_seconds(exc.headers.get('Retry-After')),generation_attempted=generation) from exc
        except urllib.error.URLError as exc:
            receipt['network_error']=type(exc.reason).__name__
            retryable=isinstance(exc.reason,(TimeoutError,socket.timeout))
            raise InfraFailure(str(exc),retryable=retryable,generation_attempted=generation) from exc
        except (TimeoutError,socket.timeout) as exc:
            receipt['network_error']=type(exc).__name__
            raise InfraFailure(str(exc),retryable=True,generation_attempted=generation) from exc
        finally:
            (folder/(label+'.response.bin')).write_bytes(raw)
            receipt.update(elapsed_seconds=time.perf_counter()-started,response_sha256=digest_bytes(raw),response_bytes=len(raw))
            (folder/(label+'.receipt.json')).write_bytes(packed(receipt))
        return raw

    def _identity(self,folder,prefix):
        version=json.loads(self._http(folder,prefix+'_version','/api/version'))
        tags=json.loads(self._http(folder,prefix+'_tags','/api/tags'))
        show=json.loads(self._http(folder,prefix+'_show','/api/show',packed({'model':self.freeze['model']})))
        if not all(isinstance(item,dict) for item in (version,tags,show)) or not isinstance(tags.get('models'),list):
            raise ProtocolViolation('Malformed identity API envelope.')
        if version.get('version')!=self.freeze['engine_revision']:raise ProtocolViolation('Ollama engine revision changed.')
        models=[m for m in tags.get('models',[]) if isinstance(m,dict) and (m.get('name')==self.freeze['model'] or m.get('model')==self.freeze['model'])]
        if len(models)!=1 or models[0].get('digest')!=self.freeze['model_sha256']:raise ProtocolViolation('Ollama model digest changed or missing.')
        if digest_bytes(show.get('template','').encode('utf-8'))!=self.freeze['chat_template_sha256']:
            raise ProtocolViolation('Ollama chat template changed.')
        if show.get('details',{}).get('quantization_level')!=self.freeze['quantization_level']:
            raise ProtocolViolation('Ollama quantization changed.')
        if self.freeze['think'] is not None and 'thinking' not in show.get('capabilities',[]):
            raise ProtocolViolation('Pinned think option lacks declared model support.')

    def _translate(self,raw_request):
        req=json.loads(raw_request)
        required={'model','messages','temperature','max_output_tokens','stream','response_schema'}
        if required-set(req) or set(req)-required-{'seed','expected_prompt_tokens'}:raise ProtocolViolation('Unknown runner request schema.')
        if req['model']!=self.freeze['model'] or req['temperature']!=self.freeze['temperature'] or req['max_output_tokens']!=self.freeze['output_tokens'] or req['stream'] is not False:
            raise ProtocolViolation('Request differs from frozen model/sampler/output/stream policy.')
        if digest_bytes(packed(req['response_schema'])) not in self.freeze['allowed_response_schema_sha256']:
            raise ProtocolViolation('Response schema hash drift.')
        if self.freeze['seed_support']=='supported':
            if req.get('seed')!=self.freeze['seed']:raise ProtocolViolation('Frozen seed mismatch.')
        elif 'seed' in req:raise ProtocolViolation('Unverified seed support cannot be assumed.')
        options=deepcopy(self.freeze.get('fixed_options',{}))
        forbidden={'num_ctx','num_predict','temperature','seed'} & set(options)
        if forbidden:raise ProtocolViolation('Fixed hardware options cannot override sampler/context fields.')
        options.update(num_ctx=self.freeze['context_tokens'],num_predict=self.freeze['output_tokens'],temperature=self.freeze['temperature'])
        if 'seed' in req:options['seed']=req['seed']
        payload={'model':req['model'],'messages':req['messages'],'stream':False,'format':req['response_schema'],
                 'options':options,'truncate':False,'shift':False}
        if self.freeze['think'] is not None:payload['think']=self.freeze['think']
        return packed(payload)

    def __call__(self,raw_request):
        folder=self.logs/f'attempt_{self.next_id:06d}'
        folder.mkdir(exist_ok=False)
        self.next_id+=1
        (folder/'runner_request.bin').write_bytes(raw_request)
        generation_started=False
        try:
            body=self._translate(raw_request)
            try:self._identity(folder,'before')
            except (InfraFailure,ValueError,TypeError,KeyError) as exc:
                raise ProtocolViolation('Unable to verify model identity before generation: '+str(exc)) from exc
            generation_started=True
            raw=self._http(folder,'generation','/api/chat',body,generation=True)
            try:
                result=json.loads(raw)
            except (ValueError,UnicodeError):
                return {'content':raw.decode('utf-8','replace'),'finish_reason':'incomplete',
                        'model_sha256':self.freeze['model_sha256'],'transport_generation_requests':1,'transport_log':str(folder)}
            if not isinstance(result,dict) or not isinstance(result.get('message'),dict) or not isinstance(result['message'].get('content'),str):
                return {'content':raw.decode('utf-8','replace'),'finish_reason':'incomplete',
                        'model_sha256':self.freeze['model_sha256'],'transport_generation_requests':1,'transport_log':str(folder)}
            try:self._identity(folder,'after')
            except (InfraFailure,ValueError,TypeError,KeyError) as exc:
                raise ProtocolViolation('Unable to verify model identity after generation: '+str(exc),generation_attempted=True) from exc
            if result.get('model')!=self.freeze['model']:
                raise ProtocolViolation('Returned model name differs from pinned model.',generation_attempted=True)
            expected=json.loads(raw_request).get('expected_prompt_tokens')
            if expected is not None and result.get('prompt_eval_count')!=expected:
                raise ProtocolViolation('Provider prompt token count differs from exact preflight tokenizer.',generation_attempted=True)
            content=result.get('message',{}).get('content','')
            return {'content':content,'model_sha256':self.freeze['model_sha256'],
                    'finish_reason':result.get('done_reason','stop') if result.get('done') is True else 'incomplete',
                    'usage':{k:result.get(k) for k in ('prompt_eval_count','eval_count','total_duration','prompt_eval_duration','eval_duration','load_duration')},
                    'transport_generation_requests':1,'transport_log':str(folder)}
        except ProtocolViolation as exc:
            exc.generation_attempted=exc.generation_attempted or generation_started
            raise
        finally:
            atomic_json(folder/'attempt_receipt.json',{'generation_requests':int(generation_started),
                'runner_request_sha256':digest_bytes(raw_request),'model_sha256':self.freeze['model_sha256'],
                'completed_at_utc':datetime.now(timezone.utc).isoformat()})
