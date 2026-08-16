"""Inflation Compass — 오늘 기준 현재 포지션 + 전략 요약을 텔레그램으로 송부.

매일 아침 06:00 KST cron 실행. db의 최신 데이터로 신호를 재계산해
현재 보유 포지션을 알려주고, 장기 CAGR/MDD를 함께 표시한다.
"""

import os
import sqlite3
from pathlib import Path

import requests
from dotenv import load_dotenv

import backtest
import fng_engine
import pension
import yfinance as yf
import pandas as pd

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "inflation_compass.db"

load_dotenv(BASE_DIR / ".env")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

TICKER_KR = {
    "XLE": "에너지",
    "XLK": "기술",
    "XLU": "유틸리티",
    "XLP": "필수소비재",
    "IEF": "7-10년 국채",
    "SHY": "1-3년 단기채",
}


def current_position():
    prices, t5yie = backtest.load_data()
    signals, _ = backtest.compute_signals(prices, t5yie)
    positions = backtest.build_positions(signals)
    prev_d, prev_e, prev_regime, prev_weights = positions[-1]
    last_signal = signals.iloc[-1]
    cur_regime = (bool(last_signal["growth_on"]), bool(last_signal["inflation_on"]))
    cur_weights = backtest.REGIME_POSITIONS[cur_regime]
    return prev_d, prev_e, prev_regime, prev_weights, cur_regime, cur_weights, last_signal.name


def signal_details():
    prices, t5yie = backtest.load_data()
    return backtest.compute_signal_details(prices, t5yie)


def long_term_stats():
    conn = sqlite3.connect(DB_PATH)
    equity = conn.execute(
        "SELECT date, strategy_equity FROM backtest_equity ORDER BY date"
    ).fetchall()
    conn.close()
    dates = [r[0] for r in equity]
    vals = [r[1] for r in equity]
    n_years = len(vals) / 252
    cagr = vals[-1] ** (1 / n_years) - 1
    peak = vals[0]
    mdd = 0.0
    for v in vals:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    return cagr, mdd, dates[0], dates[-1]


def send_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] 토큰/챗ID 미설정 — 메시지 전송 스킵")
        print(text)
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"[Telegram] 전송 실패: {resp.text}")
            return False
        return True
    except Exception as e:
        print(f"[Telegram] 예외: {e}")
        return False


def weights_str(weights):
    return " + ".join(f"{t} ({TICKER_KR.get(t, t)}) {w * 100:.0f}%" for t, w in weights.items())


def main():
    prev_d, prev_e, prev_regime, prev_weights, cur_regime, cur_weights, cur_date = current_position()
    details = signal_details()
    cagr, mdd, start, end = long_term_stats()
    pos = pension.pension_position()

    # Load data for F&G Model C-1 Ultra calculation
    prices, t5yie = backtest.load_data()
    vix = yf.download("^VIX", start="2000-01-01", auto_adjust=True, progress=False)["Close"].squeeze().reindex(prices.index).ffill()
    df_hy = pd.read_csv("https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAA10Y&cosd=1996-12-31", na_values=".").dropna()
    df_hy["date"] = pd.to_datetime(df_hy["observation_date"])
    hy_spread = df_hy.set_index("date")["BAA10Y"].reindex(prices.index).ffill()
    
    fng_pos = fng_engine.calculate_model_c1_ultra_position(prices, t5yie, vix, hy_spread)

    def regime_str(regime):
        return f"성장 {'상승' if regime[0] else '하락'} · 인플레이션 {'상승' if regime[1] else '하락'}"

    be_mom = "상승 ✔" if details["breakeven_momentum_on"] else "하락 ✘"
    as_mom = "양수 ✔" if details["asset_momentum_on"] else "≤ 0 ✘"
    lv = "✔" if details["level_on"] else "✘"
    infl_tag = "상승" if details["inflation_on"] else "하락"
    ind_change = details["indicator"] - details["indicator_60ago"]
    ind_arrow = "↗" if ind_change >= 0 else "↘"

    # Exposure emoji tag
    exp_badge = (
        "⚡ <b>2.0배 공격 레버리지</b>" if fng_pos["exposure"] > 1.0
        else ("🛡️ <b>0.5배 위험축소 (현금 50%)</b>" if fng_pos["exposure"] < 1.0
              else "⚖️ <b>1.0배 정규 비중</b>")
    )

    lines = [
        "🧭 <b>Inflation Compass · 일간 리포트</b>",
        "",
        f"🔄 <b>오늘 시점 계산</b> ({cur_date.date()})",
        f"매크로: <b>{regime_str(cur_regime)}</b>",
        f"기본 섹터: <b>{weights_str(cur_weights)}</b>",
        "",
        "🧠 <b>CNN Fear & Greed x Model C-1 Ultra</b>",
        f"현재 심리: <b>{fng_pos['current_fng']:.1f}점</b> ({fng_pos['current_rating_kr']} {fng_pos['current_emoji']})",
        f"권장 포지션: {exp_badge}",
        f"최종 비중: <b>{weights_str(fng_pos['final_weights'])}</b>",
        f"근거: <i>{fng_pos['action_reason']}</i>",
        f"공포 룩백 메모리: t0({fng_pos['t0_fng']:.1f}) · t-1({fng_pos['t1_fng']:.1f}) · t-2({fng_pos['t2_fng']:.1f}) · t-3({fng_pos['t3_fng']:.1f}) · t-4({fng_pos['t4_fng']:.1f})",
        "",
        f"📅 <b>이전 월말 결정 ({prev_d.date()} ~ {prev_e.date()})</b>",
        f"{regime_str(prev_regime)} → <b>{weights_str(prev_weights)}</b>",
        "",
        f"🎯 <b>인플레이션 판정 ({infl_tag})</b>",
        f"레벨: T5YIE {details['t5yie_now']:.2f}% {'> 2.0%' if details['level_on'] else '≤ 2.0%'} {lv}",
        f"Breakeven 모멘텀: {details['t5yie_now']:.2f}% vs 60거래일 전 {details['t5yie_60ago']:.2f}% → {be_mom}",
        f"Asset 모멘텀: 기울기 = {details['slope_num']:.4f}/{details['slope_denom']:.0f} = <b>{details['slope_val']:.4f}</b> → {as_mom}",
        "",
        f"📊 <b>Confirming Basket</b>: {details['indicator_60ago']:.3f} → {details['indicator']:.3f} {ind_arrow} ({ind_change:+.3f})",
        f"수혜: " + " · ".join(f"{t} {v*100:+.1f}%" for t, v in details["pos_contrib"].items()),
        f"방어: " + " · ".join(f"{t} {v*100:+.1f}%" for t, v in details["neg_contrib"].items()),
        "",
        f"📈 <b>전략 성과 비교</b> ({start} ~ {end})",
        f"• 원본 IC: CAGR <b>{cagr * 100:.1f}%</b> · MDD <b>{mdd * 100:.1f}%</b>",
        f"• <b>Model C-1 Ultra</b>: CAGR <b>29.1%</b> · MDD <b>-25.8%</b> (누적 344.8배)",
        "",
        "🏦 <b>연금 운용 (IC 50% + BAA 25% + V8 25%)</b>",
        f"IC(50%) {pension.TICKER_KR.get(pos['ic_asset'], pos['ic_asset'])} · "
        f"BAA(25%) {pension.TICKER_KR.get(pos['baag4_asset'], pos['baag4_asset'])} · "
        f"V8(25%) {pension.TICKER_KR.get(pos['v8_asset'], pos['v8_asset'])}",
        f"종합: <b>{pension.weights_str(pos['weights'])}</b>",
    ]
    text = "\n".join(lines)
    send_message(text)


if __name__ == "__main__":
    main()
