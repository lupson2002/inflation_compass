"""인플레만 칸 = GLD·XLU·XLE 모멘텀 1위 테스트 (infl_cell_momentum_prereg.md, 9c3c064). 운용 반영 아님 — 연구용.

    python3 research_infl_cell_momentum.py
"""
from __future__ import annotations

import pandas as pd

import research_longrun_ic as L
import research_longrun_momentum as LM
import run_16_matrix_experiments as r16
from research_cssa_strategies import mix, stats
from test_all_16_combinations import compute_signals, load_master_data

LAST = pd.Timestamp("2026-09-30")
VARIANTS = {"XLU100 (현행)": "xlu", "모멘텀 1·3·6 (주)": "mom136", "민감도 3개월": "mom63", "민감도 6개월": "mom126",
            "민감도 12개월": "mom252", "민감도 1·3·6+절대필터": "mom136abs"}


def main() -> int:
    prices, t5, vix, baa, dtb3 = load_master_data()
    sig, _ = compute_signals(prices, t5, vix, baa, fred_lag=1)
    pent = pd.read_csv("data/pension_mix_backtest.csv", index_col=0, parse_dates=True)["PENT"]
    pent.index = pent.index.to_period("M").to_timestamp("M")
    pens = lambda past, p1, p4, prm: (0.5, False) if past[0]["fng"] > 85 else (1.0, False)
    orig = r16.leverage
    rows, monthly = {}, {}
    for name, cell in VARIANTS.items():
        prm = r16.Params(infl_cell=cell)
        for acct in ("일반", "연금"):
            if acct == "연금":
                r16.leverage = pens
            try:
                res = r16.simulate(sig, prices, dtb3, 0, 0, 1, 0, prm)
            finally:
                r16.leverage = orig
            m = res["monthly_ret"]
            m.index = m.index.to_period("M").to_timestamp("M")
            m = m[m.index <= LAST]
            monthly[(acct, name)] = m
            s = stats(m)
            d = {"CAGR": s["CAGR"], "MDD일": res["MDD"], "최악월": s["worst"], "Calmar": s["Calmar"],
                 "2008": (1 + m.loc["2008"]).prod() - 1, "2022": (1 + m.loc["2022"]).prod() - 1,
                 "2021-03~(연)": (1 + m.loc["2021-03":]).prod() ** (12 / len(m.loc["2021-03":])) - 1}
            rows[(acct, name)] = d
            if acct == "연금":
                x = pd.concat({"IC": m, "PENT": pent}, axis=1).dropna()
                mm = mix(x["IC"], x["PENT"], 0.5)
                sm = stats(mm)
                rows[("연금혼합", name)] = {"CAGR": sm["CAGR"], "MDD일": sm["MDD"], "최악월": sm["worst"], "Calmar": sm["Calmar"],
                                         "2008": (1 + mm.loc["2008"]).prod() - 1, "2022": (1 + mm.loc["2022"]).prod() - 1,
                                         "2021-03~(연)": (1 + mm.loc["2021-03":]).prod() ** (12 / len(mm.loc["2021-03":])) - 1}
    T = pd.DataFrame(rows).T
    print(T.map(lambda x: f"{x:+.1%}").to_string())
    # 칸이 켜진 달: 선택 자산과 다음 달 수익
    me = [pd.Timestamp(d) for d in sorted(sig.groupby([sig.index.year, sig.index.month]).apply(lambda x: x.index[-1]).values)]
    rec = []
    for d0, d1 in zip(me[:-1], me[1:]):
        s = sig.loc[d0]
        if s["growth_on"] or not s["inflation_on"] or d1 > LAST + pd.offsets.MonthEnd(0):
            continue
        row = {"월": f"{d0:%Y-%m}"}
        for name, cell in (("주", "mom136"), ("3m", "mom63"), ("12m", "mom252")):
            a = r16.infl_cell_asset(s, r16.Params(infl_cell=cell))
            row[name] = a
        for t in ("XLU", "GLD", "XLE"):
            row[f"{t}%"] = round((prices.loc[d1, t] / prices.loc[d0, t] - 1) * 100, 1)
        m1 = d1.to_period("M").to_timestamp("M")
        row["현행 일반%"] = round(monthly[("일반", "XLU100 (현행)")].get(m1, float("nan")) * 100, 1)
        row["모멘텀 일반%"] = round(monthly[("일반", "모멘텀 1·3·6 (주)")].get(m1, float("nan")) * 100, 1)
        rec.append(row)
    print("\n■ 인플레만 칸 달별 선택\n" + pd.DataFrame(rec).to_string(index=False))
    # 초장기 보조: 주식 vs 금 모멘텀 1위
    t1, sig1, _, _, cpi = LM.tiers()
    wb = pd.read_csv(L.D / "worldbank_cmo_monthly.csv", parse_dates=["date"]).set_index("date")["gold"]
    R = t1.copy()
    R["gold"] = (wb / wb.shift(1) - 1).reindex(R.index)
    R = R.loc["1971-09-30":]
    mom = {c: ((1 + R[c]).rolling(1).apply(lambda x: x.prod(), raw=True) - 1 + (1 + R[c]).rolling(3).apply(lambda x: x.prod(), raw=True) - 1
               + (1 + R[c]).rolling(6).apply(lambda x: x.prod(), raw=True) - 1) / 3 for c in ("us", "gold")}

    def rule(use_mom):
        def f(d):
            s = sig1.loc[d]
            if s.growth:
                w = {"us": 1.0}
            elif s.inflation:
                w = {(max(("us", "gold"), key=lambda c: mom[c].loc[d]) if use_mom else "us"): 1.0}
            elif s.bond_shield:
                w = {"cash": 1.0}
            else:
                w = {"bond": 1.0}
            w = {k: v * 0.85 for k, v in w.items()}
            w["gold"] = w.get("gold", 0) + 0.10
            w["cash"] = w.get("cash", 0) + 0.05
            return w
        return f
    M = pd.DataFrame({"주식100(현행 대리)": LM.run(R, rule(False), 2, "1972-06-30"),
                      "주식·금 모멘텀 1위": LM.run(R, rule(True), 2, "1972-06-30")}).dropna().loc[:"2025-12-31"]
    print("\n■ 초장기 보조 1972~2025 (Shiller + WB 금)")
    print(pd.DataFrame({k: L.stats(M[k], cpi) for k in M}).T[["CAGR", "실질CAGR", "MDD", "최악12개월"]].map(lambda x: f"{x:+.1%}").to_string())
    for w, (a, b) in {"1973~74": ("1973", "1974"), "1977~80": ("1977", "1980"), "1990": ("1990", "1990"),
                      "2007-10~09-03": ("2007-10", "2009-03"), "2022": ("2022", "2022")}.items():
        print(f"  {w}: " + " · ".join(f"{k} {(1 + M.loc[a:b, k]).prod() - 1:+.1%}" for k in M))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
