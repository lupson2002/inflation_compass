"""연금 운용 · IC 50/25/25 — 대시보드.

dual-momentum 연구의 정적/동적 자산배분 전략 전체를 담고,
전략을 선택하면 백테스트 차트(수익곡선·낙폭·연도별·비중)와 지표를 보여준다.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).parent.parent))

import pension
import pension_strategies as ps

COPPER = "#bb6b2c"
COPPER_DIM = "#d3a578"
SLATE = "#3d5a73"
GOOD = "#2f7d4f"
BAD = "#b0442f"

st.markdown("<style>div.block-container { padding-top: 2.6rem; }</style>", unsafe_allow_html=True)

st.title("연금 운용 · IC 50/25/25")

# ── 현재 포지션 ──
pos = pension.pension_position()
regime = pos["regime"]
regime_str = f"성장 {'상승' if regime[0] else '하락'} · 인플레이션 {'상승' if regime[1] else '하락'}"

st.markdown("### 📍 현재 포지션")
st.markdown(
    f"""
    <div style="background:#f7f8f4;border:1px solid #e1e0d9;border-radius:10px;padding:18px 20px">
    <div style="font-size:15px;font-weight:600;color:#16191a">🏦 연금 운용용 IC 50/25/25</div>
    <div style="font-size:13px;color:#52564d;margin:6px 0 10px">
    IC(50%) {pension.TICKER_KR.get(pos['ic_asset'], pos['ic_asset'])} · BAA-G4(25%) {pension.TICKER_KR.get(pos['baag4_asset'], pos['baag4_asset'])} · V8(25%) {pension.TICKER_KR.get(pos['v8_asset'], pos['v8_asset'])} · 신호일 {pos['signal_date'].date()}</div>
    <div style="font-size:22px;font-weight:700;color:#bb6b2c">{pension.weights_str(pos['weights'])}</div>
    <div style="font-size:12px;color:#898781;margin-top:8px">{regime_str} · SPY 12M 모멘텀 {pos['spy_12m_mom'] * 100:+.1f}%</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── 연금 전략 구성 설명 ──
st.markdown("### 🧩 연금 전략 구성 (IC 50/25/25)")
st.markdown(
    "20년 연금 인출 목표로, 상관이 낮은 3개 동적 전략을 혼합해 하락방어를 강화한 포트폴리오."
)
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

# ── 전략 선택 ──
st.markdown("### 📊 전략 백테스트")
returns = ps.load_strategy_returns()

group_tab = st.radio("전략 그룹", ["연금 추천 (IC 50/25/25)", "동적 자산배분", "정적 자산배분"], horizontal=True)

if group_tab == "연금 추천 (IC 50/25/25)":
    strategy_keys = list(ps.PENSION_STRATEGIES.keys())
    labels = {k: ps.PENSION_STRATEGIES[k]["name"] for k in strategy_keys}
else:
    strategy_keys = ps.DYNAMIC_STRATEGIES if group_tab == "동적 자산배분" else ps.STATIC_STRATEGIES
    labels = {k: ps.STRATEGY_INFO[k]["name"] for k in strategy_keys}

selected = st.selectbox("전략 선택", strategy_keys, format_func=lambda k: labels[k])

info = ps.STRATEGY_INFO[selected]
st.markdown(f"**{info['name']}** · {info['group']} 자산배분")
st.markdown(info["desc"])

# 전략 수익률
strat_ret = returns[selected].dropna()
if len(strat_ret) == 0:
    st.warning("선택한 전략의 데이터가 없습니다.")
    st.stop()

# 벤치마크 (S&P500)
bench_ret = returns["S&P500"].dropna()
bench_ret = bench_ret.loc[strat_ret.index[0]:]

# 지표
m = ps.strategy_metrics(strat_ret)
bm = ps.strategy_metrics(bench_ret)

# ── 지표 카드 ──
st.markdown("#### 성과 지표")
metric_cols = st.columns(6)
metrics_display = [
    ("CAGR", f"{m['CAGR'] * 100:.1f}%"),
    ("변동성", f"{m['Vol'] * 100:.1f}%"),
    ("Sharpe", f"{m['Sharpe']:.2f}"),
    ("MaxDD", f"{m['MaxDD'] * 100:.1f}%"),
    ("Calmar", f"{m['Calmar']:.2f}"),
    ("복리배수", f"${m['Multiple']:.1f}"),
]
for col, (label, value) in zip(metric_cols, metrics_display):
    with col:
        st.metric(label, value)

st.caption(f"기간: {m['start']} ~ {m['end']} ({m['n_months']}개월) · 벤치마크 S&P500 CAGR {bm['CAGR'] * 100:.1f}%")

# ── 차트 ──
tab_chart, tab_stats, tab_yearly, tab_rolling = st.tabs(
    ["수익곡선·낙폭", "통계표", "연도별 수익률", "롤링 지표"]
)

with tab_chart:
    strat_eq = (1 + strat_ret).cumprod()
    bench_eq = (1 + bench_ret).cumprod()
    strat_dd = strat_eq / strat_eq.cummax() - 1
    bench_dd = bench_eq / bench_eq.cummax() - 1

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.06)
    fig.add_trace(go.Scatter(x=bench_eq.index, y=bench_eq, name="S&P500", line=dict(color=SLATE, width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=strat_eq.index, y=strat_eq, name=info["name"], line=dict(color=COPPER, width=2)), row=1, col=1)
    fig.update_yaxes(type="log", title="growth of $1", row=1, col=1)
    fig.add_trace(go.Scatter(x=bench_dd.index, y=bench_dd * 100, line=dict(color=SLATE, width=1), fill="tozeroy", fillcolor="rgba(61,90,115,0.15)", showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=strat_dd.index, y=strat_dd * 100, line=dict(color=COPPER, width=1), fill="tozeroy", fillcolor="rgba(187,107,44,0.18)", showlegend=False), row=2, col=1)
    fig.update_yaxes(title="drawdown %", row=2, col=1)
    fig.update_layout(height=520, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", yanchor="bottom", y=1.02), hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch")

with tab_stats:
    metric_order = ["CAGR", "Vol", "Sharpe", "MaxDD", "Calmar", "Multiple"]

    def fmt_metric(name, v):
        if name == "Sharpe" or name == "Calmar":
            return f"{v:.2f}"
        if name == "Multiple":
            return f"${v:.1f}"
        return f"{v:.1%}"

    stats_df = pd.DataFrame({
        "S&P500": {k: fmt_metric(k, bm[k]) for k in metric_order},
        info["name"]: {k: fmt_metric(k, m[k]) for k in metric_order},
    })
    st.dataframe(stats_df, width="stretch")

with tab_yearly:
    def yearly_returns(r):
        return r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1)

    strat_yearly = yearly_returns(strat_ret)
    bench_yearly = yearly_returns(bench_ret)
    years = sorted(strat_yearly.index)
    yearly_df = pd.DataFrame({
        "연도": years,
        "S&P500": [bench_yearly.get(y, 0) * 100 for y in years],
        info["name"]: [strat_yearly.get(y, 0) * 100 for y in years],
    })
    yearly_df["초과수익"] = yearly_df[info["name"]] - yearly_df["S&P500"]

    def color_excess(v):
        return f"color: {GOOD}" if v >= 0 else f"color: {BAD}"

    st.dataframe(
        yearly_df.style.format({c: "{:.1f}%" for c in yearly_df.columns if c != "연도"}).map(color_excess, subset=["초과수익"]),
        width="stretch", hide_index=True,
    )

with tab_rolling:
    st.markdown("#### 롤링 지표 (3/5/10년)")
    for months, label in [(36, "3년"), (60, "5년"), (120, "10년")]:
        if len(strat_ret) < months:
            continue
        rdf = ps.rolling_metrics(strat_ret, months)
        st.markdown(f"**{label} 롤링** ({len(rdf)}개 윈도우)")
        rdf_display = rdf[["CAGR", "MDD", "기간수익률", "Sharpe", "Calmar"]].agg(["mean", "median", "min", "max"])
        rdf_display = rdf_display.T
        rdf_display.columns = ["평균", "중앙", "최소", "최대"]
        for c in ["CAGR", "MDD", "기간수익률"]:
            rdf_display[c] = rdf_display[c].map(lambda v: f"{v * 100:.2f}%")
        for c in ["Sharpe", "Calmar"]:
            rdf_display[c] = rdf_display[c].map(lambda v: f"{v:.3f}")
        st.dataframe(rdf_display, width="stretch")

# ── 연구 보고서 요약 ──
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
