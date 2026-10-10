"""Main dashboard page: sidebar cost control + tabbed results.

Reads only backtest_daily_returns, backtest_turnover_events, backtest_weights (원조 IC)
and confirmed_equity (확정 전략, 실거래 조건) from data/inflation_compass.db.
표는 backtest.refresh_if_new_month() 가 월 1회 갱신한다 — 캐시는 6시간.
"""

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "inflation_compass.db"

COPPER = "#bb6b2c"
COPPER_DIM = "#d3a578"
SLATE = "#3d5a73"
GOOD = "#2f7d4f"
BAD = "#b0442f"
WEIGHT_COLORS = {"XLE": "#2a78d6", "XLK": "#eb6834", "XLU": "#1baf7a", "XLP": "#eda100", "IEF": "#e87ba4"}   # 원조 IC 비중


@st.cache_data(ttl=6 * 3600)
def load_data():
    conn = sqlite3.connect(DB_PATH)
    daily = pd.read_sql("SELECT * FROM backtest_daily_returns ORDER BY date", conn, parse_dates=["date"]).set_index("date")
    turnover = pd.read_sql("SELECT * FROM backtest_turnover_events ORDER BY decision_date", conn, parse_dates=["decision_date"])
    weights = pd.read_sql("SELECT * FROM backtest_weights ORDER BY date", conn, parse_dates=["date"]).set_index("date")
    try:
        confirmed = pd.read_sql("SELECT * FROM confirmed_equity ORDER BY date", conn, parse_dates=["date"]).set_index("date")["confirmed_equity"]
    except Exception:
        confirmed = None
    conn.close()
    return daily, turnover, weights, confirmed


def apply_cost(strat_ret, turnover_df, cost_pct):
    rate = cost_pct / 100
    ret = strat_ret.copy()
    idx = ret.index
    for _, row in turnover_df.iterrows():
        loc = idx.get_indexer([row["decision_date"]])[0]
        if loc + 1 < len(idx):
            d = idx[loc + 1]
            ret.loc[d] = (1 + ret.loc[d]) * (1 - row["turnover"] * rate) - 1
    return ret


def equity_curve(ret):
    return (1 + ret).cumprod()


def drawdown_of(eq):
    return eq / eq.cummax() - 1


def perf_stats(ret, eq):
    n_years = len(ret) / 252
    cagr = eq.iloc[-1] ** (1 / n_years) - 1
    vol = ret.std() * np.sqrt(252)
    sharpe = (ret.mean() * 252) / vol
    mdd = drawdown_of(eq).min()
    return {"CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "MaxDD": mdd, "Multiple": eq.iloc[-1]}


def yearly_returns(ret):
    return ret.groupby(ret.index.year).apply(lambda r: (1 + r).prod() - 1)


st.markdown("<style>div.block-container { padding-top: 2.6rem; }</style>", unsafe_allow_html=True)

daily, turnover, weights, confirmed = load_data()
st.caption(
    "원조 IC = 저자 모델(레버리지 없음, 월말 종가 체결, 비용은 사이드바 값). "
    "확정 전략 = 원조 + 침체 국면 IEF 100·채권방어 + IC 위험선호 지수 당월 레버리지(주식 칸은 섹터 200일선 위일 때만) + 상시 보험 금 10·BIL 5, 실거래 조건(전일 FRED·월말 30bp·DTB3 차입) 반영 — 사이드바 비용과 무관."
)
zero_ret = daily["strategy_ret"]
bench_ret = daily["spy_ret"]
zero_eq, bench_eq = equity_curve(zero_ret), equity_curve(bench_ret)
zero_stats, bench_stats = perf_stats(zero_ret, zero_eq), perf_stats(bench_ret, bench_eq)
zero_yearly, bench_yearly = yearly_returns(zero_ret), yearly_returns(bench_ret)

with st.sidebar:
    st.markdown("**편도 매매비용(%)**")
    cost_pct = st.number_input("%", min_value=0.0, max_value=5.0, value=0.3, step=0.05, label_visibility="collapsed")

net_ret = apply_cost(zero_ret, turnover, cost_pct)
net_eq = equity_curve(net_ret)
net_stats = perf_stats(net_ret, net_eq)
net_yearly = yearly_returns(net_ret)

conf_eq = conf_stats = conf_yearly = None
if confirmed is not None and len(confirmed):
    conf_ret = confirmed.pct_change().fillna(0.0)
    conf_eq = confirmed / confirmed.iloc[0] * net_eq.asof(confirmed.index[0])   # 같은 날 원조 곡선 값에서 출발
    conf_stats = perf_stats(conf_ret.iloc[1:], (confirmed / confirmed.iloc[0]).iloc[1:])
    conf_yearly = yearly_returns(conf_ret)

tab_chart, tab_stats, tab_rel, tab_yearly, tab_weights = st.tabs(
    ["그래프", "통계표", "상대성과", "연도별 수익률", "비중"]
)

with tab_chart:
    fig1 = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.06)
    fig1.add_trace(go.Scatter(x=bench_eq.index, y=bench_eq, name="SPY", line=dict(color=SLATE, width=2)), row=1, col=1)
    fig1.add_trace(go.Scatter(x=zero_eq.index, y=zero_eq, name="Inflation Compass (0%)", line=dict(color=COPPER_DIM, width=1.4, dash="dot")), row=1, col=1)
    fig1.add_trace(go.Scatter(x=net_eq.index, y=net_eq, name=f"Inflation Compass ({cost_pct:.2f}%)", line=dict(color=COPPER, width=2)), row=1, col=1)
    if conf_eq is not None:
        fig1.add_trace(go.Scatter(x=conf_eq.index, y=conf_eq, name="확정 전략 (실거래 조건)", line=dict(color=GOOD, width=2.2)), row=1, col=1)
    fig1.update_yaxes(type="log", title="growth of $1", row=1, col=1)

    bench_dd, net_dd = drawdown_of(bench_eq), drawdown_of(net_eq)
    fig1.add_trace(go.Scatter(x=bench_dd.index, y=bench_dd * 100, line=dict(color=SLATE, width=1), fill="tozeroy", fillcolor="rgba(61,90,115,0.15)", showlegend=False), row=2, col=1)
    fig1.add_trace(go.Scatter(x=net_dd.index, y=net_dd * 100, line=dict(color=COPPER, width=1), fill="tozeroy", fillcolor="rgba(187,107,44,0.18)", showlegend=False), row=2, col=1)
    if conf_eq is not None:
        fig1.add_trace(go.Scatter(x=conf_eq.index, y=drawdown_of(conf_eq) * 100, line=dict(color=GOOD, width=1), showlegend=False), row=2, col=1)
    fig1.update_yaxes(title="drawdown %", row=2, col=1)
    fig1.update_layout(height=560, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", yanchor="bottom", y=1.02), hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig1, width="stretch")

with tab_stats:
    metric_order = ["CAGR", "Vol", "Sharpe", "MaxDD", "Multiple"]

    def fmt_metric(name, v):
        if name == "Sharpe":
            return f"{v:.2f}"
        if name == "Multiple":
            return f"${v:.1f}"
        return f"{v:.1%}"

    stats_df = pd.DataFrame({
        "SPY": {k: fmt_metric(k, bench_stats[k]) for k in metric_order},
        "Strategy (0%)": {k: fmt_metric(k, zero_stats[k]) for k in metric_order},
        f"Strategy ({cost_pct:.2f}%)": {k: fmt_metric(k, net_stats[k]) for k in metric_order},
        **({"확정 전략 (실거래)": {k: fmt_metric(k, conf_stats[k]) for k in metric_order}} if conf_eq is not None else {}),
    })
    st.dataframe(stats_df, width="stretch")
    st.caption(
        "⚠️ 열마다 조건이 다르다: 원조 열은 FRED 당일 값·2003-03 시작(첫해 +45%)이라 유리하고, "
        "확정 전략 열은 실거래 조건(전일 FRED·2003-09 시작·월말 30bp·DTB3 차입)이다. "
        "같은 실거래 조건으로 맞추면 원조(레버리지 없음) 연 19.1% vs 확정 전략 19.5%(상시 보험 15% 포함), 최대낙폭 −24.5% vs −20.2%, 2008 낙폭 −18.8% vs −11.0%. "
        "Sharpe 는 무위험 금리 차감 없이 계산."
    )

with tab_rel:
    ratio = net_eq / bench_eq
    ratio_dd = drawdown_of(ratio)
    fig3 = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.65, 0.35], vertical_spacing=0.06)
    fig3.add_trace(go.Scatter(x=ratio.index, y=ratio, line=dict(color=COPPER, width=2), showlegend=False), row=1, col=1)
    fig3.update_yaxes(type="log", tickformat=".1f", ticksuffix="x", title="Strategy / SPY", row=1, col=1)
    fig3.add_trace(go.Scatter(x=ratio_dd.index, y=ratio_dd * 100, line=dict(color=COPPER, width=1), fill="tozeroy", fillcolor="rgba(187,107,44,0.18)", showlegend=False), row=2, col=1)
    fig3.update_yaxes(title="상대낙폭 %", row=2, col=1)
    fig3.update_layout(height=480, margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig3, width="stretch")

with tab_yearly:
    years = sorted(zero_yearly.index)
    yearly_df = pd.DataFrame({
        "연도": years,
        "SPY": [bench_yearly.get(y, 0) * 100 for y in years],
        "Strategy (0%)": [zero_yearly.get(y, 0) * 100 for y in years],
        f"Strategy ({cost_pct:.2f}%)": [net_yearly.get(y, 0) * 100 for y in years],
        **({"확정 전략 (실거래)": [conf_yearly.get(y, np.nan) * 100 for y in years]} if conf_eq is not None else {}),
    })
    yearly_df["초과수익"] = yearly_df[f"Strategy ({cost_pct:.2f}%)"] - yearly_df["SPY"]

    def color_excess(v):
        return f"color: {GOOD}" if v >= 0 else f"color: {BAD}"

    st.dataframe(
        yearly_df.style.format({c: "{:.1f}%" for c in yearly_df.columns if c != "연도"}, na_rep="-").map(color_excess, subset=["초과수익"]),
        width="stretch", hide_index=True,
    )

with tab_weights:
    fig2 = go.Figure()
    for t, color in WEIGHT_COLORS.items():
        fig2.add_trace(go.Scatter(x=weights.index, y=weights[t] * 100, name=t, mode="lines", stackgroup="w", line=dict(width=0.5, color=color), fillcolor=color))
    fig2.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(range=[0, 100], title="%"), legend=dict(orientation="h", yanchor="bottom", y=1.02), hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig2, width="stretch")
