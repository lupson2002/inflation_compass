"""연금 주문서 — 미국 월말 판정과 신호 신선도 경고."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nyse_calendar import is_last_session_of_month as last   # noqa: E402
import pension_order as O                                    # noqa: E402


@pytest.mark.parametrize("d", ["2024-03-28", "2018-03-29", "2021-12-31", "2010-12-31", "2021-05-28", "2027-05-28", "2027-12-31", "2029-03-29", "2026-10-30"])
def test_real_month_end_sessions(d):
    assert last(d)


@pytest.mark.parametrize("d", ["2021-12-30", "2027-12-30", "2024-03-27", "2026-11-03", "2023-10-09"])
def test_not_month_end(d):
    assert not last(d)


def test_expected_close_skips_good_friday_and_uses_prior_day_before_close():
    et = pd.Timestamp("2024-03-29 19:00", tz="America/New_York")
    assert O.last_expected_close(et) == pd.Timestamp("2024-03-28")
    et = pd.Timestamp("2026-11-04 10:00", tz="America/New_York")
    assert O.last_expected_close(et) == pd.Timestamp("2026-11-03")
    et = pd.Timestamp("2026-11-03 19:00", tz="America/New_York")
    assert O.last_expected_close(et) == pd.Timestamp("2026-11-03")


def test_freshness_alerts():
    a, e = pd.Timestamp("2026-11-03"), pd.Timestamp("2026-11-03")
    ok = {"data_asof": "2026-11-03"}
    assert O.freshness_alerts(a, e, ok, a) == []
    assert "IC 가격" in O.freshness_alerts(pd.Timestamp("2026-10-30"), e, {"data_asof": "2026-10-30"}, pd.Timestamp("2026-10-30"))[0]
    assert "PENTARCH 신호가" in O.freshness_alerts(a, e, {"data_asof": "2026-11-02"}, a)[0]
    assert "PENTARCH 신호 없음" in O.freshness_alerts(a, e, None, a)[0]
    assert "스트레스" in O.freshness_alerts(a, e, ok, pd.Timestamp("2026-11-02"))[0]
