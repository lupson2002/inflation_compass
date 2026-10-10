"""연금 운용 확정 혼합 (2026-10-09): IC 연금형 50% + PENTARCH 비레버리지 50%.

- IC 연금형: 확정 전략에서 레버리지만 뺀 것(4국면 섹터 85% + 상시 보험 금 10·BIL 5 + 침체 국면 채권방어 + IC 위험선호 지수 > 85 면 0.5배).
- PENTARCH 비레버리지: /home/mikey/pentarch 의 v18.2 신호에서 레버리지 ETF 만 끈 목표 비중.
  pentarch 크론(05:00 scripts/run_pension.sh)이 output/pension_target.json 으로 낸다. 이 모듈은 그 파일을 읽기만 한다.
  Streamlit Cloud 처럼 그 경로가 없으면 data/pentarch_pension_target.json(마지막 로컬 사본)을 읽는다.

백테스트(2008-02~2026-09, 월말 재조정, IC·BAA 30bp / PENTARCH 15bp·다음 날 체결):
  IC 연금형 단독 14.9% / MDD −14.4%  ·  PENTARCH 비레버리지 15.2% / −20.1%  ·  50/50 혼합 15.3% / −13.0%  (2026-10-10 상시 보험·침체 IEF100 반영;
  보험 전 10-09판: IC 16.3% / −17.7%, 혼합 16.0% / −15.6%)
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
IC_WEIGHT, PENT_WEIGHT = 0.5, 0.5
STALE_DAYS = 5
BACKTEST = {"기간": "2008-02 ~ 2026-09 (월말)", "CAGR": 0.153, "MDD": -0.130,
            "IC 단독": (0.149, -0.144), "PENTARCH 단독": (0.152, -0.201)}


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
    """오늘 기준 연금 혼합 목표 비중. PENTARCH 신호가 없으면 그 50% 는 표시만 비우고 합계에서 뺀다."""
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


def weights_str(w: dict) -> str:
    import pension_baa as P
    return P.weights_str(w)
