"""연금 운용 확정 혼합 (2026-10-30 비율 변경): IC 연금형 34% + PENTARCH 비레버리지 66%.

- IC 연금형: 확정 전략에서 레버리지만 뺀 것(4국면 섹터 85% + 상시 보험 금 10·BIL 5 + 침체 국면 채권방어 + IC 위험선호 지수 > 85 면 0.5배).
  공포 2배는 연금형에 없다(빌리지 않음). 탐욕 0.5배는 있다.
- PENTARCH 비레버리지: /home/mikey/pentarch 운용 모델(v18.6, 2026-10-29~) 신호에서 레버리지 ETF 만 끈 목표 비중.
  pentarch 크론(06:40 scripts/run_pension.sh, 데이터 재수집)이 output/pension_target.json 으로 낸다. 이 모듈은 그 파일을 읽기만 한다.
  Streamlit Cloud 처럼 그 경로가 없으면 data/pentarch_pension_target.json(마지막 로컬 사본)을 읽는다.

비율 근거(pentarch docs/100): IC 백테스트는 신호를 만든 월말 종가에 바로 체결하는 가정이라 실제보다 좋게 나왔다.
다음 거래일 체결로 바꾸면 Sharpe 최대 혼합은 IC 24~38%(평탄 14~50%) — 34/66 은 2003~·2008~ 두 구간 모두 평탄 구간 안, 50/50 은 2008~ 에서 밖.
백테스트(월말 재조정 30bp, IC 다음 날 체결, PENTARCH v18.6 다음 날 체결, 월말 기준):
  2008-02~2026-10: 혼합 14.2% / MDD −13.6%  ·  IC 단독 13.4% / −16.8%  ·  PENTARCH 단독 14.3% / −14.2%
  2003-10~2026-10: 혼합 15.9% / −13.6%  (50/50 이었으면 16.2% / −13.7%, Sharpe 1.17 로 같다)
종전 50/50 표기(10-09~10-29, IC 당일 종가 체결 가정): 15.3% / −13.0%.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).parent
PENTARCH_JSON = Path(os.getenv("PENTARCH_PENSION_JSON", "/home/mikey/pentarch/output/pension_target.json"))
LOCAL_COPY = BASE_DIR / "data" / "pentarch_pension_target.json"
IC_WEIGHT, PENT_WEIGHT = 0.34, 0.66
STALE_DAYS = 5
BACKTEST = {"기간": "2008-02 ~ 2026-10 (월말, 다음 날 체결)", "CAGR": 0.142, "MDD": -0.136,
            "IC 단독": (0.134, -0.168), "PENTARCH 단독": (0.143, -0.142)}


def load_pentarch_target() -> dict | None:
    """PENTARCH 비레버리지 목표. 원본이 있으면 로컬 사본도 갱신한다. 없으면 사본, 그것도 없으면 None."""
    src = PENTARCH_JSON if PENTARCH_JSON.exists() else (LOCAL_COPY if LOCAL_COPY.exists() else None)
    if src is None:
        return None
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[pension_mix] PENTARCH 신호 읽기 실패: {e}")
        return None
    if src == PENTARCH_JSON:
        try:
            shutil.copyfile(PENTARCH_JSON, LOCAL_COPY)
        except OSError:
            pass
    data["source"] = "pentarch" if src == PENTARCH_JSON else "로컬 사본"
    data["stale_days"] = (date.today() - date.fromisoformat(data["data_asof"])).days
    data["stale"] = data["stale_days"] > STALE_DAYS
    return data


def mix_position(prices, t5yie, vix, baa10y) -> dict:
    """오늘 기준 연금 혼합 목표 비중. PENTARCH 신호가 없으면 그 몫은 표시만 비우고 합계에서 뺀다."""
    import pension_baa as P
    ic = P.ic_pension_weights(prices, t5yie, vix, baa10y)
    pent = load_pentarch_target()
    total: dict[str, float] = {}
    for k, w in ic["final_weights"].items():
        total[k] = total.get(k, 0.0) + IC_WEIGHT * w
    if pent is not None:
        for k, w in pent["target"].items():
            total[k] = total.get(k, 0.0) + PENT_WEIGHT * w
    return {"ic": ic, "pentarch": pent, "weights": total}


def label(w: float) -> str:
    """슬리브 비중 표기(예: 0.34 → '34%')."""
    return f"{w * 100:.0f}%"


def ic_weights_asof(prices, t5yie, vix, baa10y, d) -> dict:
    """그 날짜 종가까지의 자료로 본 IC 연금형 목표(월말 결정 확인용)."""
    import pension_baa as P
    return P.ic_pension_weights(prices.loc[:d], t5yie.loc[:d], vix.loc[:d], baa10y.loc[:d])


def weights_str(w: dict) -> str:
    import pension_baa as P
    return P.weights_str(w)
