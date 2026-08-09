"""Inflation Compass — 리밸런싱 주파수 비교 (일간 / 주간 / 월간).

동일한 신호(성장/인플레이션 4국면)를 쓸 때, 매일·매주·매월 언제 리밸런싱하는지에
따라 포트폴리오 성과가 어떻게 달라지는지 일괄 백테스트해 비교한다.

기존 월간 전략(backtest.py)과 동일한 데이터/신호를 재사용하고, 의사결정 주기만
주파수별로 달리한다. 결과는 콘솔 표 + db(compare_frequencies)에 저장된다.

사용: python compare_frequencies.py
"""

import sqlite3
from pathlib import Path

import pandas as pd

import backtest

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "inflation_compass.db"

TRANSACTION_COST_BP = 30  # 월간 기본과 동일 (30bp, 편도)


def decision_dates(index, freq):
    """freq에 맞는 의사결정(리밸런싱) 날짜 목록을 반환한다.

    - 'daily'   : 매 거래일
    - 'weekly'  : 매 주 마지막 거래일 (금요일)
    - 'monthly' : 매 월 마지막 거래일
    - 'md<day>' : 매월 <day>일 (해당일이 휴장이면 그 다음 거래일), 예: md1, md5, md10
    의사결정일의 신호로 판단해, 다음 의사결정일까지 보유한다.
    반환값은 pandas Timestamp로 통일한다.
    """
    idx = pd.Series(index, index=index)
    if freq == "daily":
        return list(idx.index)
    if freq == "weekly":
        return [pd.Timestamp(v) for v in idx.resample("W-FRI").last().dropna().values]
    if freq == "monthly":
        return [pd.Timestamp(v) for v in idx.resample("ME").last().dropna().values]
    if freq.startswith("md"):
        day = int(freq[2:])
        return _monthly_on_day(index, day)
    raise ValueError(f"알 수 없는 주파수: {freq}")


def _monthly_on_day(index, day):
    """매월 <day>일에 리밸런싱하는 의사결정 날짜 목록.

    매월의 <day>일이 휴장이면 그 다음 거래일로 지연한다. day가 해당 월 일수보다
    크면(예: 31일 없는 달) 그 달엔 리밸런싱하지 않는다. 반환값은 pandas Timestamp.
    """
    idx = pd.Series(index, index=index)
    decisions = []
    months = idx.resample("ME").last().index  # 각 월 마지막 날짜 (Timestamp)
    for month_end in months:
        try:
            target = month_end.replace(day=day)
        except ValueError:
            continue  # day가 이 달에 없으면 스킵
        ge = idx.index[idx.index >= target]
        if len(ge) == 0:
            continue
        decisions.append(pd.Timestamp(ge[0]))
    return decisions


def build_positions_freq(signals, freq):
    """주파수별 의사결정으로 국면 포지션 리스트를 만든다.

    마지막 의사결정일의 포지션은 데이터 끝까지 연장해, 모든 주파수/시점이
    동일한 종료일까지 관측되도록 한다(비교 공정성). 
    Returns: [(decision_date, period_end, regime, weights), ...]
    """
    decision = decision_dates(signals.index, freq)
    positions = []
    for i in range(len(decision) - 1):
        d = decision[i]
        end = decision[i + 1]
        regime = (bool(signals.loc[d, "growth_on"]), bool(signals.loc[d, "inflation_on"]))
        positions.append((d, end, regime, backtest.REGIME_POSITIONS[regime]))
    if decision:
        d = decision[-1]
        regime = (bool(signals.loc[d, "growth_on"]), bool(signals.loc[d, "inflation_on"]))
        positions.append((d, signals.index.max(), regime, backtest.REGIME_POSITIONS[regime]))
    return positions


def compare_frequencies(freqs=("daily", "weekly", "monthly"), cost_bp=TRANSACTION_COST_BP):
    prices, t5yie = backtest.load_data()
    signals, returns = backtest.compute_signals(prices, t5yie)

    rows = []
    for freq in freqs:
        positions = build_positions_freq(signals, freq)
        strat_ret = backtest.simulate(positions, returns)
        strat_net = backtest.apply_costs(strat_ret, positions, cost_bp)
        bench_ret = returns["SPY"].loc[strat_ret.index]

        stats, equity = backtest.perf_stats(strat_ret)
        net_stats, _ = backtest.perf_stats(strat_net)
        bench_stats, _ = backtest.perf_stats(bench_ret)

        turnover = backtest.compute_turnover(positions)
        n_changes = sum(1 for _, t in turnover if t > 0)
        total_turnover = sum(t for _, t in turnover)
        n_years = len(strat_ret) / 252

        # 비용 후 실제 지표 (실거래 관점)
        cagr = net_stats["CAGR"]
        sharpe = net_stats["Sharpe"]
        mdd = net_stats["MaxDD"]
        vol = net_stats["Vol"]
        end_equity = net_stats["End equity ($1 start)"]

        rows.append(
            {
                "frequency": freq,
                "label": freq if not freq.startswith("md") else f"매월{freq[2:]}일",
                "decisions": len(positions),
                "trades": n_changes,
                "turnover": total_turnover,
                "turnover_per_yr": total_turnover / n_years,
                "CAGR": cagr,
                "Sharpe": sharpe,
                "MaxDD": mdd,
                "Vol": vol,
                "EndEquity": end_equity,
                "CAGR_bench": bench_stats["CAGR"],
                "period": f"{strat_ret.index.min().date()} ~ {strat_ret.index.max().date()}",
            }
        )

    return pd.DataFrame(rows)


def print_report(df):
    print("=" * 78)
    print("Inflation Compass — 리밸런싱 주파수·시점 비교 (비용 {:.0f}bp 편도 기준)".format(TRANSACTION_COST_BP))
    print("=" * 78)
    print(
        f"{'리밸런싱':<10}{'기간':<26}{'의사결정':>7}{'거래수':>7}{'턴오버/yr':>11}"
        f"{'CAGR':>9}{'Sharpe':>8}{'MaxDD':>9}{'Vol':>8}{'EndEq':>9}"
    )
    for _, r in df.iterrows():
        print(
            f"{r['label']:<10}{r['period']:<26}{int(r['decisions']):>7}{int(r['trades']):>7}"
            f"{r['turnover_per_yr']:>11.2f}{r['CAGR']*100:>8.1f}%{r['Sharpe']:>8.2f}"
            f"{r['MaxDD']*100:>8.1f}%{r['Vol']*100:>7.1f}%{r['EndEquity']:>8.1f}x"
        )
    print("=" * 78)
    print("SPY buy&hold: CAGR {:.1f}%".format(df['CAGR_bench'].iloc[0] * 100))


def save_db(df):
    conn = sqlite3.connect(DB_PATH)
    df.to_sql("compare_frequencies", conn, if_exists="replace", index=False)
    conn.close()
    print(f"\nsaved compare_frequencies table to {DB_PATH}")


def main():
    freqs = ("daily", "weekly", "monthly", "md1", "md5", "md10", "md15", "md20", "md25")
    df = compare_frequencies(freqs)
    print_report(df)
    save_db(df)


if __name__ == "__main__":
    main()
