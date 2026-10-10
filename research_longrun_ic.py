"""초장기 IC 뼈대 검증 1871~2026 (Shiller 월간 + GMD 위기 라벨) — 규칙은 longrun_ic_skeleton_prereg.md 에 먼저 고정.

데이터: data/longrun/shiller_monthly.csv (ie_data.xls 2026-10 판에서 변환), data/longrun/gmd_usa.csv (GMD v2026_09 미국),
현금 = FRED TB3MS(1934~) · GMD strate(이전, 연간).
시점: 월 t 판단 → t+1→t+2 수익에 적용(Shiller 가격이 월평균이라서), CPI 는 t−1 까지.

    python3 research_longrun_ic.py            # 표 출력 + data/longrun/longrun_monthly.csv
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

D = Path(__file__).parent / "data" / "longrun"
COST_BP = 30


def load() -> pd.DataFrame:
    s = pd.read_csv(D / "shiller_monthly.csv", parse_dates=["date"]).set_index("date")
    g = pd.read_csv(D / "gmd_usa.csv")
    tr = s["real_tr"] * s["CPI"]                                     # 명목 총수익 지수(상수배 무관)
    df = pd.DataFrame(index=s.index)
    df["r_stock"] = tr.shift(-1) / tr - 1                            # 행 t = t→t+1
    df["r_bond"] = s["bond_gross"] - 1                               # Shiller 정의상 행 t = t→t+1
    tb = pd.read_csv("https://fred.stlouisfed.org/graph/fredgraph.csv?id=TB3MS", na_values=".").dropna()
    tb.index = pd.to_datetime(tb["observation_date"]).dt.to_period("M").dt.to_timestamp("M")
    annual = g.dropna(subset=["strate"]).set_index(g.dropna(subset=["strate"])["year"].astype(int))["strate"]
    rate = pd.Series(df.index.year.map(annual), index=df.index, dtype=float)
    rate = tb["TB3MS"].reindex(df.index).combine_first(rate)
    df["r_cash"] = rate / 1200
    # 신호(월 t 시점에 알 수 있는 값)
    df["growth"] = s["P"] > s["P"].rolling(10).mean()
    yoy = s["CPI"] / s["CPI"].shift(12) - 1
    df["infl_yoy"] = yoy.shift(1)
    df["inflation"] = (yoy.shift(1) > 0.02) & (yoy.shift(1) > yoy.shift(4))
    bidx = (1 + df["r_bond"]).cumprod().shift(1)                     # 수준 t = t 까지 실현된 수익
    df["bond_shield"] = bidx <= bidx.rolling(10).mean()
    df["cpi"] = s["CPI"]
    df["year"] = df.index.year
    return df.loc["1872-01-31":], g


def ic_skeleton(row, sleeve=0.0, infl_only_cash=False) -> dict:
    if row.growth or (row.inflation and not infl_only_cash):
        w = {"stock": 1.0}
    elif row.inflation:
        w = {"cash": 1.0}
    elif row.bond_shield:
        w = {"cash": 1.0}
    else:
        w = {"stock": 0.5, "bond": 0.5}
    if sleeve:
        w = {k: v * (1 - sleeve) for k, v in w.items()}
        w["cash"] = w.get("cash", 0) + sleeve
    return w


RULES = {
    "주식 보유": lambda r: {"stock": 1.0},
    "60/40": lambda r: {"stock": 0.6, "bond": 0.4},
    "추세만": lambda r: {"stock": 1.0} if r.growth else {"cash": 1.0},
    "IC 뼈대": lambda r: ic_skeleton(r),
    "IC 뼈대+보험15": lambda r: ic_skeleton(r, sleeve=0.15),
    "IC 뼈대·인플레만→현금": lambda r: ic_skeleton(r, infl_only_cash=True),
}


def run(df: pd.DataFrame, rule, cost_bp: float = COST_BP) -> pd.Series:
    """월 t 판단 w_t 를 t+1 행 수익(t+1→t+2)에 적용. 결과 인덱스 = 수익이 끝나는 달(t+2)."""
    idx = df.index
    held: dict = {}
    out = {}
    for i in range(len(idx) - 2):
        row = df.iloc[i]
        nxt = df.iloc[i + 1]
        if any(pd.isna(nxt[c]) for c in ("r_stock", "r_bond", "r_cash")):
            break
        w = rule(row)
        to = sum(abs(w.get(k, 0) - held.get(k, 0)) for k in set(w) | set(held))
        r = {"stock": nxt.r_stock, "bond": nxt.r_bond, "cash": nxt.r_cash}
        g = sum(v * r[k] for k, v in w.items())
        out[idx[i + 2]] = (1 - to * cost_bp / 1e4) * (1 + g) - 1
        held = {k: v * (1 + r[k]) / (1 + g) for k, v in w.items()}
    return pd.Series(out)


def stats(m: pd.Series, cpi: pd.Series) -> dict:
    eq = (1 + m).cumprod()
    n = len(m) / 12
    infl = (cpi.reindex(m.index) / cpi.reindex(m.index).shift(1) - 1).fillna(0)
    real = (1 + m) / (1 + infl) - 1
    req = (1 + real).cumprod()
    r12 = (1 + m).rolling(12).apply(np.prod, raw=True) - 1
    return {"CAGR": eq.iloc[-1] ** (1 / n) - 1, "실질CAGR": req.iloc[-1] ** (1 / n) - 1,
            "MDD": (eq / eq.cummax() - 1).min(), "실질MDD": (req / req.cummax() - 1).min(),
            "Vol": m.std() * np.sqrt(12), "최악12개월": r12.min()}


WINDOWS = {"1873-79 장기불황": ("1873-01", "1879-12"), "1907 공황": ("1907-01", "1907-12"),
           "1914 폐장": ("1914-01", "1914-12"), "1929-09~32-06 대공황": ("1929-09", "1932-06"),
           "1937~38": ("1937-01", "1938-12"), "1942~51 금융억압": ("1942-01", "1951-12"),
           "1966~82 스태그플레이션": ("1966-01", "1982-12"), "1973~74": ("1973-01", "1974-12"),
           "1987-08~12": ("1987-08", "1987-12"), "2000-03~02-09": ("2000-03", "2002-09"),
           "2007-10~09-03": ("2007-10", "2009-03"), "2022": ("2022-01", "2022-12")}


def main() -> int:
    df, g = load()
    res = {k: run(df, f) for k, f in RULES.items()}
    res100 = {k: run(df, f, 100) for k, f in RULES.items() if k.startswith("IC") or k == "추세만"}
    M = pd.DataFrame(res).dropna()
    M.to_csv(D / "longrun_monthly.csv")
    cpi = df["cpi"]
    pct = lambda x: f"{x:+.1%}"
    print(f"■ 전체 {M.index[0]:%Y-%m} ~ {M.index[-1]:%Y-%m} ({len(M)}개월), 30bp")
    for name, sub in (("전체", M), ("1872~1945", M.loc[:"1945"]), ("1946~2026", M.loc["1946":])):
        t = pd.DataFrame({k: stats(sub[k], cpi) for k in M}).T
        print(f"\n[{name}]\n" + t.apply(lambda c: c.map(pct)).to_string())
    print("\n■ 비용 100bp 민감도 (전체 CAGR / MDD)")
    for k, s in res100.items():
        st = stats(s.dropna(), cpi)
        print(f"  {k}: {st['CAGR']:+.1%} / {st['MDD']:+.1%}")
    print("\n■ 구간 누적 수익 (명목 · 괄호 실질)")
    rows = {}
    for w, (a, b) in WINDOWS.items():
        sub = M.loc[a:b]
        infl = float(cpi.loc[b:].iloc[0] / cpi.loc[:a].iloc[-1] - 1) if len(sub) else np.nan
        rows[w] = {k: f"{(1 + sub[k]).prod() - 1:+.1%} ({((1 + sub[k]).prod()) / (1 + infl) - 1:+.1%})" for k in M}
    print(pd.DataFrame(rows).T.to_string())
    yr = (1 + M).groupby(M.index.year).prod() - 1
    gy = g.set_index(g["year"].astype(int))
    print("\n■ GMD 위기 연도 평균 연수익 (해당 연도 수)")
    for c in ("BankingCrisis", "CurrencyCrisis", "SovDebtCrisis"):
        ys = [y for y in gy.index[gy[c] == 1] if y in yr.index]
        print(f"  {c} {ys}: " + " · ".join(f"{k} {yr.loc[ys, k].mean():+.1%}" for k in M))
    hot = df["infl_yoy"].reindex(M.index) > 0.05
    print(f"\n■ CPI 전년비 > 5% 인 달 ({int(hot.sum())}개월) 연환산 · 그 외")
    for k in M:
        a, b = M.loc[hot, k], M.loc[~hot, k]
        print(f"  {k}: 고인플레 {(1 + a).prod() ** (12 / len(a)) - 1:+.1%} · 그 외 {(1 + b).prod() ** (12 / len(b)) - 1:+.1%}")
    reg = df.loc[M.index]
    share = pd.Series({"성장": reg.growth.mean(), "인플레": reg.inflation.mean(),
                       "인플레만": (~reg.growth & reg.inflation).mean(),
                       "침체": (~reg.growth & ~reg.inflation).mean(),
                       "침체+채권방어": (~reg.growth & ~reg.inflation & reg.bond_shield).mean()})
    print("\n■ 국면 비율\n" + share.map(lambda x: f"{x:.1%}").to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
