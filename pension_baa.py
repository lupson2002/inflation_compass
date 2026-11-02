"""연금형 혼합: IC 연금형 70% + BAA-G4 30% — ETF 로 구현한 백테스트와 현재 포지션 (2026-10-09).

IC 연금형 = 확정 전략에서 레버리지만 뺀 것: 4국면 섹터 로테이션 + 침체 국면 채권방어(IEF < 200일선 → SHY)
            + IC 위험선호 지수 > 85 면 0.5배(나머지 단기채). 빌리지 않는다.
BAA-G4    = 켈러 Bold Asset Allocation, 공격형 G4 (Keller 2022 원본 규칙, ETF):
  - 카나리아 SPY·EEM·EFA·AGG 의 13612W 모멘텀(12×R1 + 4×R3 + 2×R6 + R12)이 하나라도 < 0 → 방어
  - 공격: QQQ·EEM·EFA·AGG 중 상대 모멘텀(월말 가격 / 최근 13개 월말 평균 − 1) 1등에 100%
  - 방어: TIP·DBC·BIL·IEF·TLT·LQD·AGG 중 상대 모멘텀 상위 3개 균등, 그중 BIL 보다 낮은 것은 BIL 로 대체
  - 월말 종가에 판단·체결(가격 신호만 써서 지연 없음), 월말 매매 명목 × 비용(기본 30bp)
  - BIL 상장(2007-05) 전 BIL 가격은 DTB3 누적으로 대신한다.
  variant="research": dual-momentum-rotation 연구판(카나리아 SPY·EFA·EEM, 공격 QQQ·EFA·EEM, 방어 BIL·TLT·GLD,
  12-1 모멘텀, 방어 1등 ≤ 0 이면 BIL) — 비교용.
두 슬리브는 매월 말 70/30 으로 다시 맞춘다(그 매매도 30bp).

    python3 pension_baa.py          # 백테스트 표 + 현재 포지션
"""
from __future__ import annotations

import functools

import numpy as np
import pandas as pd
import yfinance as yf

COST_BP = 30
IC_WEIGHT, BAA_WEIGHT = 0.70, 0.30
CANARY = ["SPY", "EEM", "EFA", "AGG"]                          # 켈러 원본
ATTACK = ["QQQ", "EEM", "EFA", "AGG"]
DEFENSE = ["TIP", "DBC", "BIL", "IEF", "TLT", "LQD", "AGG"]
R_CANARY, R_ATTACK, R_DEFENSE = ["SPY", "EFA", "EEM"], ["QQQ", "EFA", "EEM"], ["BIL", "TLT", "GLD"]   # 연구판
TICKERS = sorted(set(CANARY + ATTACK + DEFENSE + R_CANARY + R_ATTACK + R_DEFENSE))
TICKER_KR = {"QQQ": "나스닥", "EFA": "선진국", "EEM": "신흥국", "BIL": "현금(초단기채)", "TLT": "장기국채", "GLD": "금",
             "AGG": "미국 종합채권", "TIP": "물가연동채", "DBC": "원자재", "LQD": "투자등급 회사채", "SPY": "S&P500",
             "XLE": "에너지", "XLK": "기술", "XLU": "유틸리티", "XLP": "필수소비재", "IEF": "7-10년 국채", "SHY": "1-3년 단기채"}


def _trailing(r: pd.DataFrame, n: int) -> pd.DataFrame:
    return (1 + r).rolling(n).apply(np.prod, raw=True) - 1


def mom_13612w(r: pd.DataFrame) -> pd.DataFrame:
    return 12 * _trailing(r, 1) + 4 * _trailing(r, 3) + 2 * _trailing(r, 6) + _trailing(r, 12)


def mom_121(r: pd.DataFrame) -> pd.DataFrame:
    return _trailing(r, 12) - _trailing(r, 1)


def load_monthly(dtb3: pd.Series | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """ETF 일별 수정종가 → (월말 가격, 월 수익률). 마지막 행은 진행 중인 달(오늘까지).
    dtb3 를 주면 BIL 상장 전 가격을 DTB3 누적으로 이어 붙인다."""
    raw = yf.download(TICKERS, start="2000-01-01", auto_adjust=True, progress=False)["Close"]
    daily = raw[TICKERS].dropna(how="all")
    me = sorted(daily.groupby([daily.index.year, daily.index.month]).apply(lambda x: x.index[-1]).values)
    px = daily.loc[me].copy()
    if dtb3 is not None:
        rf = (dtb3.reindex(px.index).ffill() / 100.0).shift(1) / 12.0
        first = px["BIL"].first_valid_index()
        synth = (1 + rf.fillna(0)).cumprod()
        px.loc[:first, "BIL"] = synth.loc[:first] / synth.loc[first] * px.loc[first, "BIL"]
    return px, px.pct_change()


def rel_mom(px: pd.DataFrame) -> pd.DataFrame:
    """켈러 상대 모멘텀: p0 / 평균(p0..p12) − 1 (월말 13개)."""
    return px / px.rolling(13).mean() - 1


def baa_target(px: pd.DataFrame, monthly: pd.DataFrame, d, variant: str = "keller") -> dict | None:
    """d 월말 기준 BAA-G4 목표 비중. 데이터가 모자라면 None."""
    hist_r, hist_p = monthly.loc[:d], px.loc[:d]
    if variant == "research":
        can = mom_13612w(hist_r[R_CANARY]).iloc[-1]
        if can.isna().any():
            return None
        if (can > 0).all():
            atk = mom_121(hist_r[R_ATTACK]).iloc[-1]
            return {atk.idxmax(): 1.0} if atk.notna().all() else None
        dfn = mom_121(hist_r[R_DEFENSE]).iloc[-1].dropna()
        if dfn.empty or dfn.max() <= 0:
            return {"BIL": 1.0}
        top = dfn.nlargest(3).index
        return {a: 1.0 / len(top) for a in top}
    can = mom_13612w(hist_r[CANARY]).iloc[-1]
    rm = rel_mom(hist_p).iloc[-1]
    if can.isna().any() or rm[ATTACK + DEFENSE].isna().any():
        return None
    if (can >= 0).all():
        return {rm[ATTACK].idxmax(): 1.0}
    out: dict = {}
    for a in rm[DEFENSE].nlargest(3).index:
        k = a if rm[a] >= rm["BIL"] else "BIL"
        out[k] = out.get(k, 0) + 1 / 3
    return out


def baa_backtest(px: pd.DataFrame, monthly: pd.DataFrame, variant: str = "keller", cost_bp: float = COST_BP) -> pd.DataFrame:
    """월 수익률(비용 차감)과 그 달 보유 비중. index = 보유한 달의 월말. 신호가 처음 유효한 달부터."""
    dates = monthly.index
    held: dict = {}
    rows = []
    for d0, d1 in zip(dates[:-1], dates[1:]):
        tgt = baa_target(px, monthly, d0, variant)
        if tgt is None:
            continue
        to = sum(abs(tgt.get(k, 0) - held.get(k, 0)) for k in set(tgt) | set(held))
        r = monthly.loc[d1]
        gross = sum(w * r[k] for k, w in tgt.items())
        net = (1 - to * cost_bp / 1e4) * (1 + gross) - 1
        held = {k: w * (1 + r[k]) / (1 + gross) for k, w in tgt.items()}
        rows.append({"date": d1, "ret": net, "hold": tgt, "turnover": to})
    return pd.DataFrame(rows).set_index("date")


def ic_pension_monthly(fred_lag: int = 1, cost_bp: float = COST_BP):
    """IC 연금형 월 수익률(30bp, 상시 보험 없음 — 2026-10-30) — run_16_matrix_experiments 엔진 재사용.
    주의: 이 엔진은 월말 신호를 그 종가에 바로 체결한다(이상화). 다음 날 체결 판은 pentarch scripts/ic100_variants.py."""
    import run_16_matrix_experiments as r16
    from test_all_16_combinations import compute_signals, load_master_data
    prices, t5yie, vix, baa10y, dtb3 = load_master_data()
    sig, _ = compute_signals(prices, t5yie, vix, baa10y, fred_lag=fred_lag)
    orig = r16.leverage
    r16.leverage = lambda past, p1, p4, prm: (0.5, False) if past[0]["fng"] > 85 else (1.0, False)
    try:
        r = r16.simulate(sig, prices, dtb3, 0, 0, 1, 0, prm=r16.Params(sleeve_gld=0.0, sleeve_bil=0.0), cost_bp=cost_bp)
    finally:
        r16.leverage = orig
    return r["monthly_ret"], dtb3


def mix(ic: pd.Series, baa: pd.Series, w_ic: float = IC_WEIGHT, cost_bp: float = COST_BP) -> pd.Series:
    """매월 말 w_ic / 1−w_ic 로 재조정한 혼합 수익률(재조정 매매 30bp 포함)."""
    out = []
    for r_ic, r_b in zip(ic.values, baa.values):
        g = w_ic * r_ic + (1 - w_ic) * r_b
        drift = w_ic * (1 + r_ic) / (1 + g)                 # 달 말 실제 IC 비중
        out.append((1 + g) * (1 - 2 * abs(drift - w_ic) * cost_bp / 1e4) - 1)
    return pd.Series(out, index=ic.index)


def stats(r: pd.Series) -> dict:
    eq = (1 + r).cumprod()
    n = len(r) / 12
    cagr = eq.iloc[-1] ** (1 / n) - 1
    mdd = (eq / eq.cummax() - 1).min()
    return {"CAGR": cagr, "MDD": mdd, "Calmar": cagr / abs(mdd), "Vol": r.std() * np.sqrt(12),
            "Sharpe": r.mean() / r.std() * np.sqrt(12), "worst": r.min(), "mult": eq.iloc[-1]}


IC_VERSION = "IC 연금형 v2.2"   # v1.0 연금형(무레버·무보험·다음 날 체결, 10-30) → v1.1 T4(10-31) → v2.0 G1S(11-02) → v2.1 I3 인플레 히스테리시스 2.15/1.85(11-02, docs/127) + I1 성장 칸 실제 보유 나스닥100(QQQ) 기준 백테스트(docs/126) → v2.2 A2 디스인플레이션 칸(11-02, docs/129)
STRESS_PATH = "/home/mikey/pentarch/output/stress_path.parquet"     # pentarch pension_signal(06:40)이 매일 갱신


@functools.lru_cache(maxsize=1)
def _g1s_inputs() -> tuple[pd.Series | None, pd.Series | None]:
    """(실업률 일별 — 관측월 다음 달 7일부터 사용, 스트레스 일별). 실패하면 None (→ G1S 고용 유예를 쓰지 않음 = v1.1 규칙)."""
    try:
        u = pd.read_csv("https://fred.stlouisfed.org/graph/fredgraph.csv?id=UNRATE", na_values=".").dropna()
        un = u.set_index(pd.to_datetime(u["observation_date"]) + pd.DateOffset(months=1, days=7))["UNRATE"].astype(float)
    except Exception as e:                                          # 네트워크 실패는 경고만, 규칙은 보수 쪽으로
        print(f"⚠️ 실업률(UNRATE) 수집 실패 — G1S 고용 유예 끔: {e}")
        un = None
    try:
        st = pd.read_parquet(STRESS_PATH)["stress"].astype(bool)
    except Exception as e:
        print(f"⚠️ 스트레스 경로 없음 — G1S 고용 유예 끔: {e}")
        st = None
    return un, st


def employment_hold(prices, d) -> bool:
    """pentarch docs/123 G1S — 실업률(하루 늦게) ≤ 그 252거래일 평균 ∧ d 가 W2 스트레스 국면이 아님."""
    un, st = _g1s_inputs()
    if un is None or st is None:
        return False
    if st.index[-1] < d - pd.Timedelta(days=7):                     # 스트레스 경로가 오래됐으면 쓰지 않는다
        return False
    ud = un.reindex(un.index.union(prices.index)).ffill().reindex(prices.index).shift(1)
    ok = ud <= ud.rolling(252, min_periods=200).mean()
    return bool(ok.asof(d)) and not bool(st.asof(d))


INFL_ON, INFL_OFF = 2.15, 1.85   # docs/127 I3: 5년 BEI 켜기/끄기 문턱(띠 폭 2h = BEI 월간 변화 1σ 0.26%p, 중심 2.0)


def inflation_hysteresis(prices, t5yie, on: float = INFL_ON, off: float = INFL_OFF) -> pd.Series:
    """인플레 판정 = 수준(히스테리시스: BEI > on 이면 켜고 < off 이면 끄고, 사이면 직전 상태) ∧ 모멘텀(기존 그대로).
    모멘텀 부분은 _macro_series 에 BEI + 10 을 넣어(수준 항상 통과) 얻는다 — 백테스트(ic127_grid)와 같은 계산."""
    import fng_engine as F
    _, mom, _ = F._macro_series(prices, t5yie + 10.0)
    level, state = [], False
    for x in t5yie.reindex(mom.index).to_numpy():
        if np.isfinite(x):
            state = True if x > on else (False if x < off else state)
        level.append(state)
    return pd.Series(level, index=mom.index) & mom.fillna(False).astype(bool)


DISINFL_LEVEL, DISINFL_LOOKBACK = 3.0, 6   # pentarch docs/129 A2: 헤드라인 CPI 전년비 ≥ 3% ∧ 6개월 전보다 낮음 = 디스인플레이션
CPI_LAG = pd.DateOffset(months=1, days=24)  # 관측월 m 은 m+1 월 25일부터 사용(백테스트 PIT 발표일 22~24일과 같은 월말 판정)
CPI_STALE_DAYS = 80                         # 마지막 사용 가능 관측이 이보다 오래되면 A2 를 쓰지 않는다


@functools.lru_cache(maxsize=1)
def _headline_cpi() -> pd.Series | None:
    """헤드라인 CPI(비계절조정 CPIAUCNS) — 사용 가능일 기준 인덱스. 실패하면 None (→ A2 끔 = v2.1 규칙)."""
    try:
        c = pd.read_csv("https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCNS", na_values=".").dropna()
        return c.set_index(pd.to_datetime(c["observation_date"]) + CPI_LAG)["CPIAUCNS"].astype(float)
    except Exception as e:
        print(f"⚠️ 헤드라인 CPI(CPIAUCNS) 수집 실패 — A2 디스인플레이션 판정 끔: {e}")
        return None


def disinflation_series(index: pd.DatetimeIndex) -> pd.Series | None:
    """docs/129 A2 — 일별 디스인플레이션 국면(하루 늦게). CPI 가 없거나 오래됐으면 None."""
    c = _headline_cpi()
    if c is None or len(c) < 24 or c.index[-1] < index[-1] - pd.Timedelta(days=CPI_STALE_DAYS):
        if c is not None:
            print(f"⚠️ 헤드라인 CPI 가 오래됨(마지막 사용 가능 {c.index[-1].date()}) — A2 끔")
        return None
    yoy = (c / c.shift(12) - 1) * 100
    flag = (yoy >= DISINFL_LEVEL) & (yoy < yoy.shift(DISINFL_LOOKBACK))
    return flag.reindex(flag.index.union(index)).ffill().reindex(index).shift(1).fillna(False).astype(bool)


def cpi_yoy_now(d) -> float | None:
    c = _headline_cpi()
    if c is None:
        return None
    yoy = (c / c.shift(12) - 1) * 100
    return float(yoy.asof(d)) if yoy.loc[:d].notna().any() else None


def ic_pension_weights(prices, t5yie, vix, baa10y) -> dict:
    """IC 연금형 v2.2 오늘 기준 목표 비중(레버리지 없음, 상시 보험 없음 — 2026-10-30 사용자 결정: 계좌가 복잡해진다).
    성장 = S&P > 200일선 ∨ G1S 고용 유예(docs/123) ∨ T4 신용 확인 재진입(docs/112)."""
    import fng_engine as F
    idx = F.compute_synthetic_fng_series(prices, baa10y, vix).dropna()
    g, _, below = F._macro_series(prices, t5yie)
    inf = inflation_hysteresis(prices, t5yie)          # docs/127 I3
    dis = disinflation_series(inf.index)                # docs/129 A2: 높지만 하락하는 물가면 인플레 칸을 쓰지 않는다
    if dis is not None:
        inf = inf & ~dis
    d = idx.index[-1]
    disinfl = None if dis is None else bool(dis.asof(d))
    exposure = 0.5 if idx.loc[d] > 85 else 1.0
    reentry = reentry_ok(prices, baa10y).asof(d)
    hold = (not bool(g.loc[d])) and employment_hold(prices, d)
    growth = bool(g.loc[d]) or hold or bool(reentry)
    w = F.confirmed_weights(growth, bool(inf.loc[d]), bool(below.loc[d]), exposure, sleeve={})
    return {"date": d, "index": float(idx.loc[d]), "growth_on": growth, "inflation_on": bool(inf.loc[d]),
            "bei": round(float(t5yie.dropna().iloc[-1]), 2), "infl_band": [INFL_OFF, INFL_ON],
            "disinflation": disinfl, "cpi_yoy": (round(cpi_yoy_now(d), 2) if cpi_yoy_now(d) is not None else None),
            "reentry": bool(reentry) and not bool(g.loc[d]) and not hold, "employment_hold": hold,
            "version": IC_VERSION, **w}


def reentry_ok(prices, baa10y) -> pd.Series:
    """pentarch docs/112 T4 — BAA10Y(하루 늦게) 63거래일 변화 < 0 그리고 SPY 63거래일 수익 > 0 인 날.
    성장 신호(S&P > 200일선)가 꺼져 있어도 이 날은 성장 칸으로 돌아간다(빠지는 규칙은 그대로)."""
    baa = baa10y.reindex(prices.index).ffill().shift(1)
    spy = prices["SPY"]
    return (((baa - baa.shift(63)) < 0) & (spy / spy.shift(63) - 1 > 0)).fillna(False)


def pension_mix_position(prices, t5yie, vix, baa10y) -> dict:
    """연금형 70/30 오늘 기준 목표 비중. BAA-G4 는 오늘 가격을 이번 달 말 값으로 본 미리보기."""
    px, monthly = load_monthly()
    ic = ic_pension_weights(prices, t5yie, vix, baa10y)
    baa = baa_target(px, monthly, monthly.index[-1])
    total: dict = {}
    for k, w in ic["final_weights"].items():
        total[k] = total.get(k, 0) + IC_WEIGHT * w
    for k, w in baa.items():
        total[k] = total.get(k, 0) + BAA_WEIGHT * w
    return {"ic": ic, "baa": baa, "weights": total, "baa_asof": monthly.index[-1]}


def weights_str(w: dict) -> str:
    return " + ".join(f"{k} ({TICKER_KR.get(k, k)}) {v * 100:.0f}%" for k, v in sorted(w.items(), key=lambda x: -x[1]))


if __name__ == "__main__":
    for cost in (30, 5):
        ic_m, dtb3 = ic_pension_monthly(cost_bp=cost)
        px, monthly = load_monthly(dtb3)
        ic_m.index = ic_m.index.to_period("M").to_timestamp("M")
        last_full = pd.Timestamp.today().to_period("M").to_timestamp("M") - pd.offsets.MonthEnd(1)
        series = {"IC 연금형": ic_m}
        for v, lab in (("keller", "BAA-G4 (켈러 원본)"), ("research", "BAA-G4 (연구판)")):
            bt = baa_backtest(px, monthly, v, cost)
            bt.index = pd.DatetimeIndex(bt.index).to_period("M").to_timestamp("M")
            series[lab] = bt["ret"]
            if v == "keller" and cost == 30:
                print(f"켈러 원본 평균 회전율 {bt['turnover'].mean():.2f}/월, 공격 비율 {bt['hold'].apply(lambda h: len(h) == 1 and list(h)[0] in ATTACK).mean():.0%}")
        df = pd.DataFrame(series).dropna()
        df = df[df.index <= last_full]
        df["70/30 (켈러)"] = mix(df["IC 연금형"], df["BAA-G4 (켈러 원본)"], cost_bp=cost)
        df["70/30 (연구판)"] = mix(df["IC 연금형"], df["BAA-G4 (연구판)"], cost_bp=cost)
        c = df.index
        print(f"\n===== 편도 비용 {cost}bp · 기간 {c[0]:%Y-%m} ~ {c[-1]:%Y-%m} ({len(c)}개월) =====")
        for a, b, lab in ((c[0], c[-1], "전체"), (c[0], "2015-12-31", "전반"), ("2016-01-31", c[-1], "후반")):
            print(f"[{lab}] | 전략 | CAGR | MDD(월말) | Calmar | 변동성 | 최악 월 |")
            for col in df.columns:
                st = stats(df.loc[a:b, col])
                print(f"| {col} | {st['CAGR']:.2%} | {st['MDD']:.2%} | {st['Calmar']:.2f} | {st['Vol']:.1%} | {st['worst']:+.1%} |")
        print("상관(전체):", df[["IC 연금형", "BAA-G4 (켈러 원본)"]].corr().iloc[0, 1].round(2),
              "| IC 손실 달:", df[df["IC 연금형"] < 0][["IC 연금형", "BAA-G4 (켈러 원본)"]].corr().iloc[0, 1].round(2))
