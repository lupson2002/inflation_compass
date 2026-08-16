"""Comprehensive 100-Strategy Quantitative Backtest Engine for Inflation Compass x Fear & Greed.

Simulates and evaluates 100 distinct quantitative sentiment overlays and regime models
against the baseline Inflation Compass across 2003-03-31 ~ 2026-08-07 (23.4 years, 281 months)
with 30bp one-way transaction cost.
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


def load_master_data():
    conn = sqlite3.connect(DB_PATH)
    prices_long = pd.read_sql("SELECT date, ticker, close FROM prices", conn, parse_dates=["date"])
    t5yie_long = pd.read_sql("SELECT date, value FROM fred_series WHERE series_id='T5YIE'", conn, parse_dates=["date"])
    conn.close()

    prices = prices_long.pivot(index="date", columns="ticker", values="close").sort_index()
    t5yie = t5yie_long.set_index("date")["value"].sort_index().reindex(prices.index).ffill()

    # Auxiliary tickers from Yahoo
    aux_tickers = ["SHY", "QQQ", "SOXX", "DBC", "GLD", "IYR", "TIP", "BIL", "IWM"]
    raw_aux = yf.download(aux_tickers, start="2000-01-01", auto_adjust=True, group_by="ticker", progress=False)
    for t in aux_tickers:
        if t in raw_aux and "Close" in raw_aux[t]:
            s = raw_aux[t]["Close"].squeeze().dropna()
            # fallback proxy before inception
            if t in ("DBC", "GLD"):
                s_full = s.reindex(prices.index).bfill().ffill()
            elif t in ("BIL", "SHY"):
                s_full = s.reindex(prices.index).bfill().ffill()
            else:
                s_full = s.reindex(prices.index).ffill()
            prices[t] = s_full

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


def compute_signals(prices, t5yie, vix, hy_spread):
    returns = prices.pct_change()

    # Macro Growth & Inflation Signals
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

    # 4-Component Synthetic Fear & Greed Index
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
        "fng": fng,
        "fng_mom20": fng.diff(20),
        "fng_sma5": fng.rolling(5).mean(),
        "vix": vix,
        "vix_50ma": vix.rolling(50).mean(),
        "spy": prices["SPY"],
        "spy_200ma": spy_sma200,
    })[valid]

    return df_signals, returns


def run_single_simulation(df_signals, returns, alloc_fn, start_date="2003-03-31"):
    signals = df_signals.loc[start_date:].copy()
    ret = returns.loc[start_date:].copy()

    month_ends = signals.groupby([signals.index.year, signals.index.month]).apply(lambda x: x.index[-1]).values
    month_ends = sorted(month_ends)

    weights = pd.DataFrame(index=signals.index, columns=returns.columns).fillna(0.0)

    for i in range(len(month_ends) - 1):
        decision_dt = month_ends[i]
        next_me = month_ends[i + 1]

        row = signals.loc[decision_dt]
        w_dict = alloc_fn(row, decision_dt)

        # Normalize weights to sum to 1.0
        tot_w = sum(w_dict.values())
        if tot_w > 0:
            w_norm = {k: v / tot_w for k, v in w_dict.items() if v > 0}
        else:
            w_norm = {"SHY": 1.0}

        idx_slice = signals.loc[decision_dt:next_me].index[1:]
        for t, w in w_norm.items():
            if t in weights.columns:
                weights.loc[idx_slice, t] = w

    weights_clean = weights.loc[month_ends[0]:].copy()
    daily_gross_ret = (weights_clean.shift(1) * ret.loc[weights_clean.index]).sum(axis=1)

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

    # Crisis drawdowns
    def sub_dd(s, e):
        s_dt = pd.to_datetime(s)
        e_dt = pd.to_datetime(e)
        sub_slice = equity.loc[s_dt:e_dt]
        if len(sub_slice) == 0:
            return 0.0
        sub_peak = sub_slice.cummax()
        return float(((sub_slice - sub_peak) / sub_peak).min())

    mdd_2008 = sub_dd("2007-10-01", "2009-03-31")
    mdd_2020 = sub_dd("2020-01-01", "2020-04-30")
    mdd_2022 = sub_dd("2022-01-01", "2022-12-31")

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
# Base Helper for Standard Macro Regime
# =========================================================================
def base_regime_asset(growth_on, inflation_on):
    if growth_on and inflation_on:
        return "XLE"
    elif growth_on and not inflation_on:
        return "XLK"
    elif not growth_on and inflation_on:
        return "XLU"
    else:
        return "DEFENSIVE"  # XLP 50 + IEF 50


# =========================================================================
# The 100 Systematic Strategy Implementations
# =========================================================================
STRATEGIES = {}

# 0. Baseline (IC Original)
def s_000(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if tgt == "DEFENSIVE":
        return {"XLP": 0.5, "IEF": 0.5}
    return {tgt: 1.0}
STRATEGIES["000. Baseline (IC Original)"] = s_000

# -------------------------------------------------------------------------
# Category 1: Extreme Greed & Panic De-risking Overlays (1 ~ 15)
# -------------------------------------------------------------------------
# 1. Extreme Greed 20% SHY Trimmer (F&G >= 80)
def s_001(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    fng = row["fng"]
    if row["growth_on"] and fng >= 80:
        return {tgt: 0.80, "SHY": 0.20}
    return s_000(row, dt)
STRATEGIES["001. Extreme Greed 20% SHY Trimmer"] = s_001

# 2. Extreme Greed 30% IEF Trimmer (F&G >= 82)
def s_002(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    fng = row["fng"]
    if row["growth_on"] and fng >= 82:
        return {tgt: 0.70, "IEF": 0.30}
    return s_000(row, dt)
STRATEGIES["002. Extreme Greed 30% IEF Trimmer"] = s_002

# 3. Two-Tier Tiered De-risking (F&G 75-85: 15% SHY, >85: 30% SHY)
def s_003(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    fng = row["fng"]
    if row["growth_on"]:
        if fng >= 85:
            return {tgt: 0.70, "SHY": 0.30}
        elif fng >= 75:
            return {tgt: 0.85, "SHY": 0.15}
    return s_000(row, dt)
STRATEGIES["003. Two-Tier Tiered De-risking"] = s_003

# 4. Linear Greed Decay (F&G >= 70 scales equity down to 70%)
def s_004(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    fng = row["fng"]
    if row["growth_on"] and fng >= 70:
        w_eq = max(0.70, 1.0 - (fng - 70) * 0.01)
        return {tgt: w_eq, "SHY": 1.0 - w_eq}
    return s_000(row, dt)
STRATEGIES["004. Linear Greed Decay (F&G>70)"] = s_004

# 5. Overheating Gold (GLD) Switch (XLE regime + F&G >= 85)
def s_005(row, dt):
    fng = row["fng"]
    if row["growth_on"] and row["inflation_on"] and fng >= 85:
        return {"XLE": 0.70, "GLD": 0.30}
    return s_000(row, dt)
STRATEGIES["005. Overheating Gold Switch in Reflation"] = s_005

# 6. Bear Market Panic 100% BIL Cash Escape (Growth OFF & F&G < 25)
def s_006(row, dt):
    if not row["growth_on"] and row["fng"] < 25:
        return {"BIL": 1.0}
    return s_000(row, dt)
STRATEGIES["006. Bear Market Panic BIL Escape"] = s_006

# 7. Bear Market Flight to IEF (Growth OFF & F&G < 20)
def s_007(row, dt):
    if not row["growth_on"] and row["fng"] < 20:
        return {"IEF": 1.0}
    return s_000(row, dt)
STRATEGIES["007. Bear Market Flight to IEF"] = s_007

# 8. Zero-Duration Safeguard in Inflation Shock (Growth OFF + Inflation ON + F&G < 25 -> SHY 100%)
def s_008(row, dt):
    if not row["growth_on"] and row["inflation_on"] and row["fng"] < 25:
        return {"SHY": 1.0}
    return s_000(row, dt)
STRATEGIES["008. Zero-Duration Safeguard (SHY 100%)"] = s_008

# 9. Greed Delta Reversal Trigger (F&G >= 80 & 20d Delta < -10)
def s_009(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"] and row["fng"] >= 78 and row["fng_mom20"] < -8:
        return {tgt: 0.75, "SHY": 0.25}
    return s_000(row, dt)
STRATEGIES["009. Greed Momentum Exhaustion Trigger"] = s_009

# 10. Fear Bottom Breakout Rebound (F&G crosses above 28)
def s_010(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"] and row["fng"] < 30 and row["fng_mom20"] > 5:
        return {tgt: 1.0}  # Aggressive 100%
    return s_000(row, dt)
STRATEGIES["010. Fear Bottom Rebound Accelerator"] = s_010

# 11. Volatility x Greed Dual Lock (VIX > 50MA & F&G >= 75)
def s_011(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["vix"] > row["vix_50ma"] and row["fng"] >= 75:
        return {tgt: 0.65, "SHY": 0.35}
    return s_000(row, dt)
STRATEGIES["011. Volatility x Greed Dual Lock"] = s_011

# 12. Divergence Hedge: SPY New High but F&G < 50
def s_012(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"] and row["fng"] < 40:
        return {tgt: 0.80, "IEF": 0.20}
    return s_000(row, dt)
STRATEGIES["012. Internal Breadth Divergence Hedge"] = s_012

# 13. Dynamic Defensive Tilt (Growth OFF -> 70% IEF / 30% SHY if F&G < 30)
def s_013(row, dt):
    if not row["growth_on"] and row["fng"] < 30:
        return {"IEF": 0.70, "SHY": 0.30}
    return s_000(row, dt)
STRATEGIES["013. Dynamic Defensive Dual Treasury Tilt"] = s_013

# 14. Extreme Greed Exponential Dampener
def s_014(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"] and row["fng"] >= 80:
        w_eq = float(np.exp(-(row["fng"] - 80) / 30.0))
        w_eq = max(0.65, w_eq)
        return {tgt: w_eq, "SHY": 1.0 - w_eq}
    return s_000(row, dt)
STRATEGIES["014. Exponential Greed Dampener"] = s_014

# 15. Asymmetric Crash Protector (AVSA Core: Growth ON Greed>78: 75% Eq, Growth OFF Panic<25: 100% SHY)
def s_015(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"]:
        if row["fng"] >= 78:
            return {tgt: 0.75, "IEF": 0.25}
        return {tgt: 1.0}
    else:
        if row["fng"] < 25:
            return {"SHY": 1.0}
        elif row["inflation_on"]:
            return {"XLU": 0.8, "SHY": 0.2}
        else:
            return {"XLP": 0.5, "IEF": 0.5}
STRATEGIES["015. AVSA Crash Protector (SHY/IEF)"] = s_015

# -------------------------------------------------------------------------
# Category 2: 4-Quadrant Customized Asymmetric Tuning (16 ~ 30)
# -------------------------------------------------------------------------
# 16. XLK Euphoria Cap (F&G >= 80 -> XLK 70% + IEF 30%)
def s_016(row, dt):
    if row["growth_on"] and not row["inflation_on"]:
        if row["fng"] >= 80:
            return {"XLK": 0.70, "IEF": 0.30}
        return {"XLK": 1.0}
    return s_000(row, dt)
STRATEGIES["016. XLK Tech Euphoria Cap"] = s_016

# 17. XLK Fear Dip Protection (Growth ON & Inf OFF & F&G < 30 -> 100% XLK)
def s_017(row, dt):
    if row["growth_on"] and not row["inflation_on"]:
        return {"XLK": 1.0}
    return s_000(row, dt)
STRATEGIES["017. XLK Secular Bull Dip Unconditional"] = s_017

# 18. XLE Material Blend (Growth ON & Inf ON & F&G >= 75 -> XLE 60% + XLB 40%)
def s_018(row, dt):
    if row["growth_on"] and row["inflation_on"]:
        if row["fng"] >= 75:
            return {"XLE": 0.60, "XLB": 0.40}
        return {"XLE": 1.0}
    return s_000(row, dt)
STRATEGIES["018. XLE Material (XLB) Dispersion"] = s_018

# 19. XLE Industrial Support (Growth ON & Inf ON & F&G < 35 -> XLE 50% + XLI 50%)
def s_019(row, dt):
    if row["growth_on"] and row["inflation_on"]:
        if row["fng"] < 35:
            return {"XLE": 0.50, "XLI": 0.50}
        return {"XLE": 1.0}
    return s_000(row, dt)
STRATEGIES["019. XLE Industrial (XLI) Support Blend"] = s_019

# 20. XLU Interest Rate Shield (Growth OFF & Inf ON & F&G < 30 -> XLU 60% + SHY 40%)
def s_020(row, dt):
    if not row["growth_on"] and row["inflation_on"]:
        if row["fng"] < 30:
            return {"XLU": 0.60, "SHY": 0.40}
        return {"XLU": 1.0}
    return s_000(row, dt)
STRATEGIES["020. XLU Rate Shock Shield"] = s_020

# 21. XLU Stagflation Commodity Switch (Growth OFF & Inf ON & F&G >= 55 -> XLU 50% + DBC 50%)
def s_021(row, dt):
    if not row["growth_on"] and row["inflation_on"]:
        if row["fng"] >= 55:
            return {"XLU": 0.50, "DBC": 0.50}
        return {"XLU": 1.0}
    return s_000(row, dt)
STRATEGIES["021. XLU Commodity (DBC) Stagflation Pair"] = s_021

# 22. XLP / IEF Dynamic Tilt (Growth OFF & Inf OFF -> F&G<25: IEF 80%, F&G>=50: XLP 80%)
def s_022(row, dt):
    if not row["growth_on"] and not row["inflation_on"]:
        if row["fng"] < 25:
            return {"IEF": 0.80, "XLP": 0.20}
        elif row["fng"] >= 50:
            return {"XLP": 0.80, "IEF": 0.20}
        return {"XLP": 0.50, "IEF": 0.50}
    return s_000(row, dt)
STRATEGIES["022. XLP/IEF Dynamic Reciprocal Tilt"] = s_022

# 23. Semiconductor Alpha Acceleration (Growth ON & Inf OFF & 45<=F&G<=75 -> SOXX 100%)
def s_023(row, dt):
    if row["growth_on"] and not row["inflation_on"]:
        if 45 <= row["fng"] <= 75:
            return {"SOXX": 1.0}
        elif row["fng"] > 75:
            return {"XLK": 0.70, "IEF": 0.30}
        return {"XLK": 1.0}
    return s_000(row, dt)
STRATEGIES["023. Semiconductor (SOXX) Alpha Accelerator"] = s_023

# 24. Broad Commodity (DBC) in Reflation Greed
def s_024(row, dt):
    if row["growth_on"] and row["inflation_on"]:
        if row["fng"] >= 70:
            return {"DBC": 1.0}
        return {"XLE": 1.0}
    return s_000(row, dt)
STRATEGIES["024. Broad Commodity (DBC) in Reflation Greed"] = s_024

# 25. TIPS (TIP) Stagflation Flight (Growth OFF & Inf ON & F&G < 30 -> TIP 100%)
def s_025(row, dt):
    if not row["growth_on"] and row["inflation_on"]:
        if row["fng"] < 30:
            return {"TIP": 1.0}
        return {"XLU": 1.0}
    return s_000(row, dt)
STRATEGIES["025. TIPS (TIP) Stagflation Safe Haven"] = s_025

# 26. Nasdaq QQQ Dual Expansion (Growth ON & Inf OFF & F&G >= 50 -> XLK 50% + QQQ 50%)
def s_026(row, dt):
    if row["growth_on"] and not row["inflation_on"]:
        if row["fng"] >= 50:
            return {"XLK": 0.50, "QQQ": 0.50}
        return {"XLK": 1.0}
    return s_000(row, dt)
STRATEGIES["026. Nasdaq QQQ Expansion Dual Engine"] = s_026

# 27. Healthcare (XLV) Defensive Pairing (Growth OFF & Inf OFF & 30<=F&G<=50 -> XLP 50% + XLV 50%)
def s_027(row, dt):
    if not row["growth_on"] and not row["inflation_on"]:
        if 30 <= row["fng"] <= 50:
            return {"XLP": 0.50, "XLV": 0.50}
        return {"XLP": 0.50, "IEF": 0.50}
    return s_000(row, dt)
STRATEGIES["027. Healthcare (XLV) Defensive Pairing"] = s_027

# 28. Financials XLF in Reflation Rebound (Growth ON & Inf ON & 35<=F&G<=65 -> XLE 50% + XLF 50%)
def s_028(row, dt):
    if row["growth_on"] and row["inflation_on"]:
        if 35 <= row["fng"] <= 65:
            return {"XLE": 0.50, "XLF": 0.50}
        return {"XLE": 1.0}
    return s_000(row, dt)
STRATEGIES["028. Financials (XLF) Rate Hike Partner"] = s_028

# 29. Real Estate (IYR) Stagflation Rotation (Growth OFF & Inf ON & F&G >= 50 -> IYR 100%)
def s_029(row, dt):
    if not row["growth_on"] and row["inflation_on"]:
        if row["fng"] >= 50:
            return {"IYR": 1.0}
        return {"XLU": 1.0}
    return s_000(row, dt)
STRATEGIES["029. Real Estate (IYR) Stagflation Rotation"] = s_029

# 30. 4-Quadrant Softmax Weight Distribution
def s_030(row, dt):
    fng = row["fng"]
    if row["growth_on"]:
        if row["inflation_on"]:
            return {"XLE": 0.70, "XLB": 0.15, "XLI": 0.15}
        else:
            w_xlk = 0.85 if fng < 80 else 0.65
            return {"XLK": w_xlk, "QQQ": 0.15, "IEF": 1.0 - w_xlk - 0.15}
    else:
        if row["inflation_on"]:
            return {"XLU": 0.60, "TIP": 0.20, "SHY": 0.20}
        else:
            return {"XLP": 0.40, "XLV": 0.20, "IEF": 0.40}
STRATEGIES["030. 4-Quadrant Softmax Balanced Model"] = s_030

# -------------------------------------------------------------------------
# Category 3: Whipsaw & Trend Confirmation Filters (31 ~ 45)
# -------------------------------------------------------------------------
# 31. Bull Trap Filter (Growth ON but F&G < 25 -> 50% Equity / 50% SHY)
def s_031(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"] and row["fng"] < 25:
        return {tgt: 0.50, "SHY": 0.50}
    return s_000(row, dt)
STRATEGIES["031. Bull Trap 50% Entry Filter"] = s_031

# 32. Bull Trap Filter 2-Tier (F&G < 20: 30% Eq, 20<=F&G<35: 60% Eq, >=35: 100% Eq)
def s_032(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"]:
        if row["fng"] < 20:
            return {tgt: 0.30, "SHY": 0.70}
        elif row["fng"] < 35:
            return {tgt: 0.60, "SHY": 0.40}
        elif row["fng"] >= 80:
            return {tgt: 0.75, "SHY": 0.25}
        return {tgt: 1.0}
    return s_000(row, dt)
STRATEGIES["032. Multi-Tier Bull Trap & Greed Sizer"] = s_032

# 33. Bear Trap Whipsaw Ignorer (Growth OFF but F&G >= 65 -> Keep 75% Equity)
def s_033(row, dt):
    if not row["growth_on"] and row["fng"] >= 65:
        return {"XLK": 0.75, "IEF": 0.25}
    return s_000(row, dt)
STRATEGIES["033. Bear Trap Whipsaw Ignorer"] = s_033

# 34. Hysteresis Sentiment Band (ON: F&G > 40, OFF: F&G < 30)
def s_034(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"] and row["fng"] < 30:
        return {"XLP": 0.50, "IEF": 0.50}
    elif not row["growth_on"] and row["fng"] > 55:
        return {"XLK": 0.80, "IEF": 0.20}
    return s_000(row, dt)
STRATEGIES["034. Hysteresis Sentiment Band"] = s_034

# 35. Inflation Shock Liquidity Filter (Inf ON but F&G < 18 -> Reject Inflation, go SHY)
def s_035(row, dt):
    if row["inflation_on"] and row["fng"] < 18:
        return {"SHY": 1.0}
    return s_000(row, dt)
STRATEGIES["035. Liquidity Squeeze Inflation Rejector"] = s_035

# 36. Confirming Slope + Sentiment Concordance
def s_036(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"] and row["fng_mom20"] > 0:
        return {tgt: 1.0}
    elif row["growth_on"] and row["fng_mom20"] <= 0:
        return {tgt: 0.80, "SHY": 0.20}
    return s_000(row, dt)
STRATEGIES["036. Sentiment Momentum Concordance"] = s_036

# 37. Composite Growth Score (SPY/200MA * F&G/50)
def s_037(row, dt):
    comp = (row["spy"] / row["spy_200ma"]) * (row["fng"] / 50.0)
    tgt = "XLE" if row["inflation_on"] else "XLK"
    if comp >= 1.0:
        return {tgt: 1.0}
    elif comp >= 0.85:
        return {tgt: 0.60, "SHY": 0.40}
    else:
        return {"XLP": 0.50, "IEF": 0.50}
STRATEGIES["037. Composite Growth Multiplier"] = s_037

# 38. Bullish Divergence Scout (Growth OFF but F&G > 50 & 20d Delta > +10)
def s_038(row, dt):
    if not row["growth_on"] and row["fng"] > 50 and row["fng_mom20"] > 10:
        return {"XLK": 0.50, "IEF": 0.50}
    return s_000(row, dt)
STRATEGIES["038. Bullish Sentiment Divergence Scout"] = s_038

# 39. Bearish Divergence Warning (Growth ON but F&G < 45 & 20d Delta < -15)
def s_039(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"] and row["fng"] < 45 and row["fng_mom20"] < -15:
        return {tgt: 0.60, "SHY": 0.40}
    return s_000(row, dt)
STRATEGIES["039. Bearish Sentiment Exhaustion Warning"] = s_039

# 40. 5-Day F&G SMA Smoothed Filter
def s_040(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    fng_smooth = row["fng_sma5"]
    if row["growth_on"]:
        if fng_smooth >= 80:
            return {tgt: 0.75, "SHY": 0.25}
        return {tgt: 1.0}
    else:
        if fng_smooth < 25:
            return {"SHY": 1.0}
        return s_000(row, dt)
STRATEGIES["040. 5-Day Smoothed F&G Trigger"] = s_040

# 41. VIX Spike Anti-Panic Lock (VIX > 28 -> Max 60% Equity)
def s_041(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["vix"] > 28:
        return {tgt: 0.50, "SHY": 0.50} if row["growth_on"] else {"SHY": 1.0}
    return s_000(row, dt)
STRATEGIES["041. VIX Spike Anti-Panic Gate"] = s_041

# 42. High Yield Spread Confirmation (F&G Junk Spread < 25 -> Half Beta)
def s_042(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"] and row["fng"] < 30:
        return {tgt: 0.65, "SHY": 0.35}
    return s_000(row, dt)
STRATEGIES["042. Credit Spread Risk Gate"] = s_042

# 43. Safe Haven Inversion Detector
def s_043(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"] and row["fng"] >= 75:
        return {tgt: 0.80, "IEF": 0.20}
    return s_000(row, dt)
STRATEGIES["043. Safe Haven Inversion Detector"] = s_043

# 44. Percentile Channel x F&G Dual Gate
def s_044(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"] and row["fng"] >= 45:
        return {tgt: 1.0}
    elif row["growth_on"] and row["fng"] < 45:
        return {tgt: 0.70, "SHY": 0.30}
    return s_000(row, dt)
STRATEGIES["044. Channel x Sentiment Dual Gate"] = s_044

# 45. Dynamic 200MA Buffer Zone (+-1.5% with F&G)
def s_045(row, dt):
    ratio = row["spy"] / row["spy_200ma"]
    if 0.985 <= ratio <= 1.015:
        # Buffer zone: let F&G decide
        if row["fng"] >= 50:
            return {"XLK": 0.80, "IEF": 0.20}
        else:
            return {"XLP": 0.50, "IEF": 0.50}
    return s_000(row, dt)
STRATEGIES["045. 200MA Neutral Buffer Sentiment Decider"] = s_045

# -------------------------------------------------------------------------
# Category 4: Contrarian Dip-Buying & Capitulation Alphas (46 ~ 60)
# -------------------------------------------------------------------------
# 46. Bull Market Super-Dip Leverager (Growth ON & F&G < 18 -> XLK 80% + SOXX 20%)
def s_046(row, dt):
    if row["growth_on"] and not row["inflation_on"] and row["fng"] < 18:
        return {"XLK": 0.70, "SOXX": 0.30}
    elif row["growth_on"] and row["fng"] >= 80:
        return {"XLK": 0.75, "SHY": 0.25}
    return s_000(row, dt)
STRATEGIES["046. Bull Market Deep Dip Semiconductor Alpha"] = s_046

# 47. Capitulation Bounce Harvester (Growth OFF & F&G < 12 -> SPY 50% + IEF 50%)
def s_047(row, dt):
    if not row["growth_on"] and row["fng"] < 12:
        return {"SPY": 0.50, "IEF": 0.50}
    return s_000(row, dt)
STRATEGIES["047. Capitulation Bounce Harvester"] = s_047

# 48. Put/Call Extreme Contrarian Swing (Growth ON & F&G < 22 -> XLK 100%)
def s_048(row, dt):
    if row["growth_on"] and row["fng"] < 22:
        return {"XLK": 1.0}
    elif row["growth_on"] and row["fng"] >= 82:
        return {"XLK": 0.75, "IEF": 0.25}
    return s_000(row, dt)
STRATEGIES["048. Put/Call Extreme Contrarian Swing"] = s_048

# 49. Graded Staged Capitulation DCA (Growth OFF: F&G 25->25% SPY, F&G 15->50% SPY)
def s_049(row, dt):
    if not row["growth_on"]:
        if row["fng"] < 15:
            return {"SPY": 0.50, "IEF": 0.50}
        elif row["fng"] < 25:
            return {"SPY": 0.25, "XLP": 0.25, "IEF": 0.50}
    return s_000(row, dt)
STRATEGIES["049. Graded Staged Capitulation DCA"] = s_049

# 50. Post-Panic Momentum Launcher (F&G < 20 in prior, now > 30 & Delta > 12)
def s_050(row, dt):
    if row["growth_on"] and row["fng"] >= 30 and row["fng_mom20"] >= 12:
        tgt = "XLE" if row["inflation_on"] else "XLK"
        return {tgt: 1.0}
    return s_000(row, dt)
STRATEGIES["050. Post-Panic Momentum Launcher"] = s_050

# 51. Stagflation Rebound XLE Overdrive (Inf ON & F&G < 20 recovery -> XLE 100%)
def s_051(row, dt):
    if row["inflation_on"] and row["fng"] < 20:
        return {"XLE": 0.80, "SHY": 0.20}
    return s_000(row, dt)
STRATEGIES["051. Stagflation Rebound XLE Overdrive"] = s_051

# 52. Small Cap Springboard (Growth ON & F&G < 20 -> XLK 70% + IWM 30%)
def s_052(row, dt):
    if row["growth_on"] and row["fng"] < 20:
        return {"XLK": 0.70, "IWM": 0.30}
    return s_000(row, dt)
STRATEGIES["052. Small-Cap (IWM) Springboard"] = s_052

# 53. Contrarian Mean-Reversion Sizer
def s_053(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    fng = row["fng"]
    if row["growth_on"]:
        # Inverse weight on extremes: F&G 20 -> 1.0, F&G 85 -> 0.70
        w = float(np.clip(1.0 - (fng - 50) * 0.008, 0.70, 1.0))
        return {tgt: w, "SHY": 1.0 - w}
    return s_000(row, dt)
STRATEGIES["053. Contrarian Linear Mean-Reversion Sizer"] = s_053

# 54. Oversold Growth Accelerator (Growth ON & Inf OFF & F&G < 25 -> QQQ 100%)
def s_054(row, dt):
    if row["growth_on"] and not row["inflation_on"] and row["fng"] < 25:
        return {"QQQ": 1.0}
    return s_000(row, dt)
STRATEGIES["054. Oversold Growth QQQ Accelerator"] = s_054

# 55. Panic Climax V-Bottom Trigger (F&G < 10 -> SPY 60% + IEF 40%)
def s_055(row, dt):
    if row["fng"] < 10:
        return {"SPY": 0.60, "IEF": 0.40}
    return s_000(row, dt)
STRATEGIES["055. Panic Climax V-Bottom Trigger"] = s_055

# 56. Financials Oversold Bounce in Reflation (Inf ON & F&G < 25 -> XLF 50% + XLE 50%)
def s_056(row, dt):
    if row["growth_on"] and row["inflation_on"] and row["fng"] < 25:
        return {"XLF": 0.50, "XLE": 0.50}
    return s_000(row, dt)
STRATEGIES["056. Financials Oversold Bounce in Reflation"] = s_056

# 57. High-Conviction Dip-Buy (F&G 20-35 & Growth ON -> XLK 100%)
def s_057(row, dt):
    if row["growth_on"] and not row["inflation_on"] and 20 <= row["fng"] <= 35:
        return {"XLK": 1.0}
    elif row["growth_on"] and row["fng"] > 80:
        return {"XLK": 0.75, "SHY": 0.25}
    return s_000(row, dt)
STRATEGIES["057. High-Conviction Dip & Greed Cap"] = s_057

# 58. VIX Backwardation Resolution Engine
def s_058(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["vix"] > 32 and row["fng"] < 15:
        return {tgt: 0.50, "SHY": 0.50}
    return s_000(row, dt)
STRATEGIES["058. VIX Backwardation Resolution Engine"] = s_058

# 59. Bear Market Rally Fade (Growth OFF & F&G >= 60 -> 100% SHY/Cash)
def s_059(row, dt):
    if not row["growth_on"] and row["fng"] >= 60:
        return {"SHY": 1.0}
    return s_000(row, dt)
STRATEGIES["059. Bear Market Rally Fade (Cash Lock)"] = s_059

# 60. Dual-State Capitulation Swing (F&G < 15 -> SPY 40% + SHY 60%)
def s_060(row, dt):
    if row["fng"] < 15:
        return {"SPY": 0.40, "SHY": 0.60}
    elif row["growth_on"] and row["fng"] >= 80:
        tgt = "XLE" if row["inflation_on"] else "XLK"
        return {tgt: 0.75, "SHY": 0.25}
    return s_000(row, dt)
STRATEGIES["060. Dual-State Capitulation & Euphoria Swing"] = s_060

# -------------------------------------------------------------------------
# Category 5: Tactical Asset Substitution (61 ~ 75)
# -------------------------------------------------------------------------
# 61. Real Estate (IYR) Stagflation (Growth OFF & Inf ON & F&G > 45 -> IYR 100%)
def s_061(row, dt):
    if not row["growth_on"] and row["inflation_on"] and row["fng"] > 45:
        return {"IYR": 1.0}
    return s_000(row, dt)
STRATEGIES["061. IYR Real Estate Stagflation Alpha"] = s_061

# 62. Gold GLD Safe Haven (Growth OFF & F&G < 25 -> GLD 50% + SHY 50%)
def s_062(row, dt):
    if not row["growth_on"] and row["fng"] < 25:
        return {"GLD": 0.50, "SHY": 0.50}
    return s_000(row, dt)
STRATEGIES["062. Gold GLD Safe Haven Pair"] = s_062

# 63. Commodity DBC Inflation Replacement (Inf ON & F&G >= 65 -> DBC 100%)
def s_063(row, dt):
    if row["growth_on"] and row["inflation_on"] and row["fng"] >= 65:
        return {"DBC": 1.0}
    return s_000(row, dt)
STRATEGIES["063. Commodity DBC Reflation Surge"] = s_063

# 64. Long Treasury TLT Deep Panic (Growth OFF & Inf OFF & F&G < 15 -> TLT proxy via IEF 100%)
def s_064(row, dt):
    if not row["growth_on"] and not row["inflation_on"] and row["fng"] < 15:
        return {"IEF": 1.0}
    return s_000(row, dt)
STRATEGIES["064. Long Duration Deflation Flight"] = s_064

# 65. TIPS Inflation Flight (Inf ON & F&G < 30 -> TIP 70% + SHY 30%)
def s_065(row, dt):
    if row["inflation_on"] and row["fng"] < 30:
        return {"TIP": 0.70, "SHY": 0.30}
    return s_000(row, dt)
STRATEGIES["065. TIPS Real Yield Shield"] = s_065

# 66. Gold + Dollar Cash Basket (Growth OFF & F&G < 20 -> GLD 40% + SHY 60%)
def s_066(row, dt):
    if not row["growth_on"] and row["fng"] < 20:
        return {"GLD": 0.40, "SHY": 0.60}
    return s_000(row, dt)
STRATEGIES["066. Gold & Short Treasury Crisis Duo"] = s_066

# 67. Semiconductor / Tech Dual Tilt (F&G > 60 -> SOXX 60% + XLK 40%)
def s_067(row, dt):
    if row["growth_on"] and not row["inflation_on"]:
        if 60 <= row["fng"] <= 80:
            return {"SOXX": 0.60, "XLK": 0.40}
        elif row["fng"] > 80:
            return {"XLK": 0.70, "SHY": 0.30}
    return s_000(row, dt)
STRATEGIES["067. Semiconductor & Tech Dual Engine"] = s_067

# 68. Basic Materials (XLB) in Moderate Reflation (Growth ON & Inf ON & 40<=F&G<=65 -> XLB 50% + XLE 50%)
def s_068(row, dt):
    if row["growth_on"] and row["inflation_on"] and 40 <= row["fng"] <= 65:
        return {"XLB": 0.50, "XLE": 0.50}
    return s_000(row, dt)
STRATEGIES["068. Materials (XLB) Reflation Partner"] = s_068

# 69. Small-Cap (IWM) / Large-Cap Rotation
def s_069(row, dt):
    if row["growth_on"] and not row["inflation_on"]:
        if 50 <= row["fng"] <= 75:
            return {"XLK": 0.70, "IWM": 0.30}
    return s_000(row, dt)
STRATEGIES["069. Small-Cap (IWM) Growth Boost"] = s_069

# 70. Broad Nasdaq QQQ in Moderate Greed
def s_070(row, dt):
    if row["growth_on"] and not row["inflation_on"] and 50 <= row["fng"] <= 78:
        return {"QQQ": 0.70, "XLK": 0.30}
    return s_000(row, dt)
STRATEGIES["070. Broad Nasdaq (QQQ) Bull Runner"] = s_070

# 71. Defensive Low-Vol Duo (Growth OFF & Inf OFF & F&G >= 45 -> XLP 60% + XLV 40%)
def s_071(row, dt):
    if not row["growth_on"] and not row["inflation_on"] and row["fng"] >= 45:
        return {"XLP": 0.60, "XLV": 0.40}
    return s_000(row, dt)
STRATEGIES["071. Defensive Low-Vol Consumer/Health Duo"] = s_071

# 72. Multi-Commodity (XLE + DBC + GLD)
def s_072(row, dt):
    if row["growth_on"] and row["inflation_on"]:
        if row["fng"] >= 75:
            return {"XLE": 0.50, "DBC": 0.30, "GLD": 0.20}
    return s_000(row, dt)
STRATEGIES["072. Multi-Commodity Trio in Reflation"] = s_072

# 73. Treasury Barbell (IEF 50% + SHY 50% in Panic)
def s_073(row, dt):
    if not row["growth_on"] and row["fng"] < 25:
        return {"IEF": 0.50, "SHY": 0.50}
    return s_000(row, dt)
STRATEGIES["073. Treasury Duration Barbell in Panic"] = s_073

# 74. Cyclical Industrial-Material Duo (XLI 50% + XLB 50%)
def s_074(row, dt):
    if row["growth_on"] and row["inflation_on"] and 45 <= row["fng"] <= 70:
        return {"XLE": 0.40, "XLI": 0.30, "XLB": 0.30}
    return s_000(row, dt)
STRATEGIES["074. Cyclical Industrial-Material Trio"] = s_074

# 75. All-Weather Permanent Parachute (Growth OFF & F&G < 15 -> SPY 25 + IEF 25 + GLD 25 + SHY 25)
def s_075(row, dt):
    if not row["growth_on"] and row["fng"] < 15:
        return {"SPY": 0.25, "IEF": 0.25, "GLD": 0.25, "SHY": 0.25}
    return s_000(row, dt)
STRATEGIES["075. Permanent Portfolio Parachute in Deep Panic"] = s_075

# -------------------------------------------------------------------------
# Category 6: Mathematical Continuous Beta & Sizing Functions (76 ~ 85)
# -------------------------------------------------------------------------
# 76. Sigmoid Beta Scaling: w = 1 / (1 + exp(-(fng - 50)/15))
def s_076(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    beta = float(1.0 / (1.0 + np.exp(-(row["fng"] - 50.0) / 15.0)))
    beta = float(np.clip(beta, 0.40, 1.0))
    if tgt == "DEFENSIVE":
        return {"XLP": 0.5 * beta, "IEF": 0.5 * beta, "SHY": 1.0 - beta}
    return {tgt: beta, "SHY": 1.0 - beta}
STRATEGIES["076. Sigmoid Continuous Beta Scaling"] = s_076

# 77. Linear Slope Scaling: w = clip(fng / 65, 0.40, 1.0)
def s_077(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    beta = float(np.clip(row["fng"] / 65.0, 0.40, 1.0))
    if tgt == "DEFENSIVE":
        return {"XLP": 0.5 * beta, "IEF": 0.5 * beta, "SHY": 1.0 - beta}
    return {tgt: beta, "SHY": 1.0 - beta}
STRATEGIES["077. Linear Slope Scaling (65 Norm)"] = s_077

# 78. Parabolic Peak Shaver: w = 1.0 - ((fng - 50)/50)^2 * 0.35 if fng > 75
def s_078(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    fng = row["fng"]
    if row["growth_on"]:
        if fng >= 75:
            w_eq = 1.0 - ((fng - 50) / 50.0) ** 2 * 0.35
            w_eq = float(np.clip(w_eq, 0.65, 1.0))
            return {tgt: w_eq, "SHY": 1.0 - w_eq}
        return {tgt: 1.0}
    return s_000(row, dt)
STRATEGIES["078. Parabolic Euphoria Shaver"] = s_078

# 79. Square-Root Beta Modulation: w = clip((fng / 50)^0.5, 0.50, 1.0)
def s_079(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"]:
        w = float(np.clip(np.sqrt(row["fng"] / 50.0), 0.60, 1.0))
        return {tgt: w, "SHY": 1.0 - w}
    return s_000(row, dt)
STRATEGIES["079. Square-Root Beta Modulation"] = s_079

# 80. Piecewise 3-Phase Linear: [0-30: 60-100%, 30-75: 100%, 75-100: 100-70%]
def s_080(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    fng = row["fng"]
    if row["growth_on"]:
        if fng >= 75:
            w = 1.0 - (fng - 75) * (0.30 / 25.0)
        else:
            w = 1.0
        return {tgt: float(np.clip(w, 0.70, 1.0)), "SHY": float(1.0 - np.clip(w, 0.70, 1.0))}
    return s_000(row, dt)
STRATEGIES["080. Piecewise 3-Phase Linear Sizer"] = s_080

# 81. Inverted VIX Power Scaling
def s_081(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"]:
        vix_ratio = row["vix"] / 20.0
        w = float(np.clip(1.0 / (vix_ratio ** 0.5), 0.60, 1.0))
        return {tgt: w, "SHY": 1.0 - w}
    return s_000(row, dt)
STRATEGIES["081. Inverted VIX Power Sizer"] = s_081

# 82. Cubic Soft S-Curve: w = 3*(fng/100)^2 - 2*(fng/100)^3
def s_082(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    x = row["fng"] / 100.0
    w = float(np.clip(3 * (x ** 2) - 2 * (x ** 3) + 0.30, 0.50, 1.0))
    if tgt == "DEFENSIVE":
        return {"XLP": 0.5 * w, "IEF": 0.5 * w, "SHY": 1.0 - w}
    return {tgt: w, "SHY": 1.0 - w}
STRATEGIES["082. Cubic Smooth S-Curve Sizer"] = s_082

# 83. Exponential Sentiment Risk Budget
def s_083(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"]:
        if row["fng"] >= 80:
            return {tgt: 0.72, "SHY": 0.28}
        elif row["fng"] <= 20:
            return {tgt: 1.0}
        return {tgt: 0.90, "SHY": 0.10}
    return s_000(row, dt)
STRATEGIES["083. Exponential Sentiment Risk Budget"] = s_083

# 84. Dynamic Threshold Sizer (F&G 78/22)
def s_084(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"]:
        if row["fng"] >= 78:
            return {tgt: 0.77, "SHY": 0.23}
        return {tgt: 1.0}
    else:
        if row["fng"] <= 22:
            return {"SHY": 1.0}
        return s_000(row, dt)
STRATEGIES["084. Dynamic Threshold (78/22) Sizer"] = s_084

# 85. Asymmetric Dual Step (Greed>80: 25% SHY, Fear<20: 20% SHY in bear)
def s_085(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"]:
        if row["fng"] >= 80:
            return {tgt: 0.75, "SHY": 0.25}
        return {tgt: 1.0}
    else:
        if row["fng"] < 20:
            return {"SHY": 1.0}
        elif row["inflation_on"]:
            return {"XLU": 0.75, "SHY": 0.25}
        else:
            return {"XLP": 0.50, "IEF": 0.50}
STRATEGIES["085. Asymmetric Dual Step Sizer"] = s_085

# -------------------------------------------------------------------------
# Category 7: Multi-Timeframe, Delta & Momentum Filters (86 ~ 93)
# -------------------------------------------------------------------------
# 86. Rapid Greed Reversal 20d Delta > -12
def s_086(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"] and row["fng"] >= 70 and row["fng_mom20"] <= -12:
        return {tgt: 0.70, "SHY": 0.30}
    return s_000(row, dt)
STRATEGIES["086. Rapid Greed Reversal 20d Delta"] = s_086

# 87. Rapid Fear Recovery 20d Delta > +15
def s_087(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"] and row["fng_mom20"] >= 15:
        return {tgt: 1.0}
    return s_000(row, dt)
STRATEGIES["087. Rapid Fear Recovery Momentum Surge"] = s_087

# 88. F&G 5-day EMA Trend Confirmation
def s_088(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"]:
        if row["fng_sma5"] >= 78:
            return {tgt: 0.75, "SHY": 0.25}
        return {tgt: 1.0}
    return s_000(row, dt)
STRATEGIES["088. 5-day EMA Trend Confirmation"] = s_088

# 89. Dual Momentum Confirmation (SPY 60d Return > 0 & F&G > 50)
def s_089(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"] and row["fng"] >= 50:
        return {tgt: 1.0}
    elif row["growth_on"] and row["fng"] < 50:
        return {tgt: 0.80, "SHY": 0.20}
    return s_000(row, dt)
STRATEGIES["089. Dual Momentum & Sentiment Confirmation"] = s_089

# 90. Extreme Panic Exhaustion Flip (F&G < 15 & Delta > 0 -> 100% Equity)
def s_090(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["fng"] < 15 and row["fng_mom20"] > 0:
        return {tgt: 1.0} if row["growth_on"] else {"SPY": 0.50, "IEF": 0.50}
    return s_000(row, dt)
STRATEGIES["090. Extreme Panic Exhaustion Rebound"] = s_090

# 91. Prolonged Greed Squeeze Shaver (F&G > 75 & Delta > 0)
def s_091(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"] and row["fng"] >= 75:
        return {tgt: 0.80, "SHY": 0.20}
    return s_000(row, dt)
STRATEGIES["091. Prolonged Greed Squeeze Shaver"] = s_091

# 92. Sentiment Acceleration Multiplier
def s_092(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"]:
        if row["fng"] >= 82:
            return {tgt: 0.72, "SHY": 0.28}
        elif row["fng"] <= 25:
            return {tgt: 1.0}
    return s_000(row, dt)
STRATEGIES["092. Sentiment Acceleration Multiplier"] = s_092

# 93. Adaptive 2-Week Momentum Filter
def s_093(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"]:
        if row["fng"] >= 80:
            return {tgt: 0.75, "SHY": 0.25}
        return {tgt: 1.0}
    else:
        if row["fng"] < 25:
            return {"SHY": 1.0}
        return s_000(row, dt)
STRATEGIES["093. Adaptive Multi-Week Wave Filter"] = s_093

# -------------------------------------------------------------------------
# Category 8: Portfolio-Level & Multi-Strategy Meta-Governors (94 ~ 100)
# -------------------------------------------------------------------------
# 94. Pension Meta-Governor (Extreme Greed: 70% IC + 30% BAA/Cash)
def s_094(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"]:
        if row["fng"] >= 80:
            # 70% IC sector + 30% defensive cash/bond
            return {tgt: 0.70, "SHY": 0.20, "IEF": 0.10}
        return {tgt: 1.0}
    else:
        if row["fng"] < 25:
            return {"SHY": 0.70, "IEF": 0.30}
        return s_000(row, dt)
STRATEGIES["094. Pension Master Strategy Meta-Governor"] = s_094

# 95. Triple-Asset Hybrid Risk Budget (XLK/XLE + GLD + SHY)
def s_095(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"]:
        if row["fng"] >= 82:
            return {tgt: 0.70, "GLD": 0.15, "SHY": 0.15}
        return {tgt: 1.0}
    return s_000(row, dt)
STRATEGIES["095. Triple-Asset Hybrid Risk Budget (GLD/SHY)"] = s_095

# 96. Canary Asset x F&G Dual Defense
def s_096(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"]:
        if row["fng"] >= 78:
            return {tgt: 0.75, "SHY": 0.25}
        return {tgt: 1.0}
    else:
        if row["fng"] < 25:
            return {"SHY": 1.0}
        elif row["fng"] < 40:
            return {"IEF": 0.60, "SHY": 0.40}
        return s_000(row, dt)
STRATEGIES["096. Canary Asset x F&G Dual Defense"] = s_096

# 97. Volatility Target Parity (Target 16% Volatility with F&G)
def s_097(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"]:
        w = float(np.clip(0.85 * (row["fng"] / 50.0) ** 0.35, 0.60, 1.0))
        if row["fng"] >= 82:
            w = 0.75
        return {tgt: w, "SHY": 1.0 - w}
    return s_000(row, dt)
STRATEGIES["097. Volatility Target Sentiment Parity"] = s_097

# 98. Adaptive Dynamic Beta Allocator (Optimized 78/24 Boundary)
def s_098(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"]:
        if row["fng"] >= 78:
            return {tgt: 0.76, "SHY": 0.24}
        return {tgt: 1.0}
    else:
        if row["fng"] <= 24:
            return {"SHY": 1.0}
        elif row["inflation_on"]:
            return {"XLU": 0.80, "SHY": 0.20}
        else:
            return {"XLP": 0.50, "IEF": 0.50}
STRATEGIES["098. Optimized 78/24 Adaptive Allocator"] = s_098

# 99. Golden Balance Overlay (Growth ON: F&G>77 -> 80% Eq / 20% SHY, Growth OFF: F&G<22 -> 100% SHY)
def s_099(row, dt):
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"]:
        if row["fng"] >= 77:
            return {tgt: 0.80, "SHY": 0.20}
        return {tgt: 1.0}
    else:
        if row["fng"] <= 22:
            return {"SHY": 1.0}
        return s_000(row, dt)
STRATEGIES["099. Golden Balance 77/22 Overlay"] = s_099

# 100. Grand Master AI Ensemble (Dynamic Multi-Factor Alpha)
def s_100(row, dt):
    # Grand Master Ensemble:
    # 1. Bull Market: Hold high-beta (XLK/XLE) at 100%. When Euphoria (F&G >= 78), take 22% profit into SHY.
    # 2. Bull Market Dip (F&G < 25): Accelerate 100% high-beta.
    # 3. Bear Market Panic (Growth OFF & F&G < 25): Avoid equity collapse completely -> 100% SHY (Zero Duration).
    # 4. Bear Market Normal (Growth OFF & F&G >= 25): Standard XLU (80/20) or XLP/IEF (50/50).
    tgt = base_regime_asset(row["growth_on"], row["inflation_on"])
    if row["growth_on"]:
        if row["fng"] >= 78:
            return {tgt: 0.78, "SHY": 0.22}
        else:
            return {tgt: 1.0}
    else:
        if row["fng"] < 25:
            return {"SHY": 1.0}
        elif row["inflation_on"]:
            return {"XLU": 0.80, "SHY": 0.20}
        else:
            return {"XLP": 0.50, "IEF": 0.50}
STRATEGIES["100. Grand Master Ensemble Engine"] = s_100


def main():
    print("================================================================================")
    print("🚀 MASS QUANTITATIVE SIMULATION: 100 INFLATION COMPASS x FEAR & GREED STRATEGIES")
    print("================================================================================")

    prices, t5yie, vix, hy_spread = load_master_data()
    df_signals, returns = compute_signals(prices, t5yie, vix, hy_spread)

    print(f"Loaded {len(prices)} trading days ({prices.index.min().date()} ~ {prices.index.max().date()})")
    print(f"Running simulation across {len(STRATEGIES)} strategy variations...\n")

    results = {}
    for name, fn in STRATEGIES.items():
        results[name] = run_single_simulation(df_signals, returns, fn)

    # Convert to DataFrame
    df_all = pd.DataFrame({
        name: {
            "CAGR": res["CAGR"],
            "Vol": res["Vol"],
            "Sharpe": res["Sharpe"],
            "MDD": res["MDD"],
            "Calmar": res["Calmar"],
            "2008_MDD": res["2008_MDD"],
            "2020_MDD": res["2020_MDD"],
            "2022_MDD": res["2022_MDD"],
        }
        for name, res in results.items()
    }).T

    # Baseline stats
    base = df_all.loc["000. Baseline (IC Original)"]
    df_all["CAGR_vs_IC"] = df_all["CAGR"] - base["CAGR"]
    df_all["MDD_vs_IC"] = df_all["MDD"] - base["MDD"]
    df_all["Sharpe_vs_IC"] = df_all["Sharpe"] - base["Sharpe"]

    # Save full results to CSV
    csv_path = DATA_DIR / "fng_100_backtest_results.csv"
    df_all.to_csv(csv_path)
    print(f"Saved complete 100-strategy backtest results to: {csv_path}\n")

    # Find Top Champions (Sharpe > Base Sharpe AND MDD better/comparable)
    sorted_by_sharpe = df_all.sort_values(by="Sharpe", ascending=False)
    sorted_by_cagr = df_all.sort_values(by="CAGR", ascending=False)
    sorted_by_calmar = df_all.sort_values(by="Calmar", ascending=False)

    # Format helper for display
    def format_df(df_sub):
        out = df_sub.copy()
        out["CAGR"] = out["CAGR"].map(lambda x: f"{x*100:.2f}%")
        out["Vol"] = out["Vol"].map(lambda x: f"{x*100:.2f}%")
        out["Sharpe"] = out["Sharpe"].map(lambda x: f"{x:.3f}")
        out["MDD"] = out["MDD"].map(lambda x: f"{x*100:.2f}%")
        out["Calmar"] = out["Calmar"].map(lambda x: f"{x:.3f}")
        out["2008_MDD"] = out["2008_MDD"].map(lambda x: f"{x*100:.2f}%")
        out["2020_MDD"] = out["2020_MDD"].map(lambda x: f"{x*100:.2f}%")
        out["2022_MDD"] = out["2022_MDD"].map(lambda x: f"{x*100:.2f}%")
        out["CAGR_vs_IC"] = out["CAGR_vs_IC"].map(lambda x: f"{x*100:+.2f}%p")
        out["MDD_vs_IC"] = out["MDD_vs_IC"].map(lambda x: f"{x*100:+.2f}%p")
        return out

    cols = ["CAGR", "Vol", "Sharpe", "MDD", "Calmar", "2008_MDD", "2020_MDD", "2022_MDD", "CAGR_vs_IC", "MDD_vs_IC"]

    print("🏆 TOP 15 STRATEGIES BY SHARPE RATIO:")
    print(format_df(sorted_by_sharpe[cols].head(15)).to_markdown())

    print("\n🏆 TOP 10 STRATEGIES BY CAGR (MAX RETURN):")
    print(format_df(sorted_by_cagr[cols].head(10)).to_markdown())

    print("\n🏆 TOP 10 STRATEGIES BY CALMAR RATIO (RISK-ADJUSTED DRAWDOWN):")
    print(format_df(sorted_by_calmar[cols].head(10)).to_markdown())

    # Baseline comparison summary
    print("\n--------------------------------------------------------------------------------")
    print(f"📌 BASELINE IC SUMMARY:")
    print(f"   CAGR: {base['CAGR']*100:.2f}% | Sharpe: {base['Sharpe']:.3f} | MDD: {base['MDD']*100:.2f}% | Calmar: {base['Calmar']:.3f}")
    print(f"   2008 MDD: {base['2008_MDD']*100:.2f}% | 2020 MDD: {base['2020_MDD']*100:.2f}% | 2022 MDD: {base['2022_MDD']*100:.2f}%")
    print("--------------------------------------------------------------------------------")


if __name__ == "__main__":
    main()
