"""16개 조합 차트 — run_16_matrix_experiments.simulate(월별 모델·DTB3·30bp)와 data/matrix_16_results.csv 를 쓴다.

    python3 run_16_matrix_experiments.py && python3 generate_matrix_charts.py   # → matrix_16_combinations_chart.png
"""
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd

from run_16_matrix_experiments import simulate
from test_all_16_combinations import compute_signals, load_master_data

prices, t5yie, vix, baa10y, dtb3 = load_master_data()
df_signals, _ = compute_signals(prices, t5yie, vix, baa10y)
df_res = pd.read_csv("data/matrix_16_results.csv")
res = df_res.set_index("Model_ID")


def get_equity(p1, p2, p3, p4):
    return simulate(df_signals, prices, dtb3, p1, p2, p3, p4)["equity"]


def legend(mid, title):
    r = res.loc[mid]
    return f"{mid}: {title} [CAGR {r.CAGR:.1%}, MDD {r.MDD:.1%}, Calmar {r.Calmar:.3f}]"


eq_m00 = get_equity(0, 0, 0, 0)
eq_m02 = get_equity(0, 0, 1, 0)
eq_m08 = get_equity(1, 0, 0, 0)
eq_m10 = get_equity(1, 0, 1, 0)
eq_m03 = get_equity(0, 0, 1, 1)
eq_m15 = get_equity(1, 1, 1, 1)

plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
fig = plt.figure(figsize=(18, 12))

# 1. Cumulative Equity Curve (Log scale)
ax1 = plt.subplot2grid((2, 2), (0, 0), colspan=2)
ax1.plot(eq_m00.index, eq_m00, label=legend("M00", "Baseline (IC + fear-month leverage)"), color="#7f8c8d", lw=1.8, ls="--")
ax1.plot(eq_m02.index, eq_m02, label=legend("M02", "P3 Bond Shield (CONFIRMED)"), color="#3498db", lw=2.0)
ax1.plot(eq_m08.index, eq_m08, label=legend("M08", "P1 (Circuit Breaker, BAA10Y/VIX)"), color="#e67e22", lw=2.0)
ax1.plot(eq_m10.index, eq_m10, label=legend("M10", "P1+P3"), color="#9b59b6", lw=2.8)
ax1.plot(eq_m03.index, eq_m03, label=legend("M03", "P3+P4"), color="#2ecc71", lw=2.5)
ax1.plot(eq_m15.index, eq_m15, label=legend("M15", "P1+P2+P3+P4"), color="#e74c3c", lw=2.0)

ax1.set_yscale("log")
ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y:.0f}x"))
ax1.set_title("16 Combinatorial Models: Cumulative Asset Multiplier (2003 ~ 2026, Log Scale)", fontsize=14, fontweight="bold", pad=12)
ax1.set_ylabel("Asset Growth (x Initial)", fontsize=12)
ax1.legend(loc="upper left", frameon=True, fontsize=10)
ax1.grid(True, which="both", alpha=0.3)

# 2. Risk-Return Scatter: CAGR vs MDD
ax2 = plt.subplot2grid((2, 2), (1, 0))
scatter = ax2.scatter(
    df_res["MDD"] * 100,
    df_res["CAGR"] * 100,
    c=df_res["Sharpe"],
    s=df_res["Calmar"] * 160,
    cmap="viridis",
    alpha=0.85,
    edgecolors="black",
    linewidths=1.2,
)
cbar = plt.colorbar(scatter, ax=ax2)
cbar.set_label("Sharpe (excess over T-bill)", fontsize=11)

# Annotate key models
labels_map = {
    "M00": "M00 (Baseline)",
    "M01": "M01 (P4)",
    "M02": "M02 (P3)",
    "M03": "M03 (P3+P4)",
    "M08": "M08 (P1)",
    "M10": "M10 (P1+P3)",
    "M11": "M11 (P1+P3+P4)",
    "M15": "M15 (P1-P4 All)",
}

for _, row in df_res.iterrows():
    mid = row["Model_ID"]
    if mid in labels_map:
        ax2.annotate(
            labels_map[mid],
            (row["MDD"] * 100, row["CAGR"] * 100),
            xytext=(4, -4),
            textcoords="offset points",
            fontsize=9,
            fontweight="bold" if mid in ["M00", "M10", "M03"] else "normal",
        )

ax2.set_title("Risk-Return Tradeoff: CAGR vs MDD (Bubble Size = Calmar Ratio)", fontsize=13, fontweight="bold")
ax2.set_xlabel("Maximum Drawdown MDD (%) [Less Negative is Better]", fontsize=11)
ax2.set_ylabel("Compound Annual Growth Rate CAGR (%)", fontsize=11)
ax2.grid(True, alpha=0.3)

# 3. Crisis Resilience: 2008 Financial Crisis vs 2022 Inflation Shock MDD
ax3 = plt.subplot2grid((2, 2), (1, 1))
key_models = ["M00", "M01", "M02", "M03", "M08", "M10", "M11", "M15"]
df_sub = df_res[df_res["Model_ID"].isin(key_models)].copy()
x = np.arange(len(df_sub))
width = 0.35

rects1 = ax3.bar(x - width/2, df_sub["2008_MDD"] * 100, width, label="2008 Financial Crisis MDD", color="#e74c3c", alpha=0.85)
rects2 = ax3.bar(x + width/2, df_sub["2022_MDD"] * 100, width, label="2022 Inflation Shock MDD", color="#3498db", alpha=0.85)

ax3.set_title("Crisis Stress Test: 2008 vs 2022 Drawdown by Model", fontsize=13, fontweight="bold")
ax3.set_xticks(x)
ax3.set_xticklabels([labels_map[m] for m in df_sub["Model_ID"]], fontsize=8.5, rotation=15)
ax3.set_ylabel("Maximum Drawdown (%)", fontsize=11)
ax3.legend(loc="lower right", frameon=True, fontsize=10)
ax3.grid(True, alpha=0.3)

plt.tight_layout()
out_path = Path(__file__).parent / "matrix_16_combinations_chart.png"
plt.savefig(out_path, dpi=200, bbox_inches="tight")
print(f"Chart saved successfully: {out_path}")
