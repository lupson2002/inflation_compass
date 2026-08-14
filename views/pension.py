"""연금 운용용 IC 50/25/25 전략 — 대시보드 신규 섹션.

dual-momentum 연구 결과(REPORT_PENSION_MASTER.md)를 요약하고,
현재 포지션과 롤링 성과 지표를 표시한다.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

import pension

st.markdown("<style>div.block-container { padding-top: 2.6rem; }</style>", unsafe_allow_html=True)

st.title("연금 운용 · IC 50/25/25")

st.markdown(
    """
    <style>
    .pn-card { background:#f7f8f4; border:1px solid #e1e0d9; border-radius:10px; padding:18px 20px; }
    .pn-title { font-size:15px; font-weight:600; color:#16191a; }
    .pn-asset { font-size:22px; font-weight:700; color:#bb6b2c; }
    .pn-note { font-size:12px; color:#898781; margin-top:8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── 현재 포지션 ──
pos = pension.pension_position()
regime = pos["regime"]
regime_str = f"성장 {'상승' if regime[0] else '하락'} · 인플레이션 {'상승' if regime[1] else '하락'}"

st.markdown("### 📍 현재 포지션")
col1, col2 = st.columns(2)
with col1:
    st.markdown(
        f"""
        <div class="pn-card">
        <div class="pn-title">🧭 IC 성분 (50%)</div>
        <div class="pn-note">{regime_str} · 신호일 {pos['signal_date'].date()}</div>
        <div class="pn-asset">{pension.TICKER_KR.get(pos['ic_asset'], pos['ic_asset'])} ({pos['ic_asset']})</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col2:
    st.markdown(
        f"""
        <div class="pn-card">
        <div class="pn-title">🔄 BAA-G4 (25%) · V8 (25%)</div>
        <div class="pn-note">SPY 12M 모멘텀 {pos['spy_12m_mom'] * 100:+.1f}%</div>
        <div class="pn-asset">{pension.TICKER_KR.get(pos['baag4_asset'], pos['baag4_asset'])} ({pos['baag4_asset']}) · {pension.TICKER_KR.get(pos['v8_asset'], pos['v8_asset'])} ({pos['v8_asset']})</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("")
st.markdown("#### 종합 포지션")
st.markdown(
    f"""
    <div style="background:#f7f8f4;border:1px solid #e1e0d9;border-radius:10px;padding:18px 20px">
    <div style="font-size:22px;font-weight:700;color:#bb6b2c">{pension.weights_str(pos['weights'])}</div>
    <div style="font-size:12px;color:#898781;margin-top:8px">연금 운용용 IC 50/25/25 — 성장 신호는 200MA 유지</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── 롤링 성과 지표 ──
st.markdown("### 📊 롤링 성과 지표 (2003-02 ~ 2026-06)")
st.markdown(
    "IC+BAA-G4+V8 (50/25/25) — 3/5/10년 롤링 평균. 모든 윈도우에서 CAGR 양수, MDD -18.9% 통제."
)

rolling_data = {
    "3년": {"CAGR": "16.03%", "MDD": "-9.20%", "기간수익률": "57.75%", "Sharpe": "1.370", "Calmar": "2.235"},
    "5년": {"CAGR": "15.32%", "MDD": "-11.30%", "기간수익률": "108.10%", "Sharpe": "1.320", "Calmar": "1.689"},
    "10년": {"CAGR": "14.73%", "MDD": "-13.20%", "기간수익률": "307.05%", "Sharpe": "1.301", "Calmar": "1.239"},
}
rolling_df = pd.DataFrame(rolling_data).T
rolling_df.index.name = "윈도우"
st.dataframe(rolling_df, width="stretch")

st.markdown("#### 전체 기간 (23년 Buy&Hold)")
st.markdown(
    "**CAGR 16.42% | MDD -18.9% | 기간수익률 3416% | Sharpe 1.350 | Calmar 0.869 | 변동성 11.8%**"
)

# ── 보고서 요약 ──
st.markdown("### 📄 연구 보고서 요약")
st.markdown(
    """
    **20년 연금 인출 로드맵:**
    - **축적기 (지금~15년 전):** IC+BAA-G4+V8 (50/25/25) — CAGR 16.4%, MDD -18.8%
    - **전환기 (15년~5년 전):** 점진적 디리스킹 (혼합 → IC 단독 → 정적 60/40)
    - **인출준비기 (5년 전~인출):** 정적 60/40 또는 IC 방어 레짐

    **핵심 원칙:**
    1. 동적 자산배분이 정적보다 우월 (모든 윈도우에서 CAGR·Sharpe·MDD 우위)
    2. 성장 신호는 200MA 유지 (ICSA/SAHM/곡선역전/12-1모멘텀/GAC보다 우월)
    3. 상관 낮은 혼합이 하락방어 (MDD -28.9% → -18.8%)
    4. 과최적화 경계 — 둥근 비율, 아웃오브샘플 검증
    """
)

st.caption("본 보고서는 과거 데이터 기반 백테스트로, 미래 수익을 보장하지 않습니다.")
