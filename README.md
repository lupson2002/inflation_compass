# Inflation Compass

David Varadi의 "Inflation Compass" 섹터 로테이션 전략 백테스트.

참고 자료:
- https://cssanalytics.wordpress.com/2026/07/27/the-inflation-compass-model/
- https://allocatesmartly.com/taming-the-wildcard-david-varadis-inflation-compass/

## 전략

성장(Growth)과 인플레이션(Inflation) 두 축으로 매월 하나의 섹터 ETF에 전액 투자하는 로테이션 전략.

| 성장 | 인플레이션 | 보유자산 |
|---|---|---|
| 상승 | 상승 | XLE (에너지) |
| 상승 | 하락 | XLK (기술) |
| 하락 | 상승 | XLU (유틸리티) |
| 하락 | 하락 | XLP + IEF 50/50 (필수소비재 + 국채) |

매월 마지막 거래일에 판단하고, 다음 한 달간 보유.

### 신호

**성장 상승** - SPY 종가가 200일 이동평균 위.

**인플레이션 상승** = (T5YIE > 2.0%) AND (breakeven 모멘텀 또는 confirming indicator 모멘텀 중 하나라도 양수)

- **레벨**: T5YIE(5년 기대인플레이션, FRED) > 2.0%
- **Breakeven 모멘텀**: T5YIE가 60거래일 전보다 높음
- **Asset 모멘텀**: confirming indicator의 60일 선형회귀 기울기 > 0

**Confirming indicator** - 인플레이션 수혜/피해 섹터 바스켓의 누적수익률 비율(둘 다 일별수익률 기반):

- 포지티브 바스켓 = 0.5·XLE + (1/6)·XLI + (1/6)·XLF + (1/6)·XLB
- 네거티브 바스켓 = (1/3)·XLU + (1/3)·XLV + (1/3)·XLP
- indicator = 포지티브 바스켓 누적수익률 / 네거티브 바스켓 누적수익률

## 데이터

10개 티커(Yahoo Finance, 배당반영 수정종가) + T5YIE(FRED):
SPY, XLE, XLK, XLU, XLP, IEF, XLI, XLF, XLB, XLV

섹터 SPDR는 전부 1998-12-16 상장, IEF는 2002-07-22 상장이라 confirming indicator와
T5YIE 기반 신호는 2003년 이전에는 계산 불가 - 그래서 백테스트는 2003-03-31부터 시작.

## db 테이블

`backtest.py`가 한 번 계산한 결과를 db 테이블로 저장해두기 때문에, 이후 차트나 대시보드는
가격 데이터를 다시 읽거나 신호를 재계산하지 않고 이 테이블들만 SELECT해서 씀:

- `backtest_daily_returns` - 일별 원(gross) 전략/SPY 수익률 (비용 미반영)
- `backtest_turnover_events` - 리밸런싱마다의 턴오버 (비용 시나리오 재계산용)
- `backtest_weights` - 일별 티커별 비중
- `backtest_equity`, `backtest_yearly`, `backtest_positions` - 기본 비용 가정(30bp) 기준 결과

## 참고할 점 (allocatesmartly 리뷰 기준)

- 4개 섹터 중 하나를 고르는 건 자산군 로테이션보다 노이즈에 취약한 예측 문제.
- T5YIE(TIPS breakeven)는 2008-09, 2020-21 같은 유동성 스트레스 구간에서 왜곡됨. 다른
  인플레이션 지표(스왑, Fed 전망치)로 대체하면 성과가 크게 약화돼서, TIPS 특이 현상에 대한
  과적합 가능성이 있음.
- T5YIE는 2003년부터만 존재해서, 그 이전까지 보여주는 백테스트(allocatesmartly는 1990년까지
  표시)는 재구성된 입력값에 의존함 - allocatesmartly 자신도 2003년 이전은 out-of-sample로
  봐야 한다고 명시함. 이 리포지토리는 그래서 2003-03-31을 진짜 시작점으로 삼음.