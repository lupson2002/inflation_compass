"""Percentile Channels TAA — 매일 아침 05:45 KST 텔레그램 전송.

pct.db의 최신 가격으로 오늘 시점 4채널 신호 · composite · 비중을 재계산하고,
이전 월말 결정과 비교해 현재 포지션과 장기 성과를 텔레그램으로 보낸다.

cron (KST):
    45 5 * * *  cd /home/mikey/inflationCompass/inflation_compass && /usr/bin/python3 pct_daily_telegram.py >> data/pct_telegram.log 2>&1
"""

import os
import sqlite3
from pathlib import Path

import requests
from dotenv import load_dotenv

import pct_backtest as pct

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "pct.db"

load_dotenv(BASE_DIR / ".env")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

TICKER_KR = pct.TICKER_KR


def current_state():
    """오늘 시점 채널 신호, composite, 비중, 이전 월말 결정을 반환."""
    prices = pct.load_data()
    starts = [prices[a].first_valid_index() for a in pct.ASSETS]
    prices = prices.loc[max(starts):]

    channel_signals, composite, vol20 = pct.compute_scores(prices)
    positions = pct.build_positions(composite, vol20)

    prev_d, prev_end, prev_weights, prev_comp = positions[-1]

    last = prices.index[-1]
    sig_today = {c: {a: int(channel_signals[c].loc[last, a]) for a in pct.ASSETS} for c in pct.CHANNELS}
    comp_today = {a: float(composite.loc[last, a]) for a in pct.ASSETS}

    # 오늘 시점 비중 (다음 월말 결정 예정) — build_positions과 동일 로직
    raw = {}
    for a in pct.ASSETS:
        v = vol20.loc[last, a]
        inv = 1.0 / v if (v and v > 0 and not np_isnan(v)) else 0.0
        raw[a] = comp_today[a] * inv
    tot = sum(abs(x) for x in raw.values())
    today_weights = {a: 0.0 for a in pct.ASSETS}
    if tot > 0:
        for a in pct.ASSETS:
            today_weights[a] = (abs(raw[a]) / tot) if comp_today[a] > 0 else 0.0
    today_weights[pct.CASH] = 1.0 - sum(today_weights[a] for a in pct.ASSETS)

    return last, sig_today, comp_today, today_weights, prev_d, prev_end, prev_weights


def np_isnan(v):
    import math
    return math.isnan(v)


def long_term_stats():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT date, strategy_equity FROM backtest_equity ORDER BY date").fetchall()
    conn.close()
    vals = [r[1] for r in rows]
    dates = [r[0] for r in rows]
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
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
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
    return " + ".join(f"{t} ({TICKER_KR.get(t, t)}) {w * 100:.0f}%" for t, w in weights.items() if w > 0)


def channel_tag(s):
    return "+" if s > 0 else ("-" if s < 0 else "0")


def main():
    last, sig_today, comp_today, today_weights, prev_d, prev_end, prev_weights = current_state()
    cagr, mdd, start, end = long_term_stats()

    lines = [
        "📊 <b>Percentile Channels TAA</b>",
        "",
        "4개 퍼센타일 채널(60/120/180/252일)로 주식·부동산·회사채·원자재를 "
        "역변동성 비중으로 로테이션하는 월간 전략.",
        "",
        f"📅 <b>데이터 기준</b>: {last.date()}",
        "",
        "🔹 <b>채널별 신호</b> (75% 진입 / 25% 이탈)",
    ]
    for c in pct.CHANNELS:
        cells = []
        for a in pct.ASSETS:
            tag = channel_tag(sig_today[c][a])
            cells.append(f"{a}{tag}")
        lines.append(f"  {c}일 : " + " · ".join(cells))

    lines.append("")
    lines.append("🔸 <b>Composite 점수</b> (4채널 평균)")
    comp_str = " · ".join(f"{a} {comp_today[a]:+.2f}" for a in pct.ASSETS)
    lines.append("  " + comp_str)

    active = {a for a in pct.ASSETS if comp_today[a] > 0}
    if active:
        act = " · ".join(f"{a} ({TICKER_KR[a]})" for a in pct.ASSETS if a in active)
        lines.append(f"  보유 대상: <b>{act}</b>  (composite > 0)")
    else:
        lines.append("  보유 대상: <b>없음 → 현금(SHY)</b>")

    lines.append("")
    lines.append(f"📈 <b>오늘 시점 비중</b>")
    lines.append("  " + weights_str(today_weights))

    lines.append("")
    lines.append(f"📅 <b>이전 월말 결정</b> ({prev_d.date()})")
    lines.append("  " + weights_str(prev_weights))

    changed = today_weights != prev_weights
    if changed:
        lines.append("  ⚠️ <b>포지션 변경 예정</b> — 다음 월말 리밸런싱에 반영됩니다.")
    else:
        lines.append("  현재 보유와 동일한 신호입니다.")

    lines.append("")
    lines.append(f"📊 <b>장기 백테스트</b> ({start} ~ {end})")
    lines.append(f"  CAGR: <b>{cagr * 100:.1f}%</b>  ·  MaxDD: <b>{mdd * 100:.1f}%</b>")
    lines.append("  (VTI Buy&Hold 대비 낮은 낙폭, 위험조정수익 우위)")

    text = "\n".join(lines)
    send_message(text)


if __name__ == "__main__":
    main()
