import io

from upr.config import Settings
from upr.pipeline import run_review
from upr.reporting import (
    build_excel_report,
    build_html_report,
    by_college,
)


def _result():
    return run_review(Settings(data_source="mock", fiscal_year=2025))


def test_html_report_contains_key_sections():
    html = build_html_report(_result())
    assert "<!doctype html>" in html.lower()
    assert "Program Financial Review" in html
    assert "By college" in html
    assert "underwater" in html.lower()
    # a known sample program should appear
    assert "Nursing" in html


def test_excel_report_is_valid_workbook():
    data = build_excel_report(_result())
    assert isinstance(data, bytes) and len(data) > 0
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert {"Summary", "Programs", "Underwater", "By College"} <= set(wb.sheetnames)


def test_by_college_reconciles_to_totals():
    result = _result()
    college = by_college(result)
    totals = result.totals()
    assert round(college["net_margin"].sum(), 2) == totals["net_margin"]
    assert int(college["enrolled_majors"].sum()) == totals["enrolled_majors"]
