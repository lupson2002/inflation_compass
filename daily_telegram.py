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
    cagr, mdd, start, end = long_term_stats()

    def regime_str(regime):
        return f"성장 {'상승' if regime[0] else '하락'} · 인플레이션 {'상승' if regime[1] else '하락'}"

    lines = [
        "🧭 <b>Inflation Compass</b>",
        "",
        "성장(Growth)과 인플레이션(Inflation) 두 축으로 매크로 국면을 4가지로 나눠, "
        "매월 마지막 거래일에 판단해 해당 섹터 ETF 하나에 전액 투자하는 로테이션 전략.",
        "",
        f"📅 <b>이전 월말 결정</b> ({prev_d.date()})",
        f"{regime_str(prev_regime)}",
        f"선택 ETF: <b>{weights_str(prev_weights)}</b>",
        f"(보유기간 ~ {prev_e.date()})",
        "",
        f"🔄 <b>오늘 시점 계산</b> ({cur_date.date()})",
        f"{regime_str(cur_regime)}",
        f"선택 ETF: <b>{weights_str(cur_weights)}</b>",
        "",
        f"📈 <b>장기 성과</b> ({start} ~ {end})",
        f"CAGR: <b>{cagr * 100:.1f}%</b>",
        f"MaxDD: <b>{mdd * 100:.1f}%</b>",
    ]
    text = "\n".join(lines)
    send_message(text)


if __name__ == "__main__":
    main()
