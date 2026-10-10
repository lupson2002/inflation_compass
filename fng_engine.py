"""IC 위험선호 지수 & 확정 전략 포지션 계산기 (2026-10-09 개편).

- 신호: **IC 위험선호 지수** — 4요소(S&P 모멘텀·VIX·주식-채권 20일 차이·BAA 스프레드)를 1년 백분위로 평균한
  0~100 지수. 연구(run_16_matrix_experiments)와 같은 지수라 백테스트 규칙이 그대로 맞는다.
  (종전엔 "CNN Fear & Greed" 로 불렀지만 CNN 지수가 아니라 이 대리 지표였다.)
- 참고: CNN Fear & Greed 실지수(현재값 + GitHub 아카이브 2011~)는 화면·메시지에 비교용으로만 표시한다.
- 레버리지: 당월 지수 < 15 → 2배, > 85 → 0.5배, 그 외 1배. 지연 공포(2~4개월 전) 2배는 CNN 검증에서 무너져 제외.
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import requests
import yfinance as yf

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "inflation_compass.db"

CNN_API_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
CNN_ARCHIVE_URL = "https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/main/fear-greed.csv"   # 2011~ 일별
INDEX_NAME = "IC 위험선호 지수"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.cnn.com/",
}

POS_BASKET = {"XLE": 0.5, "XLI": 1 / 6, "XLF": 1 / 6, "XLB": 1 / 6}
NEG_BASKET = {"XLU": 1 / 3, "XLV": 1 / 3, "XLP": 1 / 3}


def get_cnn_live_fng():
    """Fetch live CNN Fear & Greed index from official dataviz endpoint."""
    try:
        r = requests.get(CNN_API_URL, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            data = r.json()
            curr = data.get("fear_and_greed", {})
            score = float(curr.get("score", 50.0))
            rating = str(curr.get("rating", "neutral")).replace("_", " ").title()
            hist = data.get("fear_and_greed_historical", {}).get("data", [])
            df_hist = pd.DataFrame(hist)
            if not df_hist.empty:
                df_hist["date"] = pd.to_datetime(df_hist["x"], unit="ms").dt.tz_localize(None).dt.normalize()
                s_hist = df_hist.set_index("date")["y"].sort_index()
                s_hist = s_hist[~s_hist.index.duplicated(keep="last")]
                return score, rating, s_hist
            return score, rating, None
    except Exception as e:
        print(f"[F&G Engine] CNN live fetch fallback: {e}")
    return None, None, None


def load_cnn_archive():
    """CNN Fear & Greed 일별 이력(GitHub 공개 아카이브, 2011~). 실패 시 None — 참고 표시용."""
    try:
        df = pd.read_csv(CNN_ARCHIVE_URL)
        s_ = df.set_index(pd.to_datetime(df["Date"]))["Fear Greed"].astype(float).sort_index()
        return s_[~s_.index.duplicated(keep="last")]
    except Exception as e:
        print(f"[F&G Engine] CNN archive fetch failed: {e}")
        return None


def compute_synthetic_fng_series(prices, hy_spread, vix):
    """IC 위험선호 지수(일별 0~100) — 4요소 1년 백분위 평균. 연구 compute_signals 의 fng 와 같은 식."""
    # 1. Momentum (SPY vs 125 SMA)
    mom = (prices["SPY"] - prices["SPY"].rolling(125).mean()) / prices["SPY"].rolling(125).mean()
    score_mom = mom.rolling(252).rank(pct=True) * 100

    # 2. Volatility (^VIX vs 50 SMA, inverted)
    vol = (vix - vix.rolling(50).mean()) / vix.rolling(50).mean()
    score_vol = (1.0 - vol.rolling(252).rank(pct=True)) * 100

    # 3. Safe Haven Demand (SPY 20d return - IEF 20d return)
    safe_haven = prices["SPY"].pct_change(20) - prices["IEF"].pct_change(20)
    score_safe = safe_haven.rolling(252).rank(pct=True) * 100

    # 4. Junk Bond / Credit Spread (BAA10Y, inverted)
    score_junk = (1.0 - hy_spread.rolling(252).rank(pct=True)) * 100

    fng_synth = (score_mom + score_vol + score_safe + score_junk) / 4.0
    return fng_synth


def get_fng_rating_kr(score):
    """Return Korean sentiment label and emoji for a given F&G score."""
    if score < 25:
        return "극단적 공포 (Extreme Fear)", "😱"
    elif score < 45:
        return "공포 (Fear)", "😨"
    elif score <= 55:
        return "중립 (Neutral)", "😐"
    elif score <= 75:
        return "탐욕 (Greed)", "🤑"
    else:
        return "극단적 탐욕 (Extreme Greed)", "🔥"


IEF_MA_DAYS = 200          # 채권방어: 침체 국면에서 IEF < 200일선이면 SHY 100%
SLEEVE = {"GLD": 0.10, "BIL": 0.05}   # 상시 보험(2026-10-10, run_16_matrix_experiments.Params.sleeve_*) — 국면 칸은 85%


def fear_exposure(t0: float, growth_on: bool = True) -> tuple[float, str]:
    """노출 배수 — 연구 leverage(fear_rule="t0") 와 같은 규칙. t0 = 판단 시점 IC 위험선호 지수."""
    if t0 > 85:
        return 0.5, f"극단적 탐욕 ({INDEX_NAME} {t0:.1f} > 85) ➔ 0.5배 (절반 단기채)"
    if t0 < 15:
        return 2.0, f"극단적 공포 ({INDEX_NAME} {t0:.1f} < 15) ➔ 2.0배"
    return 1.0, f"정상 국면 ({INDEX_NAME} {t0:.1f}) ➔ 1.0배"


def confirmed_weights(growth_on: bool, inflation_on: bool, ief_below_ma: bool, exposure: float,
                      sector_up: bool = True) -> dict:
    """확정 전략(2026-10-10, run_16_matrix_experiments 기본 Params) 목표 비중.

    - 국면 칸 85% + 상시 보험 15%(금 GLD 10 · 초단기채 BIL 5). 배수는 이 비중 전체에 곱한다.
    - 침체 국면(성장·인플레 모두 꺼짐): IEF 100(× 0.85) — 2026-10-10 GEM 결합(종전 XLP 50 + IEF 50).
      IEF < 200일선이면 SHY 100%(× 0.85) 이고 1배로 제한.
    - 침체 국면 2배: 늘린 몫은 IEF 에만 → IEF 185 + GLD 10 + BIL 5.
    - 주식 칸(XLE·XLK·XLU) 2배는 그 섹터가 자기 200일선 위일 때만(sector_up), 아니면 1배.
    - 0.5배: 나머지 50% 는 단기채(SHY)로 둔다(백테스트는 T-bill 이자).
    """
    slowdown = not growth_on and not inflation_on
    shield = slowdown and ief_below_ma
    if growth_on and inflation_on:
        regime = {"XLE": 1.0}
    elif growth_on:
        regime = {"XLK": 1.0}
    elif inflation_on:
        regime = {"XLU": 1.0}
    elif shield:
        regime = {"SHY": 1.0}
    else:
        regime = {"IEF": 1.0}
    ins = sum(SLEEVE.values())
    base = {k: v * (1 - ins) for k, v in regime.items()}
    for k, v in SLEEVE.items():
        base[k] = base.get(k, 0.0) + v
    sector_capped = False
    if exposure > 1.0 and (shield or (not slowdown and not sector_up)):
        exposure, sector_capped = 1.0, not slowdown
    if slowdown and not shield and exposure > 1.0:
        final = dict(base)
        final["IEF"] = base["IEF"] + (exposure - 1.0)
    else:
        final = {t: w * exposure for t, w in base.items()}
        if exposure < 1.0:
            final["SHY"] = final.get("SHY", 0.0) + (1.0 - exposure)
    return {"exposure": exposure, "base_weights": base, "regime_weights": regime, "final_weights": final,
            "bond_shield": shield, "sector_capped": sector_capped}


def _macro_series(prices, t5yie):
    """일별 성장·인플레 신호와 IEF 200일선 아래 여부(백테스트 compute_signals 와 같은 정의)."""
    growth = prices["SPY"] > prices["SPY"].rolling(200).mean()
    returns = prices.pct_change()
    pos_ret = sum(returns[t] * w for t, w in POS_BASKET.items())
    neg_ret = sum(returns[t] * w for t, w in NEG_BASKET.items())
    valid = pos_ret.notna() & neg_ret.notna()
    indicator = (1 + pos_ret.where(valid, 0)).cumprod().where(valid) / (1 + neg_ret.where(valid, 0)).cumprod().where(valid)
    x = np.arange(60)
    xm = x - x.mean()
    denom = (xm ** 2).sum()
    slope = indicator.rolling(60).apply(lambda y: (xm * (y - y.mean())).sum() / denom, raw=True)
    inflation = (t5yie > 2.0) & ((t5yie > t5yie.shift(60)) | (slope > 0))
    ief_below = prices["IEF"] <= prices["IEF"].rolling(IEF_MA_DAYS, min_periods=60).mean()
    return growth, inflation, ief_below


def sector_trend(prices) -> pd.DataFrame:
    """XLE·XLK·XLU 가 자기 200일선 위인가(주식 칸 2배 조건)."""
    return pd.DataFrame({t: prices[t] > prices[t].rolling(200).mean() for t in ("XLE", "XLK", "XLU")})


def regime_sector(growth_on: bool, inflation_on: bool) -> str | None:
    if growth_on:
        return "XLE" if inflation_on else "XLK"
    return "XLU" if inflation_on else None


def _decision_at(index_series, growth, inflation, ief_below, d, trend=None):
    """d 시점 판단(그 날의 IC 위험선호 지수·국면·IEF 200일선·보유 섹터 자기 추세)."""
    t0 = float(index_series.loc[d])
    g, inf, below = bool(growth.loc[d]), bool(inflation.loc[d]), bool(ief_below.loc[d])
    sec = regime_sector(g, inf)
    up = True if (trend is None or sec is None) else bool(trend.loc[d, sec])
    exposure, reason = fear_exposure(t0, g)
    w = confirmed_weights(g, inf, below, exposure, sector_up=up)
    if w["sector_capped"]:
        reason += f" · {sec} 가 자기 200일선 아래 ➔ 2배 대신 1배"
    if w["bond_shield"]:
        reason += " · 채권방어(IEF < 200일선) ➔ 단기채 100%" + (", 1배 제한" if exposure > 1 else "")
    elif not g and not inf and exposure > 1:
        reason += " · 침체 국면: 늘린 몫은 IEF 에만"
    return {"date": d, "index": t0, "growth_on": g, "inflation_on": inf, "reason": reason, **w}


def calculate_model_c1_ultra_position(prices, t5yie, vix, hy_spread):
    """확정 전략의 오늘 시점 포지션과 직전 월말 결정(신호 = IC 위험선호 지수, CNN 은 참고)."""
    index_series = compute_synthetic_fng_series(prices, hy_spread, vix).dropna()
    growth, inflation, ief_below = _macro_series(prices, t5yie)
    me = sorted(index_series.groupby([index_series.index.year, index_series.index.month]).apply(lambda x: x.index[-1]).values)
    me = [pd.Timestamp(d) for d in me]
    trend = sector_trend(prices)
    live = _decision_at(index_series, growth, inflation, ief_below, me[-1], trend)
    prev = _decision_at(index_series, growth, inflation, ief_below, me[-2], trend)

    cnn_score, cnn_rating, _ = get_cnn_live_fng()
    cnn_hist = load_cnn_archive()
    cur = live["index"]
    rating_kr, emoji = get_fng_rating_kr(cur)
    return {
        "index_name": INDEX_NAME,
        "current_fng": cur,
        "current_rating_kr": rating_kr,
        "current_emoji": emoji,
        "cnn_score": cnn_score,
        "cnn_rating_kr": get_fng_rating_kr(cnn_score)[0] if cnn_score is not None else "조회 실패",
        "growth_on": live["growth_on"],
        "inflation_on": live["inflation_on"],
        "bond_shield": live["bond_shield"],
        "base_weights": live["base_weights"],
        "exposure": live["exposure"],
        "action_reason": live["reason"],
        "final_weights": live["final_weights"],
        "prev_decision": prev,
        "fng_series": index_series,
        "cnn_series": cnn_hist,
    }
