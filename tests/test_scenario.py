from upr.config import Settings
from upr.pipeline import run_review
from upr.scenario import (
    Scenario,
    apply_scenario,
    compare,
    compare_totals,
    run_scenario,
)


def _baseline():
    return run_review(Settings(data_source="mock", fiscal_year=2025))


def test_identity_scenario_changes_nothing():
    base = _baseline()
    scen = run_scenario(base, Scenario())
    assert Scenario().is_identity
    assert round(scen.totals()["net_margin"], 2) == round(
        base.totals()["net_margin"], 2
    )


def test_tuition_increase_raises_revenue_and_margin():
    base = _baseline()
    scen = run_scenario(base, Scenario(tuition_change_pct=0.10))
    assert scen.totals()["total_revenue"] > base.totals()["total_revenue"]
    assert scen.totals()["net_margin"] > base.totals()["net_margin"]


def test_enrollment_drop_scales_activity_down():
    base = _baseline()
    scen = run_scenario(base, Scenario(enrollment_change_pct=-0.10))
    assert scen.totals()["enrolled_majors"] < base.totals()["enrolled_majors"]
    assert scen.totals()["total_revenue"] < base.totals()["total_revenue"]


def test_target_discount_rate_sets_aid_ratio():
    base = _baseline()
    inputs = apply_scenario(base.inputs, Scenario(target_discount_rate=0.5))
    for p in inputs:
        gross = p.computed_gross_tuition
        if gross > 0:
            assert abs(p.institutional_aid / gross - 0.5) < 1e-6


def test_operations_increase_lowers_net_margin():
    base = _baseline()
    scen = run_scenario(base, Scenario(operations_cost_change_pct=0.20))
    assert scen.totals()["net_margin"] < base.totals()["net_margin"]
    # overhead grew but revenue did not
    assert scen.totals()["total_revenue"] == base.totals()["total_revenue"]


def test_compare_outputs_align():
    base = _baseline()
    scen = run_scenario(base, Scenario(tuition_change_pct=0.05))
    df = compare(base, scen)
    assert {"net_margin_delta", "revenue_delta"} <= set(df.columns)
    assert len(df) == len(base.financials)
    totals = compare_totals(base, scen)
    assert totals["net_margin_delta"] == round(
        totals["net_margin_scenario"] - totals["net_margin_base"], 2
    )
