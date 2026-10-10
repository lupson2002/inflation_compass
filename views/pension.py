"""연금 운용 — 대시보드 (2026-10-09 개편).

위: 확정 연금 혼합 IC 연금형 50% + PENTARCH 비레버리지 50% 의 현재 포지션과 백테스트(pension_mix.py).
아래: 종전 dual-momentum 연구(CSV)의 정적/동적 전략 — 참고용.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).parent.parent))

import backtest
import pension_mix as PM
import pension_strategies as ps
import yfinance as yf

COPPER = "#bb6b2c"
COPPER_DIM = "#d3a578"
SLATE = "#3d5a73"
GOOD = "#2f7d4f"
BAD = "#b0442f"

st.markdown("<style>div.block-container { padding-top: 2.6rem; }</style>", unsafe_allow_html=True)

st.title("연금 운용 · IC 연금형 50 + PENTARCH 50")
st.caption("레버리지 없음(연금계좌 기준). 매월 말 50/50 으로 다시 맞춘다.")

prices, t5yie = backtest.load_data()
vix = yf.download("^VIX", start="2000-01-01", auto_adjust=True, progress=False)["Close"].squeeze().reindex(prices.index).ffill()
_baa = pd.read_csv("https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAA10Y&cosd=1996-12-31", na_values=".").dropna()
_baa["date"] = pd.to_datetime(_baa["observation_date"])
baa10y = _baa.set_index("date")["BAA10Y"].reindex(prices.index).ffill()
mix = PM.mix_position(prices, t5yie, vix, baa10y)
ic, pent = mix["ic"], mix["pentarch"]

st.markdown("### 📍 현재 목표 비중")
c1, c2, c3 = st.columns(3)
with c1:
    regime = f"성장 {'상승' if ic['growth_on'] else '하락'} · 인플레이션 {'상승' if ic['inflation_on'] else '하락'}"
    st.markdown(
        f"""<div style="background:#f7f8f4;border:1px solid #e1e0d9;border-radius:10px;padding:16px 18px;height:100%">
        <div style="font-size:14px;font-weight:600">🧭 IC 연금형 (50%)</div>
        <div style="font-size:12px;color:#52564d;margin:4px 0 8px">{regime} · IC 위험선호 지수 {ic['index']:.1f} · 노출 {ic['exposure']:.1f}배</div>
        <div style="font-size:18px;font-weight:700;color:#bb6b2c">{PM.weights_str(ic['final_weights'])}</div>
        <div style="font-size:11px;color:#898781;margin-top:6px">{'채권방어 작동 중(IEF &lt; 200일선)' if ic['bond_shield'] else '확정 전략과 같은 국면 판단, 2배 레버리지만 뺌'}</div>
        </div>""", unsafe_allow_html=True)
with c2:
    if pent is None:
        body = "<div style='font-size:14px;color:#b0442f'>PENTARCH 신호 없음 — pentarch 크론(05:00) 확인</div>"
    else:
        warn = f"<div style='font-size:11px;color:#b0442f'>⚠️ 신호가 {pent['stale_days']}일 지났다</div>" if pent["stale"] else ""
        body = (f"<div style='font-size:12px;color:#52564d;margin:4px 0 8px'>v18.3 신호 · 레버리지 ETF 제외 · {pent['effective_since']} 부터 · "
                f"데이터 {pent['data_asof']} ({pent['source']})</div>"
                f"<div style='font-size:18px;font-weight:700;color:#bb6b2c'>{PM.weights_str(pent['target'])}</div>{warn}")
    st.markdown(
        f"""<div style="background:#f7f8f4;border:1px solid #e1e0d9;border-radius:10px;padding:16px 18px;height:100%">
        <div style="font-size:14px;font-weight:600">🏛️ PENTARCH 비레버리지 (50%)</div>{body}</div>""", unsafe_allow_html=True)
with c3:
    st.markdown(
        f"""<div style="background:#fff;border:2px solid #bb6b2c;border-radius:10px;padding:16px 18px;height:100%">
        <div style="font-size:14px;font-weight:600">🏦 합계 (계좌 비중)</div>
        <div style="font-size:20px;font-weight:800;color:#bb6b2c;margin-top:8px">{PM.weights_str(mix['weights'])}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("### 📈 백테스트 (2008-02 ~ 2026-09, 월말 재조정)")
bt = pd.read_csv(Path(__file__).parent.parent / "data" / "pension_mix_backtest.csv", index_col=0, parse_dates=True)


def _mix(d: pd.DataFrame, w: dict, cost_bp: float = 30) -> pd.Series:
    cols = list(w); wv = np.array([w[c] for c in cols]); out = []
    for r in d[cols].values:
        g = float(wv @ r); drift = wv * (1 + r) / (1 + g)
        out.append((1 + g) * (1 - np.abs(drift - wv).sum() * cost_bp / 1e4) - 1)
    return pd.Series(out, index=d.index)


curves = {"IC 50 + PENTARCH 50 (확정)": _mix(bt, {"IC": .5, "PENT": .5}), "IC 연금형 단독": bt["IC"],
          "PENTARCH 비레버리지 단독": bt["PENT"], "IC 35 + BAA 30 + PENTARCH 35": _mix(bt, {"IC": .35, "BAA": .3, "PENT": .35}),
          "IC 25 + BAA 45 + PENTARCH 30 (인출 직전형)": _mix(bt, {"IC": .25, "BAA": .45, "PENT": .3})}
fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.06)
colors = [COPPER, SLATE, "#8a8d84", GOOD, "#9b59b6"]
rows = []
for (name, r), col in zip(curves.items(), colors):
    eq = (1 + r).cumprod(); dd = eq / eq.cummax() - 1
    fig.add_trace(go.Scatter(x=eq.index, y=eq, name=name, line=dict(color=col, width=2.4 if "확정" in name else 1.3)), row=1, col=1)
    fig.add_trace(go.Scatter(x=dd.index, y=dd * 100, line=dict(color=col, width=1), showlegend=False), row=2, col=1)
    n = len(r) / 12
    first, second = r.loc[:"2016-12-31"], r.loc["2017-01-31":]
    rows.append({"조합": name, "CAGR": f"{eq.iloc[-1] ** (1 / n) - 1:.1%}", "MDD(월말)": f"{dd.min():.1%}",
                 "전반 2008~16": f"{(1 + first).prod() ** (12 / len(first)) - 1:.1%}",
                 "후반 2017~": f"{(1 + second).prod() ** (12 / len(second)) - 1:.1%}"})
fig.update_yaxes(type="log", title="growth of $1", row=1, col=1)
fig.update_yaxes(title="drawdown %", row=2, col=1)
fig.update_layout(height=520, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", yanchor="bottom", y=1.02),
                  hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)")
st.plotly_chart(fig, width="stretch")
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
st.caption(
    "IC 연금형·BAA-G4(켈러 원본, ETF) = 월말 종가 전 체결·30bp, PENTARCH = 다음 날 체결·15bp. "
    "PENTARCH 비레버리지는 pentarch 의 사전등록 검증을 거친 운용 모델이 아니다(운용 v18.3 신호에서 레버리지 ETF 만 끔 — v18.3 = v18.2 + 주식·채권 상관 양수면 국채 제외, 2026-10-10). "
    "비중은 같은 기간 231개 조합 비교에서 고른 둥근 값 — 근처 비중과의 차이는 의미가 작다."
)

st.divider()
st.markdown("### 📚 종전 연구 — dual-momentum CSV (참고)")
st.caption(
    "아래 전략들의 'IC' 는 이 프로젝트 IC 가 아니라 금·나스닥·장기국채를 회전하는 변형이고, "
    "종전 화면의 BAA-G4·V8 현재 포지션은 단순 근사였다. 연구 기록으로만 남긴다."
)
# ── 전략 선택 ──
returns = ps.load_strategy_returns()

# 혼합 전략 수익률 계산
common12 = returns[["IC", "BAA-G4", "V8"]].dropna(how="any")
blend1 = 0.5 * common12["IC"] + 0.25 * common12["BAA-G4"] + 0.25 * common12["V8"]
common2 = returns[["IC", "V8"]].dropna(how="any")
blend2 = 0.7 * common2["IC"] + 0.3 * common2["V8"]

group_tab = st.radio(
    "전략 그룹",
    ["연금 혼합 전략", "동적 자산배분", "정적 자산배분"],
    horizontal=True,
)

if group_tab == "연금 혼합 전략":
    strategy_keys = ["전략1_IC50", "전략2_ICV8"]
    labels = {
        "전략1_IC50": "전략 1 · IC 50/25/25 (IC+BAA-G4+V8)",
        "전략2_ICV8": "전략 2 · IC+V8 70/30",
    }
    blend_map = {"전략1_IC50": blend1, "전략2_ICV8": blend2}
else:
    strategy_keys = ps.DYNAMIC_STRATEGIES if group_tab == "동적 자산배분" else ps.STATIC_STRATEGIES
    labels = {k: ps.STRATEGY_INFO[k]["name"] for k in strategy_keys}

selected = st.selectbox("전략 선택", strategy_keys, format_func=lambda k: labels[k])

if group_tab == "연금 혼합 전략":
    strat_ret = blend_map[selected].dropna()
    info = {
        "name": labels[selected],
        "group": "연금 혼합",
        "desc": ("IC 50% + BAA-G4 25% + V8 25% — CAGR 16.42%, MDD -18.9%, 최고 위험조정"
                 if selected == "전략1_IC50" else
                 "IC 70% + V8 30% — CAGR 17.13%, MDD -20.3%, 2중 혼합 중 최고 수익"),
    }
else:
    info = ps.STRATEGY_INFO[selected]
    strat_ret = returns[selected].dropna()

st.markdown(f"**{info['name']}** · {info['group']} 자산배분")
st.markdown(info["desc"])

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
        rdf_display = rdf[["CAGR", "MDD", "기간수익률", "Sharpe", "Calmar"]].agg(["mean", "median", "min", "max"]).T
        rdf_display.columns = ["평균", "중앙", "최소", "최대"]
        fmt = {
            "CAGR": lambda v: f"{v * 100:.2f}%",
            "MDD": lambda v: f"{v * 100:.2f}%",
            "기간수익률": lambda v: f"{v * 100:.2f}%",
            "Sharpe": lambda v: f"{v:.3f}",
            "Calmar": lambda v: f"{v:.3f}",
        }
        rdf_display = pd.DataFrame(
            {col: [fmt[idx](rdf_display.loc[idx, col]) for idx in rdf_display.index]
             for col in rdf_display.columns},
            index=rdf_display.index,
        )
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
