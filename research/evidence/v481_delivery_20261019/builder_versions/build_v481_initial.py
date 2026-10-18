"""Create new paper/status HTML from captured pilot facts, preserving v4.8."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote
from bs4 import BeautifulSoup
import sector_v48_main_gate as main_gate

ROOT=Path(__file__).resolve().parents[1]


def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def link(path,base,label):
    href=quote(os.path.relpath(Path(path).resolve(),base.parent).replace('\\','/'),safe='/._-')
    return '<a href="'+href+'">'+escape(label)+'</a>'
def pct(value):
    if value is None: return '미관측'
    text=format(Decimal(str(value))*100,'f')
    return (text.rstrip('0').rstrip('.') if '.' in text else text)+'%'
def fmt(value): return '미관측' if value is None else str(value)
def resolved(path):
    path=Path(path)
    return path.resolve() if path.is_absolute() else (ROOT/path).resolve()
def require_ref(value,path):
    if not isinstance(value,dict) or resolved(value.get('path',''))!=Path(path).resolve() or value.get('sha256')!=sha(path):
        raise ValueError('Mismatching artifact reference: '+str(path))
def pointer(value,locator):
    if not isinstance(locator,str) or not locator.startswith('/'): raise ValueError('JSON pointer required')
    for part in locator[1:].split('/'):
        part=part.replace('~1','/').replace('~0','~')
        value=value[int(part)] if isinstance(value,list) else value[part]
    return value


def main():
    p=argparse.ArgumentParser();p.add_argument('--evaluation',required=True);p.add_argument('--run-root',required=True)
    p.add_argument('--review-html',required=True);p.add_argument('--audit',action='append',required=True)
    p.add_argument('--self-review',required=True);p.add_argument('--receipt',required=True)
    p.add_argument('--source-review-html',required=True)
    p.add_argument('--prior-evaluation',required=True);p.add_argument('--environment-report',required=True)
    p.add_argument('--operating-record-root',required=True)
    p.add_argument('--current-environment-report',required=True)
    p.add_argument('--technical-receipt',required=True)
    p.add_argument('--main-candidate')
    p.add_argument('--candidate-review',action='append',default=[])
    p.add_argument('--source-review-template')
    args=p.parse_args();evaluation_path=Path(args.evaluation).resolve();report=read(evaluation_path)
    run=Path(args.run_root).resolve();summary=read(run/'summary.json');b=report['primary_C0_bundle']
    if summary['status']=='running': raise ValueError('Do not publish a final pilot status during generation')
    audits=[read(x) for x in args.audit]
    if len(audits)!=3: raise ValueError('Three post-pilot review records required, including retained failures')
    prepared_manifest=resolved(report['provenance']['prepared_manifest']['path'])
    require_ref(report['provenance']['prepared_manifest'],prepared_manifest)
    require_ref(report['provenance']['run_summary'],run/'summary.json')
    require_ref(report['provenance']['run_manifest_snapshot'],run/'manifest_snapshot.json')
    manifest=read(prepared_manifest)
    runtime_path=prepared_manifest.parent/'runtime.json';runtime=read(runtime_path)
    if sha(runtime_path)!=manifest['input_hashes']['runtime.json'] or runtime['model']!='qwen3.5:4b-q4_K_M':
        raise ValueError('Unexpected runtime for this reporting version')
    if read(run/'manifest_snapshot.json')!=manifest or summary.get('planned_cases')!=manifest['roster']:
        raise ValueError('Run and evaluation roster do not match')
    if [r.get('round') for r in audits]!=[1,2,3] or any(r.get('status') not in ('PASS','FAIL') for r in audits):
        raise ValueError('Ordered actual rounds 1, 2, 3 with explicit statuses required')
    require_ref(audits[0].get('manifest'),prepared_manifest)
    if resolved(audits[0].get('run_root',''))!=run: raise ValueError('Round 1 audited another run')
    inventoried=audits[0].get('artifact_inventory',[])
    if {resolved(x['path']) for x in inventoried}!={x.resolve() for x in run.rglob('*') if x.is_file()}:
        raise ValueError('Round 1 inventory does not cover current completed run')
    for item in inventoried: require_ref(item,resolved(item['path']))
    for r in audits[1:]:
        require_ref(r.get('provenance',{}).get('manifest'),prepared_manifest)
        require_ref(r.get('provenance',{}).get('evaluation'),evaluation_path)
    require_ref(audits[2].get('provenance',{}).get('run_summary'),run/'summary.json')
    self_review=read(args.self_review)
    for key,path in [('manifest',prepared_manifest),('evaluation',evaluation_path),('run_summary',run/'summary.json')]:
        require_ref(self_review.get('provenance',{}).get(key),path)
    if summary.get('main_model_calls')!=0 or report.get('main_model_calls_by_this_evaluation')!=0:
        raise ValueError('Pilot-only reporting requires verified zero main calls')
    if summary.get('main_frozen') is not False or summary.get('human_review_completed') is not False or report.get('independent_human_review_completed') is not False or self_review.get('independent_human_review_completed') is not False:
        raise ValueError('Unexpected human review state; update the reporting contract')
    prior_evaluation_path=Path(args.prior_evaluation).resolve();prior_evaluation=read(prior_evaluation_path)
    prior_summary_path=resolved(prior_evaluation['provenance']['run_summary']['path'])
    require_ref(prior_evaluation['provenance']['run_summary'],prior_summary_path)
    prior_summary=read(prior_summary_path);environment=read(args.environment_report)
    require_ref(environment['run_summary'],prior_summary_path)
    if prior_summary_path.parent==run or prior_summary.get('main_model_calls')!=0:
        raise ValueError('The sleep-disrupted pilot must remain a distinct pilot record')
    operating=Path(args.operating_record_root).resolve();operating_summary=read(operating/'summary.json')
    operating_invocation=read(operating/'invocation.json');operation_path=resolved(operating_summary['operation']['path'])
    require_ref(operating_summary['operation'],operation_path)
    operation=read(operation_path)
    require_ref(operation['prior_run_summary'],prior_summary_path)
    if resolved(operating_invocation['run_root'])!=run or resolved(operation['new_run_root'])!=run:
        raise ValueError('Operating record belongs to another repeat')
    if read(operating/'acquire.json')['request']['status']!='active' or operating_summary['awake_release']['status']!='released':
        raise ValueError('Report awake acquisition/restoration failure separately before delivery')
    current_environment_path=Path(args.current_environment_report).resolve()
    current_environment=read(current_environment_path)
    require_ref(current_environment.get('run_summary'),run/'summary.json')
    current_server_log=resolved(current_environment['server_log']['path'])
    require_ref(current_environment['server_log'],current_server_log)
    if report.get('system_integrity_incidents_present') and 'ggml_vulkan: device lost on Vulkan0' not in current_server_log.read_text(encoding='utf-8',errors='replace'):
        raise ValueError('This reporting version requires the preserved Vulkan incident evidence')
    source=ROOT/'paper/LIBERA_텀페이퍼_초안_v4.8_20261018.html'
    if sha(source)!='0775e2d64633d51c2f35a0378406e744ea7e0b0489a71a45b6651599c08ae7d1': raise ValueError('Frozen source paper changed')
    target=ROOT/'paper/LIBERA_텀페이퍼_초안_v4.8.1_20261019.html'
    plan=ROOT/'plan/LIBERA_실험준비현황_v4.8.1_20261019.html'
    if target.exists() or plan.exists() or Path(args.receipt).exists(): raise FileExistsError('Use a new version, do not overwrite research output')
    prior_review=ROOT/'research/evidence/v48_implementation_20261018/round1.json'
    implementation_review=ROOT/'research/evidence/v48_implementation_r2_20261018/round1.json'
    conference_review=ROOT/'research/v481_conference_alignment_20261018.json'
    inputs=[source,evaluation_path,run/'summary.json',prepared_manifest,runtime_path,prior_review,implementation_review,conference_review,Path(args.review_html),Path(args.source_review_html),Path(args.self_review),*[Path(x) for x in args.audit],prior_evaluation_path,prior_summary_path,Path(args.environment_report),current_environment_path,current_server_log,operation_path,operating/'summary.json',operating/'invocation.json',operating/'acquire.json',operating/'release.json']
    technical_path=Path(args.technical_receipt).resolve();technical=read(technical_path)
    if technical.get('artifact_kind')!='v4.8_main_technical_three_review_receipt' or technical.get('status')!='PASS' or technical.get('candidate_bound') is not False or any(type(technical.get(key)) is not int or technical[key]!=0 for key in ('model_calls','main_model_calls')) or technical.get('independent_human_review_completed') is not False:
        raise ValueError('Non-authorizing three-round technical review receipt required')
    for key,names in [('software_hashes',main_gate.SOFTWARE),('evaluator_software_hashes',main_gate.EVALUATOR_SOFTWARE)]:
        if not isinstance(technical.get(key),dict) or set(technical[key])!=set(names): raise ValueError('Incomplete technical software inventory')
        for name,value in technical[key].items():
            if sha(ROOT/'research'/name)!=value: raise ValueError('Technically reviewed code changed: '+name)
            inputs.append(ROOT/'research'/name)
    if len(technical.get('reviews',[]))!=3: raise ValueError('Three technical reviews required')
    for number,reference in enumerate(technical['reviews'],1):
        path=resolved(reference['path']);require_ref(reference,path);review=read(path)
        if review.get('round')!=number or review.get('status')!='PASS': raise ValueError('Technical review order/status mismatch')
        if any(review.get(key)!=technical[key] for key in ('software_hashes','evaluator_software_hashes')): raise ValueError('Technical review code differs')
        inputs.append(path)
    inputs.append(technical_path)
    candidate_path=Path(args.main_candidate).resolve() if args.main_candidate else None
    if candidate_path:
        candidate=read(candidate_path)
        if any(candidate.get(key) is not False for key in ('main_authorized','main_frozen','human_review_completed')) or candidate.get('main_model_calls')!=0:
            raise ValueError('Expected a non-executable, unreviewed-by-human main candidate')
        require_ref(candidate['technical_review']['receipt'],technical_path)
        require_ref(candidate['prior_pilot']['evaluation'],evaluation_path)
        if candidate.get('roster')!=main_gate.roster() or len(candidate.get('files',{}))!=32 or sum(name.startswith('previews/') for name in candidate['files'])!=16: raise ValueError('Unexpected candidate file/case counts')
        for name,value in candidate['files'].items():
            if sha(candidate_path.parent/name)!=value: raise ValueError('Candidate input changed')
            inputs.append(candidate_path.parent/name)
        if len(args.candidate_review)!=3 or not args.source_review_template: raise ValueError('Candidate requires three actual binding reviews and a blank source-review template')
        for number,path in enumerate(args.candidate_review,1):
            review=read(path);require_ref(review.get('candidate_manifest'),candidate_path)
            if review.get('round')!=number or review.get('status')!='PASS' or review.get('main_model_calls')!=0 or review.get('independent_human_review_completed') is not False:
                raise ValueError('Candidate binding review mismatch')
            inputs.append(Path(path))
        template=read(args.source_review_template);require_ref(template.get('candidate_manifest'),candidate_path)
        if template.get('independent_human_review_completed') is not False or template.get('review_status')=='completed': raise ValueError('Human source review must remain honestly pending')
        inputs.extend([candidate_path,Path(args.source_review_template)])
    elif args.candidate_review or args.source_review_template:
        raise ValueError('Candidate-specific records supplied without a candidate')
    input_refs=[{'path':str(x.resolve()),'sha256':sha(x)} for x in inputs]
    for x in (target,plan,Path(args.receipt)):
        if not x.parent.is_dir(): raise ValueError('Output parent missing: '+str(x.parent))
    generated_calls=summary['core_generation_calls']+summary['auxiliary_generation_calls']
    short=(f'예비실험에서 예정된 4사례 중 {b["attempted_case_count"]}사례를 시도했고, '
           f'완료된 첫 최종안 C0는 {b["completed_response_count"]}개, 유효 원배분은 {b["valid_raw_allocation_count"]}개였다.')
    details=(f'실제 생성 요청은 핵심 단계 {summary["core_generation_calls"]}회와 보조 수정 {summary["auxiliary_generation_calls"]}회, 합계 {generated_calls}회다. '
             '실제 요청 기록을 센 값이며 계획 상한을 관측 횟수로 대신하지 않았다. 독립 사람의 의미 검토와 본실험 전 동결은 아직 완료하지 않았다. 본실험은 0건이다.')
    names={'fidelity_q2_2026':'Fidelity Q2 2026','ubs_june_2026':'UBS June 2026'}
    statuses={'completed_response':'응답 완료','not_attempted':'C0 미도달','attempted_no_response':'요청 후 응답 없음',
              'partial_response':'부분 응답','timed_out':'시간 제한 종료','interrupted':'중단','transport_failed':'전송 실패'}
    prepared=Path(report['provenance']['prepared_manifest']['path']).parent
    packets={s:read(prepared/'packets'/f'{s}.json') for s in names}
    rows=[]
    for c in report['primary_C0_cases']:
        e=c['execution'];rows.append('<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in [
            names[c['source_id']],c['arm'],statuses.get(e['attempt_status'],e['attempt_status']),pct(e['raw_sum']),
            '예' if e['valid_raw_allocation'] else '아니요',str(c['source_fact_preservation']['exact_label_correct_count'])+'/11'])+'</tr>')
    table='<div class="table-wrap"><table><caption>개발 예비실험의 첫 최종안 C0. 등급 일치는 출처 ID의 일치도 요구하는 보조 사실 진단이다. ID가 없으면 옮긴 등급 문구가 같아도 점수를 주지 않는다. 전략 보존 점수가 아니다.</caption><thead><tr><th>공개 자료</th><th>제공 절차</th><th>C0 상태</th><th>원비중 합계</th><th>유효 원배분</th><th>출처 ID 포함 등급 일치</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
    aux_rows=[]
    for c in report['auxiliary_endpoint_cases']:
        e=c['execution']
        aux_rows.append('<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in [
            names[c['source_id']],c['arm'],c['endpoint'],statuses.get(e['attempt_status'],e['attempt_status']),
            pct(e['raw_sum']),'예' if e['valid_raw_allocation'] else '아니요'])+'</tr>')
    auxiliary_table=('<div class="table-wrap"><table><caption>실제로 시도된 보조 수정. C0를 대체하거나 새 독립 사례로 세지 않는다. 보조 요청이 없는 사례는 원답의 자격·종료 규칙에 따른 상태이며 수정 성공으로 세지 않는다.</caption><thead><tr><th>공개 자료</th><th>절차</th><th>보조안</th><th>상태</th><th>원비중 합계</th><th>유효 원배분</th></tr></thead><tbody>'+''.join(aux_rows)+'</tbody></table></div>') if aux_rows else '<p>이번 반복에서 실제 보조 수정 요청은 없었다. 이를 수정 능력의 성공이나 실패로 판정하지 않는다.</p>'
    pair_rows=[]
    for row in b['within_source_pairs']+b['between_source_pairs']:
        pair_label=' ↔ '.join(names[x.split('__')[0]]+' ('+x.split('__')[1]+')' for x in row['case_ids'])
        pair_rows.append('<tr><td>'+escape(pair_label)+'</td><td>'+escape(fmt(row['half_L1_distance']))+'</td><td>'+('관측' if row['eligible'] else '비교 불가: 유효 원배분 쌍 없음')+'</td></tr>')
    pair_table='<div class="table-wrap"><table><caption>유효한 원배분에 한정한 ½L1 거리. 작거나 큰 거리 자체는 좋은 전략·나쁜 동질화의 판정이 아니다.</caption><tr><th>비교</th><th>거리</th><th>가용성</th></tr>'+''.join(pair_rows)+'</table></div>'
    comparison=(f'기관 간 비교 가능한 원배분 쌍은 {b["eligible_between_source_pair_count"]}/2개, 같은 자료의 R1/R4 비교 가능한 쌍은 {b["eligible_within_source_pair_count"]}/2개다. '
                '부적합·미완료 답변을 정규화하여 거리 계산에 넣지 않았다. 관측되지 않은 비교는 0이나 차이 없음으로 해석하지 않는다.')
    timing='<p>예비자료의 기준일도 같지 않다. Fidelity Q2의 견해 기준일은 2026년 3월 31일(공식 소개 페이지 갱신 4월 17일), UBS June은 5월 21일(PDF에 명시된 발행일 5월 22일)이다. 이를 공통 4월 21일–7월 16일 시장 관측치와 함께 제시한 사후 문서 조건 사례다. 당시 동시에 공개된 최신 견해나 기관의 실제 보유자산·비공개 목적을 비교한 실험으로 해석하지 않는다. 원문: '+ ' · '.join('<a href="'+escape(packets[s]['source_url'],quote=True)+'">'+escape(names[s])+'</a>' for s in names)+'.</p>'
    review_links=lambda base:' · '.join(link(x,base,'실행 후 '+str(i)+'차 검증: '+audits[i-1]['status']) for i,x in enumerate(args.audit,1))
    issues=report.get('artifact_issues',[])
    unresolved_audits=[r['round'] for r in audits if r['status']!='PASS']
    issue_note=('<p>실행 기록 상태: '+escape(str(summary['status']))+'; 시스템 무결성 사건 보고: '+('있음' if report.get('system_integrity_incidents_present') else '없음')+'; 평가 입력 진단 기록 '+str(len(issues))+'개; 미통과 검증 '+escape(str(unresolved_audits))+'차. 진단 기록에는 시간 제한으로 끝난 부분 응답도 포함될 수 있으며, 그 건수만으로 실행 체계의 결함이나 전략 실패를 판정하지 않는다.</p>')
    if unresolved_audits or report.get('system_integrity_incidents_present') or summary['status']!='all_planned_cases_accounted':
        issue_note+='<p>실행·평가 검증에서 남은 문제를 먼저 확인해야 하므로 본실험 준비 완료로 판정하지 않는다. 원응답과 실패는 그대로 보존한다.</p>'
    if report.get('system_integrity_incidents_present'):
        issue_note+='<p>이번 별도 반복도 네 사례를 모두 마치지는 못했다. Fidelity R4의 마지막 단계 입력 처리 중 보존된 서버 로그에 <code>Vulkan device lost</code>가 기록됐고, 최종 답변을 받기 전에 실행이 중단됐다. 이후 UBS 두 사례는 시도하지 않았다. 이는 모델의 전략 판단 결과가 아닌 실행 환경의 실패다. 장치 오류의 근본 원인을 절전·메모리 부족·드라이버 중 하나로 확정하지 않으며, 자동 절전 방지 요청의 성공만으로 GPU의 장기 안정성까지 검증됐다고 보지 않는다.</p>'
    runtime_note='<p>실제 예비실험은 Qwen3.5-4B Q4_K_M 양자화 실행본과 Ollama '+escape(runtime['engine_version'])+'를 사용했다. 모델·템플릿 해시와 조건을 고정했다. 금융 논문의 기본 모델과 thinking 비활성화 선례를 참고했지만, 이 구현의 성능을 해당 논문 점수와 같다고 주장하지 않는다. 실행 중 오프라인 검토 작업도 같은 PC에서 진행했으므로 소요시간은 이 실행의 관측치이며 전용 성능 시험 결과가 아니다.</p>'
    runtime_note+='<p>실행 순서는 Fidelity R1 → Fidelity R4 → UBS R1 → UBS R4로 고정했으며 순서의 무작위화·교차배치를 하지 않았다. 따라서 소요시간과 시간 초과의 차이를 자료 제공 단계만의 효과로 귀속하지 않는다. 900초의 운영 제한 안에서 완료하지 못한 응답은 이 환경의 관측이며 모델이 시간과 자원에 관계없이 그 과제를 수행할 수 없다는 증거가 아니다.</p>'
    runtime_note+='<p>기관 문서가 모델의 학습자료에 포함되었는지는 확인하지 않았다. R4에서 해당 문서를 입력하지 않은 단계도 모델의 사전지식까지 제거한 조건은 아니므로, 자료 제공 절차와 결과의 관계를 해석할 때 이 한계를 유지한다.</p>'
    prior_bundle=prior_evaluation['primary_C0_bundle']
    prior_note=('<h3>절전으로 중단된 첫 실행과 별도 반복</h3><p>첫 실행에서는 핵심 생성 요청 '+str(prior_summary['core_generation_calls'])+'회와 보조 요청 '+str(prior_summary['auxiliary_generation_calls'])+'회를 기록했고, 완료 C0 '+str(prior_bundle['completed_response_count'])+'개 중 유효 원배분은 '+str(prior_bundle['valid_raw_allocation_count'])+'개였다. Windows의 Modern Standby 기록과 응답 공백이 확인됐으며, 마지막 사례는 생성 전 단계에서 시간 제한으로 종료되어 시스템 무결성 검증을 통과하지 못했다. 설정된 900초와 실제 종료 소요시간도 달랐다. 따라서 미완료 사례를 모두 모델의 과제 수행 능력 탓으로 해석하지 않는다.</p><p>사용자의 재실행 지시에 따라 동일 입력·모델·순서·평가 규칙으로 네 사례 전체를 새 폴더에서 반복했다. 운영상 추가한 것은 실행 중 자동 절전을 막는 Windows 요청이며 영구 전원설정은 바꾸지 않았다. 이 요청의 적용·해제를 기록했지만 수동 절전이나 덮개 닫기까지 방지한다고 주장하지 않는다. 아래 표는 별도 반복의 결과이며, 두 실행에서 더 나은 답을 골라 합치거나 독립 표본으로 세지 않는다. 원 실행의 실패는 보존한다.</p>')
    def observations(base):
        out=[]
        for item in self_review.get('paper_observations',[]):
            ref=item['response_artifact'];require_ref(ref,resolved(ref['path']))
            if item['case_id'] not in {x['case_id'] for x in manifest['roster']} or item['endpoint'] not in ('C0','C1','C2'):
                raise ValueError('Paper observations require a registered final or auxiliary endpoint')
            if resolved(ref['path'])!=run/item['case_id']/item['endpoint']/'record.json':
                raise ValueError('Observation belongs to another run/case/endpoint')
            record=read(resolved(ref['path']))
            if record.get('response_complete') is not True:
                raise ValueError('This summary table is for completed responses; report partial text separately')
            literal=pointer(record,item['response_locator'])
            if not isinstance(literal,str) or not item['model_quote'] or item['model_quote'] not in literal:
                raise ValueError('Observation quote does not match recorded response location')
            for evidence in item.get('evidence_refs',[]):
                path=resolved(evidence['path']);require_ref(evidence,path)
                if path.suffix=='.json' and evidence.get('locator','').startswith('/'):
                    pointer(read(path),evidence['locator'])
            cells=[escape(str(item['case_id']))+' / '+escape(str(item['endpoint'])),escape(item['claim_or_action']),
                   '<q>'+escape(item['model_quote'])+'</q><br>'+link(resolved(ref['path']),base,item['response_locator']),
                   escape(item['evidence_summary']),escape(item['author_assessment'])+'<br>'+escape(item['limits'])]
            out.append('<tr>'+''.join('<td>'+x+'</td>' for x in cells)+'</tr>')
        return '<h3>근거에서 실제 선택까지: AI 작성자의 사례 검토</h3><p>아래는 위치를 확인한 사례 관측이며 독립 사람의 의미 판정이나 전체 전략 보존 점수가 아니다. 같은 응답에서 인용한 여러 문장을 독립 표본으로 늘려 세지 않는다. 상세 근거와 검토 범위는 연결한 작성자 기록에 남겼다.</p><div class="table-wrap"><table><thead><tr><th>사례·응답</th><th>관측 대상</th><th>모델 표현과 위치</th><th>대조 근거</th><th>작성자 판단과 한계</th></tr></thead><tbody>'+''.join(out)+'</tbody></table></div>' if out else '<p>인용 가능한 작성자 사례 관측은 아직 등록되지 않았다. 수치표만으로 근거–행동의 연결을 판정하지 않는다.</p>'
    shared='<h3>연구질문과 결과의 연결</h3><p>이 실험은 같은 AI가 받은 공개 판단을 해석하고, 채택·유보·이탈의 이유를 설명하며, 그 설명에 맞는 실제 산업 비중을 제출하는지 관찰한다. 따라서 원문 등급을 복사했거나 합계를 맞췄다는 사실만으로 기관 판단이 보존됐다고 결론 내리지 않는다. 반대로 합계가 틀린 답의 해석과 근거를 버리지도 않는다. 그 답의 설명은 읽을 수 있지만 정상 배분쌍의 거리 비교에는 쓸 수 없다는 한계를 함께 기록한다.</p><p>네 사례는 개발 예비실험이다. 이전 진단에서 사용한 자료가 포함되고, 한 모델·두 문서·한 시장 입력으로 모집단 효과나 공통 AI 도입의 인과효과를 추정하지 않는다. R1/R4는 자료 노출 시점·위치·사용 기회가 함께 달라지는 업무 절차 비교다.</p>'
    readiness='<h3>본실험 직전에 남은 일</h3><p>독립 검토자는 원문과 모델의 해석·이유·비중을 대조하여 주장별 근거 위치와 판단을 기록해야 한다. AI의 세 차례 자체 검증은 이를 대신하지 않는다. 평가 기준은 이미 정한 명세를 적용하며, 예비 결과에 맞춰 정답 비중이나 유리한 종합점수를 추가하지 않는다. 검토에서 바뀌어야 할 규칙이 발견되면 새 버전과 변경 이유를 남기고 본실험 전에 고정한다.</p>'
    def technical_readiness(base):
        text='<h3>본실험 실행 준비의 범위</h3><p>본실험용 실행·기록·오프라인 평가 코드는 세 차례 기술 검증을 마쳤다. 이는 원문 해석의 타당성이나 모델 전략의 성공을 판정한 결과가 아니다. '+link(technical_path,base,'본실험 코드의 세 차례 검증 기록')+'</p>'
        if candidate_path:
            text+='<p>Fidelity Q3와 UBS July의 공개 자료를 사용할 네 본실험 사례에 대해 단계별 과제 미리보기 16개를 포함한 입력 파일 32개를 준비하고 세 차례 대조했다. 미리보기는 각 단계에 줄 과제이며, 아직 생성되지 않은 모델 답이나 계산 이력은 만들지 않았다. '+link(candidate_path,base,'본실험 입력 후보')+' · '+' · '.join(link(path,base,str(i)+'차 후보 대조') for i,path in enumerate(args.candidate_review,1))+'</p><p>본실험 전에는 사람이 원문의 등급 정의·근거·연구자 요약과 두 자료의 비교 가능성을 확인해야 한다. 사람은 차이가 불명확하거나 직접 비교할 수 없다는 판단도 근거와 함께 기록할 수 있다. '+link(args.source_review_template,base,'완료 전 사람 검토표')+'를 완료한 뒤 해당 입력·평가 버전을 고정하고 실행을 결정한다. 실제 본실험 응답의 의미 검토는 실행 후 별도로 진행한다.</p>'
        else:
            text+='<p>이번 반복의 실행 환경 검증을 통과하지 못해 실제 본실험 입력 후보는 생성하지 않았다. 먼저 동일 과제 길이를 처리할 수 있는 실행 환경을 검증해야 한다. 기술 코드의 검증 통과만으로 후보 생성·사람 검토·본실험 실행을 완료했다고 표기하지 않는다.</p>'
        return text
    body='<p>'+escape(short+' '+details)+'</p>'+issue_note+prior_note+table+auxiliary_table+'<p>'+escape(comparison)+'</p>'+pair_table+timing+runtime_note+shared+readiness
    soup=BeautifulSoup(source.read_text(encoding='utf-8'),'html.parser')
    soup.title.string='공통 생성형 AI는 기관별 투자판단을 보존하는가? · LIBERA v4.8.1'
    soup.select_one('.eyebrow').string='LIBERA 2026 · VERSION 4.8.1 · 실험 규칙 v4.8 유지'
    soup.select_one('.subtitle').string='공개 산업전망의 제공 절차와 근거–배분 연결: 사례 설계와 개발 예비실험'
    soup.select_one('header .meta').string='2026년 10월 19일 · 문헌 검토·본실험 전 설계 및 개발 예비실험 기록 · 저자 정보 제출 전 기입'
    soup.select_one('.status').string='v4.8.1 진행 상태 갱신본 · 독립 사람 의미 검토·본실험 동결 전 · 본실험 0건'
    for anchor in soup.select('header nav a'):
        if anchor.get('href')=='../paper/LIBERA_텀페이퍼_초안_v4.8_20261018.html': anchor['href']='../paper/LIBERA_텀페이퍼_초안_v4.8.1_20261019.html'
    abstract=soup.select_one('.abstract p')
    old='현재는 재설계와 오프라인 자료 준비 단계이고 새 절차의 실험 결과는 없다.'
    if old not in abstract.get_text(): raise ValueError('Expected old abstract state missing')
    abstract.string=abstract.get_text().replace(old,short+' 독립 사람의 근거–배분 연결 검토가 남아 있으므로 전략 보존의 최종 판정은 유보한다.')
    intro=soup.find(id='intro');duplicates=[x for x in intro.find_all('p') if x.get_text().startswith('경제학적으로는')]
    if len(duplicates)!=2: raise ValueError('Unexpected introduction structure')
    duplicates[0].string='경제학적으로는 정보와 판단에 따른 자본 배분의 문제이며, 경영학적으로는 AI 업무에서 근거 전달과 재검토 책임을 조직하는 문제다. 이번에 확보한 자료는 기관의 공개 산업전망이므로 전체 운용목적이나 고객 위험선호의 측정으로 확대하지 않는다. 이하에서는 선행연구, 조작적 정의, 공개자료와 사례 절차를 연결하고, 개발 예비실험의 관측 가능 범위와 본실험 전에 남은 검토를 구분한다.'
    duplicates[1].decompose()
    sec=soup.find(id='readiness')
    preserved_basis=''.join(str(x) for x in sec.find_all('p') if x.get_text().startswith(('이전에는 산술','문헌에서 가져온')))
    if not preserved_basis: raise ValueError('Numeric/source classification paragraphs missing')
    sec.clear();sec.append(BeautifulSoup('<h2>6. 개발 예비실험과 본실험 준비 상태</h2>'+body+observations(target)+'<p>'+review_links(target)+'</p><p>'+link(evaluation_path,target,'오프라인 계산·분모 보고서')+' · '+link(args.review_html,target,'원문·해석·비중 대조 검토표')+' · '+link(args.source_review_html,target,'예비·본실험 원문 비교 검토표')+' · '+link(args.self_review,target,'AI 작성자 검토 기록')+'</p><p>실행기 통합 전 검증은 새 경로의 오프라인 테스트 120개와 세 차례 검토를 거쳤다. 이전 경로의 확장 테스트 113개 중 1개 실패는 그대로 보존하며, 전체 저장소 테스트가 통과했다고 주장하지 않는다. 취소 중 부분 기록을 다루는 문제는 새 실행 경로에서 재현·수정·검증했다.</p><h3>조건의 근거와 개발 기록의 처리</h3>'+preserved_basis,'html.parser'))
    conclusion=soup.find(id='conclusion').find('p')
    sec.append(BeautifulSoup('<p>'+link(runtime_path,target,'실제 모델·템플릿 해시 및 실행 조건')+' · '+link(implementation_review,target,'120개 테스트 및 통합 1차 검증')+' · '+link(prior_review,target,'이전 확장 테스트의 실패 포함 기록')+'</p>','html.parser'))
    sec.append(BeautifulSoup(technical_readiness(target),'html.parser'))
    conclusion.string=conclusion.get_text().replace('현재는 재설계 단계이며 문헌이 제안하는 방법의 타당성과 실제 모델이 수행한 결과를 구별한다.',short+' 이러한 개발 관측과 문헌이 제안하는 방법의 타당성을 구별하며, 독립 의미 검토 없이 기관 판단 보존의 성공이나 실패를 일반화하지 않는다.')
    for text in soup.find_all(string=lambda x:x and '현재 실행기 통합은 미완료.' in x): text.replace_with(str(text).replace('현재 실행기 통합은 미완료.','현재 실행기 통합·예비 실행 기록은 제6절에서 구분한다.'))
    for text in soup.find_all(string=lambda x:x and 'Fidelity Q3 공개일은 7월 16일' in x):
        text.replace_with(str(text).replace('Fidelity Q3 공개일은 7월 16일','Fidelity Q3의 공식 소개 페이지 갱신일은 7월 16일').replace("Fidelity 산업표의 ‘6/31/26’ 오타도 보존한다.","Fidelity 산업표의 달력상 존재하지 않는 ‘6/31/26’ 표기도 보존한다. 소개 페이지의 갱신일을 PDF의 최초 발행일로 단정하지 않는다."))
    for text in soup.find_all(string=lambda x:x and 'R4가 기관 문서를 받기 전에는 해당 기관의 정체' in x):
        text.replace_with(str(text).replace('R4가 기관 문서를 받기 전에는 해당 기관의 정체·평가표·숨겨진 제약이 피드백에 포함되지 않는다.','R4가 배정된 기관 문서를 받기 전에는 그 배정 정보·평가표·숨겨진 제약이 피드백에 포함되지 않는다. 공통 기준 비중 등의 자료 출처 표시는 모든 조건에 동일하게 제시된다.'))
    for text in soup.find_all(string=lambda x:x and '결과 전에는 어느 절차도 입증된 해결책이 아니다.' in x): text.replace_with(str(text).replace('결과 전에는 어느 절차도 입증된 해결책이 아니다.','본실험과 독립 검토 전에는 어느 절차도 입증된 해결책이 아니다.'))
    response_discussion='''<h3>관측에서 대응 방향으로</h3><p>상경·경영학적 문제는 문장 오류 자체보다 조직이 그 설명을 근거로 자본 배분 제안을 승인하는 과정에 있다. 근거의 출처와 실제 선택을 함께 확인하지 않으면, 문서화된 판단이 존재해도 승인된 제안에 전달되었는지 알 수 없다. 이 연구는 그 전달 경로를 관찰하지만, 실제 운용 손실이나 사회적 비용을 측정하지는 않는다.</p><p>첫째, 분석 담당자는 산업별 원문·시점·등급 정의와 AI가 옮긴 이유를 대조하고, 출처의 주장과 모델의 추론을 구별할 수 있다. 이는 E2A-Bench의 사실–이유–행동 구분과 FinFIRST의 출처 추적 원칙을 이 과제에 적용한 운영 제안이다. 둘째, 시스템 담당자는 ‘수정했다’는 문장 대신 제출된 비중 합계와 이전 비중 대비 실제 변화를 확인하고, 실행 불가능한 안을 승인 대상에서 분리할 수 있다. 계산 통과 후에도 전략적 이유의 검토는 남는다. 이 절차는 전략을 계산기가 대신 선택한다는 뜻이 아니다.</p><p>셋째, 업무 설계자는 자료를 처음 주는 절차와 마지막에 주는 절차의 근거 보존, 완료 여부, 검토 부담을 함께 비교해야 한다. 어느 시점이 더 좋은지는 사전에 단정하지 않는다. 이번 예비실험의 소요시간은 관측하지만 사람 검토 시간이나 대응안의 순편익은 측정하지 않았으므로 임의의 비용·효과 수치를 붙이지 않는다. 이 대응안들의 효과는 더 많은 자료·모델·시장 상태와 독립 검토자를 포함한 후속 비교에서 확인해야 한다.</p>'''
    soup.find(id='implications').append(BeautifulSoup(response_discussion,'html.parser'))
    soup.find(id='appendix').append(BeautifulSoup('<p>'+link(conference_review,target,'학술제 개요와 문제·근거·대응안 연결 점검')+' · 사용자 제공 개요의 추정 배점은 실험 지표로 사용하지 않았다.</p>','html.parser'))
    soup.find(id='appendix').append(BeautifulSoup('<p>'+link(prior_evaluation_path,target,'절전 중단 원 실행의 평가')+' · '+link(args.environment_report,target,'Windows 절전 및 실제 소요시간 증거')+' · '+link(operation_path,target,'별도 반복의 사전 운영 등록')+' · '+link(operating/'summary.json',target,'자동 절전 방지 적용·해제 기록')+'</p>','html.parser'))
    soup.find(id='appendix').append(BeautifulSoup('<p>'+link(current_environment_path,target,'별도 반복의 운영·GPU 오류 조사')+' · '+link(current_server_log,target,'GPU 오류가 남은 서버 로그 보존본')+'</p>','html.parser'))
    for source_id,anchor,author,date,year_suffix in [
        ('fidelity_q2_2026','ref-fidelity26','Fidelity Investments','2026a','2026b'),
        ('ubs_june_2026','ref-ubs26','UBS Chief Investment Office Global Wealth Management','2026a, May 22','2026b, June 22')]:
        existing=soup.find(id=anchor)
        first=existing.find(string=True)
        first.replace_with(str(first).replace('(2026).','('+year_suffix+').').replace('(2026, June 22).','('+year_suffix+').'))
        source_note=('예비실험 자료. 견해 기준일 3월 31일, 공식 소개 페이지 갱신일 4월 17일. PDF 발행일로 단정하지 않는다.' if source_id.startswith('fidelity') else '예비실험 자료. 견해 기준일 5월 21일, PDF 발행일 5월 22일.')
        entry='<li id="'+anchor+'-pilot">'+escape(author)+'. ('+date+'). <i>'+escape(packets[source_id]['title'])+'</i> [Public outlook]. <a href="'+escape(packets[source_id]['source_url'],quote=True)+'">공식 원문</a><span class="refnote">'+source_note+'</span></li>'
        existing.insert_before(BeautifulSoup(entry,'html.parser'))
    source_heading=soup.find('h3',string='4.1. 공개자료와 산업 단위')
    if source_heading is None: raise ValueError('Expected source section heading missing')
    source_heading.find_next_sibling('p').insert_after(BeautifulSoup('<p class="small">기관 원문 인용: Fidelity Investments (<a href="#ref-fidelity26-pilot">2026a: Q2</a>, <a href="#ref-fidelity26">2026b: Q3</a>); UBS Chief Investment Office Global Wealth Management (<a href="#ref-ubs26-pilot">2026a: June</a>, <a href="#ref-ubs26">2026b: July</a>). 예비·본사례의 자료를 같은 문서로 합쳐 인용하지 않는다.</p>','html.parser'))
    soup.footer.string='v4.8.1 · 실험 규칙은 v4.8. 이전 버전과 실패 원문을 보존한다. 자체 검증·개발 예비실험·독립 사람 검토·본실험은 서로 다른 상태다.'
    explain='<p>같은 AI에게 미국 11개 산업의 공통 시장표를 주고, Fidelity 또는 UBS의 공개 전망 하나를 적용해 배분안을 만들게 한다. 한 조건은 첫 단계부터 전망을 읽고(R1), 다른 조건은 먼저 세 단계를 진행한 뒤 마지막에 전망을 읽는다(R4). AI는 해석, 대안과 위험 검토, 임시 배분, 최종 재검토를 거친다. 계산기는 제출된 숫자를 검사할 뿐 기관별 정답 비중을 대신 정하지 않는다.</p><p>투자 대상은 에너지·소재·산업재·경기소비재·필수소비재·건강관리·금융·정보기술·커뮤니케이션 서비스·유틸리티·부동산의 11개 산업 바구니다. 위험 수치는 과거 수익률의 변동성 진단이며 미래 손실확률이나 기관별 위험선호가 아니다.</p>'
    style=str(soup.find('style'))
    plan_html='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LIBERA v4.8.1 실험 준비 현황</title>'+style+'</head><body><main><header><h1>실험 준비 현황 · v4.8.1</h1><p>실험 규칙 v4.8 유지 · 개발 예비실험 기록 · 본실험 미실행</p><nav>'+link(target,plan,'갱신한 소논문 초안')+link(ROOT/'plan/LIBERA_실험계획_v4.8_20261018.html',plan,'전체 고정 설계')+link(args.review_html,plan,'원문·결과 검토표')+'</nav></header><section><h2>무엇을 하는 실험인가</h2>'+explain+'</section><section><h2>실제 진행 결과와 남은 요건</h2>'+body+technical_readiness(plan)+'<p>'+review_links(plan)+'</p><p>'+link(ROOT/'research/progress_20261018.html',plan,'과정 기록')+' · '+link(evaluation_path,plan,'평가 원자료')+'</p></section></main></body></html>'
    for x in input_refs:
        if sha(x['path'])!=x['sha256']: raise ValueError('Input changed while building documents')
    with target.open('x',encoding='utf-8') as handle: handle.write(str(soup))
    with plan.open('x',encoding='utf-8') as handle: handle.write(plan_html)
    receipt={'created_at_utc':datetime.now(timezone.utc).isoformat(),'artifact_kind':'v4.8.1_document_status_update_not_protocol_revision',
        'inputs':input_refs,'builder':{'path':str(Path(__file__).resolve()),'sha256':sha(__file__)},
        'outputs':[{'path':str(x),'sha256':sha(x)} for x in (target,plan)],
        'observed_core_requests':summary['core_generation_calls'],'observed_auxiliary_requests':summary['auxiliary_generation_calls'],
        'main_model_calls':0,'independent_human_review_completed':False,'model_calls_by_builder':0,'frozen_v48_modified':False}
    Path(args.receipt).write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__': main()
