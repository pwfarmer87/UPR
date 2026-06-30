from upr.config import Settings
from upr.pipeline import run_review


def test_mock_pipeline_runs_end_to_end():
    settings = Settings(data_source="mock", fiscal_year=2025)
    result = run_review(settings)
    assert result.sources_used == ["mock"]
    assert len(result.financials) >= 12
    df = result.to_frame()
    assert {"program_name", "net_margin", "total_revenue"} <= set(df.columns)


def test_live_falls_back_to_mock_when_unauthorized():
    # No credentials configured -> live connectors unavailable -> mock fallback.
    settings = Settings(data_source="live", fiscal_year=2025)
    result = run_review(settings)
    assert result.sources_used == ["mock"]
    assert len(result.financials) >= 12


def test_overhead_fully_allocated_in_portfolio():
    settings = Settings(data_source="mock", fiscal_year=2025)
    result = run_review(settings)
    totals = result.totals()
    pool = result.institution.university_operations_cost
    # allocation should distribute the whole pool (within rounding pennies)
    assert abs(totals["allocated_overhead"] - pool) < len(result.financials) * 0.01


def test_year_over_year_growth_changes_totals():
    r2025 = run_review(Settings(data_source="mock", fiscal_year=2025))
    r2026 = run_review(Settings(data_source="mock", fiscal_year=2026))
    assert r2026.totals()["total_revenue"] > r2025.totals()["total_revenue"]
