## 6. 결과에 따른 해결방안

공통 GenAI를 활용하는 펀드 투자판단의 과잉수렴과 부정적 동질화에 대응하려면, 각 펀드의 정보와 운용조건이 뒷받침하는 판단 차이를 보존하면서 투자판단의 품질도 확보해야 한다. 본실험에서 비교한 배치 중 평균적으로 두 목표를 함께 개선한 방식은 확인되지 않았다. 따라서 특정 배치를 완화책으로 채택하기보다, 근거를 해석하고 후속 선택에 적용하는 Workflow RAG의 구조를 보완할 필요가 있다. 본고는 다음 두 가지 보완 방향과 도입 전의 보조대책을 제안한다.

첫째, 상충하는 근거의 채택 기준을 사전에 정하여 Workflow RAG에 포함한다. 기관별 자료가 검색되더라도 공통 시장 전망과 다른 근거를 어떻게 다룰지 정해져 있지 않으면, 펀드별 정보가 투자판단에 작용했는지 알기 어렵다. 이에 운용사가 정한 투자목표와 운용기간을 기준으로 자료의 시점, 분석 대상과 불확실성을 대조하여 해당 펀드에 적용할 근거를 선택하도록 한다. 예를 들어 같은 산업을 공통 시장 전망은 긍정적으로, 펀드별 전망은 부정적으로 평가하면, 두 전망의 전제와 적용 기간을 비교하고 채택·보류 이유를 제시한다. 어느 쪽을 채택할지 판단하기 어려운 경우에는 상반된 전망을 구분하여 후속 평가의 입력으로 전달한다. 추가 자료가 필요한 쟁점에 대해서는 검색 범위와 횟수를 정해 반대근거를 검색한다.[^1] 전망의 채택 여부는 경제적 타당성과 해당 펀드에 대한 적용 가능성을 기준으로 정한다.

둘째, 판단 전제가 바뀌면 투자대안과 배분을 다시 검토하도록 업무 흐름을 보완한다. 후속 단계에서 근거가 갱신되거나 해석이 달라지면, 그 근거를 사용한 산업 평가와 투자대안 선택 단계로 돌아가도록 한다. 예를 들어 특정 산업의 증액을 뒷받침하던 전망이 약해졌다면, 산업 평가를 갱신하고 증액·유지·감액 대안을 현재 보유와 위험한도에 맞추어 다시 비교한다. 재검토 범위에는 바뀐 전제에 의존한 판단뿐 아니라 그에 따른 자금 이동과 전체 위험의 변화도 포함한다. 수치 계산과 제약 검사는 이러한 대안 비교를 뒷받침하고, 위반이 발견되면 해당 대안의 수정으로 연결하는 기본 절차로 둔다.[^2] 이 방안은 공통 AI의 선행 판단을 계속 이어받으면서 기관별 근거를 재검토할 기회가 제한되는 상황에 대응하려는 제안이다.

이러한 시스템 보완과 별도로, Workflow RAG 도입 전에는 GenAI 활용에 관한 내부 지침을 마련한다. 직원들이 개별적으로 활용한 AI의 해석도 후속 업무에 이어질 수 있으므로, 업무 단계별 AI의 활용 범위와 검토 책임을 정한다. 투자검토서에는 원자료의 사실, AI의 해석, 운용자의 판단을 구분하고 해당 해석을 펀드에 적용할 이유를 기재한다.[^3] 운용자가 AI 추천안을 보기 전에 핵심 투자논거와 반대근거, 검토대안을 정리한 뒤 AI 분석과 대조하는 절차도 둘 수 있다. 기관의 사전 판단 역시 새로운 근거에 따라 수정할 수 있도록 한다. 이는 기존 검토서와 회의 절차에 적용할 수 있는 도입 전 보조대책이며, 본실험에서 동질화 완화효과가 검증된 방안으로 제시하지 않는다.

보완책의 채택 여부는 필요한 전략 차이와 판단 품질을 함께 기준으로 정한다. 같은 정보와 유사한 운용조건이 같은 선택을 지지한다면 배분의 유사성은 합리적일 수 있다. 반대로 배분 간 차이가 커져도 기대수익 손실이나 제약 위반이 증가하면 완화책으로 채택하기 어렵다.[^4] 후속 비교에서는 공통정보와 펀드별 조건을 맞추어 보완 절차를 계획·작성·점검의 각 배치에 적용하고, 과잉수렴과 차이의 정합성, 모형상 기대수익 손실 및 유효성을 함께 평가한다. 필요한 차이의 회복이 판단 품질의 저하를 동반하지 않는 업무와 정보조건부터 적용하고, 추가 검색과 재검토에 드는 시간·비용도 채택 기준에 포함한다.

기관별 근거가 실제 선택에 작용했는지도 평가해야 한다. 후속 통제 과제에서는 다른 조건을 유지한 채 핵심 근거를 바꾸고 기준배분도 다시 계산하여 선택의 반응을 비교한다. 선택이 유지된다면 다른 근거나 제약이 이를 뒷받침하는지 살핀다.[^5] 기존 비중의 유지도 근거에 따른 판단인지, 제약에 따른 보류인지, 제안 실패에 따른 처리인지 구분한다. 이상의 방안은 본실험에서 확인된 공동 개선의 한계에 대응하는 설계 제안이며, 그 효과와 실제 운용에서의 적용 가능성은 후속 검증의 대상으로 남긴다.

[^1]: Asai, A., Wu, Z., Wang, Y., Sil, A., & Hajishirzi, H. (2023). [Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection](https://arxiv.org/abs/2310.11511). arXiv:2310.11511. 자료의 관련성을 검토하고 필요에 따라 검색하는 구조를 참고하였다. 전망의 채택 기준과 금융업무의 충돌 처리 절차는 본고의 제안이다. 본실험에서 검색 누락이 확인되었다는 뜻은 아니다.

[^2]: Gou, Z., et al. (2024). [CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing](https://arxiv.org/abs/2305.11738v4). ICLR 2024. 외부 검증의 결과를 출력의 수정에 연결하는 구조를 참고하였다. 판단 전제가 바뀔 때 관련 투자대안까지 재검토하는 Workflow RAG 설계의 효과는 별도 검증이 필요하다.

[^3]: ESMA. (2024, May 30). [On the use of Artificial Intelligence (AI) in the provision of retail investment services](https://www.esma.europa.eu/sites/default/files/2024-05/ESMA35-335435667-5924__Public_Statement_on_AI_and_investment_services.pdf), §§4–5; CFA Institute. (2022). [Ethics and Artificial Intelligence in Investment Management A Framework for Professionals](https://www.cfainstitute.org/-/media/documents/article/industry-research/Ethics-and-Artificial-Intelligence-in-Investment-Management_Online.pdf). 직원의 제3자 AI 활용에 대한 관리와 투자업무의 감독·책임 원칙을 참고하였다. ESMA 성명은 EU 소매투자서비스에 관한 것이며, 본문의 검토서 항목과 사전 투자논거 작성은 본고의 보조대책이다.

[^4]: Bommasani, R., Creel, K. A., Kumar, A., Jurafsky, D., & Liang, P. (2022). [Picking on the Same Person: Does Algorithmic Monoculture lead to Outcome Homogenization?](https://proceedings.neurips.cc/paper_files/paper/2022/hash/17a234c91f746d9625a75cf8a8731ee2-Abstract-Conference.html). Advances in Neural Information Processing Systems, 35, 3663–3678. 개별 판단의 품질과 여러 판단 사이의 관계를 구분하여 평가하는 관점을 참고하였다. 펀드별로 필요한 차이의 기준과 보완책의 채택 기준은 본고의 분석 틀에 따른다.

[^5]: Matton, K., Ness, R. O., Guttag, J., & Kıcıman, E. (2025). [Walk the Talk? Measuring the Faithfulness of Large Language Model Explanations](https://proceedings.iclr.cc/paper_files/paper/2025/file/b5ec50eb177908f21f78ed0d76ed525c-Paper-Conference.pdf). ICLR 2025. 설명에서 제시한 근거와 입력 변경에 따른 실제 선택의 반응을 대조하는 관점을 참고하였다. 선택이 변하지 않았다는 이유만으로 근거 미반영을 단정하지 않는다.
