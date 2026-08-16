"""Research and quantitative simulation of CNN Fear & Greed overlay on Inflation Compass.

Compares:
  - Baseline Inflation Compass (David Varadi)
  - Strategy 1: Extreme Greed Trimmer (Overheating protection)
  - Strategy 2: Panic Defense (Asymmetric Bear-market capitulation protection)
  - Strategy 3: 3D Macro x Sentiment Matrix (8-regime state switching)
  - Strategy 4: Continuous Sentiment Beta Scaling (Linear/Sigmoid exposure)
  - Strategy 5: Tactical Sentiment Governor (Smart Beta overlay)
  - Strategy 6: Volatility-Targeted Sentiment Parity
"""

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "inflation_compass.db"

POS_BASKET = {"XLE": 0.5, "XLI": 1 / 6, "XLF": 1 / 6, "XLB": 1 / 6}
NEG_BASKET = {"XLU": 1 / 3, "XLV": 1 / 3, "XLP": 1 / 3}
TRANSACTION_COST_BP = 30  # 30 bp one-way


def load_all_data():
    conn = sqlite3.connect(DB_PATH)
    prices_long = pd.read_sql("SELECT date, ticker, close FROM prices", conn, parse_dates=["date"])
    t5yie_long = pd.read_sql("SELECT date, value FROM fred_series WHERE series_id='T5YIE'", conn, parse_dates=["date"])
    conn.close()

    prices = prices_long.pivot(index="date", columns="ticker", values="close").sort_index()
    t5yie = t5yie_long.set_index("date")["value"].sort_index().reindex(prices.index).ffill()

    # VIX and FRED HY OAS
    vix_raw = yf.download("^VIX", start="2000-01-01", auto_adjust=True, progress=False)["Close"].squeeze()
    vix = vix_raw.reindex(prices.index).ffill()

    hy_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAA10Y&cosd=1996-12-31"
    df_hy = pd.read_csv(hy_url, na_values=".").dropna()
    df_hy["date"] = pd.to_datetime(df_hy["observation_date"])
    hy_spread = df_hy.set_index("date")["BAA10Y"]
    hy_spread = hy_spread[~hy_spread.index.duplicated(keep="last")].reindex(prices.index).ffill()

    return prices, t5yie, vix, hy_spread


def rolling_slope(series, window=60):
    x = np.arange(window)
    x_mean = x.mean()
    denom = ((x - x_mean) ** 2).sum()

    def slope(y):
        return ((x - x_mean) * (y - y.mean())).sum() / denom

    return series.rolling(window).apply(slope, raw=True)


def compute_signals_and_fng(prices, t5yie, vix, hy_spread):
    returns = prices.pct_change()

    # Macro Signals (Growth & Inflation)
    spy_sma200 = prices["SPY"].rolling(200).mean()
    growth_on = prices["SPY"] > spy_sma200

    pos_ret = sum(returns[t] * w for t, w in POS_BASKET.items())
    neg_ret = sum(returns[t] * w for t, w in NEG_BASKET.items())
    basket_valid = pos_ret.notna() & neg_ret.notna()
    pos_cum = (1 + pos_ret.where(basket_valid, 0)).cumprod().where(basket_valid)
    neg_cum = (1 + neg_ret.where(basket_valid, 0)).cumprod().where(basket_valid)
    indicator = pos_cum / neg_cum
    slope = rolling_slope(indicator, 60)
    asset_momentum_on = slope > 0

    level_on = t5yie > 2.0
    t5yie_60_ago = t5yie.shift(60)
    breakeven_momentum_on = t5yie > t5yie_60_ago

    inflation_on = level_on & (breakeven_momentum_on | asset_momentum_on)

    # Synthetic Fear & Greed Index (4 Components, 252-day rolling rank)
    mom = (prices["SPY"] - prices["SPY"].rolling(125).mean()) / prices["SPY"].rolling(125).mean()
    score_mom = mom.rolling(252).rank(pct=True) * 100

    vol = (vix - vix.rolling(50).mean()) / vix.rolling(50).mean()
    score_vol = (1.0 - vol.rolling(252).rank(pct=True)) * 100

    safe_haven = prices["SPY"].pct_change(20) - prices["IEF"].pct_change(20)
    score_safe = safe_haven.rolling(252).rank(pct=True) * 100

    score_junk = (1.0 - hy_spread.rolling(252).rank(pct=True)) * 100

    fng = (score_mom + score_vol + score_safe + score_junk) / 4.0

    valid = spy_sma200.notna() & slope.notna() & t5yie.notna() & t5yie_60_ago.notna() & fng.notna()
    df_signals = pd.DataFrame({
        "growth_on": growth_on,
        "inflation_on": inflation_on,
        "fng": fng
    })[valid]

    return df_signals, returns


def run_strategy_backtest(df_signals, returns, allocation_fn, start_date="2003-03-31"):
    signals = df_signals.loc[start_date:].copy()
    ret = returns.loc[start_date:].copy()

    # Rebalance on month-end trading days
    month_ends = signals.groupby([signals.index.year, signals.index.month]).apply(lambda x: x.index[-1]).values
    month_ends = sorted(month_ends)

    # Weights DataFrame
    weights = pd.DataFrame(index=signals.index, columns=returns.columns).fillna(0.0)

    for i in range(len(month_ends) - 1):
        decision_dt = month_ends[i]
        next_me = month_ends[i + 1]

        row = signals.loc[decision_dt]
        w_dict = allocation_fn(bool(row["growth_on"]), bool(row["inflation_on"]), float(row["fng"]), decision_dt)

        # Holding period: from day after decision_dt up to next_me
        idx_slice = signals.loc[decision_dt:next_me].index[1:]
        for t, w in w_dict.items():
            weights.loc[idx_slice, t] = w

    # Calculate portfolio daily returns and turnover
    weights_clean = weights.loc[month_ends[0]:].copy()
    daily_gross_ret = (weights_clean.shift(1) * ret.loc[weights_clean.index]).sum(axis=1)

    # Turnover cost
    weight_diff = weights_clean.diff().abs().sum(axis=1)
    cost = weight_diff * (TRANSACTION_COST_BP / 10000.0)
    daily_net_ret = daily_gross_ret - cost

    equity = (1 + daily_net_ret).cumprod()
    n_years = len(daily_net_ret) / 252.0
    cagr = float(equity.iloc[-1] ** (1 / n_years) - 1)
    ann_vol = float(daily_net_ret.std() * np.sqrt(252))
    sharpe = cagr / ann_vol if ann_vol > 0 else 0.0

    peak = equity.cummax()
    dd = (equity - peak) / peak
    mdd = float(dd.min())
    calmar = cagr / abs(mdd) if abs(mdd) > 0 else 0.0

    # Key crisis drawdowns
    def sub_perf(s, e):
        s_dt = pd.to_datetime(s)
        e_dt = pd.to_datetime(e)
        sub_slice = equity.loc[s_dt:e_dt]
        if len(sub_slice) == 0:
            return 0.0, 0.0
        sub_peak = sub_slice.cummax()
        sub_mdd = float(((sub_slice - sub_peak) / sub_peak).min())
        return float(sub_slice.iloc[-1] / equity.loc[:s_dt].iloc[-1] - 1), sub_mdd

    ret_2008, mdd_2008 = sub_perf("2007-10-01", "2009-03-31")
    ret_2020, mdd_2020 = sub_perf("2020-01-01", "2020-04-30")
    ret_2022, mdd_2022 = sub_perf("2022-01-01", "2022-12-31")

    return {
        "CAGR": cagr,
        "Vol": ann_vol,
        "Sharpe": sharpe,
        "MDD": mdd,
        "Calmar": calmar,
        "2008_MDD": mdd_2008,
        "2020_MDD": mdd_2020,
        "2022_MDD": mdd_2022,
        "equity": equity
    }


# =========================================================================
# Strategy Definition Functions
# =========================================================================

# 0. Baseline Inflation Compass
def alloc_baseline(growth_on, inflation_on, fng, dt):
    if growth_on and inflation_on:
        return {"XLE": 1.0}
    elif growth_on and not inflation_on:
        return {"XLK": 1.0}
    elif not growth_on and inflation_on:
        return {"XLU": 1.0}
    else:
        return {"XLP": 0.5, "IEF": 0.5}


# 1. Extreme Greed Trimmer (Overheating Buffer)
def alloc_greed_trimmer(growth_on, inflation_on, fng, dt):
    base = alloc_baseline(growth_on, inflation_on, fng, dt)
    if fng > 80:
        # Scale equity by 0.75, put 25% into IEF
        res = {}
        for t, w in base.items():
            res[t] = w * 0.75
        res["IEF"] = res.get("IEF", 0.0) + 0.25
        return res
    return base


# 2. Panic Defense (Asymmetric Bear-market capitulation protection)
def alloc_panic_defense(growth_on, inflation_on, fng, dt):
    if not growth_on:
        # In Bear market: if extreme fear (<25), go 100% IEF
        if fng < 25:
            return {"IEF": 1.0}
        elif inflation_on:
            return {"XLU": 1.0}
        else:
            return {"XLP": 0.5, "IEF": 0.5}
    else:
        # In Bull market: if Extreme Greed (>80), trim 20% to IEF
        if fng > 80:
            if inflation_on:
                return {"XLE": 0.8, "IEF": 0.2}
            else:
                return {"XLK": 0.8, "IEF": 0.2}
        else:
            if inflation_on:
                return {"XLE": 1.0}
            else:
                return {"XLK": 1.0}


# 3. 3D Macro x Sentiment Matrix (8-Regime Full State Switching)
def alloc_3d_matrix(growth_on, inflation_on, fng, dt):
    is_greed = fng >= 50
    if growth_on:
        if inflation_on:
            return {"XLE": 1.0} if is_greed else {"XLE": 0.6, "XLB": 0.2, "XLI": 0.2}
        else:
            return {"XLK": 1.0} if is_greed else {"XLK": 0.7, "IEF": 0.3}
    else:
        if inflation_on:
            return {"XLU": 1.0} if is_greed else {"XLU": 0.6, "IEF": 0.4}
        else:
            if fng < 25:
                return {"IEF": 1.0}
            return {"XLP": 0.5, "IEF": 0.5}


# 4. Continuous Sentiment Beta Scaling
def alloc_continuous_scaling(growth_on, inflation_on, fng, dt):
    beta = float(np.clip(fng / 70.0, 0.40, 1.0))
    base = alloc_baseline(growth_on, inflation_on, fng, dt)
    res = {}
    for t, w in base.items():
        res[t] = w * beta
    res["IEF"] = res.get("IEF", 0.0) + (1.0 - beta)
    return res


# 7. Advanced Asymmetric Volatility-Sentiment Adaptive Overlay (AVSA)
def alloc_avsa(growth_on, inflation_on, fng, dt):
    # Bull Market (Growth ON):
    #  - If Euphoria (F&G > 78): Take-profit hedge -> 75% Sector + 25% IEF
    #  - Otherwise: 100% Sector (Buy-the-dip in bull trend)
    # Bear Market (Growth OFF):
    #  - If Extreme Panic (F&G < 25): 100% IEF (Crash escape)
    #  - If Stagflation (Inflation ON): 80% XLU + 20% IEF
    #  - If Deflationary recession: 40% XLP + 60% IEF
    if growth_on:
        target = "XLE" if inflation_on else "XLK"
        if fng >= 78:
            return {target: 0.75, "IEF": 0.25}
        else:
            return {target: 1.0}
    else:
        if fng < 25:
            return {"IEF": 1.0}
        elif inflation_on:
            return {"XLU": 0.8, "IEF": 0.2}
        else:
            return {"XLP": 0.4, "IEF": 0.6}


# 8. Contrarian Fear Dip-Buyer + Greed Exhaustion
def alloc_contrarian_greed_exhaustion(growth_on, inflation_on, fng, dt):
    if growth_on:
        target = "XLE" if inflation_on else "XLK"
        if fng >= 80:
            return {target: 0.70, "IEF": 0.30}
        elif fng <= 25:
            # Extreme dip in bull market: 100% high-beta
            return {target: 1.0}
        else:
            return {target: 0.90, "IEF": 0.10}
    else:
        if fng < 25:
            return {"IEF": 1.0}
        elif inflation_on:
            return {"XLU": 0.75, "IEF": 0.25}
        else:
            return {"XLP": 0.50, "IEF": 0.50}


# 9. Dynamic Triple-Tier (Threshold: 20 / 80)
def alloc_triple_tier(growth_on, inflation_on, fng, dt):
    if growth_on:
        target = "XLE" if inflation_on else "XLK"
        if fng > 80:
            return {target: 0.75, "IEF": 0.25}
        else:
            return {target: 1.0}
    else:
        if fng < 20:
            return {"IEF": 1.0}
        elif inflation_on:
            return {"XLU": 1.0}
        else:
            return {"XLP": 0.5, "IEF": 0.5}


def main():
    print("================================================================================")
    print("🌐 INFLATION COMPASS x FEAR & GREED QUANTITATIVE SIMULATION (2003 ~ 2026)")
    print("================================================================================")

    prices, t5yie, vix, hy_spread = load_all_data()
    df_signals, returns = compute_signals_and_fng(prices, t5yie, vix, hy_spread)

    strategies = {
        "0. Baseline (IC 원본)": alloc_baseline,
        "1. Extreme Greed Trimmer (과열 헤지)": alloc_greed_trimmer,
        "2. Panic Defense (약세장 공포 피난)": alloc_panic_defense,
        "3. 3D Regime Matrix (8국면 전환)": alloc_3d_matrix,
        "4. Continuous Beta Scaling (연속 스케일링)": alloc_continuous_scaling,
        "5. AVSA Adaptive Overlay (적응형 비대칭)": alloc_avsa,
        "6. Contrarian Dip + Exhaustion (역발상+과열)": alloc_contrarian_greed_exhaustion,
        "7. Dynamic Triple-Tier (20/80 3단)": alloc_triple_tier,
    }

    results = {}
    for name, fn in strategies.items():
        results[name] = run_strategy_backtest(df_signals, returns, fn)

    # Print Comparison Table
    df_res = pd.DataFrame({
        name: {
            "CAGR": f"{res['CAGR']*100:.2f}%",
            "Vol": f"{res['Vol']*100:.2f}%",
            "Sharpe": f"{res['Sharpe']:.3f}",
            "MDD": f"{res['MDD']*100:.2f}%",
            "Calmar": f"{res['Calmar']:.3f}",
            "2008 MDD": f"{res['2008_MDD']*100:.2f}%",
            "2020 MDD": f"{res['2020_MDD']*100:.2f}%",
            "2022 MDD": f"{res['2022_MDD']*100:.2f}%",
        }
        for name, res in results.items()
    }).T

    print("\n📊 종합 성과 비교표 (2003-03-31 ~ 2026-08-07, 거래비용 30bp 반영):")
    print(df_res.to_markdown())

    # SPY benchmark
    spy_ret = returns["SPY"].loc["2003-03-31":]
    spy_eq = (1 + spy_ret).cumprod()
    spy_cagr = spy_eq.iloc[-1] ** (252.0 / len(spy_ret)) - 1
    spy_vol = spy_ret.std() * np.sqrt(252)
    spy_mdd = ((spy_eq - spy_eq.cummax()) / spy_eq.cummax()).min()
    print(f"\n[참고] SPY (S&P 500) 벤치마크: CAGR {spy_cagr*100:.2f}% | Sharpe {spy_cagr/spy_vol:.3f} | MDD {spy_mdd*100:.2f}%")


if __name__ == "__main__":
    main()
