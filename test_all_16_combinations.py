"""16개 조합 매트릭스 — 데이터 로더·신호 계산 (2026-10-08 정정).

정정 사항(검토 결과):
- P1 의 신용 스프레드는 하이일드(HY)가 아니라 **BAA10Y**(Moody's Baa 회사채 − 10년 국채, 투자등급)다. 변수명을 baa10y 로 바꿨다.
  FRED 의 진짜 HY 스프레드(BAMLH0A0HYM2)는 라이선스 제한으로 2023-10 이후만 제공돼 2003~2026 검증에 쓸 수 없다.
- 공포·탐욕 지수는 CNN 지수가 아니라 4요소(모멘텀·VIX·주식-채권·신용 스프레드)로 만든 **대리 지표**다.
- 무위험 금리 DTB3(FRED 3개월 T-bill, 연율 %)를 함께 읽는다 — 차입·현금 이자에 쓴다(종전엔 SHY 가격 수익률을 썼다).
- fred_lag: FRED 지표(T5YIE·BAA10Y)를 n 거래일 늦춰 쓴다. 실거래(월말 오후 실행)에서는 그날 FRED 값이 아직 없다.
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

def load_master_data():
    conn = sqlite3.connect(DB_PATH)
    prices_long = pd.read_sql("SELECT date, ticker, close FROM prices", conn, parse_dates=["date"])
    t5yie_long = pd.read_sql("SELECT date, value FROM fred_series WHERE series_id='T5YIE'", conn, parse_dates=["date"])
    conn.close()

    prices = prices_long.pivot(index="date", columns="ticker", values="close").sort_index()
    t5yie = t5yie_long.set_index("date")["value"].sort_index().reindex(prices.index).ffill()

    aux_tickers = ["SHY", "QQQ", "SOXX", "DBC", "GLD", "BIL", "^SPGSCI", "GC=F"]
    raw_aux = yf.download(aux_tickers, start="2000-01-01", auto_adjust=True, group_by="ticker", progress=False)
    for t in ["SHY", "QQQ", "SOXX", "BIL"]:
        if t in raw_aux and "Close" in raw_aux[t]:
            s = raw_aux[t]["Close"].squeeze().dropna()
            prices[t] = s.reindex(prices.index).bfill().ffill()

    # Splice DBC with ^SPGSCI
    if "^SPGSCI" in raw_aux and "Close" in raw_aux["^SPGSCI"] and "DBC" in raw_aux and "Close" in raw_aux["DBC"]:
        gsci = raw_aux["^SPGSCI"]["Close"].squeeze().dropna()
        dbc = raw_aux["DBC"]["Close"].squeeze().dropna()
        ret_gsci = gsci.pct_change()
        first_dbc_dt = dbc.index[0]
        first_dbc_px = dbc.iloc[0]
        gsci_pre = ret_gsci.loc[:first_dbc_dt].iloc[:-1]
        pre_prices = first_dbc_px / (1 + gsci_pre.iloc[::-1]).cumprod().iloc[::-1]
        spliced_dbc = pd.concat([pre_prices, dbc]).sort_index()
        spliced_dbc = spliced_dbc[~spliced_dbc.index.duplicated(keep="first")]
        prices["DBC"] = spliced_dbc.reindex(prices.index).bfill().ffill()
    else:
        prices["DBC"] = prices["XLE"]

    # Splice GLD with GC=F
    if "GC=F" in raw_aux and "Close" in raw_aux["GC=F"] and "GLD" in raw_aux and "Close" in raw_aux["GLD"]:
        gc = raw_aux["GC=F"]["Close"].squeeze().dropna()
        gld = raw_aux["GLD"]["Close"].squeeze().dropna()
        ret_gc = gc.pct_change()
        first_gld_dt = gld.index[0]
        first_gld_px = gld.iloc[0]
        gc_pre = ret_gc.loc[:first_gld_dt].iloc[:-1]
        pre_prices = first_gld_px / (1 + gc_pre.iloc[::-1]).cumprod().iloc[::-1]
        spliced_gld = pd.concat([pre_prices, gld]).sort_index()
        spliced_gld = spliced_gld[~spliced_gld.index.duplicated(keep="first")]
        prices["GLD"] = spliced_gld.reindex(prices.index).bfill().ffill()
    else:
        prices["GLD"] = prices["IEF"]

    vix_raw = yf.download("^VIX", start="2000-01-01", auto_adjust=True, progress=False)["Close"].squeeze()
    vix = vix_raw.reindex(prices.index).ffill()

    baa10y = _fred("BAA10Y").reindex(prices.index).ffill()
    dtb3 = _fred("DTB3").reindex(prices.index).ffill()

    # BIL 상장(2007-05) 전은 DTB3 누적으로 잇는다 — bfill 이면 그 구간 수익이 0 이 된다(2026-10-10 상시 보험 BIL 5%)
    if "BIL" in raw_aux and "Close" in raw_aux["BIL"]:
        bil = raw_aux["BIL"]["Close"].squeeze().dropna()
        first = bil.index[0]
        accr = (1 + (dtb3.fillna(0) / 100 / 252)).cumprod()
        synth = accr / accr.loc[:first].iloc[-1] * bil.iloc[0]
        prices["BIL"] = bil.reindex(prices.index).ffill().where(prices.index >= first, synth)

    return prices, t5yie, vix, baa10y, dtb3


def _fred(series_id: str) -> pd.Series:
    df = pd.read_csv(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd=1996-12-31", na_values=".").dropna()
    df["date"] = pd.to_datetime(df["observation_date"])
    s = df.set_index("date")[series_id]
    return s[~s.index.duplicated(keep="last")]

def rolling_slope(series, window=60):
    x = np.arange(window)
    x_mean = x.mean()
    denom = ((x - x_mean) ** 2).sum()
    def slope(y):
        return ((x - x_mean) * (y - y.mean())).sum() / denom
    return series.rolling(window).apply(slope, raw=True)

def compute_signals(prices, t5yie, vix, baa10y, fred_lag: int = 0):
    """fred_lag > 0 이면 T5YIE·BAA10Y 를 그만큼 거래일 늦춘다(시장 데이터 — 가격·VIX — 는 그날 값)."""
    returns = prices.pct_change()
    if fred_lag:
        t5yie, baa10y = t5yie.shift(fred_lag), baa10y.shift(fred_lag)

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

    score_junk = (1.0 - baa10y.rolling(252).rank(pct=True)) * 100
    fng = (score_mom + score_vol + score_safe + score_junk) / 4.0

    vol_20_spy = returns["SPY"].rolling(20).std() * np.sqrt(252)
    ief_sma200 = prices["IEF"].rolling(200, min_periods=60).mean()
    # 보유 섹터 자기 추세(2026-10-10): 주식 칸 2배는 그 섹터가 자기 200일선 위일 때만
    sector_up = {f"{t.lower()}_up": prices[t] > prices[t].rolling(200).mean() for t in ("XLE", "XLK", "XLU", "GLD", "XLB")}
    # 인플레만 칸 모멘텀 후보(2026-10-10, infl_cell_momentum_prereg.md): 거래일 기준 수익
    for t in ("GLD", "XLU", "XLE", "XLB"):
        p = prices[t]
        r = {n: p / p.shift(n) - 1 for n in (21, 63, 126, 252)}
        sector_up[f"mom136_{t}"] = (r[21] + r[63] + r[126]) / 3
        sector_up[f"mom63_{t}"], sector_up[f"mom126_{t}"], sector_up[f"mom252_{t}"] = r[63], r[126], r[252]

    valid = spy_sma200.notna() & slope.notna() & t5yie.notna() & t5yie_60_ago.notna() & fng.notna()
    df_signals = pd.DataFrame({
        "growth_on": growth_on,
        "inflation_on": inflation_on,
        "spy": prices["SPY"],
        "spy_200ma": spy_sma200,
        "fng": fng,
        "vix": vix,
        "baa10y": baa10y,
        "vol_20_spy": vol_20_spy,
        "ief": prices["IEF"],
        "ief_sma200": ief_sma200,
        **sector_up,
    })[valid]

    return df_signals, returns

