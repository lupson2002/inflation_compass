"""성장+인플레 칸(현행 XLE) 자산 탐색 → 후보 모멘텀 1위 테스트 (reflation_cell_prereg.md, 6086df7). 운용 반영 아님.

    python3 research_reflation_cell.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

import run_16_matrix_experiments as r16
from research_cssa_strategies import mix, stats
from research_stagflation_assets import episodes, summarize
from test_all_16_combinations import _fred, compute_signals, load_master_data

LAST = pd.Timestamp("2026-09-30")
UNIVERSE = ["XLE", "XLB", "XLI", "XLF", "XLK", "XLY", "XLP", "XLV", "XLU", "SPY", "IWM", "EFA", "EEM", "GLD", "DBC", "TIP", "IEF"]
HALF = ("2014-12-31", "2015-01-31")


def add_columns(sig: pd.DataFrame, px: pd.DataFrame, tickers) -> pd.DataFrame:
    extra = {}
    for t in tickers:
        p = px[t]
        r = {n: p / p.shift(n) - 1 for n in (21, 63, 126, 252)}
        extra[f"mom136_{t}"] = (r[21] + r[63] + r[126]) / 3
        extra[f"mom63_{t}"], extra[f"mom126_{t}"], extra[f"mom252_{t}"] = r[63], r[126], r[252]
        extra[f"{t.lower()}_up"] = p > p.rolling(200).mean()
    e = pd.DataFrame(extra).reindex(sig.index)
    return pd.concat([sig.drop(columns=[c for c in e.columns if c in sig.columns]), e], axis=1)


def main() -> int:
    prices, t5, vix, baa, dtb3 = load_master_data()
    sig, _ = compute_signals(prices, t5, vix, baa, fred_lag=1)
    miss = [t for t in UNIVERSE if t not in prices]
    ext = yf.download(miss, start="1998-01-01", auto_adjust=True, progress=False)["Close"]
    px = prices.copy()
    for t in miss:
        px[t] = ext[t].reindex(px.index).ffill()
    me = [pd.Timestamp(d) for d in sorted(sig.groupby([sig.index.year, sig.index.month]).apply(lambda x: x.index[-1]).values)]
    cpi = _fred("CPIAUCSL")
    cpi.index = cpi.index.to_period("M").to_timestamp("M")
    rows, infl = {}, {}
    for d0, d1 in zip(me[:-1], me[1:]):
        s = sig.loc[d0]
        if not (s["growth_on"] and s["inflation_on"]) or d1 > LAST + pd.offsets.MonthEnd(0):
            continue
        m0 = d0.to_period("M").to_timestamp("M")
        rows[m0] = px.loc[d1, UNIVERSE] / px.loc[d0, UNIVERSE] - 1
        m1 = d1.to_period("M").to_timestamp("M")
        infl[m0] = float(cpi.loc[m1] / cpi.loc[m1 - pd.offsets.MonthEnd(1)] - 1) if m1 in cpi.index else 0.0
    RR = pd.DataFrame(rows).T
    inf = pd.Series(infl)
    pct = lambda x: f"{x:+.1%}" if isinstance(x, float) else x
    tops = {}
    for lab, sub in (("전체", RR), ("전반 2003-09~2014", RR.loc[:HALF[0]]), ("후반 2015~2026-09", RR.loc[HALF[1]:])):
        cols = [c for c in sub if sub[c].notna().all()]
        S = sub[cols]
        eps = episodes(S.index)
        T = summarize(S, inf.loc[S.index], eps, "IEF")
        T = T.sort_values("연환산", ascending=False)
        tops[lab] = list(T.index[:5])
        print(f"\n■ 성장+인플레 칸 — {lab}: {len(S)}개월 · 에피소드 {len(eps)}개 (누락 자산: {sorted(set(UNIVERSE) - set(cols))})")
        print(T.map(pct).to_string())
    both = [a for a in tops["전반 2003-09~2014"] if a in tops["후반 2015~2026-09"]]
    cands = tuple(dict.fromkeys(["XLE"] + both))
    print(f"\n■ 후보 규칙: 전반 상위5 {tops['전반 2003-09~2014']} · 후반 상위5 {tops['후반 2015~2026-09']} → 후보 {cands}")
    if len(cands) < 2:
        print("XLE 외 통과 자산 없음 → 시험 종료(칸 유지)")
        return 0
    sig2 = add_columns(sig, px, cands)
    pent = pd.read_csv("data/pension_mix_backtest.csv", index_col=0, parse_dates=True)["PENT"]
    pent.index = pent.index.to_period("M").to_timestamp("M")
    pens = lambda past, p1, p4, prm: (0.5, False) if past[0]["fng"] > 85 else (1.0, False)
    orig = r16.leverage
    out, mon = {}, {}
    for name, mode in {"XLE100 (현행)": "xle", "모멘텀 1·3·6 (주)": "mom136", "민감도 3개월": "mom63", "민감도 6개월": "mom126",
                       "민감도 12개월": "mom252", "민감도 1·3·6+절대": "mom136abs"}.items():
        prm = r16.Params(reflation_cell=mode, reflation_candidates=cands)
        for acct in ("일반", "연금"):
            if acct == "연금":
                r16.leverage = pens
            try:
                res = r16.simulate(sig2, px, dtb3, 0, 0, 1, 0, prm)
            finally:
                r16.leverage = orig
            m = res["monthly_ret"]
            m.index = m.index.to_period("M").to_timestamp("M")
            m = m[m.index <= LAST]
            mon[(acct, name)] = m
            s = stats(m)
            d = {"CAGR": s["CAGR"], "MDD일": res["MDD"], "최악월": s["worst"], "Calmar": s["Calmar"],
                 "전반": stats(m.loc[:HALF[0]])["CAGR"], "후반": stats(m.loc[HALF[1]:])["CAGR"],
                 "2008": (1 + m.loc["2008"]).prod() - 1, "2022": (1 + m.loc["2022"]).prod() - 1}
            out[(acct, name)] = d
            if acct == "연금":
                x = pd.concat({"IC": m, "PENT": pent}, axis=1).dropna()
                mm = mix(x["IC"], x["PENT"], 0.5)
                sm = stats(mm)
                out[("연금혼합", name)] = {"CAGR": sm["CAGR"], "MDD일": sm["MDD"], "최악월": sm["worst"], "Calmar": sm["Calmar"],
                                        "전반": stats(mm.loc[:HALF[0]])["CAGR"], "후반": stats(mm.loc[HALF[1]:])["CAGR"],
                                        "2008": (1 + mm.loc["2008"]).prod() - 1, "2022": (1 + mm.loc["2022"]).prod() - 1}
    print("\n■ 테스트 (운용 엔진: 침체 IEF100 · 인플레만 XLU · 보험 GLD10/BIL5)")
    print(pd.DataFrame(out).T.map(lambda x: f"{x:+.1%}").to_string())
    pick = {}
    for d0 in me:
        s = sig2.loc[d0]
        if s["growth_on"] and s["inflation_on"] and d0 <= LAST:
            pick[f"{d0:%Y-%m}"] = r16.reflation_asset(s, r16.Params(reflation_cell="mom136", reflation_candidates=cands))
    vc = pd.Series(pick).value_counts()
    print("\n■ 주 정의 선택 빈도:", vc.to_dict())
    ser = pd.Series(pick)
    runs = (ser != ser.shift()).cumsum()
    print("  구간:", " · ".join(f"{g.index[0]}~{g.index[-1]} {g.iloc[0]}" for _, g in ser.groupby(runs)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
