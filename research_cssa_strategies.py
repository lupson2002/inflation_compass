"""CSS Analytics 블로그 전략 재현 + IC 혼합 가능성 (2026-10-10).

후보 3개를 IC 와 같은 실행 조건(월말 종가에 판단·체결, 월중 보유, 매매 명목 × 30bp, 현금 = DTB3)으로 재현한다.
  GIST  Growth and Inflation Sector Timing (2025-03-20): 성장 = SPY > 200일선, 인플레 = 수혜(0.5 XLE + ⅙ XLI·XLF·XLB)
        ÷ 피해(⅓ XLU·XLV·XLP) 누적비율이 그 200일 중앙값 위. Goldilocks XLK · Reflation XLE · Stagflation XLV · Deflation XLP.
  RMOM  Real Momentum (2015-05-09): SPY 일간수익 − (TIP − IEF 일간수익 5일 평균) 의 120일 평균 > 0 → SPY, 아니면 TIP.
  AAA   Adaptive Asset Allocation (2012-07-17, Butler·Philbrick·Gordillo): 10 자산 중 6개월(126일) 수익 상위 5개,
        60일 공분산 최소분산(롱온리) 비중.
IC 쪽은 run_16_matrix_experiments 엔진의 확정 전략(레버리지)·연금형(비레버리지) 월 수익률을 쓴다.

    python3 research_cssa_strategies.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.optimize import minimize

COST_BP = 30
AAA_UNIVERSE = ["SPY", "IEV", "EWJ", "EEM", "VNQ", "RWX", "IEF", "TLT", "DBC", "GLD"]
TICKERS = sorted(set(AAA_UNIVERSE + ["XLK", "XLE", "XLV", "XLP", "XLI", "XLF", "XLB", "XLU", "TIP", "BIL"]))


def load_prices() -> pd.DataFrame:
    px = yf.download(TICKERS, start="1998-01-01", auto_adjust=True, progress=False)["Close"]
    return px[TICKERS].dropna(how="all")


def month_ends(idx: pd.DatetimeIndex) -> list:
    return [pd.Timestamp(d) for d in sorted(pd.Series(idx, index=idx).groupby([idx.year, idx.month]).last().values)]


def backtest(px: pd.DataFrame, target_fn, rf: pd.Series, start: str) -> pd.Series:
    """월말 d0 에 target_fn(d0) 비중으로 체결 → d1 까지 보유. 월 수익률(d1 인덱스)."""
    mes = [d for d in month_ends(px.index) if d >= pd.Timestamp(start)]
    held: dict = {}
    out = {}
    for d0, d1 in zip(mes[:-1], mes[1:]):
        w = target_fn(d0)
        if w is None:
            continue
        to = sum(abs(w.get(k, 0) - held.get(k, 0)) for k in set(w) | set(held))
        cash = 1 - sum(w.values())
        r = {k: px.loc[d1, k] / px.loc[d0, k] - 1 for k in w}
        g = sum(w[k] * r[k] for k in w) + cash * float(rf.loc[d0:d1].iloc[1:].add(1).prod() - 1)
        out[d1] = (1 - to * COST_BP / 1e4) * (1 + g) - 1
        held = {k: w[k] * (1 + r[k]) / (1 + g) for k in w}
    s = pd.Series(out)
    s.index = s.index.to_period("M").to_timestamp("M")
    return s


def gist_fn(px: pd.DataFrame):
    ret = px.pct_change()
    pos = 0.5 * ret["XLE"] + (ret["XLI"] + ret["XLF"] + ret["XLB"]) / 6
    neg = (ret["XLU"] + ret["XLV"] + ret["XLP"]) / 3
    ratio = (1 + pos.fillna(0)).cumprod() / (1 + neg.fillna(0)).cumprod()
    infl = ratio > ratio.rolling(200).median()
    growth = px["SPY"] > px["SPY"].rolling(200).mean()

    def f(d):
        if pd.isna(px["SPY"].rolling(200).mean().loc[d]):
            return None
        g, i = bool(growth.loc[d]), bool(infl.loc[d])
        return {("XLE" if i else "XLK") if g else ("XLV" if i else "XLP"): 1.0}
    return f


def rmom_fn(px: pd.DataFrame):
    ret = px.pct_change()
    infl = (ret["TIP"] - ret["IEF"]).rolling(5).mean()
    real = (ret["SPY"] - infl).rolling(120).mean()

    def f(d):
        v = real.loc[d]
        return None if pd.isna(v) else {"SPY" if v > 0 else "TIP": 1.0}
    return f


def _minvar(cov: np.ndarray) -> np.ndarray:
    n = len(cov)
    res = minimize(lambda w: w @ cov @ w, np.full(n, 1 / n), method="SLSQP",
                   bounds=[(0, 1)] * n, constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}])
    w = np.clip(res.x, 0, 1)
    return w / w.sum()


def aaa_fn(px: pd.DataFrame):
    u = px[AAA_UNIVERSE]
    ret = u.pct_change()

    def f(d):
        hist = u.loc[:d]
        if hist.dropna().shape[0] < 130:
            return None
        mom = hist.iloc[-1] / hist.iloc[-127] - 1
        top = list(mom.nlargest(5).index)
        cov = ret.loc[:d, top].iloc[-60:].cov().values * 252
        return dict(zip(top, _minvar(cov)))
    return f


def stats(r: pd.Series) -> dict:
    eq = (1 + r).cumprod()
    n = len(r) / 12
    cagr = eq.iloc[-1] ** (1 / n) - 1
    mdd = (eq / eq.cummax() - 1).min()
    return {"CAGR": cagr, "MDD": mdd, "Calmar": cagr / abs(mdd), "Vol": r.std() * np.sqrt(12), "worst": r.min()}


def mix(a: pd.Series, b: pd.Series, w: float) -> pd.Series:
    out = []
    for ra, rb in zip(a.values, b.values):
        g = w * ra + (1 - w) * rb
        drift = w * (1 + ra) / (1 + g)
        out.append((1 + g) * (1 - 2 * abs(drift - w) * COST_BP / 1e4) - 1)
    return pd.Series(out, index=a.index)


def ic_monthly(levered: bool):
    import run_16_matrix_experiments as r16
    from test_all_16_combinations import compute_signals, load_master_data
    prices, t5, vix, baa, dtb3 = load_master_data()
    sig, _ = compute_signals(prices, t5, vix, baa, fred_lag=1)
    orig = r16.leverage
    if not levered:
        r16.leverage = lambda past, p1, p4, prm: (0.5, False) if past[0]["fng"] > 85 else (1.0, False)
    try:
        r = r16.simulate(sig, prices, dtb3, 0, 0, 1, 0)["monthly_ret"]
    finally:
        r16.leverage = orig
    r.index = r.index.to_period("M").to_timestamp("M")
    return r, dtb3


def main() -> int:
    ic2, dtb3 = ic_monthly(True)
    ic1, _ = ic_monthly(False)
    px = load_prices()
    rf = (dtb3.reindex(px.index).ffill() / 100 / 252).fillna(0)
    strat = {"GIST": backtest(px, gist_fn(px), rf, "1999-01-01"),
             "RMOM": backtest(px, rmom_fn(px), rf, "2004-01-01"),
             "AAA": backtest(px, aaa_fn(px), rf, "2004-01-01")}
    last = pd.Timestamp.today().to_period("M").to_timestamp("M") - pd.offsets.MonthEnd(1)
    print("■ 단독 (자체 전 기간)")
    for k, r in strat.items():
        r = r[r.index <= last]
        s = stats(r)
        print(f"| {k} | {r.index[0]:%Y-%m}~{r.index[-1]:%Y-%m} | {s['CAGR']:.2%} | {s['MDD']:.2%} | {s['Calmar']:.2f} | {s['Vol']:.1%} | {s['worst']:+.1%} |")
    df = pd.DataFrame({"IC확정": ic2, "IC연금": ic1, **strat}).dropna()
    df = df[df.index <= last]
    print(f"\n■ 공통 기간 {df.index[0]:%Y-%m} ~ {df.index[-1]:%Y-%m} ({len(df)}개월)")
    for k in df:
        s = stats(df[k])
        print(f"| {k} | {s['CAGR']:.2%} | {s['MDD']:.2%} | {s['Calmar']:.2f} | {s['Vol']:.1%} |")
    print("\n상관\n", df.corr().round(2).to_string())
    for base in ("IC확정", "IC연금"):
        d = df[df[base] < 0]
        print(f"{base} 손실 달 상관:", d.corr()[base].drop(["IC확정", "IC연금"]).round(2).to_dict())
    halves = {"전체": df, "전반": df.loc[:"2015-12-31"], "후반": df.loc["2016-01-31":]}
    for base in ("IC확정", "IC연금"):
        print(f"\n■ {base} 와 혼합 (월말 재조정)")
        for k in strat:
            for w in (1.0, 0.7, 0.5):
                cells = []
                for h, d in halves.items():
                    s = stats(mix(d[base], d[k], w) if w < 1 else d[base])
                    cells.append(f"{s['CAGR']:.1%} / {s['MDD']:.1%}")
                print(f"| {base} {int(w * 100)} + {k} {int(round((1 - w) * 100))} | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
