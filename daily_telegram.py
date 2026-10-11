"""Inflation Compass — 오늘 기준 현재 포지션 + 전략 요약을 텔레그램으로 송부.

매일 아침 06:00 KST cron 실행. db의 최신 데이터로 신호를 재계산해
현재 보유 포지션을 알려주고, 장기 CAGR/MDD를 함께 표시한다.
"""

import html
import os
import sqlite3
from pathlib import Path

import requests
from dotenv import load_dotenv

import backtest
import fetch_data
import fng_engine
import pension_mix
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
    "GLD": "금",
    "BIL": "초단기채(현금)",
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


SHORT_KR = {"XLE": "에너지", "XLK": "기술", "XLU": "유틸리티", "XLP": "필수소비재", "IEF": "중기국채", "SHY": "단기채",
            "GLD": "금", "BIL": "현금", "DBC": "원자재", "TLT": "장기국채", "SPY": "S&amp;P500", "QQQ": "나스닥",
            "IWM": "소형주", "EFA": "선진국", "EEM": "신흥국", "TIP": "물가채", "GDX": "금광주", "VNQ": "리츠",
            "LQD": "회사채", "HYG": "하이일드", "EMB": "신흥국채"}


def _pct(v):
    p = v * 100
    return f"{p:.0f}%" if abs(p - round(p)) < 0.05 else f"{p:.1f}%"


def bullets(weights):
    """비중을 한 줄에 하나씩: '• XLE 에너지 85%' (큰 순서)."""
    items = sorted(((k, v) for k, v in weights.items() if abs(v) > 1e-6), key=lambda kv: -kv[1])
    return [f"• <b>{k}</b> {SHORT_KR.get(k, '')} {_pct(v)}".replace("  ", " ") for k, v in items] or ["• 현금 100%"]


def weights_str(weights):
    return " + ".join(f"{t} ({TICKER_KR.get(t, t)}) {w * 100:.0f}%" for t, w in weights.items())


def refresh_data():
    """가격·T5YIE 를 받아 DB 를 갱신한다(2026-10-09: 그동안 갱신 경로가 없어 DB 가 08-07 에 멈춰 있었다)."""
    try:
        fetch_data.main()
    except Exception as e:
        print(f"[refresh] 데이터 갱신 실패 — DB 기존 값으로 계산: {e}")


def main():
    refresh_data()
    backtest.refresh_if_new_month()
    prev_d, prev_e, prev_regime, prev_weights, cur_regime, cur_weights, cur_date = current_position()
    details = signal_details()
    cagr, mdd, start, end = long_term_stats()

    # Load data for F&G Model C-1 Ultra calculation
    prices, t5yie = backtest.load_data()
    vix = yf.download("^VIX", start="2000-01-01", auto_adjust=True, progress=False)["Close"].squeeze().reindex(prices.index).ffill()
    df_hy = pd.read_csv("https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAA10Y&cosd=1996-12-31", na_values=".").dropna()
    df_hy["date"] = pd.to_datetime(df_hy["observation_date"])
    hy_spread = df_hy.set_index("date")["BAA10Y"].reindex(prices.index).ffill()
    
    fng_pos = fng_engine.calculate_model_c1_ultra_position(prices, t5yie, vix, hy_spread)
    prev = fng_pos["prev_decision"]
    pmix = pension_mix.mix_position(prices, t5yie, vix, hy_spread)
    pic, pent = pmix["ic"], pmix["pentarch"]
    if pent is None:
        pent_lines = ["└ PENTARCH 50%", "   ⚠️ 신호 없음 (05시 크론 확인)"]
    else:
        pent_lines = [f"└ PENTARCH 50% · {pent.get('model', '')}", *["   " + b for b in bullets(pent["target"])],
                      f"   {pent['effective_since'][5:]}부터" + (f" · ⚠️ {pent['stale_days']}일 지남" if pent["stale"] else "")]

    # 휴대폰 폭(약 30자)에 맞춘 세로 배치 — 한 줄에 정보 하나 (2026-10-11)
    def cell_name(g, i):
        return {(True, True): "에너지 칸", (True, False): "기술 칸", (False, True): "유틸리티 칸",
                (False, False): "침체 칸"}[(bool(g), bool(i))]

    def regime_line(g, i):
        return f"성장 {'↑' if g else '↓'} · 인플레 {'↑' if i else '↓'}"

    def exp_label(e):
        return "2배 (공포)" if e > 1.0 else ("0.5배 (탐욕)" if e < 1.0 else "1배")

    cur_w, prev_w = fng_pos["final_weights"], prev["final_weights"]
    same_as_held = all(abs(cur_w.get(k, 0) - prev_w.get(k, 0)) < 1e-9 for k in set(cur_w) | set(prev_w))
    next_dec = pd.Timestamp(cur_date) + pd.offsets.BMonthEnd(0)      # 이번 달 마지막 영업일(오늘이 월말이면 오늘)
    be_mom = "상승 ✔" if details["breakeven_momentum_on"] else "하락 ✘"
    lv = "✔" if details["level_on"] else "✘"
    dow = "월화수목금토일"[next_dec.weekday()]
    ief_info = ("IEF &lt; 200일선 → 단기채" if fng_pos["bond_shield"] else
                ("IEF 200일선 위 → IEF" if not fng_pos["growth_on"] and not fng_pos["inflation_on"] else "해당 없음 (침체 칸 아님)"))

    lines = [
        "🧭 <b>Inflation Compass</b>",
        f"{cur_date:%Y-%m-%d} 종가 기준",
        "",
        "📍 <b>국면</b>",
        regime_line(fng_pos["growth_on"], fng_pos["inflation_on"]),
        f"→ <b>{cell_name(fng_pos['growth_on'], fng_pos['inflation_on'])}</b>",
        "",
        f"💼 <b>일반계좌 · {exp_label(fng_pos['exposure'])}</b>",
        *bullets(cur_w),
        f"IC 지수 <b>{fng_pos['current_fng']:.0f}</b> ({fng_pos['current_rating_kr'].split(' (')[0]})",
        "CNN " + (f"{fng_pos['cnn_score']:.0f} (참고)" if fng_pos["cnn_score"] is not None else "조회 실패"),
        "",
        f"📅 <b>지금 보유</b> ({prev['date']:%m-%d} 결정)",
        *(["위와 같음 · 매매 없음"] if same_as_held else
          [f"{regime_line(prev['growth_on'], prev['inflation_on'])} · {exp_label(prev['exposure'])}", *bullets(prev_w),
           "⚠️ 월말에 위 비중으로 교체"]),
        f"다음 판단 {next_dec:%m-%d}({dow}) 종가 전",
        "",
        "🏦 <b>연금 합계</b>",
        *bullets(pmix["weights"]),
        f"└ IC 연금형 50% · {pic['exposure']:.1f}배" + (" · 채권방어" if pic["bond_shield"] else ""),
        *["   " + b for b in bullets(pic["final_weights"])],
        *pent_lines,
        "",
        "🔎 <b>신호 상세</b>",
        f"성장: SPY 200일선 {'위 ✔' if fng_pos['growth_on'] else '아래 ✘'}",
        f"인플레: {'켜짐 ✔' if details['inflation_on'] else '꺼짐 ✘'}",
        f" · T5YIE {details['t5yie_now']:.2f}% {lv} (기준 2%)",
        f" · 60일 전 {details['t5yie_60ago']:.2f}% → {be_mom}",
        f" · 업종 기울기 {details['slope_val']:+.4f} {'✔' if details['asset_momentum_on'] else '✘'}",
        f"채권방어: {ief_info}",
        f"2배 조건: 지수 &lt; 15 (지금 {fng_pos['current_fng']:.0f})",
        "",
        "📈 <b>백테스트</b>",
        "일반 19.5% · MDD −20.2%",
        "연금 혼합 15.3% · MDD −13.0%",
        f"<i>원본 IC {cagr * 100:.1f}% · MDD {mdd * 100:.1f}%</i>",
    ]
    text = "\n".join(lines)
    send_message(text)


if __name__ == "__main__":
    main()
