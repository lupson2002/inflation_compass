"""IC 급 공개 TAA 전략 재현·검증 + IC 혼합 (2026-10-10).

원문 규칙 그대로, IC 와 같은 조건(월말 종가 판단·체결, 매매 명목 × 30bp, 현금 = DTB3)으로 재현한다.
  HAA     Keller & Keuning (2023, SSRN 4346906) Hybrid Asset Allocation — 카나리아 TIP, 13612U(1·3·6·12개월 평균),
          공격 SPY·IWM·VEA·VWO·VNQ·DBC·IEF·TLT 상위 4 각 25%(음수면 방어로), 방어 = IEF·BIL 중 모멘텀 높은 쪽.
          VEA·VWO 상장 전은 EFA·EEM 으로 잇는다.
  VAA4    Keller & Keuning (2017) Vigilant Asset Allocation G4 공격형 — 13612W, 공격 SPY·EFA·EEM·AGG 모두 > 0 이면
          공격 1등 100%, 아니면 방어 LQD·IEF·SHY 1등 100%.
  ADM     Accelerating Dual Momentum (EngineeredPortfolio) — SPY·SCZ 의 1·3·6개월 수익 평균, 큰 쪽이 > 0 이면 그것, 아니면 TLT.
  LFLR2   Gayed & Bilello (2016) Leverage for the Long Run — SPY > 200일선이면 2배 SPY(일간 2배 − 차입 DTB3+0.5%),
          아니면 T-bill. 일별 신호, **다음 날 종가 체결**, 전환 1회당 2배 명목 × 30bp.
IC = run_16_matrix_experiments 확정 전략(레버리지) · 연금형(비레버리지) 월 수익률(전일 FRED, 실거래 조건).

    python3 research_taa_candidates.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

from research_cssa_strategies import backtest, ic_monthly, mix, stats

TICKERS = ["SPY", "IWM", "VEA", "VWO", "EFA", "EEM", "VNQ", "DBC", "IEF", "TLT", "TIP", "BIL", "AGG", "LQD", "SHY", "SCZ"]


def load() -> pd.DataFrame:
    px = yf.download(TICKERS, start="1998-01-01", auto_adjust=True, progress=False)["Close"][TICKERS]
    for new, old in (("VEA", "EFA"), ("VWO", "EEM")):            # 상장 전 구간을 옛 ETF 수익률로 잇는다
        r = px[new].pct_change().fillna(px[old].pct_change())
        first = px[new].first_valid_index()
        px[new] = (1 + r.fillna(0)).cumprod() * (px.loc[first, new] / (1 + r.fillna(0)).cumprod().loc[first])
        px.loc[px[old].isna(), new] = np.nan
    return px


def _mret(px: pd.DataFrame, d, months: int, cols) -> pd.Series:
    me = px.loc[:d].groupby([px.loc[:d].index.year, px.loc[:d].index.month]).tail(1)
    if len(me) <= months:
        return pd.Series(np.nan, index=cols)
    return me[cols].iloc[-1] / me[cols].iloc[-1 - months] - 1


def m13612u(px, d, cols):
    return sum(_mret(px, d, m, cols) for m in (1, 3, 6, 12)) / 4


def m13612w(px, d, cols):
    return 12 * _mret(px, d, 1, cols) + 4 * _mret(px, d, 3, cols) + 2 * _mret(px, d, 6, cols) + _mret(px, d, 12, cols)


def haa_fn(px):
    off = ["SPY", "IWM", "VEA", "VWO", "VNQ", "DBC", "IEF", "TLT"]

    def f(d):
        can = m13612u(px, d, ["TIP"])["TIP"]
        mo = m13612u(px, d, off)
        dm = m13612u(px, d, ["IEF", "BIL"])
        if pd.isna(can) or mo.isna().any() or dm.isna().any():
            return None
        defe = dm.idxmax()
        if can <= 0:
            return {defe: 1.0}
        out = {}
        for a in mo.nlargest(4).index:
            k = a if mo[a] > 0 else defe
            out[k] = out.get(k, 0) + 0.25
        return out
    return f


def vaa4_fn(px):
    off, de = ["SPY", "EFA", "EEM", "AGG"], ["LQD", "IEF", "SHY"]

    def f(d):
        mo, md = m13612w(px, d, off), m13612w(px, d, de)
        if mo.isna().any() or md.isna().any():
            return None
        return {mo.idxmax(): 1.0} if (mo > 0).all() else {md.idxmax(): 1.0}
    return f


def adm_fn(px):
    def f(d):
        s = sum(_mret(px, d, m, ["SPY", "SCZ"]) for m in (1, 3, 6)) / 3
        if s.isna().any():
            return None
        best = s.idxmax()
        return {best if s[best] > 0 else "TLT": 1.0}
    return f


def lflr2(px, rf_d: pd.Series, cost_bp: float = 30) -> pd.Series:
    spy = px["SPY"].dropna()
    r = spy.pct_change().fillna(0)
    on = (spy > spy.rolling(200).mean()).shift(1).fillna(False)          # 다음 날 체결
    rf = rf_d.reindex(spy.index).fillna(0)
    lev = 2 * r - (rf + 0.005 / 252)
    daily = np.where(on, lev, rf)
    switch = on.astype(int).diff().abs().fillna(0)
    daily = (1 + pd.Series(daily, index=spy.index)) * (1 - switch * 2 * cost_bp / 1e4) - 1
    daily = daily.loc[spy.index[200]:]
    m = (1 + daily).resample("ME").prod() - 1
    m.index = m.index.to_period("M").to_timestamp("M")
    return m


def main() -> int:
    ic2, dtb3 = ic_monthly(True)
    ic1, _ = ic_monthly(False)
    px = load()
    rf = (dtb3.reindex(px.index).ffill() / 100 / 252).fillna(0)
    S = {"HAA": backtest(px, haa_fn(px), rf, "2004-01-01"),
         "VAA4": backtest(px, vaa4_fn(px), rf, "2004-01-01"),
         "ADM": backtest(px, adm_fn(px), rf, "2008-01-01"),
         "LFLR2": lflr2(px, rf)}
    last = pd.Timestamp.today().to_period("M").to_timestamp("M") - pd.offsets.MonthEnd(1)
    print("■ 단독 (자체 전 기간, 월말 기준 MDD)")
    for k, r in S.items():
        r = r[r.index <= last].dropna()
        s = stats(r)
        print(f"| {k} | {r.index[0]:%Y-%m}~{r.index[-1]:%Y-%m} | {s['CAGR']:.2%} | {s['MDD']:.2%} | {s['Calmar']:.2f} | {s['Vol']:.1%} | {s['worst']:+.1%} |")
    df = pd.DataFrame({"IC확정": ic2, "IC연금": ic1, **S}).dropna()
    df = df[df.index <= last]
    print(f"\n■ 공통 기간 {df.index[0]:%Y-%m} ~ {df.index[-1]:%Y-%m} ({len(df)}개월)")
    halves = {"전체": df, "전반": df.loc[:"2016-12-31"], "후반": df.loc["2017-01-31":]}
    for k in df:
        cells = [f"{stats(d[k])['CAGR']:.1%} / {stats(d[k])['MDD']:.1%}" for d in halves.values()]
        print(f"| {k} | " + " | ".join(cells) + f" | Calmar {stats(df[k])['Calmar']:.2f} |")
    print("\n상관\n", df.corr().round(2).to_string())
    for base in ("IC확정", "IC연금"):
        d = df[df[base] < 0]
        print(f"{base} 손실 달 상관:", d.corr()[base].drop(["IC확정", "IC연금"]).round(2).to_dict())
    for base, cands in (("IC확정", ["LFLR2", "HAA", "VAA4", "ADM"]), ("IC연금", ["HAA", "VAA4", "ADM"])):
        print(f"\n■ {base} 혼합 (월말 재조정) — 전체 | 전반 ~2016 | 후반 2017~")
        for k in cands:
            for w in (0.7, 0.5):
                cells = []
                for d in halves.values():
                    s = stats(mix(d[base], d[k], w))
                    cells.append(f"{s['CAGR']:.1%} / {s['MDD']:.1%}")
                print(f"| {base} {int(w * 100)} + {k} {int(round((1 - w) * 100))} | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
