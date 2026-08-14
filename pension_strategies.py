"""연금 운용 전략 — 전략 정의·설명·성과 지표.

dual-momentum 연구 결과를 기반으로 정적/동적 자산배분 전략 전체를 정의한다.
"""

import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
STRATEGY_CSV = DATA_DIR / "pension_strategies.csv"

# ── 전략 분류 ──
DYNAMIC_STRATEGIES = [
    "V0", "V1", "V3", "V5", "V8", "V9", "V12", "V17",
    "V13", "V14", "V15", "V16", "V19", "V20", "V20T1", "V21",
    "T8", "IC", "BAA-G4", "VAA-G1",
]
STATIC_STRATEGIES = ["S&P500", "60/40", "EW4", "NDX", "DM", "GOLD", "EM"]

# ── 전략 설명 ──
STRATEGY_INFO = {
    # 동적 - V 시리즈
    "V0": {"name": "V0 · 4자산 모멘텀 원형", "group": "동적",
           "desc": "4자산(나스닥·선진국·금·신흥국) 중 모멘텀 점수 최고 1개에 100% 투자. 주식 3개 모두 음수면 금리 스프레드로 현금/장기국채 방어."},
    "V1": {"name": "V1 · V0 + 절대모멘텀 12M", "group": "동적",
           "desc": "V0에 절대모멘텀(12개월) 필터 추가. 선택 자산이 12M 음수면 방어."},
    "V3": {"name": "V3 · V0 + 리스크조정 점수", "group": "동적",
           "desc": "V0의 모멘텀 점수를 12M 변동성으로 나눠 리스크조정."},
    "V5": {"name": "V5 · 금 공격 제외", "group": "동적",
           "desc": "금을 공격 자산에서 제외, 주식 3자산(나스닥·선진국·신흥국)만 모멘텀 회전."},
    "V8": {"name": "V8 · V5 + 절대모멘텀 12M", "group": "동적",
           "desc": "V5에 절대모멘텀 12M 추가. 하락장 방어 강화."},
    "V9": {"name": "V9 · V5 + 절대모멘텀 6M", "group": "동적",
           "desc": "V5에 절대모멘텀 6M 추가. 더 빠른 방어 전환."},
    "V12": {"name": "V12 · V5 + Top-2 + 절대모멘텀 12M", "group": "동적",
            "desc": "상위 2개 자산에 50/50 분산 투자 + 절대모멘텀 12M."},
    "V17": {"name": "V17 · V5 + Top-2 + 절대모멘텀 6M", "group": "동적",
            "desc": "상위 2개 자산 50/50 + 절대모멘텀 6M."},
    "V13": {"name": "V13 · 금 방어자산화", "group": "동적",
            "desc": "방어 시 금을 포함한 안전자산(현금/장기국채/금) 중 1M+3M 모멘텀 최고 선택."},
    "V14": {"name": "V14 · V13 + 절대모멘텀 12M", "group": "동적",
            "desc": "V13에 절대모멘텀 12M 추가."},
    "V15": {"name": "V15 · V13 + 절대모멘텀 6M", "group": "동적",
            "desc": "V13에 절대모멘텀 6M 추가."},
    "V16": {"name": "V16 · V13 + Top-2 + 절대모멘텀 12M", "group": "동적",
            "desc": "V13에 Top-2 분산 + 절대모멘텀 12M."},
    "V19": {"name": "V19 · V12 + ICSA 샴 필터", "group": "동적",
            "desc": "V12에 ICSA(신규실업수당) 샴 규칙 침체 필터 추가."},
    "V20": {"name": "V20 · V12 + SAHM 필터", "group": "동적",
            "desc": "V12에 SAHM(실업률 샴) 침체 필터 추가."},
    "V20T1": {"name": "V20T1 · V8 + SAHM 필터", "group": "동적",
              "desc": "V8에 SAHM 침체 필터 추가, Top-1."},
    "V21": {"name": "V21 · V8 + GAC 필터", "group": "동적",
            "desc": "V8에 GAC(제조업) 3M 하락 침체 필터 추가."},
    "T8": {"name": "T8 · V12 + TIPS 방어", "group": "동적",
           "desc": "V12에 방어 자산으로 TIPS(물가연동채) 추가, 6M 모멘텀 최고 선택."},
    "IC": {"name": "IC · Inflation Compass", "group": "동적",
           "desc": "성장(SPY>200SMA)과 인플레이션(T5YIE) 두 축으로 4레짐 매핑. Up/Rising→금, Up/Falling→나스닥, Down/Rising→금, Down/Falling→장기국채."},
    "BAA-G4": {"name": "BAA-G4 · 켈러 Bold", "group": "동적",
               "desc": "카나리아 13612W 모멘텀이 모두 양수면 공격 자산 12-1 Top1 올인, 아니면 방어 자산 12-1 Top3 균등."},
    "VAA-G1": {"name": "VAA-G1 · 켈러 Vigilant", "group": "동적",
               "desc": "공격 자산 13612W 중 min_pos개 이상 양수면 12-1 Top1 올인, 아니면 방어 자산 12-1 Top1."},
    # 정적
    "S&P500": {"name": "S&P500 · Buy&Hold", "group": "정적",
               "desc": "미국 대형주 지수 단순 보유."},
    "60/40": {"name": "60/40 · 주식/채권", "group": "정적",
              "desc": "S&P500 60% + 현금 40% 고정 배분."},
    "EW4": {"name": "EW4 · 4자산 동일가중", "group": "정적",
            "desc": "나스닥·선진국·금·신흥국 4자산 동일가중(각 25%) 고정 보유."},
    "NDX": {"name": "NDX · 나스닥 Buy&Hold", "group": "정적",
            "desc": "나스닥 100 지수 단순 보유."},
    "DM": {"name": "DM · 선진국 Buy&Hold", "group": "정적",
           "desc": "선진국(제외 미국) 지수 단순 보유."},
    "GOLD": {"name": "GOLD · 금 Buy&Hold", "group": "정적",
             "desc": "금 단순 보유."},
    "EM": {"name": "EM · 신흥국 Buy&Hold", "group": "정적",
           "desc": "신흥국 지수 단순 보유."},
}

# ── 연금 추천 전략 (IC 50/25/25 구성) ──
PENSION_STRATEGIES = {
    "IC": {"name": "IC · Inflation Compass", "weight": 0.50,
           "desc": "성장/인플레이션 4레짐 매핑. 금·나스닥·장기국채 회전."},
    "BAA-G4": {"name": "BAA-G4 · 켈러 Bold", "weight": 0.25,
               "desc": "카나리아 모멘텀 기반 공격/방어 전환."},
    "V8": {"name": "V8 · 모멘텀 Top-1 + 절대모멘텀", "weight": 0.25,
           "desc": "주식 3자산 모멘텀 최고 + 절대모멘텀 방어."},
}


def load_strategy_returns():
    """전략별 월간 수익률 DataFrame 로드."""
    df = pd.read_csv(STRATEGY_CSV, index_col=0, parse_dates=True)
    return df


def strategy_metrics(returns: pd.Series):
    """단일 전략 성과 지표."""
    r = returns.dropna()
    if len(r) == 0:
        return None
    eq = (1 + r).cumprod()
    peak = eq.cummax()
    mdd = (eq / peak - 1).min()
    n_years = len(r) / 12
    cagr = eq.iloc[-1] ** (1 / n_years) - 1
    vol = r.std(ddof=1) * np.sqrt(12)
    sharpe = r.mean() / r.std(ddof=1) * np.sqrt(12) if r.std(ddof=1) > 0 else np.nan
    calmar = cagr / abs(mdd) if mdd < 0 else np.nan
    return {
        "CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "MaxDD": mdd,
        "Calmar": calmar, "Multiple": eq.iloc[-1], "n_months": len(r),
        "start": r.index[0].date(), "end": r.index[-1].date(),
    }


def rolling_metrics(returns: pd.Series, months: int):
    """롤링 윈도우 CAGR/MDD/기간수익률/Sharpe/Calmar."""
    r = returns.dropna()
    out = []
    for i in range(months - 1, len(r)):
        seg = r.iloc[i - months + 1:i + 1]
        eq = (1 + seg).cumprod()
        mdd = (eq / eq.cummax() - 1).min()
        cagr = (1 + seg).prod() ** (12 / months) - 1
        period_ret = (1 + seg).prod() - 1
        vol = seg.std(ddof=1) * np.sqrt(12)
        sharpe = seg.mean() / seg.std(ddof=1) * np.sqrt(12) if seg.std(ddof=1) > 0 else np.nan
        calmar = cagr / abs(mdd) if mdd < 0 else np.nan
        out.append({"end": r.index[i], "CAGR": cagr, "MDD": mdd,
                    "기간수익률": period_ret, "Sharpe": sharpe, "Calmar": calmar})
    return pd.DataFrame(out)


def pension_weights():
    """연금 IC 50/25/25 비중 dict."""
    return {k: v["weight"] for k, v in PENSION_STRATEGIES.items()}
