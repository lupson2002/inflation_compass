"""확정 전략 · IC 위험선호 지수 레버리지 오버레이 대시보드 (2026-10-09 개편)."""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent))

import backtest
import fng_engine

st.markdown("<style>div.block-container { padding-top: 2.6rem; }</style>", unsafe_allow_html=True)

st.title("🧠 확정 전략 · IC 위험선호 지수 오버레이")
st.caption("David Varadi 의 Inflation Compass 4국면 로테이션 + IC 위험선호 지수(4요소) 당월 극단값 레버리지(2.0x / 0.5x) + 침체 국면 채권방어")

prices, t5yie = backtest.load_data()
vix = yf.download("^VIX", start="2000-01-01", auto_adjust=True, progress=False)["Close"].squeeze().reindex(prices.index).ffill()
df_hy = pd.read_csv("https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAA10Y&cosd=1996-12-31", na_values=".").dropna()
df_hy["date"] = pd.to_datetime(df_hy["observation_date"])
hy_spread = df_hy.set_index("date")["BAA10Y"].reindex(prices.index).ffill()

pos = fng_engine.calculate_model_c1_ultra_position(prices, t5yie, vix, hy_spread)

# 1. Top KPI Cards
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric(f"{pos['index_name']} (신호)", f"{pos['current_fng']:.1f}점", pos["current_rating_kr"])
with c2:
    cnn = pos["cnn_score"]
    st.metric("참고: CNN Fear & Greed", f"{cnn:.1f}점" if cnn is not None else "조회 실패", pos["cnn_rating_kr"])
with c3:
    st.metric("권장 노출 배수", f"{pos['exposure']:.1f}x", "지수 < 15 → 2x · > 85 → 0.5x")
with c4:
    st.metric("확정 전략 CAGR (실거래 조건)", "19.5%", "MDD −20.2% · 2008 −14.9%")

st.divider()

# 2. Real-time Action Guide
st.markdown("### ⚡ 오늘 시점 운용 가이드")
st.info(f"**💡 판단 근거:** {pos['action_reason']}  \n**🎯 최종 목표 포트폴리오:** 기본 `{pos['base_weights']}` → 최종 `{pos['final_weights']}`")

st.markdown(f"#### 📈 {pos['index_name']} vs CNN Fear & Greed (2022~)")
s_idx = pos["fng_series"].loc["2022-01-01":]
fig, ax = plt.subplots(figsize=(12, 4))
ax.plot(s_idx.index, s_idx.values, color="#2b6cb0", lw=1.6, label="IC Risk Appetite Index (signal)")
if pos["cnn_series"] is not None:
    s_cnn = pos["cnn_series"].loc["2022-01-01":]
    ax.plot(s_cnn.index, s_cnn.values, color="#a0aec0", lw=1.0, alpha=0.9, label="CNN Fear & Greed (reference)")
ax.axhline(85, color="#e53e3e", linestyle="--", alpha=0.7, label="> 85: 0.5x")
ax.axhline(15, color="#38a169", linestyle="--", alpha=0.7, label="< 15: 2.0x")
ax.fill_between(s_idx.index, 0, 15, color="#38a169", alpha=0.12)
ax.fill_between(s_idx.index, 85, 100, color="#e53e3e", alpha=0.12)
ax.set_ylim(0, 100)
ax.legend(loc="upper left", fontsize=8, ncol=2)
fig.tight_layout()
st.pyplot(fig)
st.caption(
    "IC 위험선호 지수 = S&P 125일선 괴리 · VIX 50일선 괴리(역) · S&P−국채 20일 수익률 차 · BAA10Y 스프레드(역)의 1년 백분위 평균. "
    "CNN(7요소: 시장 폭·신고가·풋콜 포함)과 월말 상관 0.81이지만 극단 구간은 절반만 겹친다. 레버리지 규칙은 이 지수로 검증됐다."
)

st.divider()

# 3. Strategy Comparison Table
st.markdown("### 📊 (참고·종전) Model C 계열 백테스트 — 지연 공포 2배 포함")
perf_data = [
    {"전략": "0. Baseline IC (1.0x 기준)", "CAGR": "23.11%", "23.4년 누적": "116.8배", "Sharpe": 1.192, "MDD": "-23.69%", "Calmar": 0.975, "2020s CAGR": "31.64%", "p-value": "-"},
    {"전략": "Model C (당월만 2.0x/0.5x)", "CAGR": "25.24%", "23.4년 누적": "172.9배", "Sharpe": 1.187, "MDD": "-25.75%", "Calmar": 0.980, "2020s CAGR": "36.00%", "p-value": "0.0392"},
    {"전략": "Model C-1 (t-2 반영)", "CAGR": "26.76%", "23.4년 누적": "228.0배", "Sharpe": 1.191, "MDD": "-25.75%", "Calmar": 1.039, "2020s CAGR": "39.41%", "p-value": "0.0053"},
    {"전략": "👑 Model C-1 Ultra (t-2~t-4 완성형)", "CAGR": "29.07%", "23.4년 누적": "344.8배", "Sharpe": 1.202, "MDD": "-25.75%", "Calmar": 1.129, "2020s CAGR": "44.09%", "p-value": "0.0007"},
]
st.dataframe(pd.DataFrame(perf_data), hide_index=True, use_container_width=True)
st.caption(
    "⚠️ 위 표는 종전 비용 모델(차입 이자 = SHY 가격 수익률, 거래비용 없음)과 지연 공포 2배(t-2~t-4)를 쓴 과대평가 수치다. "
    "지연 공포 2배는 CNN 실지수 교차검증에서 MDD −39.5%(2026-05~07)로 무너져 제외했다. "
    "확정 전략(당월 지수 < 15 만 2배 · 침체 국면 1배 50/50, 2배 늘린 몫은 IEF · IEF < 200일선이면 SHY): "
    "연구 조건 CAGR 22.96% / MDD −24.47%, 실거래 조건(전일 FRED) 21.37% / −24.47% — matrix_16_combinations_evaluation_report.md"
)

st.markdown(
    """
    > **💡 왜 당월 공포만 2배인가? (2026-10-09)**
    > 공포 레버리지의 근거는 투매로 위험 프리미엄이 비싸진 순간에 사는 것이다 — 그 근거는 **당월**에만 있다.
    > 2~4개월 뒤엔 지수가 대개 정상으로 돌아와 있어, 할인 없는 가격에 업종 하나를 2배로 사는 셈이 된다.
    > "4개월"은 대리 지표로 기간을 훑어 고른 값이었고, CNN 실지수로 돌리면 MDD −39.5%(2026-05~07)로 무너졌다.
    > 당월 규칙은 두 지수 모두에서 MDD 가 레버리지 없을 때 수준(IC −22.9%, CNN −24.2%, 2011~)이다.
    """
)
