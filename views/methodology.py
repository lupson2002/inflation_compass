"""Inflation Compass 전략 설명 (2026-10-11 전면 개편 — 한눈에 보기 · 신호 · 매매 · 근거 · 검증).

수치 출처: run_16_matrix_experiments(확정 엔진, 실거래 조건), research_*·*_prereg.md (2026-10-10 연구).
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

tab_strategy, tab_signals, tab_cost, tab_why, tab_test = st.tabs(["한눈에 보기", "신호 계산", "매매·비용", "왜 이렇게 했나", "검증과 한계"])

with tab_strategy:
    st.markdown(
        """
        <div class="ic-body">
        <p class="ic-intro"><b>한 줄 요약</b> — 경기가 좋은지(성장)와 물가가 오르는지(인플레)를 매달 판정해서, 그 국면에 가장 강했던 섹터 하나에
        돈의 85% 를 넣고, 나머지 15% 는 어떤 국면에서도 금·초단기채로 들고 있는 월간 전략입니다.
        원저자: David Varadi (CSS Analytics, 2026-07). 확정 전략은 원저자 규칙에 방어 장치를 더한 것입니다.</p>

        <h4>매달 하는 일 — 월말 마지막 거래일, 종가 전</h4>
        <ol>
        <li><b>성장</b>: S&amp;P500(SPY) 이 200일 이동평균 위인가?</li>
        <li><b>인플레</b>: 5년 기대인플레(T5YIE) 가 2% 넘고, 오르는 중인가? (또는 에너지·소재 같은 인플레 수혜 업종이 방어 업종보다 강한가?)</li>
        <li>두 답으로 아래 4칸 중 하나를 고르고 그 자산을 삽니다. 한 달 동안 그대로 둡니다.</li>
        </ol>
        </div>
        <div class="ic-quad">
          <div></div><div class="hdr">인플레 ↑</div><div class="hdr">인플레 ↓</div>
          <div class="rowhdr">성장 ↑</div>
          <div class="cell" style="background:#dbe8f8"><div class="ticker">XLE</div><div class="kr">에너지</div><div class="label">리플레이션</div></div>
          <div class="cell" style="background:#fbe3d8"><div class="ticker">XLK</div><div class="kr">기술</div><div class="label">골디락스</div></div>
          <div class="rowhdr">성장 ↓</div>
          <div class="cell" style="background:#e6e1f3"><div class="ticker">XLU</div><div class="kr">유틸리티</div><div class="label">스태그플레이션</div></div>
          <div class="cell" style="background:#fbedd0"><div class="ticker">IEF</div><div class="kr">7-10년 국채</div><div class="label">침체</div>
            <div class="new">IEF &lt; 200일선이면 SHY(단기채)</div></div>
        </div>
        <div class="ic-body">
        <h4>계좌 구성</h4>
        <table>
        <tr><th>몫</th><th>무엇</th><th>왜</th></tr>
        <tr><td><b>85%</b></td><td>위 4칸 중 그 달의 자산</td><td>국면에 맞는 자산</td></tr>
        <tr><td><b>10%</b></td><td>금 (GLD) — 항상</td><td>신호로 못 잡는 위기(통화가치 하락·자산 동결·금융억압) 보험</td></tr>
        <tr><td><b>5%</b></td><td>초단기채 (BIL) — 항상</td><td>금리 급등 때 완충</td></tr>
        </table>

        <h4>일반계좌만: 공포·탐욕에 따라 배수 조절</h4>
        <table>
        <tr><th>IC 위험선호 지수(0~100, 월말)</th><th>배수</th><th>예외</th></tr>
        <tr><td>&lt; 15 (극단적 공포)</td><td><b>2배</b></td><td>침체 칸은 늘린 몫을 IEF 에만 · 채권방어(SHY) 달은 1배 · 주식 칸은 섹터가 자기 200일선 아래면 1배</td></tr>
        <tr><td>&gt; 85 (극단적 탐욕)</td><td><b>0.5배</b></td><td>나머지 50% 는 단기채</td></tr>
        <tr><td>그 외</td><td>1배</td><td></td></tr>
        </table>
        <p><b>연금계좌</b>는 2배를 쓰지 않습니다(탐욕 0.5배만). 연금은 이 IC 연금형 50% + PENTARCH 비레버리지 50% 로 운용합니다 — 「연금 운용」 페이지.</p>

        <h4>백테스트 성과 (2003-09 ~ 2026-09, 전일 FRED · 월말 30bp · 차입이자 반영)</h4>
        <table>
        <tr><th></th><th>연수익</th><th>최대낙폭</th><th>2008 낙폭</th><th>2022</th></tr>
        <tr><td>원조 (레버리지·방어 없음)</td><td>19.1%</td><td>−24.5%</td><td>−18.8%</td><td>+33.7%</td></tr>
        <tr><td><b>확정 전략 · 일반계좌</b></td><td><b>19.5%</b></td><td><b>−20.2%</b></td><td><b>−11.0%</b></td><td><b>+51.0%</b></td></tr>
        <tr><td>IC 연금형 (2008-02~)</td><td>14.9%</td><td>−14.4%</td><td></td><td></td></tr>
        <tr><td>연금 혼합 IC 50 + PENTARCH 50 (2008-02~)</td><td>15.3%</td><td>−13.0%</td><td></td><td></td></tr>
        </table>
        <p>최대낙폭 −20.2% 는 2011-04~08(미국 신용등급 강등) 에 '성장' 칸(1배) 에서 나왔습니다 — 월말 판단 전략이 피할 수 없는 급락형입니다.</p>

        <h4>잘 막는 것 · 못 막는 것</h4>
        <table>
        <tr><th>잘 막는 위기</th><th>못 막는 위기</th></tr>
        <tr><td>천천히 오는 신용위기(2008: +13%), 금리 급등(2022: +51%), 디플레 붕괴(침체 칸 국채)</td>
            <td>한 달 안의 급락(1987·2020-03형), 유틸리티가 무너지는 1970s형 스태그플레이션, 섹터 한 곳 집중 위험, 거래소 폐쇄·제재 같은 제도 위기(→ 금 10% 가 일부만 완충)</td></tr>
        </table>
        <p style="margin-top:20px">참고: <a href="https://cssanalytics.wordpress.com/2026/07/27/the-inflation-compass-model/" target="_blank">cssanalytics.wordpress.com</a></p>
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

        <h4>채권방어 신호</h4>
        <p>침체 국면(성장 하락 · 인플레이션 하락)에서만 봅니다. IEF 종가가 200일 이동평균 이하이면
        국채가 하락 추세(금리 상승)라 보고 IEF 대신 SHY(1-3년 단기채) 로 피합니다.</p>
        <div class="formula">bond-shield = 침체 국면 AND IEF ≤ IEF 200일 평균  →  SHY, 레버리지 1배 제한</div>

        <h4>섹터 자기 추세 (2배 조건)</h4>
        <p>주식 칸(XLE·XLK·XLU) 에서 공포 2배가 켜져도, <b>그 섹터 ETF 가 자기 200일선 아래면 1배</b>로 둡니다.</p>

        <h4>IC 위험선호 지수 (레버리지 신호)</h4>
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
        <p>확정 전략 성과는 월말 리밸런싱 때 매매한 명목금액 × <b>30bp(편도)</b>로 계산합니다
        (평균 회전율 월 65% → 연 약 2.3%p). 섹터 ETF 실제 스프레드보다 보수적인 값입니다.</p>

        <h4>차입·현금 이자</h4>
        <ul>
        <li>2배일 때 빌린 금액: (3개월 T-bill DTB3 + 0.5%)/연 이자</li>
        <li>0.5배일 때 남는 50%: 단기채(SHY)로 표시, 연구에서는 T-bill 이자로 계산</li>
        <li>상시 보험의 BIL(초단기채) 5%: 상장(2007-05) 전은 T-bill 이자로 이어 붙여 계산</li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

with tab_why:
    st.markdown(
        """
        <div class="ic-body">
        <h4>① 침체 칸을 IEF 100% 로 (2026-10-10)</h4>
        <p>원조는 필수소비재 50 + 국채 50 이었습니다. 155년(1872~) 검증에서 듀얼 모멘텀 전략은 디플레·신용 위기(1929~32, 2008) 를
        '채권 100%' 로 막았고, IC 는 금리 급등(2022) 을 '국채가 하락 추세면 단기채' 로 막았습니다. 둘을 합쳤습니다.
        2003~ 실거래: 연수익 19.3% → 19.2%(사실상 같음), 2008 +1.2% → +13.0%, 2020-02~03 −4.4% → −0.7%. 초장기: 1929~32 −56% → −26%.</p>

        <h4>② 채권방어 — 국채가 헤지를 못 할 때 (IEF &lt; 200일선 → SHY)</h4>
        <p>국채가 200일선 아래라는 건 금리가 오르는 중이라는 뜻입니다(2022 형). 이때는 국채가 방어가 되지 않아 단기채로 피합니다.
        빌려서 단기채를 사는 건 기대수익이 0 이하라 1배로 제한합니다.</p>
        <p><b>주식·채권 동반 하락 국면(상관 양수)에 따로 규칙이 필요한가?</b> (2026-10-11 점검) 2003~ 에 IC 가 상관 양수 달에 IEF 를 든 달은 <b>0개월</b>입니다 —
        그런 국면은 대개 인플레가 원인이라 인플레 신호가 먼저 켜져 IEF 칸에 오지 않고, 남은 경우는 200일선 방어가 막습니다.
        155년 대리 자료에서도 상관 규칙을 더하면 연 7.7% → 7.4%, 최대낙폭 −41.6% → −44.9% 로 오히려 나빠졌습니다(200일선을 통과한 뒤 남은
        상관 양수 달의 국채 수익은 평균 +0.5%/월). PENTARCH 에는 이 규칙이 필요했지만(국면 판정이 성장 신호에 끌려가 인플레기에도 국채를 고름) IC 는 구조상 필요 없습니다.</p>

        <h4>③ 레버리지: 왜 당월 공포만?</h4>
        <p>공포 레버리지의 근거는 투매로 위험 프리미엄이 비싸진 순간에 사는 것이고, 그 근거는 당월에만 있습니다.
        종전 규칙(2·3·4개월 전 공포에도 2배)은 CNN 실지수로 돌리면 최대낙폭이 −39.5% 로 무너졌습니다(실제 2026-05~07).</p>
        <table>
        <tr><th>공포 2배 규칙 (2011~, 실거래)</th><th>IC 위험선호 지수</th><th>CNN 실지수</th></tr>
        <tr><td><b>당월만 (확정)</b></td><td>20.3% / −22.9%</td><td>19.5% / −24.2%</td></tr>
        <tr><td>당월·2·3~4개월 전 (종전)</td><td>23.7% / −22.9%</td><td>22.6% / <b>−39.5%</b></td></tr>
        </table>

        <h4>④ 상시 보험 15% (금 10 + BIL 5) — 신호가 아니라 '미리' 들고 있는 이유</h4>
        <p>논리·경제사·이론경제·사회·기술사·생존론 6개 관점 검토의 공통 결론: 이 전략의 방어는 <b>천천히 오는 위기</b>에만 논리가 있습니다.
        금융억압(1942~51), 통화가치 절하(1934·1971), 폐장·자산 동결(1914·2022 러시아), 이긴 섹터를 겨냥한 횡재세처럼 <b>제도가 바뀌는 위기</b>는
        가격 신호로 미리 잡을 수 없어서, 그때 들고 있던 것만 효과가 있습니다. 대가: 정상기 연 약 1.9%p, 대신 최대낙폭 4.3%p 축소(위험 대비 수익은 개선).</p>

        <h4>⑤ 주식 칸 2배에 섹터 자기 추세 조건</h4>
        <p>국면 판정은 '추세가 이어진다', 공포 2배는 '평균으로 돌아온다' 를 가정합니다 — 반대 가정입니다. 2000년처럼 S&amp;P 는 버티는데 나스닥이 먼저
        무너지면 공포 2배가 붕괴 초입의 XLK 에 걸립니다. 표본에서 바뀐 달은 1개월(비용 ≈ 0) — 표본 밖 위험을 막는 장치입니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with tab_test:
    st.markdown(
        """
        <div class="ic-body">
        <h4>초장기 검증 — 155년(1872~2026, Shiller 월간 + Global Macro Database 위기 라벨)</h4>
        <p>섹터 ETF 가 1998년에 생겨 섹터 선택은 재현할 수 없어, IC 의 <b>뼈대</b>(추세 + 인플레로 주식·채권·현금 오가기, 보험 포함)를 시장 주식으로 시험했습니다.</p>
        <table>
        <tr><th></th><th>연수익</th><th>최대낙폭</th><th>1929~32</th><th>1973~74</th><th>2007~09</th></tr>
        <tr><td>주식 보유</td><td>9.4%</td><td>−81.8%</td><td>−81%</td><td>−39%</td><td>−48%</td></tr>
        <tr><td>IC 뼈대 (현행 구조)</td><td>7.7%</td><td>−41.6%</td><td>−26%</td><td>−32%</td><td>−28%</td></tr>
        </table>
        <p>디플레 붕괴·신용위기는 잘 막습니다. 약점은 <b>'인플레만' 칸</b>(성장↓·인플레↑) — 시장 주식으로 대리하면 1973~74 에 크게 잃었습니다.
        실제 IC 는 이 칸에서 XLU 를 들고, 2003~ 에는 XLU 가 잘 버텼지만(2008·2022) 1970s 유틸리티 붕괴(Con Ed 배당 중단)는 섹터 자료가 없어 검증하지 못했습니다.</p>

        <h4>칸별 대체 자산 탐색 (2026-10-10, 모두 규칙을 먼저 정한 뒤 시험)</h4>
        <table>
        <tr><th>시험</th><th>결과</th><th>판정</th></tr>
        <tr><td>침체 칸 XLP+IEF → IEF 100</td><td>수익 같음, 2008·2020 방어 개선</td><td class="chg">채택</td></tr>
        <tr><td>인플레만 칸 XLU → XLU 50 + 금 50</td><td>연 −0.3%p, 1970s 형 대비는 좋아지나 연금에선 금 쏠림(최대 76%)</td><td>보류 → 현행 유지</td></tr>
        <tr><td>인플레만 칸 = 금·XLU·XLE(·XLB) 중 모멘텀 1위</td><td>수익 +1.4%p, 최대낙폭 −20 → −23%(에너지 쏠림)</td><td>기준 미달</td></tr>
        <tr><td>성장+인플레 칸 XLE → 후보 모멘텀 1위</td><td>XLE 가 전·후반 모두 1위, 교체 시 최대낙폭 −28%</td><td>기준 미달</td></tr>
        <tr><td>단일 자산 상한 50%</td><td>수익·낙폭이 같이 반토막(= 현금 50%)</td><td>기각</td></tr>
        <tr><td>주식·채권 상관 규칙</td><td>표본 발동 0회, 초장기에선 악화</td><td>불필요</td></tr>
        <tr><td>듀얼 모멘텀(GEM) 혼합</td><td>GEM 연 8.4%, 혼합 시 수익만 감소</td><td>혼합 대신 규칙(①)으로 결합</td></tr>
        </table>

        <h4>남은 위험</h4>
        <ul>
        <li><b>발표 후 검증이 없습니다</b> — 원저자 발표가 2026-07. 같은 계열 공개 전략(GEM·ADM·VAA)은 발표 후 수익이 절반 이하로 줄었습니다.</li>
        <li>2017 이후 성과의 상당 부분이 XLK·XLE 집중에서 나왔습니다(2008~2016 은 연 8~11%).</li>
        <li>월말 판단이라 한 달 안의 급락(1987·2020-03형)은 막지 못합니다.</li>
        <li>미국 섹터 ETF 의존 — 연금계좌는 국내 상장 대체 상품으로 실행하며 추적오차·환헤지 여부가 결과를 바꿉니다.</li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
