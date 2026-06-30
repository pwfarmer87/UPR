from upr.config import Settings
from upr.forecast import forecast_frame
from upr.pipeline import run_review
from upr.retention import (
    estimate_from_multiyear,
    estimate_retention,
    retention_frame,
    retention_map,
)
from upr.trends import run_multiyear


def _years(a, b):
    return (
        run_review(Settings(data_source="mock", fiscal_year=a)),
        run_review(Settings(data_source="mock", fiscal_year=b)),
    )


def test_estimate_returns_rate_per_program_in_range():
    prev, curr = _years(2024, 2025)
    est = estimate_retention(prev, curr)
    assert len(est) == len(curr.financials)
    for e in est:
        assert 0.0 <= e.retention_rate <= 1.0
        assert e.prior_eligible >= 0


def test_retention_components_are_consistent():
    prev, curr = _years(2024, 2025)
    est = {e.program_code: e for e in estimate_retention(prev, curr, melt_rate=0.0)}
    curr_by_code = {f.program_code: f for f in curr.financials}
    prev_in = {p.program_code: p for p in prev.inputs}
    for code, e in est.items():
        # retained = current enrolled - new students (deposits at melt=0)
        expected_retained = max(
            0.0, curr_by_code[code].enrolled_majors - prev_in[code].deposits
        )
        assert abs(e.retained - expected_retained) < 1e-6


def test_estimate_from_multiyear_uses_latest_two_years():
    myr = run_multiyear([2024, 2025, 2026], Settings(data_source="mock"))
    est = estimate_from_multiyear(myr)
    assert len(est) == len(myr.latest.financials)


def test_single_year_yields_no_estimate():
    myr = run_multiyear([2025], Settings(data_source="mock"))
    assert estimate_from_multiyear(myr) == []


def test_estimated_retention_feeds_forecast():
    prev, curr = _years(2024, 2025)
    rmap = retention_map(estimate_retention(prev, curr))
    base = forecast_frame(curr)
    est = forecast_frame(curr, retention_by_program=rmap)
    # the retention column should reflect the per-program estimates
    est_by_code = est.set_index("program_code")["retention_rate"].to_dict()
    for code, rate in rmap.items():
        assert abs(est_by_code[code] - rate) < 1e-6
    # projections should generally differ from the flat-rate baseline
    assert not base["projected_majors"].equals(est["projected_majors"])


def test_retention_frame_columns():
    prev, curr = _years(2024, 2025)
    df = retention_frame(estimate_retention(prev, curr))
    assert {"program_code", "retention_rate", "prior_eligible"} <= set(df.columns)
