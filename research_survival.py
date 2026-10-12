"""IC + PENTARCH + 금 10% + 현금 5% 생존 검증 — 규칙은 survival_prereg.md 에 먼저 고정(1bbad36).

    python3 research_survival.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

import research_longrun_ic as L
import research_longrun_momentum as LM
from test_all_16_combinations import _fred

D = L.D
LAST = pd.Timestamp("2026-09-30")
COST_BP = 30
PORTS = {"S: IC42.5+PENT42.5+금10+현금5": {"IC": .425, "PENT": .425, "GLD": .10, "BIL": .05},
         "M: IC50+PENT50 (현행)": {"IC": .5, "PENT": .5},
         "60/40": {"SPY": .6, "IEF": .4},
         "S&P500": {"SPY": 1.0}}
WINDOWS = {"2008": ("2008-01", "2008-12"), "2011-05~09": ("2011-05", "2011-09"), "2015-06~16-02": ("2015-06", "2016-02"),
           "2018-10~12": ("2018-10", "2018-12"), "2020-02~03": ("2020-02", "2020-03"), "2022": ("2022-01", "2022-12"),
           "2025-02~04": ("2025-02", "2025-04")}
PROXY_WINDOWS = {"1994 채권폭락": ("1994-02", "1994-11"), "1997~98 아시아·LTCM": ("1997-07", "1998-10"),
                 "2000-03~02-09 닷컴": ("2000-03", "2002-09"), "2007-10~08-01": ("2007-10", "2008-01")}


def me(idx) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(idx).to_period("M").to_timestamp("M")


def mix(R: pd.DataFrame, w: dict) -> pd.Series:
    cols = list(w)
    wv = np.array([w[c] for c in cols])
    out = []
    for r in R[cols].values:
        g = float(wv @ r)
        drift = wv * (1 + r) / (1 + g)
        out.append((1 + g) * (1 - np.abs(drift - wv).sum() * COST_BP / 1e4) - 1)
    return pd.Series(out, index=R.index)


def actual() -> pd.DataFrame:
    bt = pd.read_csv("data/pension_mix_backtest.csv", index_col=0, parse_dates=True)[["IC", "PENT"]]
    bt.index = me(bt.index)
    px = yf.download(["GLD", "BIL", "SPY", "IEF"], start="2007-01-01", auto_adjust=True, progress=False)["Close"]
    m = px.groupby([px.index.year, px.index.month]).tail(1)
    m.index = me(m.index)
    r = m.pct_change()
    return bt.join(r, how="left").loc[:LAST].dropna()


def proxy() -> pd.DataFrame:
    """1994-01 ~ 2008-01 대리: IC 뼈대(현행 구조 대리) · PENT 확장 · WB 금 · TB3MS · Shiller 주식·10년채."""
    t1, sig1, _, _, cpi = LM.tiers()
    wb = pd.read_csv(D / "worldbank_cmo_monthly.csv", parse_dates=["date"]).set_index("date")["gold"]
    R = t1.copy()
    R["gold"] = (wb / wb.shift(1) - 1).reindex(R.index)

    def ic_rule(d):
        s = sig1.loc[d]
        if s.growth or s.inflation:
            w = {"us": 1.0}
        elif s.bond_shield:
            w = {"cash": 1.0}
        else:
            w = {"bond": 1.0}
        w = {k: v * 0.85 for k, v in w.items()}
        w["gold"] = w.get("gold", 0) + 0.10
        w["cash"] = w.get("cash", 0) + 0.05
        return w
    ic = LM.run(R.loc["1991-01-31":], ic_rule, 2, "1993-06-30")
    pent = pd.read_csv(D / "pent_v183_nolev_ext_monthly.csv", index_col=0, parse_dates=True)["PENT_ext"]
    pent.index = me(pent.index)
    out = pd.DataFrame({"IC": ic, "PENT": pent, "GLD": R["gold"], "BIL": R["cash"], "SPY": R["us"], "IEF": R["bond"]})
    return out.loc["1994-01-31":"2008-01-31"].dropna()


def cpi_infl(idx) -> pd.Series:
    c = _fred("CPIAUCSL")
    c.index = me(c.index)
    return (c / c.shift(1) - 1).reindex(idx).fillna(0)


def krw(idx) -> pd.Series:
    fx = _fred("DEXKOUS")
    m = fx.groupby([fx.index.year, fx.index.month]).tail(1)
    m.index = me(m.index)
    return (m / m.shift(1) - 1).reindex(idx)


def underwater_max(eq: pd.Series) -> int:
    peak, run, best = eq.iloc[0], 0, 0
    for v in eq:
        if v >= peak:
            peak, run = v, 0
        else:
            run += 1
            best = max(best, run)
    return best


def criteria(r: pd.Series, infl: pd.Series, windows: dict) -> dict:
    eq = (1 + r).cumprod()
    real = (1 + r) / (1 + infl) - 1
    req = (1 + real).cumprod()
    r12 = (1 + r).rolling(12).apply(np.prod, raw=True) - 1
    real10 = (1 + real).rolling(120).apply(np.prod, raw=True) - 1
    win = {w: float((1 + r.loc[a:b]).prod() - 1) for w, (a, b) in windows.items() if len(r.loc[a:b])}
    return {"CAGR": eq.iloc[-1] ** (12 / len(r)) - 1, "실질CAGR": req.iloc[-1] ** (12 / len(r)) - 1,
            "MDD": float((eq / eq.cummax() - 1).min()), "최악12개월": float(r12.min()),
            "최악10년실질": float(real10.min()) if real10.notna().any() else np.nan,
            "최장회복(월)": underwater_max(eq), "windows": win}


def bootstrap(R: pd.DataFrame, infl: pd.Series, w: dict, n=10000, months=240, block=12, seed=20261013) -> dict:
    rng = np.random.default_rng(seed)
    X = R[list(w)].values
    I = infl.reindex(R.index).values
    T = len(X)
    wv = np.array(list(w.values()))
    mdds, reals, cagrs = np.empty(n), np.empty(n), np.empty(n)
    p = 1.0 / block
    for k in range(n):
        idx = np.empty(months, dtype=int)
        i = rng.integers(T)
        for t in range(months):
            if t > 0 and rng.random() < p:
                i = rng.integers(T)
            idx[t] = i
            i = (i + 1) % T
        g = X[idx] @ wv
        eq = np.cumprod(1 + g)
        mdds[k] = (eq / np.maximum.accumulate(eq) - 1).min()
        cagrs[k] = eq[-1] ** (12 / months) - 1
        reals[k] = np.prod((1 + g) / (1 + I[idx])) - 1
    return {"P(MDD≤−40%)": float((mdds <= -0.40).mean()), "P(MDD≤−30%)": float((mdds <= -0.30).mean()),
            "P(20년 실질<0)": float((reals < 0).mean()), "MDD 중앙/5%": (float(np.median(mdds)), float(np.quantile(mdds, 0.05))),
            "CAGR 중앙/5%": (float(np.median(cagrs)), float(np.quantile(cagrs, 0.05)))}


def main() -> int:
    A = actual()
    P = proxy()
    infl_a, infl_p = cpi_infl(A.index), cpi_infl(P.index)
    pct = lambda x: f"{x:+.1%}" if isinstance(x, float) else x
    print(f"■ 실데이터 {A.index[0]:%Y-%m} ~ {A.index[-1]:%Y-%m} ({len(A)}개월)")
    rows, wins = {}, {}
    for name, w in PORTS.items():
        c = criteria(mix(A, w), infl_a, WINDOWS)
        wins[name] = c.pop("windows")
        rows[name] = c
    print(pd.DataFrame(rows).T.map(lambda x: pct(x) if isinstance(x, float) else x).to_string())
    print(pd.DataFrame(wins).T.map(pct).to_string())
    print(f"\n■ 대리 구간 {P.index[0]:%Y-%m} ~ {P.index[-1]:%Y-%m} ({len(P)}개월, IC=뼈대 대리)")
    rows, wins = {}, {}
    for name, w in PORTS.items():
        c = criteria(mix(P, w), infl_p, PROXY_WINDOWS)
        wins[name] = c.pop("windows")
        rows[name] = c
    print(pd.DataFrame(rows).T.map(lambda x: pct(x) if isinstance(x, float) else x).to_string())
    print(pd.DataFrame(wins).T.map(pct).to_string())
    print("\n■ 이어붙인 1994~2026 (2008-01 까지 대리)")
    C = pd.concat([P, A])
    infl_c = cpi_infl(C.index)
    for name in list(PORTS)[:2]:
        c = criteria(mix(C, PORTS[name]), infl_c, {})
        c.pop("windows")
        print(" ", name, {k: pct(v) if isinstance(v, float) else v for k, v in c.items()})
    print("\n■ 원화 환산 (한국 투자자)")
    for nm, R_, wnd in (("실데이터", A, WINDOWS), ("대리", P, PROXY_WINDOWS)):
        fx = krw(R_.index).fillna(0)
        for name in list(PORTS)[:2]:
            rk = (1 + mix(R_, PORTS[name])) * (1 + fx) - 1
            c = criteria(rk, pd.Series(0, index=R_.index), wnd)
            wk = c.pop("windows")
            print(f"  {nm} {name}: CAGR {c['CAGR']:+.1%} MDD {c['MDD']:+.1%} 최악12 {c['최악12개월']:+.1%} | "
                  + " ".join(f"{k} {v:+.1%}" for k, v in wk.items()))
    print("\n■ 붓스트랩 (20년 경로 10,000개, 평균 12개월 블록)")
    for lab, src in (("전체 2008~2026", A), ("나쁜 시대 2008~2016 만", A.loc[:"2016-12-31"])):
        for name in list(PORTS)[:2]:
            b = bootstrap(src, cpi_infl(src.index), PORTS[name])
            print(f"  [{lab}] {name}: " + " · ".join(f"{k} {v[0]:+.1%}/{v[1]:+.1%}" if isinstance(v, tuple) else f"{k} {v:.1%}" for k, v in b.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
