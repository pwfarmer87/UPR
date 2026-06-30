"""Next-year enrollment & margin forecast from the Slate admissions pipeline.

Combines current-year actuals (enrollment, completions, per-student economics)
with the Slate funnel (applications -> admits -> deposits) to project next year,
and flags programs whose economics and pipeline point in opposite directions.

Model (transparent and adjustable via ``ForecastAssumptions``):

    projected_new      = deposits * (1 - melt_rate)
    continuing         = max(0, enrolled_majors - completions) * retention_rate
    projected_majors   = round(continuing + projected_new)
    projected_revenue  = projected_majors * revenue_per_student        (current)
    projected_contrib  = projected_majors * contribution_per_student   (current)

Watch flags:
    "Healthy but shrinking" — net margin > 0 yet projected enrollment falling
    "Improving"             — net margin < 0 yet projected enrollment rising
    "Stable"                — otherwise
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from upr.pipeline import ReviewResult

_SHRINK_THRESHOLD = -0.03  # >3% projected decline
_GROWTH_THRESHOLD = 0.03   # >3% projected growth


@dataclass(frozen=True)
class ForecastAssumptions:
    retention_rate: float = 0.82  # share of continuing (non-completing) majors kept
    melt_rate: float = 0.12       # share of deposits that don't enroll


def _safe_div(n: float, d: float) -> float:
    return n / d if d else 0.0


def _watch_flag(net_margin: float, pct_change: float) -> str:
    if net_margin > 0 and pct_change <= _SHRINK_THRESHOLD:
        return "Healthy but shrinking"
    if net_margin < 0 and pct_change >= _GROWTH_THRESHOLD:
        return "Improving"
    return "Stable"


def forecast_frame(
    result: ReviewResult,
    assumptions: ForecastAssumptions | None = None,
    retention_by_program: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Per-program next-year projection with watch flags.

    ``retention_by_program`` (e.g. from ``upr.retention``) overrides the flat
    assumption per program; programs not in the map use ``assumptions.retention_rate``.
    """
    a = assumptions or ForecastAssumptions()
    retention_by_program = retention_by_program or {}
    inputs_by_code = {p.program_code: p for p in result.inputs}
    rows = []
    for fin in result.financials:
        inp = inputs_by_code.get(fin.program_code)
        deposits = inp.deposits if inp else 0
        admits = inp.admits if inp else 0
        applications = inp.applications if inp else 0

        retention = retention_by_program.get(fin.program_code, a.retention_rate)
        contribution_per_student = _safe_div(
            fin.contribution_margin, fin.enrolled_majors
        )
        projected_new = deposits * (1 - a.melt_rate)
        continuing = max(0, fin.enrolled_majors - fin.completions) * retention
        projected_majors = round(continuing + projected_new)
        delta = projected_majors - fin.enrolled_majors
        pct_change = round(_safe_div(delta, fin.enrolled_majors), 4)

        rows.append({
            "program_code": fin.program_code,
            "program_name": fin.program_name,
            "college": fin.college,
            "enrolled_majors": fin.enrolled_majors,
            "applications": applications,
            "admits": admits,
            "deposits": deposits,
            "admit_rate": round(_safe_div(admits, applications), 4),
            "yield_rate": round(_safe_div(deposits, admits), 4),
            "retention_rate": round(retention, 4),
            "projected_majors": projected_majors,
            "projected_change": delta,
            "projected_pct_change": pct_change,
            "net_margin": fin.net_margin,
            "projected_revenue": round(projected_majors * fin.revenue_per_student, 2),
            "projected_contribution_margin": round(
                projected_majors * contribution_per_student, 2
            ),
            "watch_flag": _watch_flag(fin.net_margin, pct_change),
        })
    df = pd.DataFrame(rows)
    return df.sort_values("projected_pct_change")


def watch_list(
    result: ReviewResult,
    assumptions: ForecastAssumptions | None = None,
    retention_by_program: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Just the programs flagged for attention (not 'Stable')."""
    df = forecast_frame(result, assumptions, retention_by_program)
    return df[df["watch_flag"] != "Stable"].copy()


def forecast_totals(
    result: ReviewResult,
    assumptions: ForecastAssumptions | None = None,
    retention_by_program: dict[str, float] | None = None,
) -> dict:
    """Institution-level projection roll-up."""
    df = forecast_frame(result, assumptions, retention_by_program)
    current_majors = int(df["enrolled_majors"].sum())
    projected_majors = int(df["projected_majors"].sum())
    return {
        "current_majors": current_majors,
        "projected_majors": projected_majors,
        "projected_change": projected_majors - current_majors,
        "projected_pct_change": round(
            _safe_div(projected_majors - current_majors, current_majors), 4
        ),
        "projected_revenue": round(df["projected_revenue"].sum(), 2),
        "projected_contribution_margin": round(
            df["projected_contribution_margin"].sum(), 2
        ),
        "programs_shrinking": int((df["watch_flag"] == "Healthy but shrinking").sum()),
        "programs_improving": int((df["watch_flag"] == "Improving").sum()),
    }
