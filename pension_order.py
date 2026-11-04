"""연금 주문서(IC 일일 텔레그램 통합, 2026-10-31 간결판; 2026-11-01 PENTARCH 시장 위험 국면 표시 — docs/118 W2; 2026-11-02 VRP 보험료 — docs/121 V1; 2026-11-02 연금 전략 v1.0 = IC 연금형 v2.0(G1S) + PENTARCH v19.0; 같은 날 v1.1 = IC v2.1(I3 히스테리시스) + PENTARCH v19.1(P7 글로벌 패닉), v1.2 = IC v2.2(A2 디스인플레이션 칸)) — IC 연금형 35% + PENTARCH 비레버리지 65%(1위 35 · 2위 30) 합계 목표와 그 국내 ETF(2026-10-31)를 한국 장 시작 전에 텔레그램으로 보낸다(2026-10-30).

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

import backtest
import daily_telegram as dt
import pension_baa as P
import pension_mix as PM
from nyse_calendar import NYSE_BDAY, NYSE_BME

US_BME = NYSE_BME      # 2026-11-04: 연방 공휴일 달력은 성금요일·12-31 대체휴일 월말을 틀린다(1995~ 8건, 다음 2027-12-31)


def _macro(prices: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    import yfinance as yf
    vix = yf.download("^VIX", start="2000-01-01", auto_adjust=True, progress=False)["Close"].squeeze()
    hy = pd.read_csv("https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAA10Y&cosd=1996-12-31", na_values=".").dropna()
    hy = hy.set_index(pd.to_datetime(hy["observation_date"]))["BAA10Y"]
    return vix.reindex(prices.index).ffill(), hy.reindex(prices.index).ffill()


def _month_ends(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = idx.to_series()
    return pd.DatetimeIndex(s.groupby(s.index.to_period("M")).max().values)


def last_expected_close(now_et: pd.Timestamp) -> pd.Timestamp:
    """지금(미국 동부) 기준으로 끝나 있어야 할 마지막 NYSE 거래일."""
    day = now_et.tz_localize(None).normalize()
    if (now_et.hour, now_et.minute) < (16, 15):
        day -= pd.Timedelta(days=1)
    return NYSE_BDAY.rollback(day)


def freshness_alerts(asof: pd.Timestamp, expected: pd.Timestamp, pent: dict | None, stress_end: pd.Timestamp | None) -> list[str]:
    """두 슬리브가 같은 날 종가로 계산됐는지 검사(pentarch docs/138). 어긋나면 주문서 맨 위에 경고."""
    out = []
    if asof < expected:
        out.append(f"🚨 IC 가격이 {asof:%m-%d} 에 멈춤(기대 {expected:%m-%d}) — 월말 판단을 놓쳤을 수 있음, 매매 보류 후 재확인")
    if pent is None:
        out.append("🚨 PENTARCH 신호 없음 — 매매 보류 후 재확인")
    elif pd.Timestamp(pent["data_asof"]) < asof:
        out.append(f"🚨 PENTARCH 신호가 {pent['data_asof']} 기준(IC {asof:%m-%d}) — 06:40 실행 실패 가능, 매매 보류 후 재확인")
    if stress_end is None:                                          # docs/139 F06: 없으면 경고도 없던 구멍
        out.append("🚨 스트레스 경로 파일 없음 — IC 고용 유예(G1S) 판정 불가, 매매 보류 후 재확인")
    elif stress_end < asof:
        out.append(f"🚨 스트레스 경로가 {stress_end:%m-%d} 까지 — IC 고용 유예 판정이 늦은 자료 기준, 재확인")
    return out


def pent_before(pent: dict | None, held_d: pd.Timestamp) -> dict | None:
    """월말 판단일 아침, PENTARCH 가 그 판단 직전까지 들고 있던 목표(docs/139 F04).
    예전 조건(effective_since > held_d)은 새 목표의 효력일이 판단일 자체(== held_d)라 늘 거짓 → 바뀐 것을 '바꿀 것 없음'으로 냈다."""
    if not pent:
        return None
    if pent.get("decision_day") and pent.get("data_asof") == f"{held_d:%Y-%m-%d}":
        b = pent.get("target_before_decision")
        return b if b is not None else pent.get("prev_target")
    return pent.get("target")


def _stress_end() -> pd.Timestamp | None:
    try:
        return pd.read_parquet(P.STRESS_PATH).index[-1]
    except Exception as e:
        print(f"⚠️ 스트레스 경로 읽기 실패: {e}")
        return None


def _band(v: float, cuts: tuple, words: tuple) -> str:
    """v 가 cuts(오름차순) 몇 번째 구간인지에 따라 words 중 하나."""
    return words[sum(v > c for c in cuts)]


def relative_gap(prices, t5yie, vix, hy, pent: dict | None, asof) -> dict | None:
    """혼합 모델(IC35 + P65)의 최근 3·6개월 수익 − S&P (pentarch docs/115 우선순위 6). 자료가 모자라면 None."""
    rm = (pent or {}).get("recent_monthly")
    if not rm:
        return None
    me = _month_ends(prices.index)
    ends = list(me[me < asof.to_period("M").to_timestamp()][-6:]) + [asof]     # 직전 6개 월말 + 오늘
    rows = []
    for a, b in zip(ends[:-1], ends[1:]):
        w = PM.ic_weights_asof(prices, t5yie, vix, hy, a)["final_weights"]
        held = {PM.IC_HOLD.get(k, k): v for k, v in w.items()}          # 성장 칸은 실제 보유인 QQQ 수익으로(2026-11-04 XLK 근사·SHY 0% 수정)
        ic_r = sum(v * (prices[k].asof(b) / prices[k].asof(a) - 1) for k, v in held.items())
        p_r = rm.get(str(b.to_period("M")))
        if p_r is None:
            return None
        rows.append((PM.IC_WEIGHT * ic_r + PM.PENT_WEIGHT * p_r, prices["SPY"].asof(b) / prices["SPY"].asof(a) - 1))
    cum = lambda xs: float(pd.Series(xs).add(1).prod() - 1)              # noqa: E731
    out = {}
    for n in (3, 6):
        last = rows[-n:]
        out[n] = cum([x for x, _ in last]) - cum([y for _, y in last])
    return out


def _merge(ic: dict, pent: dict | None) -> dict:
    out: dict[str, float] = {}
    for k, w in ic.items():
        k = PM.IC_HOLD.get(k, k)                              # I1: IC 성장 칸 XLK 는 실제로 나스닥100(QQQ, 133690)을 산다
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
    name = lambda k: dt.SHORT_KR.get(k, k)                              # noqa: E731
    kst = pd.Timestamp.now(tz="Asia/Seoul")
    alerts = freshness_alerts(asof, last_expected_close(now_et), pent, _stress_end())
    alerts += [f"🚨 {x} — IC 가 v2.2 와 다른 규칙이 됨, 매매 보류" for x in P.input_problems(asof)]   # docs/139 F06
    lines = [f"🏦 <b>{PM.PENSION_VERSION}</b> {kst:%m-%d}({'월화수목금토일'[kst.weekday()]}) · 미국 {asof:%m-%d} 종가", *alerts, ""]

    # 1) 오늘 할 일
    if trade_today and alerts:                                          # docs/139 F06: 자료가 온전하지 않으면 '교체'를 내지 않는다
        lines += ["⛔ <b>매매 보류</b> — 위 경고를 해결하고 다시 실행한 뒤 교체(한국 휴장이면 다음 거래일)"]
    elif trade_today:
        before = _merge(ic_prev["final_weights"], pent_before(pent, held_d))
        moves = [(k, before.get(k, 0.0), total.get(k, 0.0)) for k in sorted(set(total) | set(before), key=lambda x: -total.get(x, 0))
                 if abs(total.get(k, 0) - before.get(k, 0)) > 1e-6]
        if moves:
            lines += ["🔁 <b>오늘 교체</b> (한국 휴장이면 다음 거래일)",
                      *[f"   {name(k)} {dt._pct(x)} → <b>{dt._pct(y)}</b>" for k, x, y in moves]]
        else:
            lines += ["✅ 월말 판단 끝 · <b>바꿀 것 없음</b>"]
    else:
        lines += [f"😴 오늘 매매 없음 · 다음 판단 {US_BME.rollforward(asof):%m-%d} 종가"]

    # 2) 보유
    def sleeve(icw: dict, pw: dict | None) -> str:
        """연금 신호 세 칸(계좌 기준): IC 35 · PENTARCH 1위 35 · 2위 30."""
        ic = " + ".join(f"{name(PM.IC_HOLD.get(k, k))}" + (f" {dt._pct(PM.IC_WEIGHT * v)}" if v < 1 - 1e-6 else "")
                        for k, v in sorted(icw.items(), key=lambda kv: -kv[1]) if v > 1e-6)
        parts = [f"   ① IC {dt._pct(PM.IC_WEIGHT)}: {ic}"]
        rank = sorted(((k, v) for k, v in (pw or {}).items() if v > 1e-6), key=lambda kv: -kv[1])
        for i, (k, v) in enumerate(rank, 1):
            parts.append(f"   {'②③④'[i - 1] if i <= 3 else '·'} PENTARCH {i}위 {dt._pct(PM.PENT_WEIGHT * v)}: {name(k)}")
        if not rank:
            parts.append("   ② PENTARCH: ⚠️ 신호 없음")
        return "\n".join(parts)
    lines += ["", f"📦 <b>{held_d:%m-%d} 월말 결정</b> = 이번 달 보유", sleeve(ic_held["final_weights"], p_t)]
    for k, v in sorted(total.items(), key=lambda kv: -kv[1]):
        if v > 1e-6:
            lines.append(f"• {name(k)} <b>{dt._pct(v)}</b> — {html.escape(PM.KR_ETF.get(k, k))}")

    # 3) 경제를 어떻게 보나
    g, i = ic_held.get("growth_on"), ic_held.get("inflation_on")
    cell = {(True, True): "에너지", (True, False): "나스닥100", (False, True): "유틸리티", (False, False): "국채"}[(bool(g), bool(i))]
    lines += ["", "🧭 <b>경제 판단</b>",
              f"IC: 성장{'↑' if g else '↓'} 인플레{'↑' if i else '↓'} → {cell}"]
    if pent is None:
        lines.append("PENTARCH: ⚠️ 신호 없음 (06:40 크론 확인)")
    else:
        eco = pent.get("economy")
        top = ""
        if eco:
            k, v = max(eco["regime_probs"].items(), key=lambda kv: kv[1])
            val = _band(eco["pillars"]["valuation_z"], (-1.0, -0.3, 0.3), ("주식 매우 비쌈", "주식 비쌈", "주식 보통", "주식 쌈"))
            top = f"{k} {v*100:.0f}% · {val} "
        lines.append(f"PENTARCH: {top}→ {'·'.join(name(k) for k in p_t)}")
        rr = pent.get("risk_regime")
        vr = pent.get("vrp")
        if rr or vr:
            parts = []
            if rr:
                parts.append(f"시장 위험: {'🔴 스트레스' if rr['on'] else '평온'}")
            gp = pent.get("global_panic")                        # docs/126 P7 — 자산 전반 동조화(흡수비율)
            if gp:
                parts.append(f"글로벌 동조화 {'🔴 패닉' if gp['on'] else '평온'}({gp['absorption']:.2f}/{gp['threshold_q90']:.2f})")
            if vr:                                              # docs/121 V1 — 옵션 보험료(VRP) z
                parts.append("보험료 " + _band(vr["z"], (-1.0, 1.0), ("낮음(주식 감점)", "보통", "높음(주식 가점)")))
            lines.append(" · ".join(parts))

    # 3-1) 두 값: 이번 달 보유(월말 결정) vs 오늘 종가로 판단했다면(매매 안 함, 다음 월말 미리보기) — 2026-11-03 사용자 요청
    if not trade_today and pent is not None and pent.get("if_today"):
        today_total = _merge(ic_now["final_weights"], pent["if_today"])
        diff = {k for k in set(today_total) | set(total) if abs(today_total.get(k, 0) - total.get(k, 0)) > 0.005}
        prev_line = " · ".join(f"{name(k)} {dt._pct(v)}" for k, v in sorted(today_total.items(), key=lambda kv: -kv[1]) if v > 1e-6)
        lines += ["", f"🔭 <b>오늘({asof:%m-%d} 종가) 판단이면</b> — 매매 안 함, 다음 월말 미리보기",
                  sleeve(ic_now["final_weights"], pent["if_today"]),
                  "   → " + ("월말 결정과 <b>같음</b>" if not diff else "월말 결정과 <b>다름</b>: " + "·".join(name(k) for k in sorted(diff)))]

    # 4) 알아둘 것(있을 때만)
    notes = []
    vl = pent.get("value_layer") if pent else None
    if vl and vl["penalty"] == "꺼짐":
        notes.append("PENTARCH 밸류 감점 꺼짐 → 시장 추종 중")
    if (pent and (pent.get("reentry") or {}).get("on")) or ic_held.get("reentry"):
        notes.append("신용 확인 재진입 신호 켜짐 → 주식 복귀")
    rr = (pent or {}).get("risk_regime") or {}
    if rr.get("on"):
        blk = "·".join(name(k) for k in rr.get("blocked", [])) or "없음"
        notes.append(f"시장 스트레스({rr.get('since')}~) → 월말에 3개월 손실 자산 제외(지금 해당: {blk})")
    gp = (pent or {}).get("global_panic") or {}
    if gp.get("on"):
        blk = "·".join(name(k) for k in gp.get("blocked", [])) or "없음"
        notes.append(f"글로벌 동조화 패닉(흡수비율 {gp.get('absorption'):.2f} > 과거 90분위) → 월말에 3개월 손실 자산 제외(지금 해당: {blk})")
    if ic_held.get("disinflation"):
        notes.append(f"IC 디스인플레이션(A2): 물가 {ic_held.get('cpi_yoy'):.1f}% 로 높지만 6개월 전보다 낮음 → 인플레 칸 대신 나스닥·국채")
    elif ic_held.get("disinflation") is None:
        notes.append("⚠️ 헤드라인 CPI 수집 실패·지연 → A2 디스인플레이션 판정 꺼짐(v2.1 규칙)")
    band = ic_held.get("infl_band")
    if band and ic_held.get("bei") is not None and band[0] <= ic_held["bei"] <= band[1]:
        notes.append(f"BEI {ic_held['bei']:.2f}% 가 인플레 판정 띠({band[0]}~{band[1]}%) 안 → 직전 판정 유지(I3)")
    if ic_held.get("employment_hold"):
        notes.append("IC 고용 유예(G1S): S&P 200일선 아래지만 고용 양호·시장 평온 → 성장 칸 유지")
    if ic_held["exposure"] < 1.0:
        notes.append("IC 과열(탐욕) → 절반은 단기채")
    if pent and pent["stale"]:
        notes.append(f"PENTARCH 신호 {pent['stale_days']}일 지남")
    if not trade_today and any(abs(ic_now["final_weights"].get(k, 0) - ic_held["final_weights"].get(k, 0)) > 1e-6
                               for k in set(ic_now["final_weights"]) | set(ic_held["final_weights"])):
        notes.append("월말에 IC 가 " + "·".join(name(k) for k in ic_now["final_weights"]) + "(으)로 바뀔 수 있음")
    gap = relative_gap(prices, t5yie, vix, hy, pent, asof)
    if gap and min(gap.values()) < -0.10:
        notes.append(f"최근 3·6개월 S&P 대비 {gap[3]*100:+.0f}%p · {gap[6]*100:+.0f}%p — "
                     "위기 뒤 반등·실물자산 조정 때 반복된 구간, 규칙대로 유지")
    if notes:
        lines += ["", *[f"⚠️ {n}" for n in notes]]
    return "\n".join(lines)


def main() -> None:
    msg = build_message()
    if "--dry" in sys.argv:
        print(msg)
        return
    dt.send_message(msg)


if __name__ == "__main__":
    main()
