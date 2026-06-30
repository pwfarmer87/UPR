from upr.finance.calculations import (
    compute_portfolio,
    compute_program_financials,
    portfolio_totals,
)
from upr.models import InstitutionInputs, ProgramInputs


def _program(**kw):
    base = dict(
        program_code="TEST",
        program_name="Test",
        college="X",
        student_credit_hours=1000,
        enrolled_majors=100,
        completions=20,
        tuition_rate_per_credit_hour=1000.0,
        institutional_aid=200_000,
        fees_revenue=50_000,
        other_revenue=0,
        instruction_cost=400_000,
        departmental_cost=100_000,
    )
    base.update(kw)
    return ProgramInputs(**base)


def test_revenue_and_margin_math():
    p = _program()
    fin = compute_program_financials(p, allocated_overhead=150_000)
    # gross tuition = 1000 SCH * $1000 = 1,000,000
    assert fin.gross_tuition_revenue == 1_000_000
    assert fin.net_tuition_revenue == 800_000          # − 200k aid
    assert fin.total_revenue == 850_000                # + 50k fees
    assert fin.direct_cost == 500_000                  # 400k + 100k
    assert fin.contribution_margin == 350_000          # 850k − 500k
    assert fin.total_cost == 650_000                   # 500k + 150k overhead
    assert fin.net_margin == 200_000                   # 850k − 650k


def test_per_unit_metrics():
    p = _program()
    fin = compute_program_financials(p, allocated_overhead=150_000)
    assert fin.revenue_per_student == 8_500.0          # 850k / 100
    assert fin.cost_per_student == 6_500.0             # 650k / 100
    assert fin.cost_per_credit_hour == 650.0           # 650k / 1000
    assert fin.cost_per_completion == 32_500.0         # 650k / 20


def test_gross_override_takes_precedence():
    p = _program(gross_tuition_revenue=2_000_000)
    fin = compute_program_financials(p, allocated_overhead=0)
    assert fin.gross_tuition_revenue == 2_000_000      # SCH*rate ignored


def test_zero_enrollment_does_not_divide_by_zero():
    p = _program(enrolled_majors=0, completions=0)
    fin = compute_program_financials(p, allocated_overhead=0)
    assert fin.revenue_per_student == 0.0
    assert fin.cost_per_student == 0.0
    assert fin.cost_per_completion == 0.0


def test_portfolio_totals_reconcile():
    progs = [_program(program_code="A"), _program(program_code="B")]
    inst = InstitutionInputs(fiscal_year=2025, university_operations_cost=300_000)
    results = compute_portfolio(progs, inst, "credit_hours")
    totals = portfolio_totals(results)
    # overhead fully allocated across the portfolio
    assert totals["allocated_overhead"] == 300_000
    assert totals["total_revenue"] == sum(r.total_revenue for r in results)
    assert totals["net_margin"] == round(
        totals["total_revenue"] - totals["total_cost"], 2
    )
