"""NYSE 휴장일 달력 — '이 날이 그 달 마지막 미국 거래일인가' 판정용(외부 패키지 없이).

연방 공휴일 달력과 다른 점: 성금요일 휴장, 콜럼버스·재향군인의 날 개장, 1월 1일이 토요일이면 전날(12-31)을 쉬지 않는다.
임시 휴장(허리케인·국장)은 규칙으로 알 수 없으므로 판단일 자체는 실제 가격 자료로 교차 확인한다.
"""
from __future__ import annotations

import pandas as pd
from pandas.tseries.holiday import (AbstractHolidayCalendar, GoodFriday, Holiday, USLaborDay, USMartinLutherKingJr,
                                    USMemorialDay, USPresidentsDay, USThanksgivingDay, nearest_workday,
                                    sunday_to_monday)
from pandas.tseries.offsets import CustomBusinessDay, CustomBusinessMonthEnd


class NYSEHolidayCalendar(AbstractHolidayCalendar):
    rules = [
        Holiday("New Year", month=1, day=1, observance=sunday_to_monday),
        USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
        Holiday("Independence", month=7, day=4, observance=nearest_workday),
        USLaborDay, USThanksgivingDay,
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
    ]


NYSE_BME = CustomBusinessMonthEnd(calendar=NYSEHolidayCalendar())
NYSE_BDAY = CustomBusinessDay(calendar=NYSEHolidayCalendar())


def is_last_session_of_month(d) -> bool:
    d = pd.Timestamp(d).normalize()
    return d == NYSE_BME.rollforward(d)
