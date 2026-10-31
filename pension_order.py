"""연금 주문서 — IC 연금형 35% + PENTARCH 비레버리지 65%(1위 35 · 2위 30) 합계 목표와 그 국내 ETF(2026-10-31)를 한국 장 시작 전에 텔레그램으로 보낸다(2026-10-30).

평일 08:00 KST cron. 미국 장 마감(서머타임 05:00 / 표준시 06:00 KST) 뒤, PENTARCH 연금 신호(06:40 재수집 실행)가 끝난 뒤.
- 연금은 월 1회 매매: 미국 월말 거래일 종가로 정한 비중을 다음 한 달 들고 간다.
  미국 월말 종가가 막 반영된 아침(= 그 다음 한국 거래일)에만 '오늘 교체' 를 띄우고, 나머지 날은 '매매 없음' + 지금 들고 있을 비중.
- IC 는 그날까지 종가로 다시 계산(pension_mix.ic_weights_asof), PENTARCH 는 pentarch 가 낸 pension_target.json 을 읽는다.

    python3 pension_order.py            # 발송
    python3 pension_order.py --dry      # 출력만
"""
from __future__ import annotations

import html
import sys

import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessMonthEnd

import backtest
import daily_telegram as dt
import pension_mix as PM

US_BME = CustomBusinessMonthEnd(calendar=USFederalHolidayCalendar())


def _macro(prices: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    import yfinance as yf
    vix = yf.download("^VIX", start="2000-01-01", auto_adjust=True, progress=False)["Close"].squeeze()
    hy = pd.read_csv("https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAA10Y&cosd=1996-12-31", na_values=".").dropna()
    hy = hy.set_index(pd.to_datetime(hy["observation_date"]))["BAA10Y"]
    return vix.reindex(prices.index).ffill(), hy.reindex(prices.index).ffill()


def _month_ends(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = idx.to_series()
    return pd.DatetimeIndex(s.groupby(s.index.to_period("M")).max().values)


def _scale(w: dict, k: float) -> dict:
    """슬리브 안 비중 → 계좌 기준 비중."""
    return {a: v * k for a, v in w.items()}


def _kr_lines(w: dict) -> list[str]:
    """계좌 기준 비중을 국내 ETF 이름으로: '• 금 ACE KRX금현물 411060 — 18.8%'."""
    items = sorted(((k, v) for k, v in w.items() if abs(v) > 1e-6), key=lambda kv: -kv[1])
    return [f"• <b>{dt._pct(v)}</b> {html.escape(PM.KR_ETF.get(k, k + ' (국내 대응 없음)'))} ({k})" for k, v in items]


def _band(v: float, cuts: tuple, words: tuple) -> str:
    """v 가 cuts(오름차순) 몇 번째 구간인지에 따라 words 중 하나."""
    return words[sum(v > c for c in cuts)]


def economy_line(eco: dict) -> str:
    """PENTARCH 경제 판단 한 줄: 국면 확률(10% 이상) | 기둥 해석."""
    probs = sorted(((k, v) for k, v in eco["regime_probs"].items() if v >= 0.10), key=lambda kv: -kv[1])
    p = eco["pillars"]
    desc = [
        "성장 " + _band(p["growth_z"], (-1.0, 0.0, 1.0), ("침체", "약", "보통", "강")),
        "인플레 " + _band(p["inflation_z"], (-0.5, 0.0, 0.5), ("낮음", "소폭↓", "소폭↑", "높음")),
        "유동성 " + _band(p["liquidity_z"], (-0.3, 0.3), ("조임", "보통", "양호")),
        "주식 " + _band(p["valuation_z"], (-1.0, -0.3, 0.3), ("매우 비쌈", "비쌈", "보통", "쌈")),
        "심리 " + _band(p["sentiment_z"], (-0.5, 0.5), ("공포", "중립", "낙관")),
    ]
    return "   경제 판단: " + " · ".join(f"{k} {v*100:.0f}%" for k, v in probs) + " | " + " · ".join(desc)


def _merge(ic: dict, pent: dict | None) -> dict:
    out: dict[str, float] = {}
    for k, w in ic.items():
        out[k] = out.get(k, 0.0) + PM.IC_WEIGHT * w
    for k, w in (pent or {}).items():
        out[k] = out.get(k, 0.0) + PM.PENT_WEIGHT * w
    return out


def build_message() -> str:
    dt.refresh_data()
    prices, t5yie = backtest.load_data()
    now_et = pd.Timestamp.now(tz="America/New_York")
    if prices.index[-1].date() >= now_et.date() and (now_et.hour, now_et.minute) < (16, 15):
        prices = prices.iloc[:-1]                                       # 아직 끝나지 않은 미국 장의 임시 행
        t5yie = t5yie.loc[:prices.index[-1]]
    vix, hy = _macro(prices)
    asof = prices.index[-1]
    trade_today = asof == US_BME.rollforward(asof)                     # 마지막 미국 종가가 그 달 마지막 거래일
    me = _month_ends(prices.index)
    held_d = asof if trade_today else me[me < asof.to_period("M").to_timestamp()][-1]
    prev_d = me[me < held_d.to_period("M").to_timestamp()][-1]
    ic_held = PM.ic_weights_asof(prices, t5yie, vix, hy, held_d)
    ic_prev = PM.ic_weights_asof(prices, t5yie, vix, hy, prev_d)
    ic_now = PM.ic_weights_asof(prices, t5yie, vix, hy, asof) if not trade_today else ic_held
    pent = PM.load_pentarch_target()
    p_t = pent["target"] if pent else None
    total = _merge(ic_held["final_weights"], p_t)
    ic_pct, p_pct = PM.label(PM.IC_WEIGHT), PM.label(PM.PENT_WEIGHT)

    lines = ["🏦 <b>연금 주문서</b>", f"IC {ic_pct} + PENTARCH {p_pct}", f"미국 {asof:%Y-%m-%d} 종가 기준", ""]
    if trade_today:
        p_new = bool(pent) and pd.Timestamp(pent["effective_since"]) > held_d     # PENTARCH 도 이번 월말에 새로 정했나
        p_before = (pent.get("prev_target") if p_new else p_t) if pent else None
        before = _merge(ic_prev["final_weights"], p_before)
        changed = any(abs(total.get(k, 0) - before.get(k, 0)) > 1e-6 for k in set(total) | set(before))
        lines += ["✅ <b>오늘 한국 장에서 교체</b>" if changed else "✅ 월말 판단 완료 · <b>비중 변화 없음</b>",
                  "(한국 휴장이면 다음 거래일)", ""]
        if changed:
            lines += ["🔁 <b>바뀌는 비중</b>"]
            for k in sorted(set(total) | set(before), key=lambda x: -total.get(x, 0)):
                a, b = before.get(k, 0.0), total.get(k, 0.0)
                if abs(a - b) > 1e-6:
                    lines.append(f"• <b>{k}</b> {dt.SHORT_KR.get(k, '')} {dt._pct(a)} → <b>{dt._pct(b)}</b>")
            lines.append("")
        if pent and pent.get("data_asof") != f"{asof:%Y-%m-%d}":
            lines += [f"⚠️ PENTARCH 신호가 {pent.get('data_asof')} 기준 — 월말 종가 미반영, 매매 보류 후 재확인", ""]
    else:
        nxt = US_BME.rollforward(asof)
        lines += ["😴 <b>오늘 매매 없음</b>", f"다음 판단: 미국 {nxt:%m-%d} 종가 → 그다음 한국 장", ""]

    lines += ["🎯 <b>들고 있을 비중</b> (계좌 기준)", *dt.bullets(total), "",
              "🇰🇷 <b>국내 ETF로 사기</b>", *_kr_lines(total), "",
              f"└ IC {ic_pct} · {held_d:%m-%d} 결정 · {ic_held['exposure']:.1f}배" + (" · 채권방어" if ic_held["bond_shield"] else "")
              + (" · 신용 확인 재진입" if ic_held.get("reentry") else ""),
              *["   " + b for b in dt.bullets(_scale(ic_held["final_weights"], PM.IC_WEIGHT))]]
    if pent is None:
        lines += [f"└ PENTARCH {p_pct}", "   ⚠️ 신호 없음 (06:40 크론 확인)"]
    else:
        lines += [f"└ PENTARCH {p_pct} · {pent.get('model', '')} · {pent['effective_since']}부터",
                  *["   " + b for b in dt.bullets(_scale(p_t, PM.PENT_WEIGHT))]]
        if pent.get("economy"):
            lines.append(economy_line(pent["economy"]))
        vl = pent.get("value_layer")
        if vl:
            why = ("유동성·신용 조임" if vl["guard"] else "감점 판단이 1년 성과 앞섬") if vl["penalty"] == "켜짐" \
                else "감점 판단이 1년 성과 뒤짐 → 시장 추종"
            lines.append(f"   밸류 감점 {vl['penalty']} ({why} · 12개월 {vl['E0_12m']*100:+.1f}% 대 {vl['E1_12m']*100:+.1f}%)")
        rr = pent.get("reentry")
        if rr and rr.get("on"):
            lines.append(f"   재진입 신호 켜짐 (신용 스프레드 63일 {rr['baa_63d_change']:+.2f}%p · S&P 63일 {rr['spy_63d']*100:+.1f}%)")
        if pent["stale"]:
            lines.append(f"   ⚠️ 신호 {pent['stale_days']}일 지남")
    if not trade_today and any(abs(ic_now["final_weights"].get(k, 0) - ic_held["final_weights"].get(k, 0)) > 1e-6
                               for k in set(ic_now["final_weights"]) | set(ic_held["final_weights"])):
        lines += ["", "👀 <b>참고: 오늘 종가로 보면 IC 는</b>", *["   " + b for b in dt.bullets(_scale(ic_now["final_weights"], PM.IC_WEIGHT))],
                  "   (월말까지 바뀔 수 있음 · 지금은 매매 안 함)"]
    bt = PM.BACKTEST
    lines += ["", f"📈 백테스트 {bt['기간'].split(' (')[0]}: 연 {bt['CAGR']*100:.1f}% · 최대낙폭 {bt['MDD']*100:.1f}% (달러)",
              f"   원화(국내 ETF 환노출): 연 {bt['원화 환노출'][0]*100:.1f}% · 최대낙폭 {bt['원화 환노출'][1]*100:.1f}%"]
    return "\n".join(lines)


def main() -> None:
    msg = build_message()
    if "--dry" in sys.argv:
        print(msg)
        return
    dt.send_message(msg)


if __name__ == "__main__":
    main()
