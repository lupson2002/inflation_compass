"""'인플레만' 칸(성장↓·인플레↑) 시기 전수 탐색 → 자산 비교 → 선정 규칙 → 재테스트. 규칙: stagflation_asset_prereg.md(35a423f).

    python3 research_stagflation_assets.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

import research_longrun_ic as L
import research_longrun_momentum as LM
import run_16_matrix_experiments as r16
from research_cssa_strategies import mix, stats
from test_all_16_combinations import _fred, compute_signals, load_master_data

LAST = pd.Timestamp("2026-09-30")


def episodes(months: pd.DatetimeIndex) -> list[list[pd.Timestamp]]:
    out, cur = [], []
    for d in months:
        if cur and (d.to_period("M") - cur[-1].to_period("M")).n != 1:
            out.append(cur)
            cur = []
        cur.append(d)
    return out + ([cur] if cur else [])


def summarize(R: pd.DataFrame, infl: pd.Series, eps: list, cash: str) -> pd.DataFrame:
    """R: 결정월 인덱스 → 다음 보유 기간 수익(자산별), infl: 같은 기간 CPI 변화."""
    rows = {}
    n = len(R)
    for a in R:
        r = R[a]
        real = (1 + r) / (1 + infl) - 1
        ep = [float((1 + R.loc[e, a]).prod() - 1) for e in eps]
        rows[a] = {"연환산": (1 + r).prod() ** (12 / n) - 1, "실질연환산": (1 + real).prod() ** (12 / n) - 1,
                   "승률": (r > 0).mean(), "최악월": r.min(), "최악에피소드": min(ep), "중앙에피소드": float(np.median(ep))}
    T = pd.DataFrame(rows).T
    wins = pd.Series(0, index=R.columns)
    for e in eps:
        wins[R.loc[e].add(1).prod().idxmax()] += 1
    T["에피소드1위"] = wins
    return T.sort_values("실질연환산", ascending=False)


def longrun_part():
    df, _ = L.load()
    wb = pd.read_csv(L.D / "worldbank_cmo_monthly.csv", parse_dates=["date"]).set_index("date")
    nxt = lambda s: s.shift(-1) / s - 1                      # 행 t = t→t+1 (월평균)
    R = pd.DataFrame({"주식": df["r_stock"], "10년채": df["r_bond"], "현금": df["r_cash"],
                      "금": nxt(wb["gold"]).reindex(df.index), "원유": nxt(wb["oil"]).reindex(df.index),
                      "WB에너지": nxt(wb["energy"]).reindex(df.index), "WB비에너지": nxt(wb["nonenergy"]).reindex(df.index)})
    cpi_n = nxt(df["cpi"])
    cell = (~df["growth"]) & df["inflation"]
    out = {}
    for lab, a, b, cols in (("1960~2002 (금 제외)", "1960-01", "2002-12", ["주식", "10년채", "현금", "원유", "WB에너지", "WB비에너지"]),
                            ("1971-09~2002 (금 포함)", "1971-09", "2002-12", list(R.columns))):
        dm = cell.loc[a:b]
        dm = dm[dm].index
        # 판단 t → 수익 행 t+1 (기존 규칙)
        pos = [df.index.get_loc(d) + 1 for d in dm]
        RR = R.iloc[pos][cols].copy()
        RR.index = dm
        inf = pd.Series(cpi_n.iloc[pos].values, index=dm)
        eps = episodes(dm)
        out[lab] = (summarize(RR.dropna(), inf.loc[RR.dropna().index], [e for e in eps if set(e) <= set(RR.dropna().index)], "현금"), eps)
    return out


def ic_part(sig, prices):
    tick = ["XLU", "GLD", "DBC", "XLE", "XLB", "XLP", "XLV", "SPY", "IEF", "SHY", "BIL"]
    px = prices[tick].copy()
    px["TIP"] = yf.download("TIP", start="2003-01-01", auto_adjust=True, progress=False)["Close"].squeeze().reindex(px.index).ffill()
    me = sorted(sig.groupby([sig.index.year, sig.index.month]).apply(lambda x: x.index[-1]).values)
    me = [pd.Timestamp(d) for d in me]
    cpi = _fred("CPIAUCSL")
    cpi.index = cpi.index.to_period("M").to_timestamp("M")
    rows, infl = {}, {}
    for d0, d1 in zip(me[:-1], me[1:]):
        s = sig.loc[d0]
        if s["growth_on"] or not s["inflation_on"] or d1 > LAST + pd.offsets.MonthEnd(0):
            continue
        rows[d0] = px.loc[d1] / px.loc[d0] - 1
        m1 = d1.to_period("M").to_timestamp("M")
        infl[d0] = float(cpi.loc[m1] / cpi.loc[m1 - pd.offsets.MonthEnd(1)] - 1) if m1 in cpi.index else 0.0
    RR = pd.DataFrame(rows).T.dropna(axis=1, how="all")
    dm = pd.DatetimeIndex(RR.index).to_period("M").to_timestamp("M")
    RR.index = dm
    inf = pd.Series(infl).set_axis(dm)
    eps = episodes(dm)
    return summarize(RR.dropna(), inf, eps, "BIL"), eps, RR


def select(long_T: pd.DataFrame, ic_T: pd.DataFrame) -> dict:
    """사전 고정 규칙: 두 시대 모두 실질 > 현금, 실질 상위 3, 최악 에피소드가 주식(장기)/XLU(실신호)보다 작은 손실."""
    pairs = {"금": "GLD", "원유": "DBC", "WB에너지": "XLE", "WB비에너지": "DBC", "주식": "SPY", "10년채": "IEF", "현금": "BIL"}
    res = {}
    for a_long, a_ic in pairs.items():
        if a_long not in long_T.index or a_ic not in ic_T.index:
            continue
        ok_long = (long_T.loc[a_long, "실질연환산"] > long_T.loc["현금", "실질연환산"]
                   and a_long in long_T.index[:3] and long_T.loc[a_long, "최악에피소드"] > long_T.loc["주식", "최악에피소드"])
        ok_ic = (ic_T.loc[a_ic, "실질연환산"] > ic_T.loc["BIL", "실질연환산"]
                 and a_ic in ic_T.index[:3] and ic_T.loc[a_ic, "최악에피소드"] > ic_T.loc["XLU", "최악에피소드"])
        res[f"{a_long}/{a_ic}"] = (bool(ok_long), bool(ok_ic))
    return res


def retest(sig, prices, dtb3, cells: dict):
    orig_rw, orig_lev = r16.regime_weights, r16.leverage
    pent = pd.read_csv("data/pension_mix_backtest.csv", index_col=0, parse_dates=True)["PENT"]
    pent.index = pent.index.to_period("M").to_timestamp("M")
    rows = {}
    for name, cell in cells.items():
        def rw(row, p2, p3, prm, ief_ma, _c=cell):
            w = orig_rw(row, p2, p3, prm, ief_ma)
            return dict(_c) if w == {"XLU": 1.0} else w
        for acct in ("일반", "연금"):
            r16.regime_weights = rw
            if acct == "연금":
                r16.leverage = lambda past, p1, p4, prm: (0.5, False) if past[0]["fng"] > 85 else (1.0, False)
            try:
                res = r16.simulate(sig, prices, dtb3, 0, 0, 1, 0)
            finally:
                r16.regime_weights, r16.leverage = orig_rw, orig_lev
            m = res["monthly_ret"]
            m.index = m.index.to_period("M").to_timestamp("M")
            m = m[m.index <= LAST]
            s = stats(m)
            d = {"CAGR": s["CAGR"], "MDD일": res["MDD"], "최악월": s["worst"], "Calmar": s["Calmar"]}
            for w, (a, b) in {"2008": ("2008", "2008"), "2022": ("2022", "2022"), "2021-03~": ("2021-03", "2026-09")}.items():
                sub = m.loc[a:b]
                d[w] = (1 + sub).prod() ** (12 / len(sub)) - 1 if len(sub) > 24 else (1 + sub).prod() - 1
            rows[(acct, name)] = d
            if acct == "연금":
                x = pd.concat({"IC": m, "PENT": pent}, axis=1).dropna()
                mm = mix(x["IC"], x["PENT"], 0.5)
                sm = stats(mm)
                rows[("연금혼합", name)] = {"CAGR": sm["CAGR"], "MDD일": sm["MDD"], "최악월": sm["worst"], "Calmar": sm["Calmar"],
                                         "2008": (1 + mm.loc["2008"]).prod() - 1, "2022": (1 + mm.loc["2022"]).prod() - 1,
                                         "2021-03~": (1 + mm.loc["2021-03":]).prod() ** (12 / len(mm.loc["2021-03":])) - 1}
    return pd.DataFrame(rows).T


def longrun_retest():
    t1, sig1, _, _, cpi = LM.tiers()
    wb = pd.read_csv(L.D / "worldbank_cmo_monthly.csv", parse_dates=["date"]).set_index("date")["gold"]
    R = t1.copy()
    R["gold"] = (wb / wb.shift(1) - 1).reindex(R.index)
    R = R.loc["1971-09-30":]

    def rule(cell):
        def f(d):
            s = sig1.loc[d]
            if s.growth:
                w = {"us": 1.0}
            elif s.inflation:
                w = dict(cell)
            elif s.bond_shield:
                w = {"cash": 1.0}
            else:
                w = {"bond": 1.0}
            w = {k: v * 0.85 for k, v in w.items()}
            w["gold"] = w.get("gold", 0) + 0.10
            w["cash"] = w.get("cash", 0) + 0.05
            return w
        return f
    cells = {"주식100(=XLU 자리)": {"us": 1.0}, "금100": {"gold": 1.0}, "주식50+금50": {"us": 0.5, "gold": 0.5}, "주식50+현금50": {"us": 0.5, "cash": 0.5}}
    M = pd.DataFrame({k: LM.run(R, rule(c), 2, "1972-06-30") for k, c in cells.items()}).dropna()
    M = M.loc[:"2025-12-31"]
    t = pd.DataFrame({k: L.stats(M[k], cpi) for k in M}).T[["CAGR", "실질CAGR", "MDD", "최악12개월"]]
    win = {w: {k: f"{(1 + M.loc[a:b, k]).prod() - 1:+.1%}" for k in M} for w, (a, b) in
           {"1973~74": ("1973", "1974"), "1977~80": ("1977", "1980"), "1980~82": ("1980", "1982"), "1990": ("1990", "1990"),
            "2000-03~02-09": ("2000-03", "2002-09"), "2007-10~09-03": ("2007-10", "2009-03"), "2022": ("2022", "2022")}.items()}
    return M, t, pd.DataFrame(win).T


def main() -> int:
    pct = lambda x: f"{x:+.1%}" if isinstance(x, float) else x
    lr = longrun_part()
    for lab, (T, eps) in lr.items():
        print(f"\n■ 장기 {lab}: 인플레만 {sum(len(e) for e in eps)}개월 · 에피소드 {len(eps)}개")
        print("  에피소드:", ", ".join(f"{e[0]:%Y-%m}({len(e)})" for e in eps))
        print(T.map(pct).to_string())
    prices, t5, vix, baa, dtb3 = load_master_data()
    sig, _ = compute_signals(prices, t5, vix, baa, fred_lag=1)
    icT, eps, RR = ic_part(sig, prices)
    print(f"\n■ IC 실신호 2003-09~: 인플레만 {len(RR)}개월 · 에피소드 {len(eps)}개")
    print("  에피소드:", ", ".join(f"{e[0]:%Y-%m}({len(e)})" for e in eps))
    print(icT.map(pct).to_string())
    print("\n  월별 (주요 자산):\n" + (RR[["XLU", "GLD", "DBC", "XLE", "TIP", "IEF", "BIL", "SPY"]] * 100).round(1).to_string())
    sel = select(lr["1971-09~2002 (금 포함)"][0], icT)
    print("\n■ 선정 규칙 (장기 통과, 실신호 통과):", sel)
    cells = {"XLU100 (현행)": {"XLU": 1.0}, "GLD100": {"GLD": 1.0}, "XLU50+GLD50": {"XLU": 0.5, "GLD": 0.5}}
    print("\n■ 재테스트 (운용 엔진, 침체 IEF100·보험 포함)")
    print(retest(sig, prices, dtb3, cells).map(lambda x: f"{x:+.1%}").to_string())
    M, t, win = longrun_retest()
    print(f"\n■ 장기 재테스트 {M.index[0]:%Y-%m}~{M.index[-1]:%Y-%m} (Shiller+WB 금, 보험 금10·현금5, 침체 채권100)")
    print(t.map(lambda x: f"{x:+.1%}").to_string())
    print(win.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
