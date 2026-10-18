"""Assemble the two actual review rounds and their correction trace."""
from pathlib import Path
import json
import hashlib
from html import escape
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research/audits'
OUT.mkdir(exist_ok=True)

corrections=[
    {'ids':['D1','MATH-R1-02'],'issue':'정책별 유효 사례가 달라질 수 있는 비교 문제','fix':'기관별 정책 비교는 2개 응답, 기관쌍 정책 비교는 4개 응답의 공통 유효집합으로 계산. 예정·유효·제외 분모를 함께 기록.','evidence':['../../research/prepare_workflow_v4.py','round2_mechanical.json']},
    {'ids':['D2'],'issue':'장시간 실행의 시점과 정책이 겹칠 가능성','fix':'625개 시장 묶음마다 γ 3종 × 정책 2종의 여섯 대화를 배치. 순서를 사전 해시로 고정하고 같은 기관의 두 정책을 인접 배치.','evidence':['../../data/workflow/manifest.json']},
    {'ids':['D3'],'issue':'목표 인식과 계산 실패를 구분하는 해석 한계','fix':'배분의 목적 적합성을 평가하며 기억·인식·수치 계산의 원인을 단독 식별하지 않는다고 본문·설정에 명시.','evidence':['../../paper/LIBERA_텀페이퍼_초안_20261017.html#limits']},
    {'ids':['D4'],'issue':'이전 신호·검색 실험의 표현 잔존','fix':'같은 γ별 최적 배분과 후속 검색 과제로 표현을 수정. 현재 주실험이 사적신호나 실제 검색을 평가한다는 인상을 제거.','evidence':['../../paper/LIBERA_텀페이퍼_초안_20261017.html#alternatives']},
    {'ids':['D5','R1-F01'],'issue':'PortBench 저자와 APA 인용 미완성','fix':'Zhao, Chen, Su 저자·v6·2026년 10월 9일 버전 및 저자–연도 본문 인용 반영.','evidence':['../../paper/LIBERA_텀페이퍼_초안_20261017.html#ref-portbench']},
    {'ids':['D6'],'issue':'실행 환경 미확정인데 동결로 표시','fix':'실험 설정으로 라벨 변경. 모델의 정확한 제공 버전과 실행 환경을 아직 검증하지 않았다고 명시.','evidence':['../../plan/LIBERA_실험설정_20261017.json']},
    {'ids':['MATH-R1-01'],'issue':'합계 허용오차로 인한 작은 음수 목적값 차이','fix':'비중 보정·손실 0 절단 없이 원래 합계 잔차와 부호를 유지하고 예산 승수로 설명되는 오차를 별도 표시.','evidence':['../../research/prepare_institutional_benchmark.py']},
    {'ids':['MATH-R1-03'],'issue':'분산 항을 변동성으로 설명','fix':'포트폴리오 분산에 비례하는 위험비용으로 명료화.','evidence':['../../paper/LIBERA_텀페이퍼_초안_20261017.html#design']},
    {'ids':['R1-F02','R1-F03'],'issue':'정식 출판·권호 정보 갱신','fix':'Hedden–Raghavan 정식 게재 DOI와 Dell’Acqua 등의 37(2), 403–423 반영.','evidence':['../../research/evidence_ledger_v4.json']},
    {'ids':['R1-F04'],'issue':'근거 대조표의 인용 문헌 누락','fix':'Hedden–Raghavan과 Lewis 원전을 확인 수준·적용 한계와 함께 추가.','evidence':['../../research/evidence_ledger_v4.json']},
    {'ids':['R1-F05'],'issue':'36개월 미래 구간의 현재 사용 여부 불일치','fix':'프레임에서 예약하되 현재 주실험의 AI와 기준 답에는 사용하지 않는다고 통일.','evidence':['../../research/evidence_ledger_v4.json']},
    {'ids':['R1-F06'],'issue':'참고문헌 정렬','fix':'저자명 알파벳 순으로 정렬.','evidence':['../../paper/LIBERA_텀페이퍼_초안_20261017.html#references']},
]
reports={}
for round_number in [1,2]:
    for domain in ['design','math','evidence','mechanical']:
        path=OUT/f'round{round_number}_{domain}.json'
        if path.exists():
            content=json.loads(path.read_text(encoding='utf-8'))
            reports[path.stem]={'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                                'verdict':content.get('overall_status',content.get('overall_verdict',content.get('status','mechanical checks recorded')))}
complete=all(f'round{r}_{d}' in reports for r in [1,2] for d in ['design','math','evidence','mechanical'])
tracked=[ROOT/'plan/LIBERA_실험계획_20261017.html',ROOT/'plan/LIBERA_실험설정_20261017.json',ROOT/'paper/LIBERA_텀페이퍼_초안_20261017.html',ROOT/'research/evidence_ledger_v4.json',ROOT/'research/prepare_institutional_benchmark.py',ROOT/'research/prepare_workflow_v4.py',ROOT/'data/institutional/manifest.json',ROOT/'data/workflow/manifest.json']
originals=[ROOT/'plan/문규리 제안서 상세_최종.html',ROOT/'plan/LIBERA_실험설계서0925.html',ROOT/'plan/LIBERA_실험수행보고서0925.docx']
expected=['3af00703a0e02462','dd7ddd202e6e0fca','0132e952457ec6dd']
original_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
assert all(sha.startswith(prefix) for sha,prefix in zip(original_hashes.values(),expected))
payload={'version':'4.0','generated_at_utc':datetime.now(timezone.utc).isoformat(),'two_round_records_present':complete,'scope':'consistency, logic, topic fit, and primary-source provenance of the pre-experiment design; not certification of AI outcomes or external validity','reports':reports,'first_round_corrections':corrections,'original_files_unchanged':True,'original_sha256':original_hashes,'final_artifact_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked},'AI_experiment_calls':0,'remaining_execution_conditions':['verify exact target model access and immutable backend/model revision','run the prepared campaign and preserve complete requests, responses, errors and timestamps','write observed results and revise abstract/discussion before representing this as an empirical results paper'],'scope_limits':['hypothetical explicit mandates, not real fund risk-aversion estimates','fixed overlapping public-data corpus, descriptive comparison','provided gold mandate use, not actual RAG retrieval','new combination of paper-grounded modules and a declared new workflow treatment']}
(OUT/'verification_v4.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
status='두 차례 검증 기록 작성 완료' if complete else '2차 검증 진행 중'
rows=''.join('<tr><td>'+escape(', '.join(c['ids']))+'</td><td>'+escape(c['issue'])+'</td><td>'+escape(c['fix'])+'</td></tr>' for c in corrections)
report_rows=''.join(f'<tr><td><a href="{escape(v["path"])}">{escape(k)}</a></td><td>{escape(str(v["verdict"]))}</td></tr>' for k,v in reports.items())
html=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LIBERA v4 검증 기록</title><style>body{{max-width:1080px;margin:48px auto;padding:0 24px;font:16px/1.85 "Malgun Gothic",sans-serif;color:#253842}}h1{{font-size:30px}}h2{{margin-top:40px}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:12px;border-bottom:1px solid #dce4e8;text-align:left;vertical-align:top}}th{{background:#eff4f6}}a{{color:#176b7a}}.note{{padding:18px 22px;background:#f0f7f7;border-left:4px solid #237782}}code{{overflow-wrap:anywhere}}</style></head><body>
<p>LIBERA · v4.0 · 2026-10-17</p><h1>{status}</h1>
<p class="note">검증 대상은 실험 전 소논문·계획·수치 기준 답·프롬프트·평가 코드의 <strong>정합성, 논리성, 원주제 연결성, 근거성</strong>이다. 실제 AI 실험은 수행하지 않았다. 검증을 통과했다는 말은 가설이 입증되거나 실제 운용사에 일반화된다는 뜻이 아니다.</p>
<p><a href="../../paper/LIBERA_텀페이퍼_초안_20261017.html">소논문 초안</a> · <a href="../../plan/LIBERA_실험계획_20261017.html">실험계획</a> · <a href="verification_v4.json">해시·변경 추적 전체 기록</a></p>
<h2>네 가지 검증 기준</h2><table><thead><tr><th>기준</th><th>확인한 내용</th></tr></thead><tbody><tr><td>정합성</td><td>소논문·계획·설정·프롬프트·채점기의 식, 계수, 정보 흐름, 비교 분모와 실행 수 일치.</td></tr><tr><td>논리성</td><td>목적의 차이가 기준 배분을 바꾸며, 합리적 수렴·실패·유효집합 선택을 구분. 직접 목적값 손실과 기관쌍 반응오차를 함께 평가.</td></tr><tr><td>주제 연결성</td><td>원래의 필요한 기관별 투자판단 차이를 가상 기관의 위임목적이라는 한 차원으로 직접 검증. 사적정보 전체나 시장 효과를 검증했다고 확대하지 않음.</td></tr><tr><td>근거성</td><td>원문·공식자료의 조건과 새 연구 처치·산술 계산·구현 허용오차를 구별하고 최신 서지·적용 범위 대조.</td></tr></tbody></table>
<h2>검증 절차</h2><p>1차에서는 설계·수학·문헌 담당이 실제 원고와 설정을 읽고 문제를 기록했다. 발견한 문제를 수정한 뒤, 2차에서 수정된 파일과 실행 입력·평가 규칙을 다시 대조했다. 작성자와 검토자의 역할 및 검토 시점의 파일 해시는 개별 기록에 남겼다. 수치 담당은 본인이 만든 기준 답과 루트가 만든 평가 코드를 구별하여 검토했다.</p>
<p>기계 검사는 전체 1,875개 μ·Σ를 원래 월별 수익률과 무위험 수익률에서 독립 재계산하고, 5,625개 실행 묶음의 정보 노출과 예정 호출 수를 대조했다. 평가기의 정답·오류·미응답 처리 검사는 명시적으로 표시한 임시 합성 입력만 사용했으며 AI 응답으로 보관하지 않았다.</p>
<h2>1차 발견 사항과 수정</h2><table><thead><tr><th>검토 항목</th><th>발견 사항</th><th>수정 내용</th></tr></thead><tbody>{rows}</tbody></table>
<h2>2차에서 추가 발견한 문제와 재검증</h2><p>최종 JSON에 지나치게 큰 정수나 과도하게 중첩된 구조가 들어오면 채점 배치가 멈출 수 있는 오류를 발견했다. 해당 예외를 응답별 invalid_final로 처리하도록 수정하고, 10⁴⁰⁰ 정수를 γ와 비중에 넣은 경우 및 2,000단계 중첩 JSON을 다시 시험했다. 세 응답만 오류 처리되고 나머지는 정상적으로 미응답으로 유지되는 것을 확인했다. 연구 수치나 실제 AI 응답을 바꾼 조치는 아니다.</p><p>정답 입력이 0점을 내는 검사에 더해, R4의 모든 기관에 γ=3의 기준 비중을 일괄 적용한 임시 입력도 검사했다. 필요한 기관 간 배분 차이의 소실과 기관별 목적상 손실이 함께 드러나도록 계산됨을 확인했다. 이 입력들은 평가기 점검을 위한 합성 사례이며 실험 결과가 아니다.</p>
<h2>각 회차의 실제 검토 기록</h2><table><thead><tr><th>기록</th><th>판정</th></tr></thead><tbody>{report_rows}</tbody></table>
<h2>검증 후에도 남는 범위와 실행 조건</h2><p>이 설계는 원제안서의 ‘기관별로 필요한 투자판단 차이’를 명시적 위임목적의 차이로 구현한다. 기관의 사적 전망, 실제 펀드의 전략 전체, 공통모델 도입 자체의 인과효과, 실제 검색기의 성능은 이번 실험의 추정 대상이 아니다. 모델의 목표 인식·기억·수치 계산 실패도 최종 배분만으로 각각 식별하지 않는다.</p><p>금융식·γ·자료 체계와 모델 설정에는 논문 근거를 연결했다. long-only와 quadratic의 결합, 네 단계 업무 및 제공 정책은 선언한 새 설계다. 모든 수치와 절차가 하나의 기존 논문에서 검증됐다고 표시하지 않았다.</p><p>실제 실행 전에는 선정 모델의 접근 가능성과 정확한 버전·백엔드 설정을 확정해야 한다. 이후 실제 응답을 수집하고 결과·초록·논의를 갱신한다. 현재 산출물은 설계와 입력·채점 준비를 마친 상태이며 AI 결과 논문은 아니다. 최초 plan 폴더의 원본 세 파일은 수정하지 않았다.</p></body></html>'''
(OUT/'verification_v4.html').write_text(html,encoding='utf-8')
print(json.dumps({'status':status,'reports':len(reports),'originals_unchanged':True},ensure_ascii=False))
