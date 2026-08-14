"""Fetch daily data for the Percentile Channels TAA strategy and store in SQLite.

Strategy: 4 percentile-channel (60/120/180/252) tactical asset allocation
between VTI / IYR / LQD / DBC with SHY as cash, inverse-vol risk parity sizing.

To recover history before each ETF's inception, the short ETF series is
extended backwards by splicing in a longer mutual-fund / index proxy series,
scale-aligned at their first overlapping date.

Stores into data/pct.db:
  prices            -> date, ticker, close        (extended series)
  backtest_* tables -> filled by pct_backtest.py
"""

import sqlite3
from pathlib import Path

import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "pct.db"

# ETF that the strategy actually trades
ETFS = {"VTI": "주식", "IYR": "부동산", "LQD": "회사채", "DBC": "원자재", "SHY": "현금"}
# proxy mutual-fund / index series used to extend each ETF's history backwards
EXTEND = {"VTI": "VFINX", "IYR": "VGSIX", "LQD": "VFICX", "DBC": "VGPMX", "SHY": "VFISX"}

START = "1986-01-01"

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    close REAL NOT NULL,
    PRIMARY KEY (date, ticker)
);
"""


def _series(ticker, start=START):
    return yf.Ticker(ticker).history(start=start, auto_adjust=True)["Close"]


def build_extended(ticker):
    """ETF 가격을 프록시 펀드로 뒤로 연장한 Series를 반환.

    겹치는 첫 날에서 프록시를 ETF 수준으로 스케일 정렬한 뒤, ETF 실제 이력과
    프록시 연장분을 합친다. 겹치는 이력이 없으면 ETF 원본 그대로 사용한다.
    """
    d = _series(ticker)
    p = _series(EXTEND[ticker])
    both = d.index.intersection(p.index)
    if len(both) == 0:
        return d
    i0 = both[0]
    scale = d.loc[i0] / p.loc[i0]
    p_scaled = p * scale
    merged = pd.concat([p_scaled.loc[:i0], d.loc[i0:]])
    merged = merged[~merged.index.duplicated(keep="last")].sort_index()
    return merged


def fetch_extended_prices(tickers=ETFS):
    series = {}
    for t in tickers:
        series[t] = build_extended(t)
    df = pd.DataFrame(series).dropna(how="all").sort_index()
    df.index.name = "Date"
    return df


def upsert_prices(conn, prices):
    long = prices.reset_index().melt(id_vars="Date", var_name="ticker", value_name="close")
    long = long.dropna(subset=["close"])
    long["date"] = long["Date"].dt.strftime("%Y-%m-%d")
    rows = list(long[["date", "ticker", "close"]].itertuples(index=False, name=None))
    conn.executemany("INSERT OR REPLACE INTO prices (date, ticker, close) VALUES (?, ?, ?)", rows)


def main():
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    prices = fetch_extended_prices()
    upsert_prices(conn, prices)
    conn.commit()
    conn.close()

    print(f"[pct_fetch_data] 저장 완료: {DB_PATH}")
    print(f"기간: {prices.index.min().date()} ~ {prices.index.max().date()} ({len(prices)} 거래일)")
    print("자산별 이력 시작일:")
    for t in ETFS:
        first = prices[t].first_valid_index()
        print(f"  {t:<5} ({ETFS[t]}) : {first.date()}  [프록시 {EXTEND[t]}]")


if __name__ == "__main__":
    main()
