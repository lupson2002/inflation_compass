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
details = backtest.compute_signal_details(prices, t5yie)

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

st.markdown("")
st.markdown("#### 인플레이션 판정 근거 (최신 데이터)")
if not last_signal["inflation_on"]:
    st.markdown(
        "**인플레이션 하락** — 아래 조건이 충족되지 않았습니다."
    )
st.markdown(
    f"""
    - **레벨**: T5YIE = {details['t5yie_now']:.2f}% {'> 2.0% ✔' if details['level_on'] else '≤ 2.0% ✘'}
    - **Breakeven 모멘텀**: T5YIE({details['t5yie_now']:.2f}%) vs 60거래일 전({details['t5yie_60ago']:.2f}%) → {'상승 ✔' if details['breakeven_momentum_on'] else '하락 ✘'}
    - **Asset 모멘텀**: confirming indicator 60일 기울기 = {details['indicator_slope']:.4f} → {'양수 ✔' if details['asset_momentum_on'] else '≤ 0 ✘'}
    """
)
st.caption(
    "인플레이션 상승 = (T5YIE > 2.0%) AND (Breakeven 모멘텀 OR Asset 모멘텀). "
    "모멘텀 조건은 둘 중 하나라도 양수면 충족됩니다."
)

st.markdown("")
st.markdown("#### Confirming Indicator 구성 (최근 60거래일)")
ind_change = details["indicator"] - details["indicator_60ago"]
ind_arrow = "↗" if ind_change >= 0 else "↘"
st.markdown(
    f"지표값 <b>{details['indicator_60ago']:.3f} → {details['indicator']:.3f}</b> "
    f"(60일 전 → 현재, {ind_arrow} {ind_change:+.3f}) · "
    f"수혜 바스켓 {details['pos_basket_ret'] * 100:+.1f}% / 방어 바스켓 {details['neg_basket_ret'] * 100:+.1f}%"
)
if details["indicator_slope"] > 0:
    trend_note = "전체적으로 상승 추세 → 기울기 양수 ✔"
else:
    trend_note = "전체적으로 하락 추세 → 기울기 음수 ✘"
st.markdown(
    f"<div style='background:#f7f8f4;border:1px solid #e1e0d9;border-radius:8px;padding:10px 14px;font-size:13px'>"
    f"<b>60일 기울기 = {details['indicator_slope']:.4f}</b> · {trend_note}<br>"
    f"<span style='color:#898781'>※ 시작값과 끝값이 비슷해도, 중간에 크게 내렸다 다시 오르면(산 모양) 전체는 하락 추세로 판단됩니다. "
    f"그래서 단순 뺄셈이 아니라 전체 흐름의 회귀 기울기를 씁니다.</span>"
    f"</div>",
    unsafe_allow_html=True,
)
col_pos, col_neg = st.columns(2)
with col_pos:
    st.markdown("**수혜(리플레이션)**")
    pos_rows = "".join(
        f"<tr><td>{t} <span style='color:#898781'>({backtest.POS_BASKET[t]*100:.0f}%)</span></td>"
        f"<td style='text-align:right'>{v*100:+.1f}%</td></tr>"
        for t, v in details["pos_contrib"].items()
    )
    st.markdown(
        f"<table style='width:100%;font-size:13px'>{pos_rows}</table>",
        unsafe_allow_html=True,
    )
with col_neg:
    st.markdown("**방어(피해)**")
    neg_rows = "".join(
        f"<tr><td>{t} <span style='color:#898781'>({backtest.NEG_BASKET[t]*100:.0f}%)</span></td>"
        f"<td style='text-align:right'>{v*100:+.1f}%</td></tr>"
        for t, v in details["neg_contrib"].items()
    )
    st.markdown(
        f"<table style='width:100%;font-size:13px'>{neg_rows}</table>",
        unsafe_allow_html=True,
    )
st.caption("수혜 바스켓 = 0.5·XLE + ⅙·XLI + ⅙·XLF + ⅙·XLB · 방어 바스켓 = ⅓·XLU + ⅓·XLV + ⅓·XLP · 지표 = 수혜누적 ÷ 방어누적")
