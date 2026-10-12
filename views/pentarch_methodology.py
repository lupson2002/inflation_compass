"""PENTARCH 전략 설명 (2026-10-11 신설) — 연금 혼합의 한 축. 원본 프로젝트: /home/mikey/pentarch (docs/00~55).

수치 출처: pentarch 하네스(output/harness.json, v18.3 2026-10-11), docs/51·53·54·55.
"""

import streamlit as st

import pension_mix as PM

st.markdown(
    """
    <style>
    div.block-container { padding-top: 2.6rem; }
    .ic-intro { font-size: 15px; color: #52564d; margin: 0 0 4px; line-height: 1.6; }
    .ic-body p, .ic-body ul, .ic-body ol { margin: 0 0 8px; font-size: 14px; line-height: 1.48; }
    .ic-body ul, .ic-body ol { padding-left: 20px; }
    .ic-body li { margin-bottom: 3px; }
    .ic-body h4 { font-size: 14px; margin: 14px 0 4px; font-weight: 700; color: #16191a; }
    .ic-body h4:first-child { margin-top: 0; }
    .ic-body .formula { background: #f2f3ee; border-radius: 5px; padding: 8px 12px; font-size: 13px; margin: 4px 0 8px; line-height: 1.6; }
    .ic-body table { border-collapse: collapse; font-size: 13px; margin: 6px 0 10px; }
    .ic-body th, .ic-body td { border: 1px solid #e1e0d9; padding: 5px 9px; text-align: left; vertical-align: top; }
    .ic-body th { background: #f2f3ee; font-weight: 600; }
    .ic-body .chg { color: #2f7d4f; font-weight: 600; }
    .pt-flow { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 10px 0 14px; }
    .pt-flow .box { background: #f7f8f4; border: 1px solid #e1e0d9; border-radius: 8px; padding: 8px 12px; font-size: 13px; }
    .pt-flow .box b { display: block; font-size: 13.5px; color: #16191a; }
    .pt-flow .arr { color: #8a8d84; font-size: 18px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🏛️ PENTARCH 전략 설명")
pent = PM.load_pentarch_target()
if pent:
    st.info(f"**현재 연금용 목표 ({pent.get('model', '')})**: {PM.weights_str(pent['target'])} · {pent['effective_since']} 부터 · "
            f"데이터 {pent['data_asof']}" + (" ⚠️ 신호가 오래됨" if pent.get("stale") else ""))

tab_glance, tab_engine, tab_defense, tab_test = st.tabs(["한눈에 보기", "엔진 구조", "방어 장치", "검증과 한계"])

with tab_glance:
    st.markdown(
        """
        <div class="ic-body">
        <p class="ic-intro"><b>한 줄 요약</b> — 경제를 다섯 기둥(성장·인플레·유동성·밸류에이션·심리)으로 점수 매기고, 지금이 어떤 경제 국면인지
        확률로 추정한 뒤, 16개 자산 중 매력도가 가장 높은 <b>2개</b>를 고릅니다. 하락 추세인 자산은 빼고 그 자리는 현금으로 둡니다. 매월 1회.</p>
        </div>
        <div class="pt-flow">
          <div class="box"><b>① 다섯 기둥</b>FRED 거시지표 + 시장가격 → z 점수</div><div class="arr">→</div>
          <div class="box"><b>② 국면 확률</b>HMM 4국면</div><div class="arr">→</div>
          <div class="box"><b>③ 자산 매력도</b>국면 선호 + 밸류에이션 + 머신러닝 예측</div><div class="arr">→</div>
          <div class="box"><b>④ 상위 2개</b>추세 통과 자산 중 · 위험 균등 배분</div><div class="arr">→</div>
          <div class="box"><b>⑤ 실행</b>월말 다음 날 체결</div>
        </div>
        <div class="ic-body">
        <h4>투자 대상 16개 + 현금</h4>
        <table>
        <tr><th>종류</th><th>자산</th></tr>
        <tr><td>주식</td><td>SPY(미국) · QQQ(나스닥) · IWM(소형주) · EFA(선진국) · EEM(신흥국) · VNQ(리츠)</td></tr>
        <tr><td>채권</td><td>TLT(장기국채) · IEF(중기국채) · LQD(회사채) · HYG(하이일드) · EMB(신흥국채) · TIP(물가연동채)</td></tr>
        <tr><td>실물</td><td>GLD(금) · GDX(금광주) · DBC(원자재) · XLE(에너지주)</td></tr>
        <tr><td>현금</td><td>BIL(초단기채) — 추세필터에 걸린 몫이 여기로</td></tr>
        </table>

        <h4>두 가지 판</h4>
        <table>
        <tr><th></th><th>운용판 (일반계좌)</th><th><b>연금판 (이 대시보드의 연금 혼합에 쓰는 것)</b></th></tr>
        <tr><td>레버리지</td><td>2배 ETF(SSO·QLD·UWM·UGL 등)로 노셔널 2배</td><td><b>없음</b> — 같은 신호, 1배 ETF</td></tr>
        <tr><td>보유</td><td>상위 2개 × 2배</td><td>상위 2개 50/50 (한쪽이 추세 탈락이면 남은 1개 100%)</td></tr>
        <tr><td>성과 2008~ (일간, 15bp, 다음 날 체결)</td><td>23.5% / 최대낙폭 −31.9% / Sharpe 0.90</td><td><b>15.6% / −23.1% / Sharpe 0.92</b></td></tr>
        <tr><td>성과 1994~ (대체지수 포함)</td><td>19.4% / −34.2%</td><td>14.2% / −23.7%</td></tr>
        </table>
        <p>현재 운용 모델은 <b>v18.3</b> (2026-10-11~) 입니다. 연금 혼합은 IC 연금형 50% + PENTARCH 연금판 50% — 두 전략의 월간 상관은 0.48 이라 섞으면
        낙폭이 줄어듭니다(혼합 2008-02~ 연 15.3% / 최대낙폭 −13.0%).</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with tab_engine:
    st.markdown(
        """
        <div class="ic-body">
        <h4>① 다섯 기둥 — 각 지표를 과거 5~10년 대비 z 점수로 바꿔 가중평균</h4>
        <table>
        <tr><th>기둥</th><th>재료</th><th>비고</th></tr>
        <tr><td>성장</td><td><b>S&amp;P500 200일 추세</b> (v18~) · 수익률곡선 · 산업생산 · 실업수당 청구 · 고용 · CFNAI</td><td>국면 판정에는 가격 추세가 쓰입니다</td></tr>
        <tr><td>인플레</td><td>CPI · 근원 CPI · 기대인플레(브레이크이븐) · 유가 6개월 · PPI · 장기 기대</td><td></td></tr>
        <tr><td>유동성</td><td>순유동성(연준 대차대조표) · 신용스프레드 · 신용 증가속도 · M2 · 정책금리 변화 · CP 스프레드</td><td></td></tr>
        <tr><td>밸류에이션</td><td>주식 위험프리미엄(ERP) · 실질금리 · 회사채 가치 · 장기 평균회귀</td><td>알파의 약 56%</td></tr>
        <tr><td>심리</td><td>신용·자산 상대모멘텀, 공포탐욕 등</td><td>예측기 입력</td></tr>
        </table>
        <p>모든 거시지표는 <b>그때 실제로 발표된 값과 발표일</b>로만 씁니다(시점 데이터) — 나중에 수정된 값을 쓰면 미래 정보가 섞이기 때문입니다.</p>

        <h4>② 국면 확률 (HMM)</h4>
        <p>성장·인플레·유동성 점수로 숨은 마르코프 모형이 4국면 확률을 매달 추정합니다:
        <b>Goldilocks</b>(성장↑ 인플레↓) · <b>Reflation</b>(성장↑ 인플레↑) · <b>Stagflation</b>(성장↓ 인플레↑) · <b>Deflation</b>(성장↓ 인플레↓).
        국면마다 선호 자산이 다르고, 확률 가중으로 자산 점수에 반영됩니다(알파의 약 30%).</p>

        <h4>③ 머신러닝 예측기</h4>
        <p>기둥 점수를 입력으로 자산별 다음 달 초과수익을 예측합니다(선형·LightGBM·CatBoost 앙상블 + Conformal 보정, CatBoost 시드 3개 평균).
        과거에만 학습하고 앞으로 굴려가며 예측합니다(walk-forward). 알파의 약 14%.</p>

        <h4>④ 고르기와 배분</h4>
        <div class="formula">자산 매력도 = 국면 선호(확률 가중) + 밸류에이션 틸트 + 예측 → 12개월 추세(현금 대비 초과수익 &gt; 0)를 통과한 자산 중 상위 2개
        → 위험 균등(ERC) 배분 → 운용판은 2배 슬리브</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with tab_defense:
    st.markdown(
        """
        <div class="ic-body">
        <h4>추세필터 → 현금</h4>
        <p>12개월 수익이 현금(T-bill)보다 낮은 자산은 고르지 않습니다. 고를 게 없으면 그 몫은 BIL(현금) 입니다. 2008·2022 같은 긴 하락장의 주된 방어입니다.</p>

        <h4>밸류에이션 상한</h4>
        <p>주식 위험프리미엄이 역사적으로 극단적으로 낮을 때(z &lt; −2, 주식이 매우 비쌀 때) 주식군 합계를 30% 로 제한합니다.</p>

        <h4><span class="chg">v18.3 신규</span> 국채가 헤지를 못 할 때 국채 제외 (2026-10-11)</h4>
        <div class="formula">월말 SPY·IEF 60일 상관 &gt; 0 (주식과 국채가 같이 움직이는 체제) → 그 달 TLT·IEF 를 후보에서 뺀다</div>
        <p><b>왜</b>: PENTARCH 의 국면 판정은 성장 신호(S&amp;P 200일 추세)에 끌려가서, 2022 하반기처럼 인플레가 높은데도 주가가 꺾이면 'Deflation' 으로 분류합니다.
        Deflation 국면의 선호 자산은 국채라, 금리가 오르는 중인데도 국채를 고를 위험이 있었습니다(v18.2 연금판의 최대낙폭 2022-03~2023-10 이 그 경로).
        주식·채권 상관이 양수라는 건 국채가 주식 하락을 막아주지 못한다는 뜻이므로 그때만 국채를 뺍니다.</p>
        <p><b>4개 방법을 비교한 결과</b>(규칙을 먼저 고정한 뒤 시험, pentarch docs/54):</p>
        <table>
        <tr><th>방법</th><th>연금판 2008~ 연수익 / 최대낙폭</th><th>판정</th></tr>
        <tr><td>v18.2 (이전)</td><td>15.6% / −23.0%</td><td></td></tr>
        <tr><td>① 고인플레면 Deflation 판정 금지</td><td>15.1% / <b>−30.0%</b> (2022 하반기 원자재 보유)</td><td>연금 손상</td></tr>
        <tr><td><b>② 주식·채권 상관 양수면 국채 제외</b></td><td><b>15.6% / −23.1%</b></td><td class="chg">채택 (v18.3)</td></tr>
        <tr><td>③ 실질금리 상승기만 예외</td><td>v18.2 와 동일 (표본에서 발동 없음)</td><td>효과 없음</td></tr>
        <tr><td>④ 성장 신호 50% 를 거시지표로</td><td>12.9% / −29.7%</td><td>성과 손상</td></tr>
        </table>
        <p>IC 에는 같은 규칙이 필요 없습니다 — IC 는 인플레를 따로 판정해 인플레기에 국채 칸에 오지 않고, 남은 경우는 200일선 방어가 막습니다(「Inflation Compass · 전략 설명」 참조).</p>

        <h4>인플레 방어 가드 (검증 하네스 G2)</h4>
        <p>고인플레 달에 실물(금·원자재) 이 명목 장기채보다 많아야 한다는 자동 점검입니다. 현금 100% 달은 듀레이션 노출이 없어 통과로 셉니다(docs/53).
        v18.3 은 이 가드를 개정 전 식으로도 통과합니다(0.842 ≥ 0.80).</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with tab_test:
    st.markdown(
        """
        <div class="ic-body">
        <h4>검증 하네스 (v18.3, 2026-10-11)</h4>
        <table>
        <tr><th>항목</th><th>결과</th></tr>
        <tr><td>보상 점수 (운용판 / 연금판)</td><td>+1.690 / +1.727 — 하드 게이트 전부 통과</td></tr>
        <tr><td>미래 정보 차단 (절단 불변성)</td><td>통과 — 데이터를 잘라도 과거 결정이 바뀌지 않음</td></tr>
        <tr><td>교차검증 (CPCV 15경로)</td><td>예측 정보계수 양수 100%</td></tr>
        <tr><td>과최적화 보정 (DSR, 누적 시행 502회)</td><td>확장 0.96 · ETF 0.97</td></tr>
        </table>

        <h4>추가 검증 (2026-10-12) — 모두 규칙을 먼저 고정한 뒤 시험, 결론: v18.3 유지</h4>
        <p><b>① 층별 기여 — 밸류에이션이 가장 중요한가? 다른 층이 방해하나?</b> (pentarch docs/56)</p>
        <table>
        <tr><th>구성 (연금판 2008~)</th><th>Sharpe</th><th>최대낙폭</th></tr>
        <tr><td><b>전체 v18.3</b> (밸류에이션 + 국면 + 예측기)</td><td><b>0.91</b></td><td><b>−23.1%</b></td></tr>
        <tr><td>밸류에이션만 (+ 추세필터)</td><td>0.74</td><td>−29.7%</td></tr>
        <tr><td>밸류에이션만, 추세필터 없음</td><td>0.66</td><td>−49.8%</td></tr>
        <tr><td>국면만 · 예측기만</td><td>0.59 · 0.70</td><td>−31.9% · −30.8%</td></tr>
        <tr><td>기준선 (12개월 모멘텀 상위 2 + 추세필터)</td><td>0.39</td><td>−36.7%</td></tr>
        </table>
        <table>
        <tr><th>기여 (섀플리, Sharpe)</th><th>밸류에이션</th><th>국면</th><th>예측기</th></tr>
        <tr><td>2008~</td><td><b>41~44%</b></td><td>29~37%</td><td>22~27%</td></tr>
        <tr><td>1994~</td><td>30%</td><td><b>48~55%</b></td><td>15~22%</td></tr>
        </table>
        <ul>
        <li>가장 중요한 층은 <b>구간에 따라 다릅니다</b>(2008~ 밸류에이션, 1994~ 국면).</li>
        <li>세 층은 같은 위험(비싸거나 나쁜 국면의 주식)을 <b>겹쳐서</b> 피합니다 — 둘씩 합치면 합보다 작지만, 셋을 모두 쓰면 합보다 커서
            <b>전체가 모든 부분 조합보다 낫습니다.</b> 방해가 아니라 겹침입니다.</li>
        <li>밸류에이션은 <b>위기 보험 층</b>입니다: 2000·2008·2022 에 크게 벌고, 33년 중 18년은 조금씩 잃었습니다(회복기·버블 막바지).</li>
        </ul>

        <p><b>② 성장 판정에 ISM 제조업 지수 추가</b> (pentarch docs/57, 자료 1948~ GitHub 교차검증)</p>
        <table>
        <tr><th>안</th><th>연금판 Sharpe / 최대낙폭</th><th>판정</th></tr>
        <tr><td><b>v18.3 (S&amp;P 200일 추세)</b></td><td><b>0.91 / −23.1%</b></td><td>유지</td></tr>
        <tr><td>성장 = 가격 50 + 거시(ISM 포함) 50</td><td>0.69 / −31.2%</td><td>기준 미달</td></tr>
        <tr><td>성장 = 가격 50 + ISM 50</td><td>0.69 / −29.2%</td><td>기준 미달</td></tr>
        <tr><td>ISM 을 예측기 입력으로만</td><td>0.91 / −23.1%</td><td>이득 없음, 1994~ 낙폭 예산 초과</td></tr>
        <tr><td>성장 = ISM 단독</td><td>0.81 / −29.2%</td><td>기준 미달</td></tr>
        </table>
        <p>ISM 을 넣으면 '고인플레를 디플레로 보는 오분류' 는 사라지지만(0/18), 그 결과 2022 하반기에 원자재를 들어 −15% 를 잃고
        2008 에는 너무 일찍 국면을 바꿉니다. <b>배분 신호로는 가격 추세가 설문 지표보다 낫다</b>는 결론입니다.</p>

        <p><b>③ 주식 30% 상한은 실제로 작동하나?</b></p>
        <p>고평가(ERP z &lt; −2) 날 대부분은 밸류에이션이 이미 주식을 빼서(평균 비중 0.1%) 상한이 필요 없습니다.
        실제로 걸린 날은 <b>1997~1999 닷컴 버블기 53일</b>(국면·예측기가 나스닥을 강하게 밀던 때)과 2018-04 3일뿐이고, 2008 이후 성과 차이는 없습니다.
        1994~ 에서는 상한이 버블 막바지 상승을 막아 수익이 낮았지만(19.4% vs 21.0%), 그 근거가 1999년 한 번이라 <b>안전장치로 유지</b>합니다.</p>

        <h4>남은 한계</h4>
        <ul>
        <li><b>502번의 시행</b>에서 고른 구성입니다 — DSR 로 보정하지만 같은 표본을 여러 번 본 위험은 남습니다.</li>
        <li>확장 구간(1994~) 최대낙폭 −34.2% 가 사전등록 예산(−34.5%) 에 근접합니다.</li>
        <li>v18.3 은 사전등록 규칙상 선정안(①)이 아니라 결과를 본 뒤 사용자가 고른 안입니다 — 그림자 운용으로 2026-10-11 이후 실제 성과를 따로 추적합니다.</li>
        <li>성장 신호가 국면 판정을 좌우하는 구조(고인플레 Deflation 오분류 5/18개월)는 남아 있습니다. v18.3 은 그 오분류가 국채로 이어지는 경로만 막습니다.</li>
        <li>1994 이전 자료가 없어 1970s 형 장기 스태그플레이션은 검증할 수 없습니다.</li>
        <li>연금판은 60/40 대비 우위가 통계적으로 확증되지 않았습니다(v18.2 연금판 기준 사전등록 7게이트 중 6개 통과, docs/51 · v18.3 연금판은 하네스만 재검증).</li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
