"""Systematic Parameter Sweep for Extreme Fear Lags (t-0 to t-12) on Inflation Compass.

Analyzes:
  1. Marginal value of each individual lag k in [0..12]
  2. Cumulative horizon from t-0 up to t-k in [0..12]
  3. Cumulative horizon with Trend Confirmation (SPY > 200MA)
"""

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import yfinance as yf

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "inflation_compass.db"

POS_BASKET = {"XLE": 0.5, "XLI": 1 / 6, "XLF": 1 / 6, "XLB": 1 / 6}
NEG_BASKET = {"XLU": 1 / 3, "XLV": 1 / 3, "XLP": 1 / 3}


def load_master_data():
    conn = sqlite3.connect(DB_PATH)
    prices_long = pd.read_sql("SELECT date, ticker, close FROM prices", conn, parse_dates=["date"])
    t5yie_long = pd.read_sql("SELECT date, value FROM fred_series WHERE series_id='T5YIE'", conn, parse_dates=["date"])
    conn.close()

    prices = prices_long.pivot(index="date", columns="ticker", values="close").sort_index()
    t5yie = t5yie_long.set_index("date")["value"].sort_index().reindex(prices.index).ffill()

    aux_tickers = ["SHY", "QQQ", "SOXX", "DBC", "GLD", "IYR", "TIP", "BIL", "IWM"]
    raw_aux = yf.download(aux_tickers, start="2000-01-01", auto_adjust=True, group_by="ticker", progress=False)
    for t in aux_tickers:
        if t in raw_aux and "Close" in raw_aux[t]:
            s = raw_aux[t]["Close"].squeeze().dropna()
            prices[t] = s.reindex(prices.index).bfill().ffill()

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

    # Macro Signals
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

    # 4-Component Synthetic F&G
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
        "spy": prices["SPY"],
        "spy_200ma": spy_sma200,
        "fng": fng,
    })[valid]

    return df_signals, returns


def run_sweep_simulation(df_signals, returns, lev_fn, start_date="2003-03-31"):
    signals = df_signals.loc[start_date:].copy()
    ret = returns.loc[start_date:].copy()
    rf_daily = ret["SHY"].fillna(0.0)

    month_ends = sorted(signals.groupby([signals.index.year, signals.index.month]).apply(lambda x: x.index[-1]).values)

    daily_returns = []

    for i in range(len(month_ends) - 1):
        decision_dt = month_ends[i]
        next_me = month_ends[i + 1]

        # Fetch past rows up to t-15
        past_rows = [signals.loc[month_ends[i - lag]] if i >= lag else signals.loc[decision_dt] for lag in range(16)]

        w_dict, lev = lev_fn(past_rows, decision_dt)
        idx_slice = signals.loc[decision_dt:next_me].index[1:]
        base_ret = sum(ret.loc[idx_slice, t] * w for t, w in w_dict.items())

        if lev >= 1.0:
            borrow_cost = (lev - 1.0) * (rf_daily.loc[idx_slice] + 0.005 / 252.0)
            p_ret = base_ret * lev - borrow_cost
        else:
            cash_yield = (1.0 - lev) * rf_daily.loc[idx_slice]
            p_ret = base_ret * lev + cash_yield

        daily_returns.append(p_ret)

    daily_net_ret = pd.concat(daily_returns)
    equity = (1 + daily_net_ret).cumprod()
    n_years = len(daily_net_ret) / 252.0
    cagr = float(equity.iloc[-1] ** (1 / n_years) - 1)
    ann_vol = float(daily_net_ret.std() * np.sqrt(252))
    sharpe = cagr / ann_vol if ann_vol > 0 else 0.0
    peak = equity.cummax()
    dd = (equity - peak) / peak
    mdd = float(dd.min())
    calmar = cagr / abs(mdd) if abs(mdd) > 0 else 0.0

    return {
        "CAGR": cagr,
        "Total_Mult": float(equity.iloc[-1]),
        "Vol": ann_vol,
        "Sharpe": sharpe,
        "MDD": mdd,
        "Calmar": calmar,
        "equity": equity,
    }


def get_base_dict(row):
    if row["growth_on"] and row["inflation_on"]:
        return {"XLE": 1.0}
    elif row["growth_on"] and not row["inflation_on"]:
        return {"XLK": 1.0}
    elif not row["growth_on"] and row["inflation_on"]:
        return {"XLU": 1.0}
    else:
        return {"XLP": 0.5, "IEF": 0.5}


def main():
    print("================================================================================")
    print("🔬 EXTREME FEAR LOOKBACK SWEEP: t-0 ~ t-12 (최적 한계선 도출)")
    print("================================================================================")

    prices, t5yie, vix, hy_spread = load_master_data()
    df_signals, returns = compute_signals(prices, t5yie, vix, hy_spread)

    # 1. Baseline IC
    def fn_base(rows, dt):
        return get_base_dict(rows[0]), 1.0

    res_base = run_sweep_simulation(df_signals, returns, fn_base)
    eq_base = res_base["equity"].astype(float)
    m_base = eq_base.resample("ME").last().pct_change().dropna()

    print(
        f"0. Baseline IC (1.0x): CAGR {res_base['CAGR']*100:.2f}% | Sharpe {res_base['Sharpe']:.3f} | MDD {res_base['MDD']*100:.2f}% | Calmar {res_base['Calmar']:.3f}"
    )

    # -------------------------------------------------------------------------
    # Test A: Cumulative Horizon Sweep (t0, t2, t3 ... tk)
    # -------------------------------------------------------------------------
    print("\n--------------------------------------------------------------------------------")
    print("📊 [테스트 1] 누적 룩백 지평 (t-0, t-2 ~ t-k) 확장 스위프 (k = 0..12)")
    print("--------------------------------------------------------------------------------")

    cum_results = {}
    for max_k in range(13):

        def make_cum_fn(k):
            def fn(rows, dt):
                if rows[0]["fng"] > 85:
                    return get_base_dict(rows[0]), 0.50
                # Check fear in lag 0 or lags 2..k
                is_fear = (rows[0]["fng"] < 15) or any(rows[lag]["fng"] < 15 for lag in range(2, k + 1))
                lev = 2.0 if is_fear else 1.0
                return get_base_dict(rows[0]), lev

            return fn

        r = run_sweep_simulation(df_signals, returns, make_cum_fn(max_k))
        m_strat = r["equity"].astype(float).resample("ME").last().pct_change().dropna()
        diff = (m_strat - m_base).astype(float)
        _, p_val = stats.ttest_1samp(diff, 0.0)

        label = "t0 (당월만)" if max_k == 0 else f"t0, t2~t{max_k}"
        cum_results[f"k = {max_k:2d} ({label})"] = {
            "CAGR": f"{r['CAGR']*100:.2f}%",
            "누적 배수": f"{r['Total_Mult']:.1f}배",
            "Sharpe": f"{r['Sharpe']:.3f}",
            "MDD": f"{r['MDD']*100:.2f}%",
            "Calmar": f"{r['Calmar']:.3f}",
            "p-value": f"{p_val:.4f}",
            "raw_cagr": r["CAGR"],
            "raw_sharpe": r["Sharpe"],
            "raw_mdd": r["MDD"],
            "raw_calmar": r["Calmar"],
        }

    df_cum = pd.DataFrame(cum_results).T
    print(df_cum[["CAGR", "누적 배수", "Sharpe", "MDD", "Calmar", "p-value"]].to_markdown())

    # -------------------------------------------------------------------------
    # Test B: Cumulative Horizon with Trend Confirmation (SPY > 200MA for k >= 3)
    # -------------------------------------------------------------------------
    print("\n--------------------------------------------------------------------------------")
    print("📊 [테스트 2] 상승장 확증 필터 결합 누적 룩백 (k = 0..12)")
    print("--------------------------------------------------------------------------------")

    trend_results = {}
    for max_k in range(13):

        def make_trend_fn(k):
            def fn(rows, dt):
                if rows[0]["fng"] > 85:
                    return get_base_dict(rows[0]), 0.50
                is_direct_fear = (rows[0]["fng"] < 15) or (k >= 2 and rows[2]["fng"] < 15)
                is_lagged_fear = any(rows[lag]["fng"] < 15 for lag in range(3, k + 1)) if k >= 3 else False
                is_trend = rows[0]["growth_on"]

                if is_direct_fear or (is_lagged_fear and is_trend):
                    lev = 2.0
                else:
                    lev = 1.0
                return get_base_dict(rows[0]), lev

            return fn

        r = run_sweep_simulation(df_signals, returns, make_trend_fn(max_k))
        m_strat = r["equity"].astype(float).resample("ME").last().pct_change().dropna()
        diff = (m_strat - m_base).astype(float)
        _, p_val = stats.ttest_1samp(diff, 0.0)

        label = "t0 (당월만)" if max_k == 0 else f"t0, t2~t{max_k}"
        trend_results[f"k = {max_k:2d} ({label})"] = {
            "CAGR": f"{r['CAGR']*100:.2f}%",
            "누적 배수": f"{r['Total_Mult']:.1f}배",
            "Sharpe": f"{r['Sharpe']:.3f}",
            "MDD": f"{r['MDD']*100:.2f}%",
            "Calmar": f"{r['Calmar']:.3f}",
            "p-value": f"{p_val:.4f}",
            "raw_cagr": r["CAGR"],
            "raw_sharpe": r["Sharpe"],
            "raw_mdd": r["MDD"],
            "raw_calmar": r["Calmar"],
        }

    df_trend = pd.DataFrame(trend_results).T
    print(df_trend[["CAGR", "누적 배수", "Sharpe", "MDD", "Calmar", "p-value"]].to_markdown())

    # -------------------------------------------------------------------------
    # Test C: Pure Marginal Contribution of Each Single Lag k
    # -------------------------------------------------------------------------
    print("\n--------------------------------------------------------------------------------")
    print("📊 [테스트 3] 각 개별 룩백(t-k 단독)의 한계 기여도 분석 (k = 0..12)")
    print("--------------------------------------------------------------------------------")

    single_results = {}
    for single_k in range(13):

        def make_single_fn(k):
            def fn(rows, dt):
                if rows[0]["fng"] > 85:
                    return get_base_dict(rows[0]), 0.50
                # ONLY this single lag triggers 2.0x
                is_fear = rows[k]["fng"] < 15
                lev = 2.0 if is_fear else 1.0
                return get_base_dict(rows[0]), lev

            return fn

        r = run_sweep_simulation(df_signals, returns, make_single_fn(single_k))
        single_results[f"t-{single_k:d} 단독"] = {
            "CAGR": f"{r['CAGR']*100:.2f}%",
            "Sharpe": f"{r['Sharpe']:.3f}",
            "MDD": f"{r['MDD']*100:.2f}%",
            "Calmar": f"{r['Calmar']:.3f}",
            "CAGR_vs_IC": f"{(r['CAGR'] - res_base['CAGR'])*100:+.2f}%p",
        }

    df_single = pd.DataFrame(single_results).T
    print(df_single.to_markdown())


if __name__ == "__main__":
    main()
