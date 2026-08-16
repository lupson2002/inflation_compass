"""현재 포지션 페이지 — 이전 월말 결정 vs 오늘 시점 계산 비교."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

import backtest

import fng_engine
import yfinance as yf

TICKER_KR = {
    "XLE": "에너지",
    "XLK": "기술",
    "XLU": "유틸리티",
    "XLP": "필수소비재",
    "IEF": "7-10년 국채",
    "SHY": "1-3년 단기채",
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
    .ic-fng-card { background:#ffffff; border:2px solid #2b6cb0; border-radius:12px; padding:20px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
    .ic-fng-score { font-size:32px; font-weight:800; color:#2b6cb0; }
    </style>
    """,
    unsafe_allow_html=True,
)

prices, t5yie = backtest.load_data()
signals, _ = backtest.compute_signals(prices, t5yie)
positions = backtest.build_positions(signals)
details = backtest.compute_signal_details(prices, t5yie)

# F&G Engine Data
vix = yf.download("^VIX", start="2000-01-01", auto_adjust=True, progress=False)["Close"].squeeze().reindex(prices.index).ffill()
df_hy = pd.read_csv("https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAA10Y&cosd=1996-12-31", na_values=".").dropna()
df_hy["date"] = pd.to_datetime(df_hy["observation_date"])
hy_spread = df_hy.set_index("date")["BAA10Y"].reindex(prices.index).ffill()
fng_pos = fng_engine.calculate_model_c1_ultra_position(prices, t5yie, vix, hy_spread)

prev_d, prev_e, prev_regime, prev_weights = positions[-1]
last_signal = signals.iloc[-1]
cur_regime = (bool(last_signal["growth_on"]), bool(last_signal["inflation_on"]))
cur_weights = backtest.REGIME_POSITIONS[cur_regime]

st.title("현재 포지션 및 심리 레버리지 오버레이")

# 1. Fear & Greed Model C-1 Ultra Live Banner
st.markdown("### 🧠 CNN Fear & Greed x Model C-1 Ultra 실시간 포지션")
fcol1, fcol2, fcol3 = st.columns([1.2, 1.8, 1.5])

with fcol1:
    st.metric(
        label="CNN Fear & Greed 심리지수",
        value=f"{fng_pos['current_fng']:.1f}점 {fng_pos['current_emoji']}",
        delta=fng_pos["current_rating_kr"],
    )

with fcol2:
    exp_text = "⚡ 2.0배 공격 레버리지 (200%)" if fng_pos["exposure"] > 1.0 else ("🛡️ 0.5배 위험축소 (현금 50%)" if fng_pos["exposure"] < 1.0 else "⚖️ 1.0배 정규 비중 (100%)")
    st.markdown(f"**권장 노출 배수:** `{exp_text}`")
    st.markdown(f"**최종 목표 비중:** **{weights_str(fng_pos['final_weights'])}**")
    st.caption(f"💡 판단 근거: {fng_pos['action_reason']}")

with fcol3:
    st.markdown("**공포 룩백 메모리 ($F&G < 15$ 탐지)**")
    st.markdown(
        f"- $t_0$ (당월): `{fng_pos['t0_fng']:.1f}` {'🚨' if fng_pos['t0_fng'] < 15 else 'OK'}\n"
        f"- $t-2$ (2달 전): `{fng_pos['t2_fng']:.1f}` {'🚨' if fng_pos['t2_fng'] < 15 else 'OK'}\n"
        f"- $t-3$ (3달 전): `{fng_pos['t3_fng']:.1f}` {'🚨' if fng_pos['t3_fng'] < 15 else 'OK'}\n"
        f"- $t-4$ (4달 전): `{fng_pos['t4_fng']:.1f}` {'🚨' if fng_pos['t4_fng'] < 15 else 'OK'}"
    )

st.divider()

# 2. Original Baseline IC Regime Position Cards
st.markdown("### 🧭 Inflation Compass 4국면 기본 로테이션")
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
st.markdown(
    f"<div style='background:#f7f8f4;border:1px solid #e1e0d9;border-radius:8px;padding:10px 14px;font-size:13px'>"
    f"<b>60일 기울기</b> = Σ(x−x̄)(y−ȳ) / Σ(x−x̄)² = "
    f"<b>{details['slope_num']:.4f}</b> / <b>{details['slope_denom']:.0f}</b> = "
    f"<b>{details['slope_val']:.4f}</b> {'→ 양수 ✔ (asset 모멘텀 ON)' if details['asset_momentum_on'] else '→ ≤ 0 ✘ (asset 모멘텀 OFF)'}"
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

# ─────────────────────────────────────────────────────────────
# 연금 운용용 IC 50/25/25 전략 포지션 (하단)
# ─────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("## 🏦 연금 운용 · IC 50/25/25")

import pension as pension_mod
import pension_strategies as ps

pos = pension_mod.pension_position()
regime = pos["regime"]
regime_str = f"성장 {'상승' if regime[0] else '하락'} · 인플레이션 {'상승' if regime[1] else '하락'}"

st.markdown(
    f"""
    <div style="background:#f7f8f4;border:1px solid #e1e0d9;border-radius:10px;padding:18px 20px">
    <div style="font-size:15px;font-weight:600;color:#16191a">🏦 연금 운용용 IC 50/25/25 전략</div>
    <div style="font-size:13px;color:#52564d;margin:6px 0 10px">
    IC(50%) {pension_mod.TICKER_KR.get(pos['ic_asset'], pos['ic_asset'])} · BAA-G4(25%) {pension_mod.TICKER_KR.get(pos['baag4_asset'], pos['baag4_asset'])} · V8(25%) {pension_mod.TICKER_KR.get(pos['v8_asset'], pos['v8_asset'])} · 신호일 {pos['signal_date'].date()}</div>
    <div style="font-size:22px;font-weight:700;color:#bb6b2c">{pension_mod.weights_str(pos['weights'])}</div>
    <div style="font-size:12px;color:#898781;margin-top:8px">{regime_str} · SPY 12M 모멘텀 {pos['spy_12m_mom'] * 100:+.1f}%</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("")
st.markdown("#### 🧩 전략 구성 설명")
pension_cols = st.columns(3)
for col, (key, info) in zip(pension_cols, ps.PENSION_STRATEGIES.items()):
    with col:
        st.markdown(
            f"""
            <div style="background:#f7f8f4;border:1px solid #e1e0d9;border-radius:10px;padding:14px 16px;height:100%">
            <div style="font-size:14px;font-weight:600;color:#16191a">{info['name']}</div>
            <div style="font-size:12px;color:#bb6b2c;margin:4px 0">비중 {info['weight'] * 100:.0f}%</div>
            <div style="font-size:12px;color:#52564d">{info['desc']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown("")
st.markdown("#### 📄 연구 보고서 요약")
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

    **롤링 성과 (IC+BAA-G4+V8 50/25/25):**
    - 3년: CAGR 16.03% · MDD -9.20% · Sharpe 1.370 · Calmar 2.235
    - 5년: CAGR 15.32% · MDD -11.30% · Sharpe 1.320 · Calmar 1.689
    - 10년: CAGR 14.73% · MDD -13.20% · Sharpe 1.301 · Calmar 1.239
    - 전체(23년): CAGR 16.42% · MDD -18.9% · Sharpe 1.350 · Calmar 0.869
    """
)
st.caption("본 보고서는 과거 데이터 기반 백테스트로, 미래 수익을 보장하지 않습니다.")
