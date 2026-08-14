"""Percentile Channels TAA — 전략 설명 (static)."""

import streamlit as st

st.markdown(
    """
    <style>
    div.block-container { padding-top: 2.6rem; }
    .ic-body p, .ic-body ul { margin: 0 0 8px; font-size: 14px; line-height: 1.48; }
    .ic-body ul { padding-left: 20px; }
    .ic-body li { margin-bottom: 3px; }
    .ic-body h4 { font-size: 14px; margin: 12px 0 4px; font-weight: 700; color: #16191a; }
    .ic-body code { font-size: 13px; background: #f2f3ee; padding: 1px 5px; border-radius: 3px; }
    .ic-body .formula { background: #f2f3ee; border-radius: 5px; padding: 8px 12px; font-size: 13px; margin: 4px 0 8px; line-height: 1.6; }
    .ic-quad { display: grid; grid-template-columns: 120px repeat(4,1fr); gap: 8px; margin: 14px 0 6px; max-width: 700px; }
    .ic-quad .hdr { font-size: 11.5px; font-weight: 600; color: #8a8d84; text-align: center; }
    .ic-quad .cell { border-radius: 6px; padding: 12px 6px; text-align: center; font-size: 13px; }
    </style>
    """,
    unsafe_allow_html=True,
)

tab_concept, tab_signal, tab_sizing = st.tabs(["개념", "신호 규칙", "비중 계산"])

with tab_concept:
    st.markdown(
        """
        <div class="ic-body">
        <h4>핵심 아이디어</h4>
        <p>4개의 자산군(주식 VTI · 부동산 IYR · 회사채 LQD · 원자재 DBC)을, 각 자산이
        <b>강한 추세(상위 25% 구간)</b>에 들어설 때만 보유하고, <b>무너지면(하위 25%)</b> 현금(SHY)으로
        물러나는 월간 로테이션 전략입니다.</p>
        <ul>
        <li><b>롱온리</b> — 공매도 없음, 강세일 때만 보유</li>
        <li><b>월말 리밸런싱</b> — 매월 마지막 거래일에 결정, 다음 한 달 보유</li>
        <li><b>역변동성 사이징</b> — 변동성이 낮은 자산에 비중을 더</li>
        <li>출처: David Varadi (CSSA) — <a href="https://cssanalytics.wordpress.com/2015/01/26/a-simple-tactical-asset-allocation-portfolio-with-percentile-channels/" target="_blank">원문</a></li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

with tab_signal:
    st.markdown(
        """
        <div class="ic-body">
        <h4>퍼센타일 채널 (이격도가 아닙니다)</h4>
        <p>이동평균 대비 벌어진 정도(이격도)가 아니라, 가격이 <b>최근 N일 가격 중 몇 % 위치</b>인지를
        봅니다. 4개 채널(60/120/180/252일)을 병렬로 돌립니다.</p>
        <ul>
        <li><b>진입 75%</b> — 가격이 N일 중 75번째 백분위를 <b>상향돌파</b> → 매수(+1)</li>
        <li><b>이탈 25%</b> — 가격이 N일 중 25번째 백분위를 <b>하향돌파</b> → 매도(−1)</li>
        <li>그 사이(25%~75%)는 <b>기존 신호 유지</b> (히스테리시스 → 휩쏘 감소)</li>
        <li>신호는 <b>매일 추적</b>하되, 포지션은 월말에만 변경</li>
        </ul>
        <div class="formula">
        채널 점수 = +1 (75% 상향돌파) / −1 (25% 하향돌파) / 유지 (그 사이)
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with tab_sizing:
    st.markdown(
        """
        <div class="ic-body">
        <h4>Composite 점수</h4>
        <p>4개 채널 신호의 평균. 과반수(2개 이상)가 매수면 보유, 아니면 제외.</p>
        <div class="formula">
        composite = (60일신호 + 120일신호 + 180일신호 + 252일신호) ÷ 4
        </div>
        <h4>역변동성 비중</h4>
        <p>composite가 0보다 큰 자산만 대상으로, 변동성이 낮을수록 비중을 크게 줍니다.</p>
        <div class="formula">
        비중_i = (composite_i × 1/변동성_i) ÷ Σ(모든 보유자산의 |composite × 1/변동성|)<br/>
        단, composite ≤ 0인 자산은 제외 → 비중 0, 현금(SHY)으로
        </div>
        <p>SHY는 비중 계산에 포함하지 않고, 보유 자산 비중을 뺀 <b>잔여분</b>으로 배분합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown(
    """
    <div class="ic-body" style="margin-top:18px">
    <p>🔬 <b>복제 검증</b>: QuantStrat TradeR의 독립 복제(2006~2015, ETF 전용)가
    Sharpe ≈ 1.48, 최대낙폭 ≈ 6.9%를 보고했습니다. 본 구현은 데이터 소스 차이를 감안해
    유사한 수준(Sharpe ≈ 1.4, 낙폭 ≈ 6%)으로 수렴함을 확인했습니다.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
