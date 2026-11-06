"""연금 레버리지 판단층 V1 — 계산·보수적 실패·주문서 문구."""
import pandas as pd

import pension_leverage as L

D = pd.Timestamp("2026-10-30")
X = L.Inputs(ey=.0246, be=2.35, y10=4.98, y2=4.6, bill=4.0)


def _macro(end="2026-10-30"):
    ix = pd.bdate_range("2026-10-01", end)
    return pd.DataFrame({"T10YIE": 2.35, "DGS10": 4.98, "DGS2": 4.6, "DTB3": 4.0}, index=ix)


def _shiller():
    return pd.Series([.03, .0246, .0243], index=pd.to_datetime(["2026-08-14", "2026-09-14", "2026-10-15"]))


def test_value_excess_matches_worked_example():
    e = L.value_excess({"XLE": .4, "GUNR": .3, "BIL": .3}, X)
    assert abs(e - (.4 * .0081 + .3 * -.0165)) < 1e-12


def test_bond_and_short_bond_blocks():
    assert abs(L.value_excess({"IEF": 1.0}, X) - .0098) < 1e-12
    assert abs(L.value_excess({"SHY": 1.0}, X) - .006) < 1e-12


def test_low_rate_equity_turns_on():
    x = pd.DataFrame({"T10YIE": 2.4, "DGS10": 2.0, "DGS2": .2, "DTB3": .1}, index=pd.bdate_range("2026-10-01", "2026-10-30"))
    d = L.decide({"QQQ": 1.0}, D, x, pd.Series([.042, .042], index=pd.to_datetime(["2026-09-14", "2026-10-15"])))
    assert d.on and abs(d.excess - (.042 + .024 - .001)) < 1e-12


def test_uses_lagged_cape_observation():
    x, p = L.read_inputs(D, _macro(), _shiller())
    assert p is None and x.ey == .0246


def test_stale_rates_fail_safe():
    d = L.decide({"QQQ": 1.0}, D, _macro("2026-10-20"), _shiller())
    assert not d.on and "오래됨" in d.problem


def test_stale_cape_fail_safe():
    d = L.decide({"QQQ": 1.0}, pd.Timestamp("2027-02-26"), _macro("2027-02-26"), _shiller())
    assert not d.on and "CAPE" in d.problem


def test_missing_sources_and_weights_fail_safe():
    assert not L.decide({"QQQ": 1.0}, D, None, None).on
    assert not L.decide(None, D, _macro(), _shiller()).on


def test_no_future_data_used():
    a = L.decide({"QQQ": 1.0}, D, _macro(), _shiller())
    m = _macro("2026-11-20"); m.loc["2026-11-02":, "DTB3"] = 0.0
    s = pd.concat([_shiller(), pd.Series([.2], index=pd.to_datetime(["2026-11-15"]))])
    b = L.decide({"QQQ": 1.0}, D, m, s)
    assert a == b


def test_order_lines_transitions():
    on, off = L.Decision(True, .05), L.Decision(False, .01)
    assert "대출 시작" in "\n".join(L.order_lines(on, off, True, False, D))
    assert "대출 유지" in "\n".join(L.order_lines(on, on, True, False, D))
    assert "상환" in "\n".join(L.order_lines(off, on, True, False, D))
    assert "할 일 없음" in "\n".join(L.order_lines(off, off, True, False, D))
    assert "대출 운용 중" in "\n".join(L.order_lines(on, None, False, False, D))
    assert "보류" in "\n".join(L.order_lines(on, off, True, True, D))
    assert "판정 불가" in "\n".join(L.order_lines(L.Decision(False, None, "x"), None, True, False, D))
