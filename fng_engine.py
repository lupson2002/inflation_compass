"""CNN Fear & Greed Engine & Model C-1 Ultra Position Calculator.

Provides:
  - Real-time and Synthetic Fear & Greed index fetching
  - Model C-1 Ultra signal calculation (2.0x / 1.0x / 0.5x exposure)
  - Historical lookback flags (t0, t-1, t-2, t-3, t-4)
  - Helper functions for Streamlit UI and Telegram daily alerts
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


def compute_synthetic_fng_series(prices, hy_spread, vix):
    """Compute daily 4-component synthetic Fear & Greed index (2000~2026)."""
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


def fear_exposure(t0: float, t2: float, t3: float, t4: float, growth_on: bool) -> tuple[float, str]:
    """Model C-1 Ultra 노출 배수 — 백테스트(run_16_matrix_experiments.leverage)와 같은 규칙."""
    if t0 > 85:
        return 0.5, f"극단적 탐욕 (F&G {t0:.1f} > 85) ➔ 0.5배 (절반 현금)"
    if t0 < 15:
        return 2.0, f"당월 극단적 공포 (F&G {t0:.1f} < 15) ➔ 2.0배"
    if t2 < 15:
        return 2.0, f"2개월 전 극단적 공포 ({t2:.1f} < 15) ➔ 2.0배"
    if (t3 < 15 or t4 < 15) and growth_on:
        lag, val = ("3개월", t3) if t3 < 15 else ("4개월", t4)
        return 2.0, f"{lag} 전 공포 ({val:.1f} < 15) + S&P 200일선 위 ➔ 2.0배"
    return 1.0, "정상 국면 ➔ 1.0배"


def confirmed_weights(growth_on: bool, inflation_on: bool, ief_below_ma: bool, exposure: float) -> dict:
    """확정 전략(2026-10-09, run_16_matrix_experiments M02 + slowdown_lev='ief_only') 목표 비중.

    - 침체 국면(성장·인플레 모두 꺼짐): XLP 50 + IEF 50. IEF < 200일선이면 SHY 100% 이고 레버리지는 1배로 제한.
    - 침체 국면 2배: 늘린 몫은 IEF 에만 → XLP 50 + IEF 150.
    - 0.5배: 나머지 50% 는 단기채(SHY)로 둔다(백테스트는 T-bill 이자).
    """
    slowdown = not growth_on and not inflation_on
    shield = slowdown and ief_below_ma
    if growth_on and inflation_on:
        base = {"XLE": 1.0}
    elif growth_on:
        base = {"XLK": 1.0}
    elif inflation_on:
        base = {"XLU": 1.0}
    elif shield:
        base = {"SHY": 1.0}
    else:
        base = {"XLP": 0.5, "IEF": 0.5}
    if shield and exposure > 1.0:
        exposure = 1.0
    if slowdown and not shield and exposure > 1.0:
        final = {"XLP": 0.5, "IEF": 0.5 + (exposure - 1.0)}
    else:
        final = {t: w * exposure for t, w in base.items()}
        if exposure < 1.0:
            final["SHY"] = final.get("SHY", 0.0) + (1.0 - exposure)
    return {"exposure": exposure, "base_weights": base, "final_weights": final, "bond_shield": shield}


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


def _decision_at(fng_series, growth, inflation, ief_below, month_ends, j, t0_override=None):
    """month_ends[j] 시점 판단. 공포 룩백은 그 시점 기준 당월·2·3·4개월 전 월말."""
    d = month_ends[j]
    look = [float(fng_series.loc[month_ends[j - k]]) if len(month_ends) + j - k >= 0 else np.nan for k in range(5)]
    t0 = look[0] if t0_override is None else t0_override
    g, inf, below = bool(growth.loc[d]), bool(inflation.loc[d]), bool(ief_below.loc[d])
    exposure, reason = fear_exposure(t0, look[2], look[3], look[4], g)
    w = confirmed_weights(g, inf, below, exposure)
    if w["bond_shield"]:
        reason += " · 채권방어(IEF < 200일선) ➔ 단기채 100%" + (", 1배 제한" if exposure > 1 else "")
    elif not g and not inf and exposure > 1:
        reason += " · 침체 국면: 늘린 몫은 IEF 에만"
    return {"date": d, "growth_on": g, "inflation_on": inf, "reason": reason, "lookback": look, **w}


def calculate_model_c1_ultra_position(prices, t5yie, vix, hy_spread):
    """확정 전략의 오늘 시점 포지션과 직전 월말 결정.

    공포·탐욕은 CNN 실지수(최근 1년 일별 이력 + 현재값)를 쓴다. CNN 이 응답하지 않을 때만
    합성 대리 지표로 대신하고 fng_source 에 그 사실을 남긴다(대시보드·텔레그램에 표시).
    """
    fng_synth = compute_synthetic_fng_series(prices, hy_spread, vix)
    live_score, live_rating, live_hist = get_cnn_live_fng()

    fng_series = fng_synth.copy()
    cnn_ok = live_hist is not None and not live_hist.empty
    if cnn_ok:
        common_idx = live_hist.index.intersection(fng_series.index)
        fng_series.loc[common_idx] = live_hist.loc[common_idx]
    fng_source = "CNN 실지수" if live_score is not None else "⚠️ 합성 대리 지표 (CNN 응답 없음)"

    current_fng = float(live_score) if live_score is not None else float(fng_series.iloc[-1])
    current_rating_kr, current_emoji = get_fng_rating_kr(current_fng)

    growth, inflation, ief_below = _macro_series(prices, t5yie)
    month_ends = sorted(fng_series.groupby([fng_series.index.year, fng_series.index.month]).apply(lambda x: x.index[-1]).values)
    month_ends = [pd.Timestamp(d) for d in month_ends]

    live = _decision_at(fng_series, growth, inflation, ief_below, month_ends, -1, t0_override=current_fng)
    prev = _decision_at(fng_series, growth, inflation, ief_below, month_ends, -2)
    t0, t1, t2, t3, t4 = live["lookback"][0], live["lookback"][1], live["lookback"][2], live["lookback"][3], live["lookback"][4]

    return {
        "current_fng": current_fng,
        "current_rating_kr": current_rating_kr,
        "current_emoji": current_emoji,
        "fng_source": fng_source,
        "growth_on": live["growth_on"],
        "inflation_on": live["inflation_on"],
        "bond_shield": live["bond_shield"],
        "base_weights": live["base_weights"],
        "exposure": live["exposure"],
        "action_reason": live["reason"],
        "final_weights": live["final_weights"],
        "prev_decision": prev,
        "t0_fng": t0,
        "t1_fng": t1,
        "t2_fng": t2,
        "t3_fng": t3,
        "t4_fng": t4,
        "fng_series": fng_series,
    }
