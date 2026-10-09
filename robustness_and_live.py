"""16개 조합 후속 점검 (2026-10-08) — ① 실거래 시점 가능성 ② 임계값 견고성. 결과: robustness_and_live_report.md

① 실거래: 월말 오후(종가 전)에 yfinance 시장 데이터로 모델을 돌려 종가 전에 매매한다.
   - 가격·VIX 는 그날 장중 값(≈ 종가)을 쓸 수 있다 → 백테스트의 '그날 종가' 가정과 같다고 본다.
   - FRED 지표(T5YIE·BAA10Y)는 그날 값이 아직 없다(다음 영업일 게시) → **하루 전 값**으로 판단해야 한다.
   그래서 비교: FRED 지연 0일(연구) / 1일(실거래) / 2일(게시 지연 여유) / 전체 신호 1일 지연(종가 다음 날 매매 — 참고).
② 견고성: P1(BAA10Y·VIX 임계값)·P3(IEF 이동평균)·P4(목표 변동성·하한)를 주변 값으로 바꿔도 효과가 유지되나.
   기준선 M00 대비 같은 조건에서의 증분으로 본다. 모두 월별 모델·T-bill 금리·30bp 비용(run_16_matrix_experiments).
    python3 robustness_and_live.py
"""
from __future__ import annotations

from dataclasses import replace

import pandas as pd

from run_16_matrix_experiments import Params, simulate
from test_all_16_combinations import compute_signals, load_master_data

MODELS = {"M00 기준": (0, 0, 0, 0), "M02 P3": (0, 0, 1, 0), "M08 P1": (1, 0, 0, 0), "M10 P1+P3": (1, 0, 1, 0),
          "M01 P4": (0, 0, 0, 1), "M03 P3+P4": (0, 0, 1, 1)}


def row(r: dict) -> str:
    return f"{r['CAGR']:.2%} | {r['MDD']:.2%} | {r['Calmar']:.3f} | {r['Sharpe']:.2f} | {r['2008_MDD']:.2%} | {r['2022_Ret']:+.1%}"


def cnn_cross_check(prices, t5yie, vix, baa10y, dtb3) -> list[str]:
    """③ 지수 교차검증: 연구 지수(IC 위험선호 지수, 4요소 대리) 대신 CNN 실지수(2011~)를 넣어도 규칙이 버티나."""
    import fng_engine
    cnn = fng_engine.load_cnn_archive()
    out = ["", "## ③ 지수 교차검증 — IC 위험선호 지수 vs CNN Fear & Greed 실지수 (2011-06~, FRED 1일)", ""]
    if cnn is None:
        return out + ["CNN 아카이브 조회 실패 — 생략"]
    sig, _ = compute_signals(prices, t5yie, vix, baa10y, fred_lag=1)
    sc = sig.copy()
    sc["fng"] = cnn.reindex(sc.index).ffill()
    sc = sc.loc["2011-01-03":].dropna(subset=["fng"])
    out += ["| 공포 2배 규칙 | 지수 | CAGR | MDD | Calmar | 최악 월 |", "|---|---|---|---|---|---|"]
    for rule, lab in (("t0", "당월만 (확정)"), ("ultra", "당월·2·3~4개월 전 (종전)")):
        for name, ss in (("IC 위험선호", sig), ("CNN 실지수", sc)):
            r = simulate(ss, prices, dtb3, 0, 0, 1, 0, replace(Params(), fear_rule=rule), start="2011-06-30")
            out.append(f"| {lab} | {name} | {r['CAGR']:.2%} | {r['MDD']:.2%} | {r['Calmar']:.3f} | {r['monthly_ret'].min():+.1%} |")
    return out


def main() -> int:
    prices, t5yie, vix, baa10y, dtb3 = load_master_data()
    lines = ["# 16개 조합 후속 점검 — 실거래 시점 · 임계값 견고성 (2026-10-08)", "",
             "모두 월별 모델(월말 종가 체결·월중 보유), 차입·현금 = DTB3(+50bp 차입), 거래비용 = 월말 매매 명목 × 30bp.",
             "침체 국면 = XLP 50 + IEF 50(1배), 공포 2배 때 늘린 몫은 IEF 에만, IEF < 200일선이면 SHY 100%·1배 (2026-10-09 확정).",
             "공포 2배 = 당월 IC 위험선호 지수 < 15 만(fear_rule='t0', 2026-10-09 확정).", "",
             "## ① 실거래 시점 — FRED 지표(T5YIE·BAA10Y) 지연", "",
             "| 신호 시점 | 모델 | CAGR | MDD | Calmar | Sharpe | 2008 MDD | 2022 수익 |", "|---|---|---|---|---|---|---|---|"]
    variants = {"FRED 0일(연구)": dict(fred_lag=0), "FRED 1일(실거래)": dict(fred_lag=1), "FRED 2일": dict(fred_lag=2)}
    sigs = {k: compute_signals(prices, t5yie, vix, baa10y, **v)[0] for k, v in variants.items()}
    sigs["전체 신호 1일(다음 날 매매)"] = sigs["FRED 1일(실거래)"].shift(1).dropna()
    for vname, sig in sigs.items():
        for mname, c in MODELS.items():
            lines.append(f"| {vname} | {mname} | {row(simulate(sig, prices, dtb3, *c))} |")
    sig = sigs["FRED 0일(연구)"]

    base = simulate(sig, prices, dtb3, 0, 0, 0, 0)
    lines += ["", "## ② 임계값 견고성 (FRED 0일, 기준선 M00 대비 증분)", "",
              f"기준선 M00: {row(base)}", "",
              "### P1 서킷브레이커 — BAA10Y × VIX (M08 = P1 단독)", "",
              "| BAA10Y > | VIX > | 발동 월 | CAGR 증분 | MDD | Calmar | 2008 MDD |", "|---|---|---|---|---|---|---|"]
    for baa in (2.6, 2.8, 3.0, 3.2, 3.4, 3.6, 99.0):
        for vx in (30.0, 35.0, 40.0, 999.0):
            if baa == 99.0 and vx == 999.0:
                continue
            r = simulate(sig, prices, dtb3, 1, 0, 0, 0, replace(Params(), p1_baa=baa, p1_vix=vx))
            lines.append(f"| {'끔' if baa == 99 else baa} | {'끔' if vx == 999 else vx:} | {r['P1_Months']} | "
                         f"{(r['CAGR'] - base['CAGR']) * 100:+.2f}%p | {r['MDD']:.2%} | {r['Calmar']:.3f} | {r['2008_MDD']:.2%} |")
    lines += ["", "### P3 채권방어 — IEF 이동평균 일수 (M02 = P3 단독)", "",
              "| IEF MA | CAGR 증분 | MDD | Calmar | 2022 수익 | 2022 MDD |", "|---|---|---|---|---|---|"]
    for ma in (100, 150, 200, 250):
        r = simulate(sig, prices, dtb3, 0, 0, 1, 0, replace(Params(), p3_ma=ma))
        lines.append(f"| {ma} | {(r['CAGR'] - base['CAGR']) * 100:+.2f}%p | {r['MDD']:.2%} | {r['Calmar']:.3f} | {r['2022_Ret']:+.1%} | {r['2022_MDD']:.2%} |")
    lines += ["", "### P4 볼록성 레버리지 — 목표 변동성 × 하한 (M01 = P4 단독)", "",
              "| 목표 변동성 | 하한 | CAGR 증분 | MDD | Calmar | Sharpe |", "|---|---|---|---|---|---|"]
    for tgt in (0.24, 0.28, 0.32, 0.36, 0.40):
        for fl in (1.0, 1.3, 1.6):
            r = simulate(sig, prices, dtb3, 0, 0, 0, 1, replace(Params(), p4_target=tgt, p4_floor=fl))
            lines.append(f"| {tgt} | {fl} | {(r['CAGR'] - base['CAGR']) * 100:+.2f}%p | {r['MDD']:.2%} | {r['Calmar']:.3f} | {r['Sharpe']:.2f} |")
    lines += cnn_cross_check(prices, t5yie, vix, baa10y, dtb3)
    text = "\n".join(lines) + "\n"
    with open("robustness_and_live_report.md", "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
