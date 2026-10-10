"""6인 전문가(논리·경제사·이론경제·사회·기술사·생존론) 개선안 검증 (2026-10-10).

목적은 CAGR 극대화가 아니라 **보험료 측정**: 정상 국면에서 얼마를 내고, 위기 국면에서 얼마를 덜 잃는가.
규칙은 실행 전에 고정했다(아래 값은 메커니즘에서 정한 것이고 결과를 보고 바꾸지 않는다).

  V0  확정 전략(그대로)
  V1  단일 자산 상한 50% — 섹터 100% 칸은 그 섹터 50 + SHY 50 (6/6 합의: 집중)
  V2  '인플레만' 칸 XLU → GLD 50 + SHY 50 (유틸리티 = 채권 대용, 1973~74 붕괴)
  V3  상시 보험 15% — 전략 85% + GLD 10 + BIL 5 (BIL 상장 2007-05 전은 수익 0) (몰수·폐장·가격고정은 신호로 못 잡는다)
  V4  공포 2배 조건 — 보유 위험자산이 전부 자기 200일선 위일 때만 2배 (평균회귀 vs 추세 모순)
  V5  보유 섹터 자기 추세 — XLE/XLK/XLU 가 자기 200일선 아래면 SHY (2000 신호-보유 불일치)
  VB  V1~V5 전부 (적용 순서: V2 → V5 → V1 → V3, 레버리지 V4)
  C9  실질금리 조건 — '성장만' 칸에서 DFII5 가 60거래일 전보다 높으면 XLK 대신 SPY (듀레이션)
  C10 주식-채권 상관 — SPY·IEF 60일 상관 > 0 이면 침체 칸 IEF → SHY, 2배 금지 (국채가 헤지 아님)
레버리지판(일반계좌)과 연금형(레버리지 없음, 탐욕 0.5배만), 연금형은 PENTARCH 비레버리지 50% 혼합까지.

    python3 research_resilience_variants.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import run_16_matrix_experiments as r16
from research_cssa_strategies import mix, stats
from test_all_16_combinations import _fred, compute_signals, load_master_data

SECTORS = ("XLE", "XLK", "XLU")
VARIANTS = {
    "V0 확정": set(), "V1 상한50": {"cap"}, "V2 인플레칸 금": {"infl_gold"}, "V3 보험15": {"sleeve"},
    "V4 2배 추세조건": {"lev_trend"}, "V5 섹터 자기추세": {"own_trend"},
    "VB 전부": {"cap", "infl_gold", "sleeve", "lev_trend", "own_trend"},
    "C9 실질금리": {"real_rate"}, "C10 주식채권상관": {"sb_corr"},
}


def make_rules(prices: pd.DataFrame, flags: set, pension: bool):
    ma = prices.rolling(200, min_periods=150).mean()
    dfii5 = _fred("DFII5").reindex(prices.index).ffill().shift(1)            # 전일 값(실거래 조건)
    rr_up = dfii5 > dfii5.shift(60)
    rets = prices[["SPY", "IEF"]].pct_change()
    sb_pos = rets["SPY"].rolling(60).corr(rets["IEF"]) > 0
    ief_ma_s = prices["IEF"].rolling(200, min_periods=60).mean()
    base_tw, base_lev = r16.target_weights, r16.leverage

    def weights(row, p2, p3, prm, ief_ma):
        d = row.name
        w = dict(base_tw(row, p2, p3, prm, ief_ma))
        if "infl_gold" in flags and w == {"XLU": 1.0}:
            w = {"GLD": 0.5, "SHY": 0.5}
        if "real_rate" in flags and w == {"XLK": 1.0} and bool(rr_up.loc[d]):
            w = {"SPY": 1.0}
        if "sb_corr" in flags and "IEF" in w and bool(sb_pos.loc[d]):
            w = {("SHY" if k == "IEF" else k): v for k, v in w.items()}
        if "own_trend" in flags:
            w = {("SHY" if k in SECTORS and prices.loc[d, k] < ma.loc[d, k] else k): v for k, v in w.items()}
        if "cap" in flags:
            w = {k: v for k, v in w.items()}
            for k in [k for k, v in w.items() if v > 0.5 and k != "SHY"]:
                w["SHY"] = w.get("SHY", 0) + w[k] - 0.5
                w[k] = 0.5
        if "sleeve" in flags:
            w = {k: v * 0.85 for k, v in w.items()}
            w["GLD"] = w.get("GLD", 0) + 0.10
            w["BIL"] = w.get("BIL", 0) + 0.05      # SHY 로 두면 침체 칸 2배가 꺼진다(slowdown_target 의 SHY 판정)
        out: dict = {}
        for k, v in w.items():
            out[k] = out.get(k, 0) + v
        return out

    def lev(past, p1, p4, prm):
        if pension:
            return (0.5, False) if past[0]["fng"] > 85 else (1.0, False)
        L, trig = base_lev(past, p1, p4, prm)
        if L > 1:
            row = past[0]
            d = row.name
            w = weights(row, 0, 1, prm, ief_ma_s.loc[d])
            if "lev_trend" in flags and any(prices.loc[d, k] < ma.loc[d, k] for k in w if k not in ("SHY", "BIL")):
                L = 1.0
            if "sb_corr" in flags and bool(sb_pos.loc[d]) and not row["growth_on"] and not row["inflation_on"]:
                L = 1.0
        return L, trig
    return weights, lev


def run(sig, prices, dtb3, flags, pension):
    w, l = make_rules(prices, flags, pension)
    r16.target_weights, r16.leverage = w, l
    try:
        return r16.simulate(sig, prices, dtb3, 0, 0, 1, 0)
    finally:
        r16.target_weights, r16.leverage = ORIG


ORIG = (r16.target_weights, r16.leverage)


def window_ret(m: pd.Series, a: str, b: str) -> float:
    return float((1 + m.loc[a:b]).prod() - 1)


def row_stats(name, res_or_m, eq=None):
    m = res_or_m
    s = stats(m)
    sub = {k: stats(m.loc[a:b])["CAGR"] for k, (a, b) in
           {"03~07": ("2003", "2007"), "08~16": ("2008", "2016"), "17~": ("2017", "2026")}.items() if len(m.loc[a:b])}
    return {"변형": name, "CAGR": s["CAGR"], "MDD(월)": s["MDD"], "MDD(일)": (eq / eq.cummax() - 1).min() if eq is not None else np.nan,
            **sub, "2008-09~09-02": window_ret(m, "2008-09", "2009-02"), "2020-02~03": window_ret(m, "2020-02", "2020-03"),
            "2022": window_ret(m, "2022-01", "2022-12"), "최악월": s["worst"]}


def stress_2000(prices: pd.DataFrame) -> pd.DataFrame:
    """2000~02 양식화 스트레스(참고용): T5YIE·IEF 가 없어 인플레 판정·침체 바구니를 못 만든다.
    성장(SPY>200일선) 이면 XLK 1배, 아니면 현금(0%) 으로 두고 V5(XLK 자기 200일선) 만 비교한다."""
    px = prices.loc["1999-06":"2003-03", ["SPY", "XLK"]]
    ma = prices[["SPY", "XLK"]].rolling(200).mean().loc[px.index]
    me = px.groupby([px.index.year, px.index.month]).tail(1).index
    rows = []
    for d0, d1 in zip(me[:-1], me[1:]):
        g = px.loc[d0, "SPY"] > ma.loc[d0, "SPY"]
        own = px.loc[d0, "XLK"] > ma.loc[d0, "XLK"]
        r = px.loc[d1, "XLK"] / px.loc[d0, "XLK"] - 1
        rows.append({"월": d1, "base": r if g else 0.0, "V5": r if (g and own) else 0.0})
    df = pd.DataFrame(rows).set_index("월")
    return df.loc["2000-01":]


def main() -> int:
    prices, t5, vix, baa, dtb3 = load_master_data()
    sig, _ = compute_signals(prices, t5, vix, baa, fred_lag=1)
    last = pd.Timestamp.today().to_period("M").to_timestamp("M") - pd.offsets.MonthEnd(1)
    pent = pd.read_csv("data/pension_mix_backtest.csv", index_col=0, parse_dates=True)["PENT"]
    pent.index = pent.index.to_period("M").to_timestamp("M")
    out = {}
    for label, pension in (("레버리지(일반계좌)", False), ("연금형(비레버리지)", True)):
        rows, mixrows = [], []
        for name, flags in VARIANTS.items():
            if pension and flags == {"lev_trend"}:
                continue
            res = run(sig, prices, dtb3, flags, pension)
            m = res["monthly_ret"]
            m.index = m.index.to_period("M").to_timestamp("M")
            m = m[m.index <= last]
            rows.append(row_stats(name, m, res["equity"]))
            if pension:
                df = pd.concat({"IC": m, "PENT": pent}, axis=1).dropna()
                mixrows.append(row_stats(name + " +PENT50", mix(df["IC"], df["PENT"], 0.5)))
        out[label] = pd.DataFrame(rows).set_index("변형")
        if mixrows:
            out["연금 혼합 IC50+PENT50 (2008-02~)"] = pd.DataFrame(mixrows).set_index("변형")
    pct = lambda x: f"{x:+.1%}" if pd.notna(x) else "—"
    for k, df in out.items():
        print(f"\n■ {k}")
        print(df.apply(lambda c: c.map(pct)).to_string())
    s = stress_2000(prices)
    print("\n■ 2000-01~2003-03 양식화 스트레스 (성장이면 XLK, 아니면 현금 — 참고용)")
    for c in s:
        eq = (1 + s[c]).cumprod()
        print(f"  {c}: 누적 {eq.iloc[-1] - 1:+.1%}, MDD {(eq / eq.cummax() - 1).min():.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
