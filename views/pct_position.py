"""Percentile Channels — 현재 포지션 페이지.

오늘 시점 4채널 신호 · composite · 비중을 실시간 계산하고,
이전 월말 결정과 비교한다. pct_backtest 모듈 재사용.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

import pct_backtest as pct

TICKER_KR = pct.TICKER_KR


def weights_str(weights):
    return " + ".join(f"{t} ({TICKER_KR.get(t, t)}) {w * 100:.0f}%" for t, w in weights.items() if w > 0)


def signal_tag(s):
    if s > 0:
        return ("🟢", "매수(+1)")
    if s < 0:
        return ("🔴", "매도(-1)")
    return ("⚪", "유지(0)")


st.markdown("<style>div.block-container { padding-top: 2.6rem; }</style>", unsafe_allow_html=True)

prices = pct.load_data()
starts = [prices[a].first_valid_index() for a in pct.ASSETS]
prices = prices.loc[max(starts):]

channel_signals, composite, vol20 = pct.compute_scores(prices)
positions = pct.build_positions(composite, vol20)

prev_d, prev_end, prev_weights, prev_comp = positions[-1]
last = prices.index[-1]

st.title("현재 포지션")

# ---- 이전 월말 결정 vs 오늘 시점 ----
col1, col2 = st.columns(2)

with col1:
    st.markdown(
        f"""
        <div style="background:#f7f8f4;border:1px solid #e1e0d9;border-radius:10px;padding:18px 20px">
        <div style="font-size:15px;font-weight:600;color:#16191a">📅 이전 월말 결정 ({prev_d.date()})</div>
        <div style="font-size:13px;color:#52564d;margin:6px 0 10px">보유기간 ~ {prev_end.date()}</div>
        <div style="font-size:20px;font-weight:700;color:#bb6b2c">{weights_str(prev_weights) or '현금(SHY) 100%'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# 오늘 시점 비중 (다음 월말 예정)
comp_today = {a: float(composite.loc[last, a]) for a in pct.ASSETS}
raw = {}
for a in pct.ASSETS:
    v = vol20.loc[last, a]
    inv = 1.0 / v if (v and v > 0 and not pd.isna(v)) else 0.0
    raw[a] = comp_today[a] * inv
tot = sum(abs(x) for x in raw.values())
today_weights = {a: 0.0 for a in pct.ASSETS}
if tot > 0:
    for a in pct.ASSETS:
        today_weights[a] = (abs(raw[a]) / tot) if comp_today[a] > 0 else 0.0
today_weights[pct.CASH] = 1.0 - sum(today_weights[a] for a in pct.ASSETS)

with col2:
    st.markdown(
        f"""
        <div style="background:#f7f8f4;border:1px solid #e1e0d9;border-radius:10px;padding:18px 20px">
        <div style="font-size:15px;font-weight:600;color:#16191a">🔄 오늘 시점 계산 ({last.date()})</div>
        <div style="font-size:13px;color:#52564d;margin:6px 0 10px">최신 데이터 기준 실시간 신호</div>
        <div style="font-size:20px;font-weight:700;color:#bb6b2c">{weights_str(today_weights) or '현금(SHY) 100%'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

changed = today_weights != prev_weights
st.info(
    "⚠️ 포지션이 변경됩니다 — 다음 월말 리밸런싱에 반영됩니다." if changed
    else "현재 포지션과 오늘 시점 신호가 동일합니다."
)

st.markdown("")
st.markdown("#### 채널별 신호 (오늘)")

rows = []
for a in pct.ASSETS:
    row = {"자산": f"{a} ({TICKER_KR[a]})"}
    for c in pct.CHANNELS:
        s = channel_signals[c].loc[last, a]
        row[f"{c}일"] = f"{s:+.0f}"
    row["Composite"] = f"{comp_today[a]:+.2f}"
    row["판정"] = "보유" if comp_today[a] > 0 else "제외(현금)"
    rows.append(row)
sig_df = pd.DataFrame(rows)
st.dataframe(sig_df, width="stretch", hide_index=True)

st.caption(
    "진입 = 가격이 75번째 백분위를 상향돌파(+1) · 이탈 = 25번째 백분위를 하향돌파(−1) · "
    "그 사이는 기존 신호 유지(히스테리시스). Composite = 4채널 평균, 0 초과면 보유."
)

st.markdown("")
st.markdown("#### 최근 3개월 채널 신호 변화")

recent = last - pd.Timedelta(days=130)
plot_rows = []
for a in pct.ASSETS:
    for c in pct.CHANNELS:
        series = channel_signals[c][a].loc[recent:]
        plot_rows.append(pd.DataFrame({"date": series.index, "channel": f"{c}일", "asset": a, "signal": series.values}))
plot_df = pd.concat(plot_rows)
pivot = plot_df.pivot_table(index="date", columns="asset", values="signal", aggfunc="mean")
if not pivot.empty:
    st.line_chart(pivot, height=280)

st.markdown("")
st.markdown("#### Composite 점수 추이 (최근 1년)")
comp_recent = composite.loc[last - pd.Timedelta(days=380):]
st.area_chart(comp_recent, height=280)

st.markdown("")
st.markdown("#### 현재 비중")
weight_df = pd.DataFrame({"자산": pct.ASSETS + [pct.CASH], "비중": [today_weights[a] for a in pct.ASSETS] + [today_weights[pct.CASH]]})
weight_df["비중%"] = weight_df["비중"] * 100
st.dataframe(weight_df[["자산", "비중%"]].style.format({"비중%": "{:.1f}%"}), width="stretch", hide_index=True)
