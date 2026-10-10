"""IC × GEM 장점 결합 · 인플레 시대형 변형 · GEM 정밀 재현 — 규칙은 ic_gem_hybrid_prereg.md 에 먼저 고정(a29bcdb).

    python3 research_ic_gem_hybrid.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

import research_longrun_ic as L
import run_16_matrix_experiments as r16
from research_cssa_strategies import backtest, mix, stats
from test_all_16_combinations import _fred, compute_signals, load_master_data

LAST = pd.Timestamp("2026-09-30")
CELLS = {  # 이름: (침체 칸 Params.recession, 인플레만 칸 비중)
    "V0 현행": ("xlp_ief", {"XLU": 1.0}),
    "S1 결합(침체 IEF100)": ("ief", {"XLU": 1.0}),
    "S2 결합+인플레칸 XLU50/BIL50": ("ief", {"XLU": 0.5, "BIL": 0.5}),
    "E1 인플레형 XLU50/GLD50": ("ief", {"XLU": 0.5, "GLD": 0.5}),
    "E2 인플레형 DBC50/GLD50": ("ief", {"DBC": 0.5, "GLD": 0.5}),
}
WINDOWS = {"2008": ("2008-01", "2008-12"), "2011-05~09": ("2011-05", "2011-09"), "2018-10~12": ("2018-10", "2018-12"),
           "2020-02~03": ("2020-02", "2020-03"), "2022": ("2022-01", "2022-12"),
           "인플레기 2004-01~08-07": ("2004-01", "2008-07"), "인플레기 2021-03~26-09": ("2021-03", "2026-09")}


def ic_runs(sig, prices, dtb3):
    orig_rw, orig_lev = r16.regime_weights, r16.leverage
    out = {}
    for name, (rec, cell) in CELLS.items():
        def rw(row, p2, p3, prm, ief_ma, _cell=cell):
            w = orig_rw(row, p2, p3, prm, ief_ma)
            return dict(_cell) if w == {"XLU": 1.0} else w
        for acct in ("일반", "연금"):
            r16.regime_weights = rw
            if acct == "연금":
                r16.leverage = lambda past, p1, p4, prm: (0.5, False) if past[0]["fng"] > 85 else (1.0, False)
            try:
                res = r16.simulate(sig, prices, dtb3, 0, 0, 1, 0, r16.Params(recession=rec))
            finally:
                r16.regime_weights, r16.leverage = orig_rw, orig_lev
            m = res["monthly_ret"]
            m.index = m.index.to_period("M").to_timestamp("M")
            out[(acct, name)] = (m[m.index <= LAST], res)
    return out


def gem_runs(dtb3):
    px = yf.download(["SPY", "EFA", "VEU", "AGG"], start="2002-01-01", auto_adjust=True, progress=False)["Close"]
    rf_d = (dtb3.reindex(px.index).ffill() / 100 / 252).fillna(0)
    cash_idx = (1 + rf_d).cumprod()
    px["CASH"] = cash_idx

    def gem(ex):
        def f(d):
            h = px.loc[:d]
            me = h.groupby([h.index.year, h.index.month]).tail(1)
            if len(me) < 13 or me[["SPY", ex, "AGG"]].iloc[-13].isna().any():
                return None
            r12 = me.iloc[-1] / me.iloc[-13] - 1
            if not r12["SPY"] > r12["CASH"]:
                return {"AGG": 1.0}
            return {ex: 1.0} if r12[ex] > r12["SPY"] else {"SPY": 1.0}
        return f
    out = {}
    for ex, start in (("EFA", "2004-09-01"), ("VEU", "2008-03-01")):
        m = backtest(px.drop(columns="CASH"), gem(ex), rf_d, start)
        out[f"GEM({ex})"] = m[m.index <= LAST]
    return out


def real_cagr(m: pd.Series, cpi: pd.Series) -> float:
    infl = cpi.reindex(m.index).pct_change().fillna(0)
    return float(((1 + m) / (1 + infl)).prod() ** (12 / len(m)) - 1)


def table(S: dict, cpi: pd.Series, extra: dict | None = None) -> pd.DataFrame:
    rows = {}
    for k, m in S.items():
        s = stats(m)
        d = {"CAGR": s["CAGR"], "실질": real_cagr(m, cpi), "MDD월": s["MDD"], "최악월": s["worst"], "Calmar": s["Calmar"]}
        for w, (a, b) in WINDOWS.items():
            sub = m.loc[a:b]
            if len(sub) > 24:
                d[w] = (1 + sub).prod() ** (12 / len(sub)) - 1          # 긴 구간은 연환산
            elif len(sub):
                d[w] = (1 + sub).prod() - 1
        if extra and k in extra:
            d.update(extra[k])
        rows[k] = d
    return pd.DataFrame(rows).T


def longrun_variant() -> None:
    df, _ = L.load()

    def rule(bond100: bool, half: bool):
        def f(r):
            if r.growth:
                w = {"stock": 1.0}
            elif r.inflation:
                w = {"stock": 0.5, "cash": 0.5} if half else {"stock": 1.0}
            elif r.bond_shield:
                w = {"cash": 1.0}
            else:
                w = {"bond": 1.0} if bond100 else {"stock": 0.5, "bond": 0.5}
            w = {k: v * 0.85 for k, v in w.items()}
            w["cash"] = w.get("cash", 0) + 0.15
            return w
        return f
    M = pd.DataFrame({"뼈대(침체 주식50/채권50)": L.run(df, rule(False, False)),
                      "뼈대(침체 채권100)": L.run(df, rule(True, False)),
                      "뼈대(침체 채권100 · 인플레칸 50/50)": L.run(df, rule(True, True))}).dropna()
    print("\n■ 초장기 대리 1872~ (Shiller, 보험 15 포함)")
    t = pd.DataFrame({k: L.stats(M[k], df.cpi) for k in M}).T[["CAGR", "실질CAGR", "MDD", "최악12개월"]]
    print(t.map(lambda x: f"{x:+.1%}").to_string())
    t2 = pd.DataFrame({k: L.stats(M.loc["1946":, k], df.cpi) for k in M}).T[["CAGR", "MDD", "최악12개월"]]
    print("[1946~]\n" + t2.map(lambda x: f"{x:+.1%}").to_string())
    for w, (a, b) in {"1929-09~32-06": ("1929-09", "1932-06"), "1937~38": ("1937", "1938"), "1942~51": ("1942", "1951"),
                      "1966~82": ("1966", "1982"), "1973~74": ("1973", "1974"), "2007-10~09-03": ("2007-10", "2009-03"),
                      "2022": ("2022", "2022")}.items():
        infl = float(df.cpi.loc[b:].iloc[0] / df.cpi.loc[:a].iloc[-1] - 1)
        print(f"  {w}: " + " · ".join(f"{k} {(1 + M.loc[a:b, k]).prod() - 1:+.1%} (실질 {(1 + M.loc[a:b, k]).prod() / (1 + infl) - 1:+.1%})" for k in M))


def main() -> int:
    prices, t5, vix, baa, dtb3 = load_master_data()
    sig, _ = compute_signals(prices, t5, vix, baa, fred_lag=1)
    cpi = _fred("CPIAUCSL")
    cpi.index = cpi.index.to_period("M").to_timestamp("M")
    cpi = cpi.shift(0)
    ic = ic_runs(sig, prices, dtb3)
    gem = gem_runs(dtb3)
    pent = pd.read_csv("data/pension_mix_backtest.csv", index_col=0, parse_dates=True)["PENT"]
    pent.index = pent.index.to_period("M").to_timestamp("M")
    pct = lambda x: f"{x:+.1%}" if pd.notna(x) else "—"
    for acct in ("일반", "연금"):
        S = {k: ic[(acct, k)][0] for k in CELLS}
        extra = {k: {"MDD일": ic[(acct, k)][1]["MDD"]} for k in CELLS}
        print(f"\n■ IC 변형 — {acct}계좌 (2003-09~2026-09)")
        print(table(S, cpi, extra).map(pct).to_string())
    print("\n■ 공통 기간 2004-10~ : IC 일반 S1 · E1 vs GEM vs 혼합 50/50")
    base = {"S1 일반": ic[("일반", "S1 결합(침체 IEF100)")][0], "E1 일반": ic[("일반", "E1 인플레형 XLU50/GLD50")][0],
            "S1 연금": ic[("연금", "S1 결합(침체 IEF100)")][0], "E1 연금": ic[("연금", "E1 인플레형 XLU50/GLD50")][0]}
    df = pd.DataFrame({**base, **gem}).loc["2004-10-31":].dropna(subset=["GEM(EFA)"])
    S = {k: df[k].dropna() for k in df}
    for k in ("S1 일반", "E1 일반", "S1 연금", "E1 연금"):
        S[f"{k} 50 + GEM 50"] = mix(df[k], df["GEM(EFA)"], 0.5)
    print(table(S, cpi).map(pct).to_string())
    print("상관(월):", df[["S1 일반", "S1 연금", "GEM(EFA)"]].corr().round(2).to_dict())
    print("\n■ 연금 혼합 (IC 연금형 50 + PENTARCH 50, 2008-02~)")
    P = {}
    for k in ("V0 현행", "S1 결합(침체 IEF100)", "E1 인플레형 XLU50/GLD50", "E2 인플레형 DBC50/GLD50"):
        x = pd.concat({"IC": ic[("연금", k)][0], "PENT": pent}, axis=1).dropna()
        P[k + " +PENT"] = mix(x["IC"], x["PENT"], 0.5)
    print(table(P, cpi).map(pct).to_string())
    longrun_variant()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
