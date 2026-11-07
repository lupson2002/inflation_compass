"""일반계좌 레버리지 판단층 V1 (pentarch docs/148, 2026-11-06 사용자 확정).

매 월말 판단일에 계좌 비중의 '현금 대비 기대 초과수익(밸류 블록)' 을 계산해 대출 가산금리를 넘으면 대출한다.
- 주식류 = 이익수익률(1/CAPE, shiller.parquet 은 이미 공시 시차 45일 반영) + 기대 물가(T10YIE) − 단기금리(DTB3)
- IEF·TLT = 10년 금리 − 단기금리 · SHY = 2년 금리 − 단기금리 · 금·원자재 = 기대 물가 − 단기금리 · 현금 0
입력이 없거나 오래됐으면 **대출하지 않는다**(판정 보류). 판단은 월 1회, 월중에는 바꾸지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

MACRO_PIT = "/home/mikey/pentarch/data/point_in_time/macro_pit.parquet"
SHILLER = "/home/mikey/pentarch/data/raw/shiller.parquet"
LOAN_SPREAD = 0.035                # 대출금리 − 단기금리(백테스트 가정). 실제 대출금리가 정해지면 이 값을 맞춘다.
LOAN_RATIO = 0.5                   # 백테스트 L = 1.5 → 대출액 = 연금 평가액 × 50%
MAX_RATE_AGE_DAYS = 5
MAX_CAPE_AGE_DAYS = 65
COMMODITY = {"GLD", "DBC", "GUNR"}
LONG_BOND = {"IEF", "TLT"}
CASH = {"BIL"}


@dataclass(frozen=True)
class Inputs:
    ey: float                      # 소수
    be: float                      # 이하 %
    y10: float
    y2: float
    bill: float


@dataclass(frozen=True)
class Decision:
    on: bool
    excess: float | None           # 연율 소수
    problem: str | None = None


def value_excess(weights: dict[str, float], x: Inputs) -> float:
    cash = x.bill / 100
    equity = x.ey + x.be / 100 - cash
    total = 0.0
    for asset, w in weights.items():
        if asset in CASH:
            v = 0.0
        elif asset in LONG_BOND:
            v = x.y10 / 100 - cash
        elif asset == "SHY":
            v = x.y2 / 100 - cash
        elif asset in COMMODITY:
            v = x.be / 100 - cash
        else:
            v = equity
        total += w * v
    return total


def read_inputs(d, macro: pd.DataFrame, shiller: pd.Series) -> tuple[Inputs | None, str | None]:
    d = pd.Timestamp(d)
    vals = {}
    for col in ("T10YIE", "DGS10", "DGS2", "DTB3"):
        s = macro[col].dropna().loc[:d]
        if s.empty or (d - s.index[-1]).days > MAX_RATE_AGE_DAYS:
            return None, f"{col} 자료가 {d:%m-%d} 기준으로 오래됨"
        vals[col] = float(s.iloc[-1])
    obs = shiller.dropna().loc[:d]
    if obs.empty or (d - obs.index[-1]).days > MAX_CAPE_AGE_DAYS:
        return None, f"CAPE 자료가 {d:%m-%d} 기준으로 오래됨"
    return Inputs(ey=float(obs.iloc[-1]), be=vals["T10YIE"], y10=vals["DGS10"], y2=vals["DGS2"], bill=vals["DTB3"]), None


def decide(weights: dict[str, float] | None, d, macro: pd.DataFrame | None, shiller: pd.Series | None) -> Decision:
    if not weights:
        return Decision(False, None, "계좌 비중 없음")
    if macro is None or shiller is None:
        return Decision(False, None, "금리·CAPE 파일 없음")
    x, problem = read_inputs(d, macro, shiller)
    if x is None:
        return Decision(False, None, problem)
    e = value_excess(weights, x)
    return Decision(e > LOAN_SPREAD, e)


def load_sources() -> tuple[pd.DataFrame | None, pd.Series | None]:
    try:
        return pd.read_parquet(MACRO_PIT), pd.read_parquet(SHILLER)["earnings_yield"]
    except Exception as e:
        print(f"⚠️ 레버리지 입력 읽기 실패: {e}")
        return None, None


def _state(x: Decision) -> str:
    return f"기대 초과 {x.excess * 100:+.2f}% / 문턱 {LOAN_SPREAD * 100:.1f}%"


def order_lines(now: Decision, prev: Decision | None, trade_today: bool, blocked: bool, held_d) -> list[str]:
    """주문서 레버리지 칸. prev 는 월말 판단일 아침에만 쓴다(직전 달 상태)."""
    head = f"💳 <b>일반계좌 레버리지(V1)</b> {pd.Timestamp(held_d):%m-%d} 판단"
    ratio = f"연금 평가액의 {LOAN_RATIO * 100:.0f}%"
    if now.problem:
        return [head, f"   ⛔ 판정 불가({now.problem}) → 신규 대출 금지, 입력 복구 후 재확인"]
    state = _state(now)
    if not trade_today:
        return [head + (" · <b>대출 운용 중</b>" if now.on else " · <b>대출 없음</b>"), f"   {state}"]
    if blocked:
        return [head, f"   ⛔ 위 경고 해결 전 대출·상환 보류 ({state})"]
    was_on = bool(prev and prev.on)
    if now.on and not was_on:
        act = f"🟢 <b>대출 시작</b>: {ratio} 대출 → 일반계좌에서 위 비중대로 매수"
    elif now.on:
        act = f"🟢 <b>대출 유지</b>: 대출액을 {ratio}에 맞추고 위 비중대로 교체"
    elif was_on:
        act = "🔴 <b>전량 매도 → 대출 상환</b>"
    else:
        act = "대출 없음 · 할 일 없음"
    lines = [head, f"   {act}", f"   {state}"]
    if now.on or was_on:
        lines.append("   ⚠️ 일반계좌 세금: 아래 국내 상장 ETF 는 매매차익 15.4%·금융소득종합과세 대상 — 해외 상장 ETF(22%)·금은 KRX 금현물 검토, 세무 확인")
    if prev is not None and prev.problem:
        lines.append(f"   ⚠️ 직전 달 판정 불가({prev.problem}) — 실제 대출 잔액과 대조")
    return lines
