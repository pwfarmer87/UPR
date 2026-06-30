from upr.config import Settings
from upr.trends import (
    institution_trend,
    program_trajectory,
    run_multiyear,
    trend_frame,
    yoy_summary,
)


def _myr():
    return run_multiyear([2024, 2025, 2026], Settings(data_source="mock"))


def test_run_multiyear_collects_each_year():
    myr = _myr()
    assert myr.years == [2024, 2025, 2026]
    assert set(myr.results) == {2024, 2025, 2026}
    assert myr.latest.fiscal_year == 2026


def test_trend_frame_is_long_and_complete():
    df = trend_frame(_myr())
    assert {"fiscal_year", "program_code", "net_margin"} <= set(df.columns)
    # 3 years × N programs
    n_programs = len(_myr().results[2025].financials)
    assert len(df) == 3 * n_programs


def test_institution_trend_grows_year_over_year():
    it = institution_trend(_myr()).sort_values("fiscal_year")
    revenues = it["total_revenue"].tolist()
    assert revenues == sorted(revenues)  # monotonic increase in sample data


def test_program_trajectory_wide_has_year_columns():
    wide = program_trajectory(_myr(), "enrolled_majors")
    assert 2024 in wide.columns and 2026 in wide.columns
    assert "program_name" in wide.columns


def test_yoy_summary_has_change_and_cagr():
    summary = yoy_summary(_myr(), "net_margin")
    assert {"change", "pct_change", "cagr"} <= set(summary.columns)
    # sample data grows ~3%/yr, so net margin should rise over the window
    assert (summary["change"] > 0).any()
