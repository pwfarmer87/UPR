"""Scenario modeling: what-if adjustments on top of a baseline review.

Apply global levers — tuition rate, enrollment, discount/aid, costs, and the
operations pool — to the baseline inputs, recompute, and compare. Used by the
dashboard's Scenario tab (live sliders) and available programmatically.

Assumptions (documented so they're easy to revisit):
  * Enrollment changes scale activity that moves with students — credit hours,
    completions, aid, fees, other revenue, and the admissions funnel.
  * Tuition changes scale the per-credit-hour rate (and any actual gross-tuition
    figure from NetSuite).
  * Cost levers are independent of enrollment (faculty/department costs are
    sticky in the short run) — that's the point of modeling them separately.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from upr.config import Settings
from upr.models import ProgramInputs
from upr.pipeline import ReviewResult, compute_review


@dataclass(frozen=True)
class Scenario:
    tuition_change_pct: float = 0.0
    enrollment_change_pct: float = 0.0
    aid_change_pct: float = 0.0
    target_discount_rate: float | None = None  # overrides aid_change if set
    fees_change_pct: float = 0.0
    instruction_cost_change_pct: float = 0.0
    departmental_cost_change_pct: float = 0.0
    operations_cost_change_pct: float = 0.0

    @property
    def is_identity(self) -> bool:
        return self.target_discount_rate is None and not any([
            self.tuition_change_pct, self.enrollment_change_pct,
            self.aid_change_pct, self.fees_change_pct,
            self.instruction_cost_change_pct, self.departmental_cost_change_pct,
            self.operations_cost_change_pct,
        ])


def apply_scenario_to_program(p: ProgramInputs, s: Scenario) -> ProgramInputs:
    """Return a new ProgramInputs with the scenario levers applied."""
    t = 1 + s.tuition_change_pct
    e = 1 + s.enrollment_change_pct

    rate = p.tuition_rate_per_credit_hour * t
    sch = p.student_credit_hours * e

    gross = p.gross_tuition_revenue
    if gross is not None:
        gross = gross * t * e
        gross_for_aid = gross
    else:
        gross_for_aid = sch * rate

    if s.target_discount_rate is not None:
        aid = gross_for_aid * s.target_discount_rate
    else:
        aid = p.institutional_aid * e * (1 + s.aid_change_pct)

    data = p.model_dump()
    data.update(
        tuition_rate_per_credit_hour=round(rate, 4),
        student_credit_hours=round(sch, 2),
        enrolled_majors=max(0, round(p.enrolled_majors * e)),
        completions=max(0, round(p.completions * e)),
        gross_tuition_revenue=None if gross is None else round(gross, 2),
        institutional_aid=round(max(0.0, aid), 2),
        fees_revenue=round(p.fees_revenue * e * (1 + s.fees_change_pct), 2),
        other_revenue=round(p.other_revenue * e, 2),
        instruction_cost=round(
            p.instruction_cost * (1 + s.instruction_cost_change_pct), 2
        ),
        departmental_cost=round(
            p.departmental_cost * (1 + s.departmental_cost_change_pct), 2
        ),
        applications=max(0, round(p.applications * e)),
        admits=max(0, round(p.admits * e)),
        deposits=max(0, round(p.deposits * e)),
    )
    return ProgramInputs(**data)


def apply_scenario(
    inputs: list[ProgramInputs], s: Scenario
) -> list[ProgramInputs]:
    return [apply_scenario_to_program(p, s) for p in inputs]


def run_scenario(
    baseline: ReviewResult, scenario: Scenario, settings: Settings | None = None
) -> ReviewResult:
    """Recompute the portfolio under ``scenario`` from a baseline review."""
    inputs = apply_scenario(baseline.inputs, scenario)
    institution = baseline.institution.model_copy(
        update={
            "university_operations_cost": round(
                baseline.institution.university_operations_cost
                * (1 + scenario.operations_cost_change_pct),
                2,
            )
        }
    )
    s = settings or Settings()
    s.allocation_driver = baseline.allocation_driver
    s.fiscal_year = baseline.fiscal_year
    return compute_review(
        inputs, institution, s, sources_used=[*baseline.sources_used, "scenario"]
    )


def compare(baseline: ReviewResult, scenario_result: ReviewResult) -> pd.DataFrame:
    """Per-program baseline vs scenario with net-margin and revenue deltas."""
    base = baseline.to_frame()[
        ["program_code", "program_name", "college", "total_revenue",
         "net_margin", "enrolled_majors"]
    ].rename(columns={
        "total_revenue": "revenue_base", "net_margin": "net_margin_base",
        "enrolled_majors": "majors_base",
    })
    scen = scenario_result.to_frame()[
        ["program_code", "total_revenue", "net_margin", "enrolled_majors"]
    ].rename(columns={
        "total_revenue": "revenue_scenario", "net_margin": "net_margin_scenario",
        "enrolled_majors": "majors_scenario",
    })
    df = base.merge(scen, on="program_code", how="outer")
    df["net_margin_delta"] = (
        df["net_margin_scenario"] - df["net_margin_base"]
    ).round(2)
    df["revenue_delta"] = (df["revenue_scenario"] - df["revenue_base"]).round(2)
    return df.sort_values("net_margin_delta")


def compare_totals(
    baseline: ReviewResult, scenario_result: ReviewResult
) -> dict:
    """Institution-level baseline vs scenario deltas."""
    b, s = baseline.totals(), scenario_result.totals()
    return {
        "revenue_base": b["total_revenue"],
        "revenue_scenario": s["total_revenue"],
        "revenue_delta": round(s["total_revenue"] - b["total_revenue"], 2),
        "net_margin_base": b["net_margin"],
        "net_margin_scenario": s["net_margin"],
        "net_margin_delta": round(s["net_margin"] - b["net_margin"], 2),
        "net_margin_ratio_base": b["net_margin_ratio"],
        "net_margin_ratio_scenario": s["net_margin_ratio"],
        "majors_base": b["enrolled_majors"],
        "majors_scenario": s["enrolled_majors"],
    }
