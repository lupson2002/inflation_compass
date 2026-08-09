"""현재 포지션 페이지 — 이전 월말 결정 vs 오늘 시점 계산 비교."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

import backtest

TICKER_KR = {
    "XLE": "에너지",
    "XLK": "기술",
    "XLU": "유틸리티",
    "XLP": "필수소비재",
    "IEF": "7-10년 국채",
}


def regime_label(regime):
    growth = "상승" if regime[0] else "하락"
    infl = "상승" if regime[1] else "하락"
    return f"성장 {growth} · 인플레이션 {infl}"


def weights_str(weights):
    return " + ".join(f"{t} ({TICKER_KR.get(t, t)}) {w * 100:.0f}%" for t, w in weights.items())


st.markdown("<style>div.block-container { padding-top: 2.6rem; }</style>", unsafe_allow_html=True)

st.markdown(
    """
    <style>
    .ic-pos-card { background:#f7f8f4; border:1px solid #e1e0d9; border-radius:10px; padding:18px 20px; }
    .ic-pos-title { font-size:15px; font-weight:600; color:#16191a; }
    .ic-pos-regime { font-size:13px; color:#52564d; margin:6px 0 10px; }
    .ic-pos-asset { font-size:22px; font-weight:700; color:#bb6b2c; }
    .ic-pos-note { font-size:12px; color:#898781; margin-top:10px; }
    </style>
    """,
    unsafe_allow_html=True,
)

prices, t5yie = backtest.load_data()
signals, _ = backtest.compute_signals(prices, t5yie)
positions = backtest.build_positions(signals)

prev_d, prev_e, prev_regime, prev_weights = positions[-1]
last_signal = signals.iloc[-1]
cur_regime = (bool(last_signal["growth_on"]), bool(last_signal["inflation_on"]))
cur_weights = backtest.REGIME_POSITIONS[cur_regime]

st.title("현재 포지션")

col1, col2 = st.columns(2)

with col1:
    st.markdown(
        f"""
        <div class="ic-pos-card">
        <div class="ic-pos-title">📅 이전 월말 결정 ({prev_d.date()})</div>
        <div class="ic-pos-regime">{regime_label(prev_regime)}</div>
        <div class="ic-pos-asset">{weights_str(prev_weights)}</div>
        <div class="ic-pos-note">보유기간 ~ {prev_e.date()}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        f"""
        <div class="ic-pos-card">
        <div class="ic-pos-title">🔄 오늘 시점 계산 ({last_signal.name.date()})</div>
        <div class="ic-pos-regime">{regime_label(cur_regime)}</div>
        <div class="ic-pos-asset">{weights_str(cur_weights)}</div>
        <div class="ic-pos-note">최신 데이터 기준 실시간 신호</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

changed = prev_weights != cur_weights
st.info(
    "⚠️ 포지션이 변경됩니다 — 다음 월말 리밸런싱에 반영됩니다." if changed
    else "현재 포지션과 오늘 시점 신호가 동일합니다."
)

st.markdown("")
st.markdown("#### 신호 세부")
signals_detail = pd.DataFrame({
    "성장 신호": ["상승" if last_signal["growth_on"] else "하락"],
    "인플레이션 신호": ["상승" if last_signal["inflation_on"] else "하락"],
    "최근 신호일": [last_signal.name.date()],
    "이전 결정일": [prev_d.date()],
})
st.dataframe(signals_detail, width="stretch", hide_index=True)
