from upr.config import Settings
from upr.forecast import (
    ForecastAssumptions,
    forecast_frame,
    forecast_totals,
    watch_list,
)
from upr.pipeline import run_review


def _result():
    return run_review(Settings(data_source="mock", fiscal_year=2025))


def test_forecast_frame_has_projection_columns():
    df = forecast_frame(_result())
    assert {"projected_majors", "projected_pct_change", "watch_flag",
            "yield_rate", "projected_contribution_margin"} <= set(df.columns)
    assert len(df) == len(_result().financials)


def test_yield_and_admit_rates_between_zero_and_one():
    df = forecast_frame(_result())
    assert ((df["yield_rate"] >= 0) & (df["yield_rate"] <= 1)).all()
    assert ((df["admit_rate"] >= 0) & (df["admit_rate"] <= 1)).all()


def test_higher_retention_projects_more_students():
    low = forecast_totals(_result(), ForecastAssumptions(retention_rate=0.6))
    high = forecast_totals(_result(), ForecastAssumptions(retention_rate=0.95))
    assert high["projected_majors"] > low["projected_majors"]


def test_watch_list_is_subset_and_non_stable():
    result = _result()
    full = forecast_frame(result)
    watch = watch_list(result)
    assert len(watch) <= len(full)
    assert (watch["watch_flag"] != "Stable").all()


def test_forecast_totals_reconcile_with_frame():
    result = _result()
    df = forecast_frame(result)
    totals = forecast_totals(result)
    assert totals["projected_majors"] == int(df["projected_majors"].sum())
    assert totals["current_majors"] == int(df["enrolled_majors"].sum())
