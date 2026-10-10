"""Strategy description and calculation methodology - static reference page.

원조 Inflation Compass 설명은 그대로 두고, 확정 전략(2026-10-09)의 변경·개선 부분을 덧붙인다.
수치 출처: matrix_16_combinations_evaluation_report.md (정정판 3), robustness_and_live_report.md.
"""

import streamlit as st

st.markdown(
    """
    <style>
    div.block-container { padding-top: 2.6rem; }
    .ic-intro { font-size: 15px; color: #52564d; margin: 0 0 4px; line-height: 1.6; }
    .ic-quad { display: grid; grid-template-columns: 120px 1fr 1fr; gap: 8px; margin: 16px 0 6px; max-width: 620px; }
    .ic-quad .hdr { display: flex; align-items: center; justify-content: center; font-size: 11.5px; font-weight: 600;
        color: #8a8d84; text-transform: uppercase; letter-spacing: 0.06em; text-align: center; }
    .ic-quad .rowhdr { display: flex; align-items: center; font-size: 13px; font-weight: 600; color: #52564d; }
    .ic-quad .cell { border-radius: 6px; padding: 14px 10px; text-align: center; }
    .ic-quad .cell .ticker { font-size: 19px; font-weight: 700; color: #16191a; line-height: 1.3; }
    .ic-quad .cell .kr { font-size: 12px; color: #52564d; }
    .ic-quad .cell .label { font-size: 11.5px; color: #8a8d84; font-style: italic; }
    .ic-quad .cell .new { font-size: 11px; color: #2f7d4f; font-weight: 600; margin-top: 4px; }
    .ic-body p, .ic-body ul { margin: 0 0 8px; font-size: 14px; line-height: 1.48; }
    .ic-body ul { padding-left: 20px; }
    .ic-body li { margin-bottom: 3px; }
    .ic-body h4 { font-size: 14px; margin: 14px 0 4px; font-weight: 700; color: #16191a; }
    .ic-body h4:first-child { margin-top: 0; }
    .ic-body code { font-size: 13px; background: #f2f3ee; padding: 1px 5px; border-radius: 3px; }
    .ic-body .formula { background: #f2f3ee; border-radius: 5px; padding: 8px 12px; font-size: 13px; margin: 4px 0 8px; line-height: 1.6; }
    .ic-body table { border-collapse: collapse; font-size: 13px; margin: 6px 0 10px; }
    .ic-body th, .ic-body td { border: 1px solid #e1e0d9; padding: 5px 9px; text-align: left; vertical-align: top; }
    .ic-body th { background: #f2f3ee; font-weight: 600; }
    .ic-body .chg { color: #2f7d4f; font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)

tab_strategy, tab_signals, tab_cost, tab_why = st.tabs(["전략설명", "신호", "매매·비용", "개선 근거"])

with tab_strategy:
    st.markdown(
        """
        <div class="ic-body">
        <ul>
        <li><b>성장(Growth)</b>과 <b>인플레이션(Inflation)</b> 두 축으로 매크로 국면을 4가지로 나눕니다.</li>
        <li>매월 마지막 거래일에 국면을 판정해서 해당하는 섹터 ETF 하나에 전액 투자하고, 다음 한 달간 보유합니다.</li>
        <li>포지션은 항상 하나입니다 (디스인플레 침체 국면만 예외로 2개 자산을 절반씩 보유).</li>
        <li>매달 국면이 바뀌지 않으면 포지션도 그대로 유지됩니다.</li>
        </ul>
        <div class="ic-quad">
          <div></div>
          <div class="hdr">인플레이션 상승</div>
          <div class="hdr">인플레이션 하락</div>
          <div class="rowhdr">성장 ↑</div>
          <div class="cell" style="background:#dbe8f8"><div class="ticker">XLE</div><div class="kr">에너지</div><div class="label">reflation</div></div>
          <div class="cell" style="background:#fbe3d8"><div class="ticker">XLK</div><div class="kr">기술</div><div class="label">goldilocks</div></div>
          <div class="rowhdr">성장 ↓</div>
          <div class="cell" style="background:#e6e1f3"><div class="ticker">XLU</div><div class="kr">유틸리티</div><div class="label">stagflation</div></div>
          <div class="cell" style="background:linear-gradient(90deg,#fbedd0 50%,#fbe1ea 50%)"><div class="ticker">XLP + IEF</div><div class="kr">필수소비재 + 7-10년 국채</div><div class="label">disinflation</div>
            <div class="new">확정: <b>IEF 100%</b> (10-10), IEF &lt; 200일선이면 SHY 100%</div></div>
        </div>
        <p style="margin-top:12px"><b>확정 (2026-10-10):</b> 위 칸은 계좌의 <b>85%</b>. 나머지 15% 는 국면과 무관하게 <b>금 GLD 10% + 초단기채 BIL 5%</b> 상시 보유.</p>
        <p style="margin-top:20px">참고: <a href="https://cssanalytics.wordpress.com/2026/07/27/the-inflation-compass-model/" target="_blank">cssanalytics.wordpress.com</a></p>

        <h4>확정 전략 — 원조 대비 바뀐 점 (2026-10-09 · 10-10 보완)</h4>
        <p>원조의 4국면 판정과 섹터 배분은 그대로 쓰고, 아래를 더했습니다.</p>
        <table>
        <tr><th>항목</th><th>원조 (저자)</th><th>확정 전략</th></tr>
        <tr><td>침체 국면</td><td>XLP 50 + IEF 50 고정</td>
            <td class="chg"><b>IEF 100%</b> (10-10, 듀얼 모멘텀의 '위험 신호 땐 채권 100%') · IEF 가 200일선 아래면 <b>SHY(1-3년 단기채) 100%</b></td></tr>
        <tr><td>레버리지</td><td>없음 (항상 1배)</td>
            <td class="chg">IC 위험선호 지수 월말 값 &lt; 15 → <b>2배</b>, &gt; 85 → <b>0.5배</b>, 그 외 1배</td></tr>
        <tr><td>침체 국면 2배</td><td>—</td>
            <td class="chg">늘린 1배는 <b>IEF 에만</b> → IEF 185 (+ 보험 15). SHY 로 바뀐 달은 1배로 제한</td></tr>
        <tr><td>상시 보험 (10-10)</td><td>없음</td>
            <td class="chg">국면 칸 85% + <b>금 10% + BIL 5%</b> 항상 보유. 배수(2배·0.5배)는 보험까지 포함한 전체에 곱함</td></tr>
        <tr><td>주식 칸 2배 조건 (10-10)</td><td>—</td>
            <td class="chg">XLE·XLK·XLU 2배는 <b>그 섹터가 자기 200일선 위일 때만</b>, 아니면 1배 (침체 칸 IEF 2배는 그대로)</td></tr>
        <tr><td>매매 시점</td><td>월말 종가</td>
            <td>월말 오후, <b>종가 전</b> 체결 (FRED 지표는 전일 값)</td></tr>
        </table>
        <p>성과 (2003-09 ~, 월말 30bp·DTB3 차입 반영):</p>
        <table>
        <tr><th></th><th>연수익</th><th>최대낙폭</th><th>2008 낙폭</th><th>2022 수익</th></tr>
        <tr><td>원조 (레버리지 없음)</td><td>19.1%</td><td>−24.5%</td><td>−18.8%</td><td>+33.7%</td></tr>
        <tr><td>확정 전략 10-09판 (보험 없음)</td><td>21.4%</td><td>−24.5%</td><td>−16.2%</td><td>+63.7%</td></tr>
        <tr><td><b>확정 전략 · 실거래 조건 (10-10)</b></td><td><b>19.5%</b></td><td><b>−20.2%</b></td><td><b>−11.0%</b></td><td><b>+51.0%</b></td></tr>
        </table>
        <p>최대낙폭 −20.2% 는 2011-04~08(미국 신용등급 강등)에 1배 주식 국면에서 나온 것으로, 레버리지·침체 규칙과 무관합니다.
        보험 15% 는 정상기에 연 약 1.9%p 를 내고 그 낙폭을 4.3%p 줄입니다(위험 대비 수익은 오히려 개선).</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with tab_signals:
    st.markdown(
        """
        <div class="ic-body">
        <h4>성장 신호</h4>
        <p>SPY(S&amp;P500 추종 ETF) 종가가 200일 이동평균보다 위에 있으면 "성장 상승", 아래에 있으면
        "성장 하락"으로 판정합니다.</p>

        <h4>인플레이션 신호</h4>
        <p>T5YIE(5년 기대인플레이션율, FRED 발표)가 연준의 목표치인 2.0%보다 높아야 하고, 그 위에
        다음 두 모멘텀 조건 중 <b>하나라도</b> 충족되면 "인플레이션 상승"으로 판정합니다 (둘 다 계산해서
        OR로 결합 — 하나를 골라 쓰는 게 아니라 서로 보완하는 이중 확인 장치입니다):</p>
        <ul>
        <li><b>Breakeven 모멘텀</b> — T5YIE 자체가 60거래일 전보다 높다</li>
        <li><b>Asset 모멘텀</b> — confirming indicator의 60일 선형회귀 기울기가 양수다</li>
        </ul>
        <div class="formula">inflation-on = (T5YIE &gt; 2.0%) AND (breakeven 모멘텀 OR asset 모멘텀)</div>

        <h4>Confirming indicator</h4>
        <p>T5YIE는 채권시장 가격이라 유동성 스트레스 시기(2008-09, 2020-21 등)에 왜곡될 수 있습니다.
        이를 보완하기 위해 인플레이션에 <b>수혜를 받는 섹터</b>와 <b>피해를 받는 섹터</b>의 누적수익률
        비율을 별도로 계산해서, 시장이 실제로 리플레이션을 가격에 반영하고 있는지 다시 확인합니다.</p>
        <div class="formula">
        positive(수혜 바스켓) = 0.5·XLE(에너지) + 1/6·XLI(산업재) + 1/6·XLF(금융) + 1/6·XLB(소재)<br/>
        negative(피해 바스켓) = 1/3·XLU(유틸리티) + 1/3·XLV(헬스케어) + 1/3·XLP(필수소비재)<br/>
        indicator = 누적수익률(positive) / 누적수익률(negative)
        </div>
        <p>이 비율이 상승 추세(60일 회귀기울기 &gt; 0)라는 건 리플레이션 수혜 섹터가 방어 섹터 대비
        계속 아웃퍼폼하고 있다는 뜻입니다.</p>

        <h4><span class="chg">[확정]</span> 채권방어 신호</h4>
        <p>침체 국면(성장 하락 · 인플레이션 하락)에서만 봅니다. IEF 종가가 200일 이동평균 이하이면
        국채가 하락 추세(금리 상승)라 보고 IEF 대신 SHY 100% 로 피합니다.</p>
        <div class="formula">bond-shield = 침체 국면 AND IEF ≤ IEF 200일 평균  →  SHY 100%, 레버리지 1배 제한</div>

        <h4><span class="chg">[확정]</span> IC 위험선호 지수 (레버리지 신호)</h4>
        <p>시장 심리를 0~100 으로 나타내는 4요소 지수입니다. 각 요소를 최근 1년(252거래일) 백분위로 바꿔 평균합니다.</p>
        <div class="formula">
        ① 모멘텀 = SPY 의 125일 평균 대비 괴리<br/>
        ② 변동성 = VIX 의 50일 평균 대비 괴리 (높을수록 공포 → 역순)<br/>
        ③ 안전자산 수요 = SPY 20일 수익률 − IEF 20일 수익률<br/>
        ④ 신용 = BAA10Y 스프레드 (넓을수록 공포 → 역순)<br/>
        IC 위험선호 지수 = 평균(①~④ 의 1년 백분위) × 100
        </div>
        <div class="formula">
        지수 &lt; 15 (극단적 공포) → 2배 · 지수 &gt; 85 (극단적 탐욕) → 0.5배 (나머지 단기채) · 그 외 1배<br/>
        판단은 <b>월말 당월 값만</b> 봅니다 — 2~4개월 전 공포로 2배를 거는 규칙은 쓰지 않습니다.
        </div>
        <p>CNN Fear &amp; Greed(7요소)는 화면·텔레그램에 <b>참고로만</b>표시합니다. 두 지수는 월말 상관 0.81 이지만
        극단 구간(&lt;15)은 절반만 겹치고, 레버리지 규칙은 IC 위험선호 지수로 검증됐기 때문입니다.
        (종전 화면에서 "CNN Fear &amp; Greed" 로 표시하던 값은 실제로는 이 지수였습니다.)</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with tab_cost:
    st.markdown(
        """
        <div class="ic-body">
        <h4>매매 시점 (실거래)</h4>
        <ul>
        <li>매월 마지막 거래일 <b>오후</b>에 모델을 돌리고 <b>종가 전</b>에 체결합니다. 가격·VIX 는 장중 값(≈ 종가)을 씁니다.</li>
        <li>FRED 지표(T5YIE·BAA10Y)는 그날 값이 다음 영업일에 게시되므로 <b>전일 값</b>으로 판단합니다
            (연구 조건 대비 연수익 약 −1.6%p, 최대낙폭 변화 없음).</li>
        <li>다음 날로 미루면 연수익 약 −2.5%p, 2008 낙폭 −16% → −20% 로 나빠집니다 — 반드시 당일 체결.</li>
        <li>월중에는 보유만 합니다(일별 리밸런싱 없음, 레버리지 비율은 월중 가격에 따라 변함).</li>
        </ul>

        <h4>매매비용 가정</h4>
        <p>매매비용은 턴오버 × 입력%로, 리밸런싱이 실제로 포지션을 바꾼 다음 거래일에만 적용됩니다
        (같은 포지션을 유지하는 달은 비용이 0). — 원조 IC 대시보드의 사이드바 비용</p>
        <p><span class="chg">[확정]</span> 확정 전략 성과는 월말 리밸런싱 때 매매한 명목금액 × <b>30bp(편도)</b>로 계산합니다
        (평균 회전율 월 65% → 연 약 2.3%p). 섹터 ETF 실제 스프레드보다 보수적인 값입니다.</p>

        <h4><span class="chg">[확정]</span> 차입·현금 이자</h4>
        <ul>
        <li>2배일 때 빌린 금액: (3개월 T-bill DTB3 + 0.5%)/연 이자</li>
        <li>0.5배일 때 남는 50%: 단기채(SHY)로 표시, 연구에서는 T-bill 이자로 계산</li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

with tab_why:
    st.markdown(
        """
        <div class="ic-body">
        <h4>침체 국면: 왜 1배는 50/50 을 지키고 2배만 IEF 로?</h4>
        <p>저자는 침체 국면을 "2008 같은 본격 침체인지 짧은 조정인지 미리 알 수 없으니, 국채는 침체를 막고
        필수소비재는 반등에 참여한다"는 이유로 반반 나눴습니다. 레버리지가 없으면 50/50 과 IEF 100% 의 수익은
        같았고, 저자 설계가 맞습니다.</p>
        <p>문제는 공포 레버리지가 대부분 침체 국면에서 켜진다는 점입니다. 필수소비재도 위기에는 주식이라
        2배가 걸리면 꼬리가 커집니다(2008-09 XLP −12.6% → 2배 −25%, 2020-03 월중 −25.7%).
        거시·채권·주식·리스크·반대검토 5개 관점 검토의 공통 결론은 "레버리지는 변동성이 낮고 위기에 오르는 국채에"였습니다.
        그래서 1배 달은 저자 원안을 지키고, 늘린 몫만 IEF 에 넣습니다.</p>

        <h4>채권방어: 왜 SHY 100%?</h4>
        <p>국채가 200일선 아래라는 건 금리가 오르는 중이라는 뜻입니다(2022 형). 이때는 국채도 필수소비재도
        방어가 되지 않아 둘 다 단기채로 피합니다. 빌려서 단기채를 사는 건 기대수익이 0 이하라 1배로 제한합니다.
        2022년 수익 +51.8% → +63.6%.</p>

        <h4>레버리지: 왜 당월 공포만?</h4>
        <p>공포 레버리지의 근거는 투매로 위험 프리미엄이 비싸진 순간에 사는 것이고, 그 근거는 당월에만 있습니다.
        2~4개월 뒤엔 지수가 대개 정상으로 돌아와 있어 할인 없는 가격에 업종 하나를 2배로 사게 됩니다.
        종전 규칙(2·3·4개월 전 공포에도 2배)은 CNN 실지수로 돌리면 최대낙폭이 −39.5% 로 무너졌습니다 —
        실제 2026-05~07: 3월 CNN 공포 → 6월 XLE 2배 −9.9%, 7월 XLK 2배 −15.9%.</p>
        <table>
        <tr><th>공포 2배 규칙 (2011~, 실거래)</th><th>IC 위험선호 지수</th><th>CNN 실지수</th></tr>
        <tr><td><b>당월만 (확정)</b></td><td>20.3% / −22.9%</td><td>19.5% / −24.2%</td></tr>
        <tr><td>당월·2·3~4개월 전 (종전)</td><td>23.7% / −22.9%</td><td>22.6% / <b>−39.5%</b></td></tr>
        </table>

        <h4>침체 칸 IEF 100%: 듀얼 모멘텀과 IC 의 장점 결합 (2026-10-10)</h4>
        <p>155년(1872~) 검증에서 듀얼 모멘텀(GEM)은 디플레·신용 위기(1929~32, 2008)를 '채권 100%'로 막았고,
        IC 는 금리 급등(2022)을 '채권 하락 추세면 단기채'로 막았습니다. 둘을 합쳐 침체 칸을 IEF 100% 로 하고 채권방어는 그대로 둡니다.
        2003~ 실거래: 연수익 19.3% → 19.2%(사실상 같음), 2008 +1.2% → +13.0%, 2020-02~03 −4.4% → −0.7%, 2022 +51.0% 그대로.
        초장기 대리: 1929~32 −56% → −26%, 최대낙폭 −57.5% → −41.6%. GEM 자체를 섞는 것은 같은 기간 GEM 연 8.4% 라 수익만 줄어 쓰지 않습니다.</p>

        <h4>상시 보험 15% (금 10 + BIL 5): 왜 신호가 아니라 '미리' 들고 있나? (2026-10-10)</h4>
        <p>논리·경제사·이론경제·사회·기술사·생존론 6개 관점 검토의 공통 결론: 이 전략의 방어는 <b>천천히 오는 위기</b>
        (2008형, 2022형)에만 논리가 있습니다. 금융억압(1942~51 금리 상한 + 인플레), 통화가치 절하(1934·1971),
        폐장·몰수·자산 동결(1914·1933·2022 러시아), 이긴 섹터를 겨냥한 횡재세처럼 <b>제도가 바뀌는 위기</b>는
        가격 신호로 미리 잡을 수 없어서, 그때 들고 있던 것만 효과가 있습니다. 금은 어느 정부의 부채도 아닌 자산이고,
        BIL 은 실질금리 급등(1980~82 볼커형 — 에너지·금 동반 하락)의 완충입니다.</p>
        <table>
        <tr><th>구간 (일반계좌)</th><th>보험 없음</th><th>보험 15%</th></tr>
        <tr><td>2003~07 연수익</td><td>35.3%</td><td>32.2%</td></tr>
        <tr><td>2008-09~09-02 금융위기</td><td>−6.0%</td><td>−3.0%</td></tr>
        <tr><td>2011-05~09 신용등급 강등</td><td>−16.1%</td><td>−13.0%</td></tr>
        <tr><td>2018-10~12</td><td>−16.4%</td><td>−13.3%</td></tr>
        <tr><td>2022</td><td>+63.7%</td><td>+51.0%</td></tr>
        </table>

        <h4>주식 칸 2배: 왜 섹터 자기 추세 조건? (2026-10-10)</h4>
        <p>국면 판정은 '추세가 이어진다', 공포 2배는 '평균으로 돌아온다'를 가정합니다 — 같은 전략 안의 반대 가정입니다.
        2000년처럼 S&P 는 버티는데 보유 섹터(나스닥)가 먼저 무너지면 성장 신호는 켜진 채 공포 2배가 붕괴 초입의 XLK 에 걸립니다.
        그래서 주식 칸 2배는 그 섹터가 자기 200일선 위일 때만 겁니다. 2003~ 표본에서 바뀐 달은 1개월(비용 ≈ 0) — 표본 밖 위험을 막는 장치입니다.
        침체 칸의 IEF 2배는 국채 헤지라 그대로 둡니다(같은 조건을 거기까지 걸면 2008 이 −6% → −12.5% 로 나빠짐).</p>

        <h4>검토했지만 쓰지 않은 것</h4>
        <ul>
        <li><b>서킷브레이커</b>(BAA10Y &gt; 3.2% 또는 VIX &gt; 35 이면 2배 금지) — 침체 국면 규칙이 같은 문제를 직접 풀어
            2008 낙폭만 키우고 수익을 깎음</li>
        <li><b>원자재 대체</b>(스태그플레이션에 DBC+XLE) — 2022 엔 이기지만 2008 하반기 원자재 폭락으로 최대낙폭 −29.7%</li>
        <li><b>변동성 비례 레버리지</b> — 모든 설정에서 수익 감소, 낙폭 개선 없음</li>
        <li><b>단일 자산 상한 50%</b>(10-10) — 표본 안에서는 '현금 50%' 와 같아 수익·낙폭이 함께 반토막(연 21.0% → 11.8%)</li>
        <li><b>스태그플레이션 칸 XLU → 금 + 단기채</b>(10-10) — 1973~74 유틸리티 붕괴 근거가 있지만 2022 수익 +64% → +10%. 연료비 연동 요금 도입 이후로 유틸리티의 인플레 취약성이 줄었다고 보고 XLU 유지</li>
        <li><b>보유 섹터 자기 추세 필터</b>(10-10) — XLK 와 S&P 가 거의 같은 때 200일선을 깨서 2000~02 재현에서도 오히려 나빠짐(MDD −32.7% → −36.8%)</li>
        <li><b>실질금리(DFII5) 상승 시 XLK → SPY</b>(10-10) — 수익만 2.6%p 감소, 방어 효과 없음</li>
        <li><b>주식-채권 상관 &gt; 0 이면 IEF 금지</b>(10-10) — 발동 0회. IEF &lt; 200일선 채권방어가 이미 같은 국면을 막고 있음</li>
        </ul>

        <h4>남은 위험</h4>
        <ul>
        <li>2011형 급락(1배 주식 국면, 국면 판단 지연) — 월별 모델로는 줄일 수 없음</li>
        <li>인플레 신호를 통과하는 금리 급등형 침체에서 IEF 150% (200일선 전환은 느린 약세만 잡음)</li>
        <li>위기 표본이 몇 번뿐이라 통계 검정보다 경제적 논리로 고른 규칙입니다</li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
