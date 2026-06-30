"""Estimate per-program retention from year-over-year enrollment.

The forecast otherwise leans on a single flat retention assumption for every
program, which hides real differences (a cohort-heavy professional program
retains very differently from a large service major). When two consecutive years
of data exist (multi-year sample, saved snapshots, or live history), we estimate
each program's retention directly.

Aggregate cohort-survival proxy (no student-level data needed), from year N-1 to
year N:

    prior_eligible = enrolled_{N-1} - completions_{N-1}    # could return
    new_students   = deposits_{N-1} * (1 - melt_rate)      # entered in year N
    retained       = enrolled_{N} - new_students
    retention_rate = retained / prior_eligible             # clamped to [0, 1]

This mirrors the forecast's own enrollment model, so an estimate fed back into
the forecast is internally consistent.
"""

from __future__ import annotations

from dataclasses import dataclass

from upr.pipeline import ReviewResult

_DEFAULT_MELT = 0.12


@dataclass
class RetentionEstimate:
    program_code: str
    program_name: str
    prior_enrolled: int
    prior_completions: int
    prior_eligible: float
    new_students: float
    retained: float
    retention_rate: float


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def estimate_retention(
    prev: ReviewResult, curr: ReviewResult, *, melt_rate: float = _DEFAULT_MELT
) -> list[RetentionEstimate]:
    """Estimate each program's retention from the prior to the current year."""
    prev_inputs = {p.program_code: p for p in prev.inputs}
    prev_fin = {f.program_code: f for f in prev.financials}
    estimates: list[RetentionEstimate] = []

    for fin in curr.financials:
        code = fin.program_code
        p_in = prev_inputs.get(code)
        p_fin = prev_fin.get(code)
        if p_in is None or p_fin is None:
            continue
        prior_eligible = max(0.0, p_fin.enrolled_majors - p_fin.completions)
        new_students = p_in.deposits * (1 - melt_rate)
        retained = max(0.0, fin.enrolled_majors - new_students)
        rate = _clamp01(retained / prior_eligible) if prior_eligible > 0 else 0.0
        estimates.append(RetentionEstimate(
            program_code=code,
            program_name=fin.program_name,
            prior_enrolled=p_fin.enrolled_majors,
            prior_completions=p_fin.completions,
            prior_eligible=round(prior_eligible, 2),
            new_students=round(new_students, 2),
            retained=round(retained, 2),
            retention_rate=round(rate, 4),
        ))
    return estimates


def estimate_from_multiyear(multiyear, *, melt_rate: float = _DEFAULT_MELT):
    """Estimate retention from the latest two years of a MultiYearReview."""
    years = sorted(multiyear.years)
    if len(years) < 2:
        return []
    prev, curr = multiyear.results[years[-2]], multiyear.results[years[-1]]
    return estimate_retention(prev, curr, melt_rate=melt_rate)


def retention_map(estimates: list[RetentionEstimate]) -> dict[str, float]:
    """{program_code: retention_rate} for feeding the forecast."""
    return {e.program_code: e.retention_rate for e in estimates}


def retention_frame(estimates: list[RetentionEstimate]):
    import pandas as pd

    return pd.DataFrame([e.__dict__ for e in estimates])
