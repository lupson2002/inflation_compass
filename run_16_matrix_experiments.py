"""4대 개선안(P1~P4) 16개 조합 매트릭스 백테스트 — 월별 모델 (2026-10-08 비용 모델 정정판).

월별 모델: 매월 마지막 거래일 종가에 판단·체결하고 다음 달 말까지 **그대로 보유**한다(월중 리밸런싱 없음).
  - 보유 중 각 자산 평가액은 가격대로 움직인다(레버리지 비율도 월중에 따라 변한다 — 일별 재조정 없음).
  - 레버리지 > 1: 빌린 금액에 (3개월 T-bill DTB3 + 50bp)/연 이자가 매일 붙는다.
  - 레버리지 < 1: 남는 현금에 DTB3 이자.
  - 거래비용: 월말 리밸런싱 때만, 매매한 명목금액 × 30bp(편도) — backtest.py 의 TRANSACTION_COST_BP 와 같은 정의.
종전판의 문제: 차입·현금 이자를 SHY 일간 **가격 수익률**로 계산했고(2022 년엔 SHY 가 −3.9% 라 빌린 돈에 이자를 받았다),
보고서의 '30bp 반영'과 달리 거래비용이 없었다. 신호 정의·기간(2003-03-31~)은 그대로다.

    python3 run_16_matrix_experiments.py            # 16개 조합 → data/matrix_16_results.csv
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from test_all_16_combinations import compute_signals, load_master_data

START = "2003-03-31"
COST_BP = 30
BORROW_SPREAD = 0.005


@dataclass(frozen=True)
class Params:
    """개선안 임계값 — 기본값은 원 보고서 값(견고성 점검 tools 가 바꿔 본다)."""
    p1_baa: float = 3.20          # P1: BAA10Y(%) 이상이면 신용 스트레스
    p1_vix: float = 35.0          # P1: VIX 이상이면 스트레스
    p3_ma: int = 200              # P3: IEF 이동평균 일수
    p4_target: float = 0.32       # P4: 목표 변동성(레버리지 = target / SPY 20일 변동성)
    p4_floor: float = 1.30        # P4: 레버리지 하한(공포 신호 시)
    recession: str = "xlp_ief"    # 침체 국면 기본 보유: "xlp_ief"(XLP 50 + IEF 50) / "ief"(IEF 100)
    p1_scope: str = "all"         # P1 적용 범위: "all" / "equity"(침체 국면 — 채권 보유 — 에서는 끈다)
    slowdown_lev: str = "ief_only"  # 침체 국면 레버리지(2026-10-09 확정: ief_only): "all"(그대로) / "shield1x"(단기채 달 1배) /
                                  #   "ief_only"(늘린 몫은 IEF 에만 + 단기채 달 1배) / "cap1x"(침체 국면 항상 1배 이하)
    extra: dict = field(default_factory=dict, compare=False)


def target_weights(row, p2: int, p3: int, prm: Params, ief_ma: float) -> dict:
    if row["growth_on"] and row["inflation_on"]:
        return {"XLE": 1.0}
    if row["growth_on"]:
        return {"XLK": 1.0}
    if row["inflation_on"]:
        return {"DBC": 0.5, "XLE": 0.5} if p2 else {"XLU": 1.0}
    if p3 and row["ief"] <= ief_ma:
        return {"SHY": 1.0}       # P3: 침체 + 국채 하락 추세 → 단기채 100% (2026-10-09, 종전 XLP 50 + SHY 50)
    return {"IEF": 1.0} if prm.recession == "ief" else {"XLP": 0.5, "IEF": 0.5}


def leverage(past: list, p1: int, p4: int, prm: Params) -> tuple[float, bool]:
    """Model C-1 Ultra 레버리지 규칙 + P1(서킷브레이커)·P4(변동성 비례). (레버리지, P1 발동 여부)."""
    r0 = past[0]
    if r0["fng"] > 85:
        return 0.5, False
    direct = (past[0]["fng"] < 15) or (past[2]["fng"] < 15)
    lagged = (past[3]["fng"] < 15) or (past[4]["fng"] < 15)
    if not (direct or (lagged and r0["growth_on"])):
        return 1.0, False
    recession = not r0["growth_on"] and not r0["inflation_on"]
    p1_on = p1 and not (prm.p1_scope == "equity" and recession)
    if p1_on and ((r0["baa10y"] > prm.p1_baa) or (r0["vix"] > prm.p1_vix)):
        return 1.0, True
    if p4:
        vol = max(0.12, float(r0["vol_20_spy"]))
        return float(np.clip(prm.p4_target / vol, prm.p4_floor, 2.0)), False
    return 2.0, False


def slowdown_target(row, w: dict, lev: float, prm: Params) -> tuple[float, dict]:
    """침체 국면 레버리지 규칙(2026-10-09 전문가 검토 후보). (레버리지, 자산별 목표 비중)."""
    if not row["growth_on"] and not row["inflation_on"] and lev > 1:
        mode = prm.slowdown_lev
        if mode == "cap1x" or (mode in ("shield1x", "ief_only") and "SHY" in w):
            lev = 1.0
        elif mode == "ief_only" and "IEF" in w:
            target = dict(w)
            target["IEF"] = w["IEF"] + (lev - 1.0)            # 빌린 몫은 IEF 에만
            return lev, target
    return lev, {k: v * lev for k, v in w.items()}


def simulate(sig, prices, rf_annual, p1, p2, p3, p4, prm: Params = Params(), cost_bp: float = COST_BP,
             start: str = START) -> dict:
    s = sig.loc[start:]
    px = prices.loc[s.index[0]:]
    rf_d = (rf_annual.reindex(px.index).ffill() / 100.0 / 252.0).fillna(0.0)
    ief_ma = prices["IEF"].rolling(prm.p3_ma, min_periods=60).mean()
    me = sorted(s.groupby([s.index.year, s.index.month]).apply(lambda x: x.index[-1]).values)
    equity = 1.0
    held: dict[str, float] = {}           # 직전 달 말 보유(자산 → 평가액 / 그때 자기자본)
    curve, levs, p1_months, turnovers = [], [], 0, []
    for i in range(len(me) - 1):
        d0, d1 = me[i], me[i + 1]
        past = [s.loc[me[i - k]] if i >= k else s.loc[d0] for k in range(5)]
        w = target_weights(past[0], p2, p3, prm, ief_ma.loc[d0])
        lev, trig = leverage(past, p1, p4, prm)
        p1_months += trig
        lev, target = slowdown_target(past[0], w, lev, prm)
        to = sum(abs(target.get(k, 0.0) - held.get(k, 0.0)) for k in set(target) | set(held))
        turnovers.append(to)
        equity *= (1 - to * cost_bp / 1e4)                     # 월말 리밸런싱 비용
        days = px.loc[d0:d1].index
        rel = px.loc[days, list(target)].div(px.loc[d0, list(target)])     # 월중 보유(재조정 없음)
        pos = rel.mul(pd.Series(target)).sum(axis=1) * equity
        acc = (1 + rf_d.loc[days].iloc[1:]).cumprod().reindex(days).fillna(1.0)
        if lev > 1:
            acc_b = (1 + rf_d.loc[days].iloc[1:] + BORROW_SPREAD / 252).cumprod().reindex(days).fillna(1.0)
            eq_path = pos - (lev - 1) * equity * acc_b
        else:
            eq_path = pos + (1 - lev) * equity * acc
        curve.append(eq_path.iloc[1:])
        end_val = eq_path.iloc[-1]
        held = {k: float(rel[k].iloc[-1] * target[k] * equity / end_val) for k in target}
        equity = float(end_val)
        levs.append(lev)
    eq = pd.concat(curve)
    dr = eq.pct_change().fillna(eq.iloc[0] - 1)
    ny = len(dr) / 252
    cagr = eq.iloc[-1] ** (1 / ny) - 1
    vol = dr.std() * np.sqrt(252)
    rf_mean = rf_d.loc[dr.index].mean() * 252
    mdd = float((eq / eq.cummax() - 1).min())

    def window(a, b):
        sub = eq.loc[a:b]
        if sub.empty:                      # 시작일이 구간 뒤(예: CNN 2011~ 백테스트)
            return float("nan"), float("nan")
        base = eq.loc[:pd.Timestamp(a) - pd.Timedelta(days=1)]
        start_val = base.iloc[-1] if len(base) else 1.0
        path = pd.concat([pd.Series([start_val]), sub])
        return sub.iloc[-1] / start_val - 1, float((path / path.cummax() - 1).min())

    _, mdd08 = window("2007-10-01", "2009-03-31")
    ret22, mdd22 = window("2022-01-01", "2022-12-31")
    m = eq.resample("ME").last()
    m_ret = m.pct_change().fillna(m.iloc[0] - 1)
    return {"CAGR": cagr, "Total_Mult": float(eq.iloc[-1]), "Vol": vol, "Sharpe": (dr.mean() * 252 - rf_mean) / vol,
            "MDD": mdd, "Calmar": cagr / abs(mdd), "2008_MDD": mdd08, "2022_MDD": mdd22, "2022_Ret": ret22,
            "Win_Rate": float((m_ret > 0).mean()), "P1_Months": p1_months, "Avg_Turnover": float(np.mean(turnovers)),
            "equity": eq, "monthly_ret": m_ret}


def name_of(p1, p2, p3, p4) -> str:
    tags = [t for t, on in (("P1(서킷)", p1), ("P2(원자재)", p2), ("P3(채권방어)", p3), ("P4(볼록성)", p4)) if on]
    return " + ".join(tags) if tags else "Baseline (Model C-1 Ultra)"


def run_matrix(sig, prices, rf, prm: Params = Params(), **kw) -> pd.DataFrame:
    base = simulate(sig, prices, rf, 0, 0, 0, 0, prm, **kw)
    rows = []
    for idx, (p1, p2, p3, p4) in enumerate(itertools.product([0, 1], repeat=4)):
        r = base if (p1, p2, p3, p4) == (0, 0, 0, 0) else simulate(sig, prices, rf, p1, p2, p3, p4, prm, **kw)
        diff = (r["monthly_ret"] - base["monthly_ret"]).dropna()
        p_val = 1.0 if idx == 0 else float(stats.ttest_1samp(diff, 0.0).pvalue)
        rows.append({"Model_ID": f"M{idx:02d}", "P1": p1, "P2": p2, "P3": p3, "P4": p4, "Name": name_of(p1, p2, p3, p4),
                     **{k: v for k, v in r.items() if k not in ("equity", "monthly_ret")}, "p_value": p_val})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    prices, t5yie, vix, baa10y, dtb3 = load_master_data()
    sig, _ = compute_signals(prices, t5yie, vix, baa10y)
    df = run_matrix(sig, prices, dtb3)
    df.to_csv("data/matrix_16_results.csv", index=False)
    cols = ["Model_ID", "Name", "CAGR", "Total_Mult", "Sharpe", "MDD", "Calmar", "2008_MDD", "2022_MDD", "2022_Ret", "P1_Months", "p_value"]
    print(df[cols].round(4).to_string())
