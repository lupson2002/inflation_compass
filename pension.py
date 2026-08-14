"""연금 운용용 IC 50/25/25 전략 — 현재 포지션 계산.

전략 구성 (dual-momentum 연구 결과):
  - IC (Inflation Compass) 50%  : 성장/인플레이션 레짐 → GLD/QQQ/TLT
  - BAA-G4 (Keller Bold) 25%     : 카나리아 모멘텀 → 공격(QQQ) / 방어(TLT)
  - V8 (모멘텀 Top-1) 25%        : SPY 12M 절대모멘텀 → QQQ / TLT

이 프로젝트의 성장(SPY>200SMA)·인플레이션(T5YIE) 신호를 재사용해
IC 성분의 레짐을 결정하고, 나머지는 모멘텀 근사로 매핑한다.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

import backtest

# ── 종목 매핑 ──
TICKER_KR = {
    "GLD": "금",
    "QQQ": "나스닥",
    "TLT": "장기국채",
    "BIL": "현금",
}

# IC 성분: 레짐 → 자산
IC_REGIME_MAP = {
    (True, True): "GLD",    # 성장↑ 인플레↑ → 금
    (True, False): "QQQ",   # 성장↑ 인플레↓ → 나스닥
    (False, True): "GLD",   # 성장↓ 인플레↑ → 금
    (False, False): "TLT",  # 성장↓ 인플레↓ → 장기국채
}

# 전략 비중
IC_W = 0.50
BAAG4_W = 0.25
V8_W = 0.25

# ── 전략 2: IC+V8 (70/30) ──
IC2_W = 0.70
V8_2_W = 0.30


def current_regime():
    """이 프로젝트 신호로 현재 성장/인플레이션 레짐 계산."""
    prices, t5yie = backtest.load_data()
    signals, _ = backtest.compute_signals(prices, t5yie)
    last = signals.iloc[-1]
    return (bool(last["growth_on"]), bool(last["inflation_on"])), last.name


def spy_12m_momentum():
    """SPY 12개월 모멘텀 (절대모멘텀 근사)."""
    prices, _ = backtest.load_data()
    spy = prices["SPY"].dropna()
    if len(spy) < 252:
        return None
    mom = spy.iloc[-1] / spy.iloc[-252] - 1
    return mom


def baag4_asset(regime):
    """BAA-G4: 카나리아(성장) 모멘텀 → 공격/방어. 레짐으로 근사."""
    growth_on = regime[0]
    return "QQQ" if growth_on else "TLT"


def v8_asset():
    """V8: SPY 12M 절대모멘텀 → 양수면 QQQ, 음수면 TLT."""
    mom = spy_12m_momentum()
    if mom is None:
        return "TLT"
    return "QQQ" if mom > 0 else "TLT"


def pension_position():
    """IC 50/25/25 현재 포지션 (자산: 비중 dict)."""
    regime, signal_date = current_regime()
    ic_asset = IC_REGIME_MAP[regime]
    baag4_asset_ = baag4_asset(regime)
    v8_asset_ = v8_asset()

    weights = {}
    for asset, w in [(ic_asset, IC_W), (baag4_asset_, BAAG4_W), (v8_asset_, V8_W)]:
        weights[asset] = weights.get(asset, 0.0) + w

    return {
        "regime": regime,
        "signal_date": signal_date,
        "ic_asset": ic_asset,
        "baag4_asset": baag4_asset_,
        "v8_asset": v8_asset_,
        "weights": weights,
        "spy_12m_mom": spy_12m_momentum(),
    }


def weights_str(weights):
    return " + ".join(f"{t} ({TICKER_KR.get(t, t)}) {w * 100:.0f}%" for t, w in weights.items())


def pension_position2():
    """전략 2: IC+V8 (70/30) 현재 포지션 (자산: 비중 dict)."""
    regime, signal_date = current_regime()
    ic_asset = IC_REGIME_MAP[regime]
    v8_asset_ = v8_asset()

    weights = {}
    for asset, w in [(ic_asset, IC2_W), (v8_asset_, V8_2_W)]:
        weights[asset] = weights.get(asset, 0.0) + w

    return {
        "regime": regime,
        "signal_date": signal_date,
        "ic_asset": ic_asset,
        "v8_asset": v8_asset_,
        "weights": weights,
        "spy_12m_mom": spy_12m_momentum(),
    }


if __name__ == "__main__":
    pos = pension_position()
    print(f"신호일: {pos['signal_date'].date()}")
    print(f"레짐: 성장 {'상승' if pos['regime'][0] else '하락'} · 인플레이션 {'상승' if pos['regime'][1] else '하락'}")
    print(f"IC(50%): {pos['ic_asset']} · BAA-G4(25%): {pos['baag4_asset']} · V8(25%): {pos['v8_asset']}")
    print(f"SPY 12M 모멘텀: {pos['spy_12m_mom'] * 100:+.1f}%")
    print(f"종합 포지션: {weights_str(pos['weights'])}")
    print()
    pos2 = pension_position2()
    print(f"[전략2] IC+V8 (70/30)")
    print(f"  IC(70%): {pos2['ic_asset']} · V8(30%): {pos2['v8_asset']}")
    print(f"  종합 포지션: {weights_str(pos2['weights'])}")
