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


def calculate_model_c1_ultra_position(prices, t5yie, vix, hy_spread):
    """Calculate Model C-1 Ultra position, lookback triggers, and exposure multiplier."""
    fng_synth = compute_synthetic_fng_series(prices, hy_spread, vix)
    live_score, live_rating, live_hist = get_cnn_live_fng()

    # Blend live score into series if available
    fng_series = fng_synth.copy()
    if live_hist is not None and not live_hist.empty:
        common_idx = live_hist.index.intersection(fng_series.index)
        fng_series.loc[common_idx] = live_hist.loc[common_idx]

    current_fng = float(live_score) if live_score is not None else float(fng_series.iloc[-1])
    current_rating_kr, current_emoji = get_fng_rating_kr(current_fng)

    # Macro Signals (Growth & Inflation)
    spy_sma200 = prices["SPY"].rolling(200).mean()
    growth_on = bool(prices["SPY"].iloc[-1] > spy_sma200.iloc[-1])

    # Inflation Signal
    returns = prices.pct_change()
    pos_ret = sum(returns[t] * w for t, w in POS_BASKET.items())
    neg_ret = sum(returns[t] * w for t, w in NEG_BASKET.items())
    basket_valid = pos_ret.notna() & neg_ret.notna()
    pos_cum = (1 + pos_ret.where(basket_valid, 0)).cumprod().where(basket_valid)
    neg_cum = (1 + neg_ret.where(basket_valid, 0)).cumprod().where(basket_valid)
    indicator = pos_cum / neg_cum

    x = np.arange(60)
    x_mean = x.mean()
    denom = ((x - x_mean) ** 2).sum()

    def slope_val(y):
        return ((x - x_mean) * (y - y.mean())).sum() / denom

    slope_60 = indicator.rolling(60).apply(slope_val, raw=True).iloc[-1]
    asset_mom = bool(slope_60 > 0)
    level_on = bool(t5yie.iloc[-1] > 2.0)
    be_mom = bool(t5yie.iloc[-1] > t5yie.shift(60).iloc[-1])
    inflation_on = level_on and (be_mom or asset_mom)

    # Monthly Decision Dates for Lookback
    month_ends = fng_series.groupby([fng_series.index.year, fng_series.index.month]).apply(lambda x: x.index[-1]).values
    month_ends = sorted(month_ends)

    # Lookback lags
    last_me = month_ends[-1]
    t0_fng = float(fng_series.loc[last_me])
    t1_fng = float(fng_series.loc[month_ends[-2]]) if len(month_ends) >= 2 else t0_fng
    t2_fng = float(fng_series.loc[month_ends[-3]]) if len(month_ends) >= 3 else t1_fng
    t3_fng = float(fng_series.loc[month_ends[-4]]) if len(month_ends) >= 4 else t2_fng
    t4_fng = float(fng_series.loc[month_ends[-5]]) if len(month_ends) >= 5 else t3_fng

    # Core Model C-1 Ultra Logic:
    # 2.0x if t0 < 15 or t-2 < 15 or ((t-3 < 15 or t-4 < 15) and growth_on)
    # 0.5x if t0 > 85
    # 1.0x otherwise
    t0_fear = current_fng < 15 or t0_fng < 15
    t2_fear = t2_fng < 15
    t3_fear = t3_fng < 15
    t4_fear = t4_fng < 15
    t0_greed = current_fng > 85 or t0_fng > 85

    reasons = []
    exposure = 1.0

    if t0_greed:
        exposure = 0.50
        reasons.append(f"극단적 탐욕 (F&G {current_fng:.1f} > 85) 발생 ➔ 50% 현금 확보 (위험축소)")
    elif t0_fear:
        exposure = 2.00
        reasons.append(f"당월 극단적 공포 (F&G {current_fng:.1f} < 15) 투매 발생 ➔ 2.0배 레버리지 공격 매수")
    elif t2_fear:
        exposure = 2.00
        reasons.append(f"전전월(t-2) 극단적 공포 ({t2_fng:.1f} < 15) 발생 ➔ 2차 파동 2.0배 레버리지 랠리 탑승")
    elif (t3_fear or t4_fear) and growth_on:
        exposure = 2.00
        active_lag = "t-3" if t3_fear else "t-4"
        lag_val = t3_fng if t3_fear else t4_fng
        reasons.append(f"과거 {active_lag} 공포 ({lag_val:.1f} < 15) + 200일선 상회(강세장) ➔ 2.0배 레버리지 확장")
    else:
        exposure = 1.00
        reasons.append("정상 매크로 국면 (1.0배 정규 비중 유지)")

    # Target IC Asset Selection
    if growth_on and inflation_on:
        base_asset = "XLE"
        base_name = "에너지 (XLE)"
        base_weights = {"XLE": 1.0}
    elif growth_on and not inflation_on:
        base_asset = "XLK"
        base_name = "기술 (XLK)"
        base_weights = {"XLK": 1.0}
    elif not growth_on and inflation_on:
        base_asset = "XLU"
        base_name = "유틸리티 (XLU)"
        base_weights = {"XLU": 1.0}
    else:
        base_asset = "XLP+IEF"
        base_name = "필수소비재(XLP 50%) + 국채(IEF 50%)"
        base_weights = {"XLP": 0.50, "IEF": 0.50}

    # Final Portfolio Weights according to Exposure
    final_weights = {}
    if exposure > 1.0:
        # Leveraged position
        for t, w in base_weights.items():
            final_weights[t] = w * exposure
    elif exposure < 1.0:
        for t, w in base_weights.items():
            final_weights[t] = w * exposure
        final_weights["SHY"] = 1.0 - exposure
    else:
        final_weights = base_weights.copy()

    return {
        "current_fng": current_fng,
        "current_rating_kr": current_rating_kr,
        "current_emoji": current_emoji,
        "growth_on": growth_on,
        "inflation_on": inflation_on,
        "base_asset": base_asset,
        "base_name": base_name,
        "exposure": exposure,
        "action_reason": " · ".join(reasons),
        "final_weights": final_weights,
        "t0_fng": t0_fng,
        "t1_fng": t1_fng,
        "t2_fng": t2_fng,
        "t3_fng": t3_fng,
        "t4_fng": t4_fng,
        "fng_series": fng_series,
    }
