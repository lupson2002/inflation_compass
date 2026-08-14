"""Percentile Channels TAA — core backtest engine.

Strategy (David Varadi, CSSA — replicated & verified against QuantStratTrader):
  - 4 percentile-channel systems (60/120/180/252 trading days)
  - entry: price crosses ABOVE the 75th percentile  -> signal +1
  - exit : price crosses BELOW the 25th percentile  -> signal -1
  - between bounds: signal persists (hysteresis). Signals tracked DAILY.
  - composite score = mean of the 4 channel signals
  - weight_i = composite_i * 1/vol20_i, normalized by abs over all assets,
    then any asset with composite <= 0 is dropped (weight -> 0, money to SHY)
  - SHY fills the residual; monthly rebalance only.

Stores backtest results into data/pct.db so the dashboard / telegram can read
them without re-running the simulation.
"""

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "pct.db"

ASSETS = ["VTI", "IYR", "LQD", "DBC"]
CASH = "SHY"
CHANNELS = [60, 120, 180, 252]
BUY_TH = 0.75
EXIT_TH = 0.25
VOL_DAYS = 20
TRANSACTION_COST_BP = 30  # 0.3% one-way per unit of notional traded

TICKER_KR = {"VTI": "주식", "IYR": "부동산", "LQD": "회사채", "DBC": "원자재", "SHY": "현금"}


def load_data():
    """pct.db의 prices를 넓은 DataFrame(pivot)으로 로드한다."""
    conn = sqlite3.connect(DB_PATH)
    long = pd.read_sql("SELECT date, ticker, close FROM prices", conn, parse_dates=["date"])
    conn.close()
    prices = long.pivot(index="date", columns="ticker", values="close").sort_index()
    return prices


def channel_signal(px, lookback, buy_th=BUY_TH, exit_th=EXIT_TH):
    """단일 채널의 일별 히스테리시스 신호 시리즈를 반환한다.

    가격이 lookback 기간의 75번째 백분위를 상향돌파하면 +1,
    25번째 백분위를 하향돌파하면 -1, 그 사이면 이전 신호 유지.
    """
    upper = px.rolling(lookback, min_periods=lookback).quantile(buy_th)
    lower = px.rolling(lookback, min_periods=lookback).quantile(exit_th)
    n = len(px)
    sig = np.zeros(n)
    prev = 0.0
    for i in range(n):
        p = px.iloc[i]
        u = upper.iloc[i]
        l = lower.iloc[i]
        if i == 0 or np.isnan(u) or np.isnan(l):
            out = prev
        else:
            pp = px.iloc[i - 1]
            if np.isnan(pp) or np.isnan(upper.iloc[i - 1]) or np.isnan(lower.iloc[i - 1]):
                out = prev
            elif p > u and not (pp > u):
                out = 1.0
            elif p < l and not (pp < l):
                out = -1.0
            else:
                out = prev
        prev = out
        sig[i] = out
    return pd.Series(sig, index=px.index)


def compute_scores(prices):
    """채널별 신호, composite 점수, 20일 역변동성(비중 사전단계)을 계산한다.

    Returns (channel_signals, composite, vol20):
      channel_signals : {lookback: DataFrame[asset]} — 일별 +1/-1/0
      composite       : DataFrame[asset]              — 채널 신호 평균
      vol20           : DataFrame[asset]              — 연율화 20일 변동성
    """
    channel_signals = {}
    for c in CHANNELS:
        channel_signals[c] = pd.DataFrame(
            {a: channel_signal(prices[a], c) for a in ASSETS}, index=prices.index
        )
    composite = sum(channel_signals[c] for c in CHANNELS) / len(CHANNELS)
    vol20 = prices[ASSETS].pct_change().rolling(VOL_DAYS).std() * np.sqrt(252)
    return channel_signals, composite, vol20


def month_end_dates(index):
    df = pd.Series(index, index=index)
    return df.groupby([index.year, index.month]).last()


def build_positions(composite, vol20):
    """월말마다 결정된 비중 딕셔너리 리스트를 생성한다.

    Returns [(decision_date, period_end, weights, composite_snapshot), ...]
    weights: {asset: w} with SHY filling the residual.
    composite_snapshot: {asset: composite_score} at decision date (for display).
    """
    ends = month_end_dates(composite.index)
    positions = []
    for i in range(len(ends) - 1):
        d = ends.iloc[i]
        end = ends.iloc[i + 1]
        # --- sizing at decision date d ---
        comp = {a: float(composite.loc[d, a]) for a in ASSETS}
        raw = {}
        for a in ASSETS:
            v = vol20.loc[d, a]
            inv = 1.0 / v if (v and v > 0 and not np.isnan(v)) else 0.0
            raw[a] = comp[a] * inv
        tot = sum(abs(x) for x in raw.values())
        w = {a: 0.0 for a in ASSETS}
        if tot > 0:
            for a in ASSETS:
                w[a] = (abs(raw[a]) / tot) if comp[a] > 0 else 0.0
        w[CASH] = 1.0 - sum(w[a] for a in ASSETS)
        positions.append((d, end, w, comp))
    return positions


def simulate(positions, prices):
    """월말 결정 비중을 다음 월말까지 보유하는 일별 포트폴리오 수익률."""
    returns = prices.pct_change().fillna(0.0)
    daily_ret = pd.Series(0.0, index=prices.index)
    for d, end, w, comp in positions:
        mask = (prices.index > d) & (prices.index <= end)
        period_ret = sum(returns.loc[mask, a] * w[a] for a in w)
        daily_ret.loc[mask] = period_ret
    start = positions[0][0]
    end = positions[-1][1]
    return daily_ret.loc[start:end]


def compute_turnover(positions):
    turnover = []
    prev = {}
    for d, end, w, comp in positions:
        tickers = set(w) | set(prev)
        t = sum(abs(w.get(k, 0) - prev.get(k, 0)) for k in tickers)
        turnover.append((d, t))
        prev = w
    return turnover


def apply_costs(daily_ret, positions, cost_bp=TRANSACTION_COST_BP):
    cost_rate = cost_bp / 10000
    adj = daily_ret.copy()
    for d, t in compute_turnover(positions):
        if t == 0:
            continue
        trade_days = adj.index[adj.index > d]
        if len(trade_days) == 0:
            continue
        first = trade_days[0]
        adj.loc[first] = (1 + adj.loc[first]) * (1 - t * cost_rate) - 1
    return adj


def perf_stats(daily_ret):
    equity = (1 + daily_ret).cumprod()
    n_years = len(daily_ret) / 252
    cagr = equity.iloc[-1] ** (1 / n_years) - 1
    vol = daily_ret.std() * np.sqrt(252)
    sharpe = (daily_ret.mean() * 252) / vol
    mdd = (equity / equity.cummax() - 1).min()
    sortino_den = daily_ret[daily_ret < 0].std() * np.sqrt(252)
    sortino = (daily_ret.mean() * 252) / sortino_den if sortino_den > 0 else np.nan
    return {
        "CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "Sortino": sortino,
        "MaxDD": mdd, "Calmar": cagr / abs(mdd) if mdd < 0 else np.nan,
        "End equity ($1 start)": equity.iloc[-1],
    }, equity


def yearly_returns(daily_ret):
    return daily_ret.groupby(daily_ret.index.year).apply(lambda r: (1 + r).prod() - 1)


def build_weights_df(positions, index):
    tickers = ASSETS + [CASH]
    wdf = pd.DataFrame(0.0, index=index, columns=tickers)
    for d, end, w, comp in positions:
        mask = (index > d) & (index <= end)
        for a, v in w.items():
            wdf.loc[mask, a] = v
    return wdf


def build_weights_schedule(positions, index):
    """각 거래일에 적용되는 비중(결정 시점 기준, 월말 보유) 일별 DataFrame."""
    wdf = pd.DataFrame(0.0, index=index, columns=ASSETS + [CASH])
    for d, end, w, comp in positions:
        mask = (index > d) & (index <= end)
        for a, v in w.items():
            wdf.loc[mask, a] = v
    return wdf


def main():
    prices = load_data()
    # 시작 시점 = 4개 자산이 모두 존재하는 시점 (연장 후에도 가장 늦은 개시일)
    starts = [prices[a].first_valid_index() for a in ASSETS]
    start = max(starts)
    prices = prices.loc[start:]

    channel_signals, composite, vol20 = compute_scores(prices)
    positions = build_positions(composite, vol20)

    returns = prices.pct_change().fillna(0.0)
    strat_ret = simulate(positions, prices)
    strat_net = apply_costs(strat_ret, positions)
    bench_ret = returns["VTI"].loc[strat_ret.index]

    strat_stats, strat_equity = perf_stats(strat_ret)
    strat_net_stats, strat_net_equity = perf_stats(strat_net)
    bench_stats, bench_equity = perf_stats(bench_ret)

    n_changes = sum(1 for _, t in compute_turnover(positions) if t > 0)
    print(f"Backtest period: {strat_ret.index.min().date()} ~ {strat_ret.index.max().date()} "
          f"({len(positions)} monthly decisions, {n_changes} position changes)")
    print()

    def fmt(v):
        return f"{v:.3f}" if v is not None else "n/a"

    header = f"{'metric':<24}{'Strategy (gross)':>18}{f'Strategy (net {TRANSACTION_COST_BP}bp)':>24}{'VTI B&H':>12}"
    print(header)
    for k in strat_stats:
        print(f"{k:<24}{fmt(strat_stats[k]):>18}{fmt(strat_net_stats[k]):>24}{fmt(bench_stats[k]):>12}")

    strat_yearly = yearly_returns(strat_ret)
    bench_yearly = yearly_returns(bench_ret)
    excess_yearly = strat_yearly - bench_yearly
    print("\nYearly returns (first/last year partial):")
    print(f"{'year':<8}{'Strategy':>12}{'VTI':>12}{'Excess':>12}")
    for y in strat_yearly.index:
        print(f"{y:<8}{strat_yearly[y] * 100:>11.1f}%{bench_yearly[y] * 100:>11.1f}%{excess_yearly[y] * 100:>11.1f}%")
    win_rate = (excess_yearly > 0).mean()
    print(f"\nYears beating VTI: {(excess_yearly > 0).sum()}/{len(excess_yearly)} ({win_rate * 100:.0f}%)")

    # ---- persist to db ----
    weights_df = build_weights_df(positions, strat_ret.index)
    daily_ret_df = pd.DataFrame({"strategy_ret": strat_ret, "spy_ret": bench_ret})
    turnover_df = pd.DataFrame(compute_turnover(positions), columns=["decision_date", "turnover"])
    turnover_df = turnover_df[turnover_df["turnover"] > 0]
    yearly_df = pd.DataFrame({"strategy": strat_yearly, "spy": bench_yearly, "excess": excess_yearly}).reset_index(names="year")
    pos_df = pd.DataFrame(
        [
            (d, e, round(comp.get("VTI", 0), 3), round(comp.get("IYR", 0), 3),
             round(comp.get("LQD", 0), 3), round(comp.get("DBC", 0), 3),
             round(w["VTI"], 4), round(w["IYR"], 4), round(w["LQD"], 4),
             round(w["DBC"], 4), round(w["SHY"], 4))
            for d, e, w, comp in positions
        ],
        columns=["decision_date", "period_end", "comp_VTI", "comp_IYR", "comp_LQD", "comp_DBC",
                 "w_VTI", "w_IYR", "w_LQD", "w_DBC", "w_SHY"],
    )
    equity_df = pd.DataFrame({"strategy_equity": strat_equity, "strategy_equity_net": strat_net_equity, "spy_equity": bench_equity})

    conn = sqlite3.connect(DB_PATH)
    pos_df.assign(decision_date=pos_df.decision_date.dt.strftime("%Y-%m-%d"), period_end=pos_df.period_end.dt.strftime("%Y-%m-%d")).to_sql(
        "backtest_positions", conn, if_exists="replace", index=False)
    equity_df.reset_index(names="date").assign(date=lambda d: d.date.dt.strftime("%Y-%m-%d")).to_sql(
        "backtest_equity", conn, if_exists="replace", index=False)
    yearly_df.to_sql("backtest_yearly", conn, if_exists="replace", index=False)
    weights_df.reset_index(names="date").assign(date=lambda d: d.date.dt.strftime("%Y-%m-%d")).to_sql(
        "backtest_weights", conn, if_exists="replace", index=False)
    daily_ret_df.reset_index(names="date").assign(date=lambda d: d.date.dt.strftime("%Y-%m-%d")).to_sql(
        "backtest_daily_returns", conn, if_exists="replace", index=False)
    turnover_df.assign(decision_date=turnover_df.decision_date.dt.strftime("%Y-%m-%d")).to_sql(
        "backtest_turnover_events", conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()
    print(f"\nsaved backtest tables to {DB_PATH}")


if __name__ == "__main__":
    main()
