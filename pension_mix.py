"""연금 운용 확정 혼합 (2026-10-30): IC 연금형 35% + PENTARCH 비레버리지 65%(매력도 1위 35 · 2위 30).

- IC 연금형: 4국면 섹터 칸 100% + 침체 국면 채권방어 + IC 위험선호 지수 > 85 면 0.5배(나머지 단기채).
  상시 보험(금 10·BIL 5)은 연금에서 뺐다(2026-10-30 사용자 결정: 계좌가 복잡해진다). 공포 2배도 없다(빌리지 않음).
- PENTARCH 비레버리지: /home/mikey/pentarch 운용 모델 v18.6 신호, 매력도 1위 35 · 2위 30(슬리브 안 53.8/46.2, pentarch docs/101).
  pentarch 크론(06:40 scripts/run_pension.sh, 데이터 재수집)이 output/pension_target.json 으로 낸다. 이 모듈은 그 파일을 읽기만 한다.
  Streamlit Cloud 처럼 그 경로가 없으면 data/pentarch_pension_target.json(마지막 로컬 사본)을 읽는다.

근거(pentarch docs/100·101): IC 백테스트는 월말 신호를 그 종가에 바로 체결하는 가정이라 실제보다 좋게 나온다 → 다음 날 체결로 평가.
백테스트(월말 재조정 30bp, 둘 다 다음 날 체결, 월말 기준):
  2008-02~2026-10: 혼합 14.6% / MDD −14.5% / Sharpe 1.08  ·  IC(보험 없음) 14.5% / −20.6%  ·  PENTARCH 35/30 14.4% / −14.8%
  2003-10~2026-10: 혼합 16.4% / −14.8% / Sharpe 1.16
  1위 30 · 2위 35 와의 차이는 ±0.1%p 안(사실상 같음). 보험이 있던 IC34/P66 은 14.2% / −13.6% — 보험을 빼면 수익 +0.4%p, 낙폭 −0.9%p.
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
IC_WEIGHT, PENT_WEIGHT = 0.35, 0.65
STALE_DAYS = 5
BACKTEST = {"기간": "2008-02 ~ 2026-10 (월말, 다음 날 체결)", "CAGR": 0.146, "MDD": -0.145,
            "IC 단독": (0.145, -0.206), "PENTARCH 단독": (0.144, -0.148)}


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
