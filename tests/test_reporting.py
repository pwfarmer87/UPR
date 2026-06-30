import io

from upr.config import Settings
from upr.pipeline import run_review
from upr.reporting import (
    build_excel_report,
    build_html_report,
    by_college,
)
from upr.trends import run_multiyear


def _result():
    return run_review(Settings(data_source="mock", fiscal_year=2025))


def test_html_report_contains_key_sections():
    html = build_html_report(_result())
    assert "<!doctype html>" in html.lower()
    assert "Program Financial Review" in html
    assert "By college" in html
    assert "underwater" in html.lower()
    # forecast section is included by default
    assert "Next-year forecast" in html
    # a known sample program should appear
    assert "Nursing" in html


def test_html_report_includes_trend_when_multiyear_given():
    myr = run_multiyear([2024, 2025, 2026], Settings(data_source="mock"))
    html = build_html_report(_result(), multiyear=myr)
    assert "Multi-year trend" in html
    assert "CAGR" in html
    # without multiyear, no trend section
    assert "Multi-year trend" not in build_html_report(_result())


def test_html_forecast_can_be_disabled():
    assert "Next-year forecast" not in build_html_report(
        _result(), include_forecast=False
    )


def test_excel_report_is_valid_workbook():
    data = build_excel_report(_result())
    assert isinstance(data, bytes) and len(data) > 0
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert {"Summary", "Programs", "Underwater", "By College", "Forecast"} <= set(
        wb.sheetnames
    )


def test_excel_report_adds_trend_sheets_with_multiyear():
    import openpyxl

    myr = run_multiyear([2024, 2025, 2026], Settings(data_source="mock"))
    data = build_excel_report(_result(), multiyear=myr)
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert "Trend by year" in wb.sheetnames


def test_by_college_reconciles_to_totals():
    result = _result()
    college = by_college(result)
    totals = result.totals()
    assert round(college["net_margin"].sum(), 2) == totals["net_margin"]
    assert int(college["enrolled_majors"].sum()) == totals["enrolled_majors"]
