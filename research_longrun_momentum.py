"""초장기 듀얼 모멘텀(GEM)·ADM vs IC 뼈대 — 규칙은 longrun_momentum_prereg.md 에 먼저 고정(7d9bd30).

T1 1872~ Shiller 미국 단일 자산판 · T2 1927~ French 미국 대형 vs 소형 대리판 · T3 1990-07~ French 미국 vs 선진국 ex-US 원형.
수익은 '그 달에 끝난 수익'(끝 인덱스). 판단 t 의 비중은 lag 만큼 뒤 달 수익에 적용(T1 = 2, T2·T3 = 1).

    python3 research_longrun_momentum.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import research_longrun_ic as L

D = L.D
COST_BP = 30


def _french(name: str, cols: list[str], section: int = 0) -> pd.DataFrame:
    """French CSV 의 section 번째 월간 표를 % → 소수로."""
    lines = open(D / name, errors="ignore").read().splitlines()
    heads = [i for i, s in enumerate(lines) if s.strip().startswith(",")]
    h = heads[section]
    header = [c.strip() for c in lines[h].split(",")]
    rows = []
    for s in lines[h + 1:]:
        p = [x.strip() for x in s.split(",")]
        if not p[0].isdigit() or len(p[0]) != 6:
            break
        rows.append(p)
    df = pd.DataFrame(rows, columns=header).set_index(header[0])
    df.index = pd.to_datetime(df.index, format="%Y%m").to_period("M").to_timestamp("M")
    return df[cols].astype(float) / 100


def tiers():
    df, _ = L.load()                      # Shiller 기반(시작 인덱스 수익) + IC 신호
    cpi = df["cpi"]
    bond_end = df["r_bond"].shift(1)      # 끝 인덱스로
    t1 = pd.DataFrame({"us": df["r_stock"].shift(1), "bond": bond_end, "cash": df["r_cash"].shift(1)})
    sig1 = df[["growth", "inflation", "bond_shield"]]
    ff = _french("F-F_Research_Data_Factors.csv", ["Mkt-RF", "RF"])
    small = _french("Portfolios_Formed_on_ME.csv", ["Lo 30"])["Lo 30"]
    us = ff["Mkt-RF"] + ff["RF"]
    t2 = pd.DataFrame({"us": us, "alt": small, "bond": bond_end.reindex(us.index), "cash": ff["RF"]}).dropna()
    dx = _french("Developed_ex_US_3_Factors.csv", ["Mkt-RF", "RF"])
    dxs = _french("Developed_ex_US_6_Portfolios_ME_BE-ME.csv", ["SMALL LoBM", "ME1 BM2", "SMALL HiBM"]).mean(axis=1)
    t3 = pd.DataFrame({"us": us, "alt": dx["Mkt-RF"] + dx["RF"], "alt_small": dxs,
                       "bond": bond_end.reindex(us.index), "cash": ff["RF"]}).dropna()
    return t1, sig1, t2, t3, cpi


def ic_signals(R: pd.DataFrame, cpi: pd.Series) -> pd.DataFrame:
    """T2·T3 용 IC 신호: 성장 = 미국 총수익 지수 > 10개월선, 인플레 = CPI(t−1) 규칙, 채권방어 = 10년채 지수 ≤ 10개월선."""
    idx_us = (1 + R["us"]).cumprod()
    idx_b = (1 + R["bond"]).cumprod()
    yoy = (cpi / cpi.shift(12) - 1).reindex(R.index)
    return pd.DataFrame({"growth": idx_us > idx_us.rolling(10).mean(),
                         "inflation": (yoy.shift(1) > 0.02) & (yoy.shift(1) > yoy.shift(4)),
                         "bond_shield": idx_b <= idx_b.rolling(10).mean()}, index=R.index)


def mom(R: pd.Series, n: int) -> pd.Series:
    return (1 + R).rolling(n).apply(np.prod, raw=True) - 1


def make_rules(R: pd.DataFrame, sig: pd.DataFrame, alt: str | None) -> dict:
    m12 = {c: mom(R[c], 12) for c in R}
    adm = {c: (mom(R[c], 1) + mom(R[c], 3) + mom(R[c], 6)) / 3 for c in R}
    idx_b = (1 + R["bond"]).cumprod()
    b_down = idx_b <= idx_b.rolling(10).mean()

    def gem(d):
        if not m12["us"].loc[d] > m12["cash"].loc[d]:
            return {"bond": 1.0}
        if alt and m12[alt].loc[d] > m12["us"].loc[d]:
            return {alt: 1.0}
        return {"us": 1.0}

    def admf(shield):
        def f(d):
            cands = ["us"] + ([alt] if alt else [])
            best = max(cands, key=lambda c: adm[c].loc[d])
            if adm[best].loc[d] > 0:
                return {best: 1.0}
            return {"cash": 1.0} if (shield and b_down.loc[d]) else {"bond": 1.0}
        return f

    def ic(half):
        def f(d):
            s = sig.loc[d]
            if s.growth:
                w = {"us": 1.0}
            elif s.inflation:
                w = {"us": 0.5, "cash": 0.5} if half else {"us": 1.0}
            elif s.bond_shield:
                w = {"cash": 1.0}
            else:
                w = {"us": 0.5, "bond": 0.5}
            w = {k: v * 0.85 for k, v in w.items()}
            w["cash"] = w.get("cash", 0) + 0.15
            return w
        return f

    return {"주식 보유": lambda d: {"us": 1.0},
            "추세만": lambda d: {"us": 1.0} if sig.loc[d].growth else {"cash": 1.0},
            "GEM": gem, "ADM": admf(False), "ADM_shield": admf(True),
            "IC 뼈대+보험": ic(False), "IC 뼈대+보험·인플레칸 50/50": ic(True)}


def run(R: pd.DataFrame, rule, lag: int, start: str) -> pd.Series:
    idx = R.index
    held: dict = {}
    out = {}
    for i in range(len(idx) - lag):
        d = idx[i]
        if d < pd.Timestamp(start):
            continue
        w = rule(d)
        r = R.iloc[i + lag]
        if r[list(w)].isna().any():
            break
        to = sum(abs(w.get(k, 0) - held.get(k, 0)) for k in set(w) | set(held))
        g = sum(v * r[k] for k, v in w.items())
        out[idx[i + lag]] = (1 - to * COST_BP / 1e4) * (1 + g) - 1
        held = {k: v * (1 + r[k]) / (1 + g) for k, v in w.items()}
    return pd.Series(out)


WINDOWS = {"1929-09~32-06": ("1929-09", "1932-06"), "1937~38": ("1937", "1938"), "1942~51 억압": ("1942", "1951"),
           "1966~82 스태그": ("1966", "1982"), "1973~74": ("1973", "1974"), "1987-08~12": ("1987-08", "1987-12"),
           "2000-03~02-09": ("2000-03", "2002-09"), "2007-10~09-03": ("2007-10", "2009-03"),
           "2020-02~03": ("2020-02", "2020-03"), "2022": ("2022", "2022")}


def report(name: str, M: pd.DataFrame, cpi: pd.Series, split: str | None) -> None:
    print(f"\n{'=' * 100}\n■ {name}  {M.index[0]:%Y-%m} ~ {M.index[-1]:%Y-%m} ({len(M)}개월)")
    parts = [("전체", M)] + ([(f"~{int(split) - 1}", M.loc[:str(int(split) - 1)]), (f"{split}~", M.loc[split:])] if split else [])
    for lab, sub in parts:
        t = pd.DataFrame({k: L.stats(sub[k], cpi) for k in M}).T[["CAGR", "실질CAGR", "MDD", "최악12개월"]]
        print(f"[{lab}]\n" + t.map(lambda x: f"{x:+.1%}").to_string())
    rows = {w: {k: f"{(1 + M.loc[a:b, k]).prod() - 1:+.1%}" for k in M} for w, (a, b) in WINDOWS.items() if len(M.loc[a:b])}
    print("[구간 누적, 명목]\n" + pd.DataFrame(rows).T.to_string())
    hot = (cpi / cpi.shift(12) - 1).shift(1).reindex(M.index) > 0.05
    if hot.sum() >= 12:
        print(f"[CPI > 5% 달 {int(hot.sum())}개월 연환산] " + " · ".join(
            f"{k} {(1 + M.loc[hot, k]).prod() ** (12 / hot.sum()) - 1:+.1%}" for k in M))


def main() -> int:
    t1, sig1, t2, t3, cpi = tiers()
    r1 = make_rules(t1, sig1, None)
    M1 = pd.DataFrame({k: run(t1, f, 2, "1872-12-31") for k, f in r1.items()}).dropna()
    report("T1 미국 단일 자산판 (Shiller)", M1, cpi, "1946")
    r2 = make_rules(t2, ic_signals(t2, cpi), "alt")
    M2 = pd.DataFrame({k: run(t2, f, 1, "1927-06-30") for k, f in r2.items()}).dropna()
    report("T2 미국 대형 vs 소형 대리판 (French 1926~)", M2, cpi, "1946")
    t3a = t3.rename(columns={"alt": "dev"})
    s3 = ic_signals(t3a, cpi)
    rg = make_rules(t3a.drop(columns="alt_small").rename(columns={"dev": "alt"}), s3, "alt")
    ra = make_rules(t3a.drop(columns="dev").rename(columns={"alt_small": "alt"}), s3, "alt")
    rules3 = {**{k: v for k, v in rg.items() if k != "ADM" and k != "ADM_shield"}, "ADM": ra["ADM"], "ADM_shield": ra["ADM_shield"]}
    R3 = t3a.rename(columns={"dev": "alt"})
    R3a = t3a.drop(columns="dev").rename(columns={"alt_small": "alt"})
    M3 = pd.DataFrame({k: run(R3a if k.startswith("ADM") else R3.drop(columns="alt_small"), f, 1, "1991-06-30")
                       for k, f in rules3.items()}).dropna()
    report("T3 원형 (미국 vs 선진국 ex-US, ADM 은 ex-US 소형주)", M3, cpi, "2015")
    pd.concat({"T1": M1, "T2": M2, "T3": M3}, axis=1).to_csv(D / "longrun_momentum_monthly.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
