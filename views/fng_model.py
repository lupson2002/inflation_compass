"""Model C-1 Ultra · CNN Fear & Greed Dynamic Overlay Dashboard."""

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

st.title("🧠 Fear & Greed x Model C-1 Ultra")
st.caption("데이비드 바라디의 매크로 4국면 로테이션에 CNN 심리지수와 4개월 시차 레버리지(2.0x/0.5x)를 결합한 퀀트 전략")

prices, t5yie = backtest.load_data()
vix = yf.download("^VIX", start="2000-01-01", auto_adjust=True, progress=False)["Close"].squeeze().reindex(prices.index).ffill()
df_hy = pd.read_csv("https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAA10Y&cosd=1996-12-31", na_values=".").dropna()
df_hy["date"] = pd.to_datetime(df_hy["observation_date"])
hy_spread = df_hy.set_index("date")["BAA10Y"].reindex(prices.index).ffill()

pos = fng_engine.calculate_model_c1_ultra_position(prices, t5yie, vix, hy_spread)

# 1. Top KPI Cards
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("현재 F&G 점수", f"{pos['current_fng']:.1f}점", pos["current_rating_kr"])
with c2:
    st.metric("권장 노출 배수", f"{pos['exposure']}x", "Model C-1 Ultra")
with c3:
    st.metric("장기 CAGR (2003~26)", "29.07%", "+5.96%p vs 기준 IC")
with c4:
    st.metric("23.4년 누적 자산", "344.8배", "기준 IC 116.8배")

st.divider()

# 2. Real-time Action Guide
st.markdown("### ⚡ 오늘 시점 운용 가이드")
st.info(f"**💡 판단 근거:** {pos['action_reason']}  \n**🎯 최종 목표 포트폴리오:** `{fng_engine.get_base_dict(pos)}` (비중: `{pos['final_weights']}`)")

col_left, col_right = st.columns([1.5, 1])

with col_left:
    st.markdown("#### 📈 CNN Fear & Greed 역사적 시계열 (최근 2년)")
    s_fng = pos["fng_series"].loc["2022-01-01":]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(s_fng.index, s_fng.values, color="#2b6cb0", lw=1.5, label="Fear & Greed Index")
    ax.axhline(85, color="#e53e3e", linestyle="--", alpha=0.7, label="Extreme Greed (>85: 0.5x 익절)")
    ax.axhline(15, color="#38a169", linestyle="--", alpha=0.7, label="Extreme Fear (<15: 2.0x 레버리지)")
    ax.axhline(50, color="#a0aec0", linestyle=":", alpha=0.5)
    ax.fill_between(s_fng.index, 0, 15, color="#38a169", alpha=0.15)
    ax.fill_between(s_fng.index, 85, 100, color="#e53e3e", alpha=0.15)
    ax.set_ylim(0, 100)
    ax.set_ylabel("F&G Score")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    st.pyplot(fig)

with col_right:
    st.markdown("#### 🕹️ 4개월 공포 룩백 메모리")
    df_lags = pd.DataFrame({
        "시점": ["당월 (t0)", "전월 (t-1)", "전전월 (t-2)", "3달 전 (t-3)", "4달 전 (t-4)"],
        "F&G 점수": [f"{pos['t0_fng']:.1f}", f"{pos['t1_fng']:.1f}", f"{pos['t2_fng']:.1f}", f"{pos['t3_fng']:.1f}", f"{pos['t4_fng']:.1f}"],
        "공포 트리거": [
            "🚨 2.0배 발동" if pos["t0_fng"] < 15 else "정상",
            "건너뜀 (휩소 방어)" if pos["t1_fng"] < 15 else "정상",
            "🚨 2.0배 발동" if pos["t2_fng"] < 15 else "정상",
            "🚨 2.0배 (강세장 시)" if pos["t3_fng"] < 15 else "정상",
            "🚨 2.0배 (강세장 시)" if pos["t4_fng"] < 15 else "정상",
        ],
    })
    st.dataframe(df_lags, hide_index=True, use_container_width=True)

st.divider()

# 3. Strategy Comparison Table
st.markdown("### 📊 23.4년 장기 퀀트 백테스트 종합 성과 비교 (2003~2026)")
perf_data = [
    {"전략": "0. Baseline IC (1.0x 기준)", "CAGR": "23.11%", "23.4년 누적": "116.8배", "Sharpe": 1.192, "MDD": "-23.69%", "Calmar": 0.975, "2020s CAGR": "31.64%", "p-value": "-"},
    {"전략": "Model C (당월만 2.0x/0.5x)", "CAGR": "25.24%", "23.4년 누적": "172.9배", "Sharpe": 1.187, "MDD": "-25.75%", "Calmar": 0.980, "2020s CAGR": "36.00%", "p-value": "0.0392"},
    {"전략": "Model C-1 (t-2 반영)", "CAGR": "26.76%", "23.4년 누적": "228.0배", "Sharpe": 1.191, "MDD": "-25.75%", "Calmar": 1.039, "2020s CAGR": "39.41%", "p-value": "0.0053"},
    {"전략": "👑 Model C-1 Ultra (t-2~t-4 완성형)", "CAGR": "29.07%", "23.4년 누적": "344.8배", "Sharpe": 1.202, "MDD": "-25.75%", "Calmar": 1.129, "2020s CAGR": "44.09%", "p-value": "0.0007"},
]
st.dataframe(pd.DataFrame(perf_data), hide_index=True, use_container_width=True)

st.markdown(
    """
    > **💡 왜 4개월(t-4) 룩백이 최적 절정점(Peak)인가?**  
    > 극단적 패닉($F&G < 15$) 이후 시장은 평균 **16주(4개월)** 동안 가장 가파른 유동성 팽창 상승 랠리를 전개합니다.  
    > $t-4$까지 2.0배 레버리지를 유지하면 **Sharpe 1.202 / Calmar 1.129 / CAGR 29.07%로 전 지표가 역사적 최고점**을 기록하며, $t-5$ 이후로는 알파가 감쇠합니다.
    """
)
