"""Multi-year trend analysis.

Runs the review across several fiscal years and assembles year-over-year views:
a long tidy frame, per-program trajectories, institution totals by year, and a
first-vs-last summary with CAGR. Works with any data source (mock, file, live).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd

from upr.config import Settings
from upr.pipeline import ReviewResult, run_review

# Per-program metrics tracked over time.
_TREND_METRICS = [
    "enrolled_majors", "student_credit_hours", "completions",
    "total_revenue", "total_cost", "contribution_margin", "net_margin",
    "net_margin_ratio", "cost_per_student", "revenue_per_student",
]


@dataclass
class MultiYearReview:
    years: list[int]
    results: dict[int, ReviewResult]

    @property
    def latest(self) -> ReviewResult:
        return self.results[max(self.years)]


def run_multiyear(
    years: list[int], settings: Settings | None = None
) -> MultiYearReview:
    """Run the review for each fiscal year and collect the results."""
    base = settings or Settings.from_env()
    years = sorted(set(years))
    results = {y: run_review(replace(base, fiscal_year=y)) for y in years}
    return MultiYearReview(years=years, results=results)


def trend_frame(myr: MultiYearReview) -> pd.DataFrame:
    """Long tidy frame: one row per (program, year) with all trend metrics."""
    frames = []
    for year, result in myr.results.items():
        df = result.to_frame()[
            ["program_code", "program_name", "college", "degree_level", *_TREND_METRICS]
        ].copy()
        df.insert(0, "fiscal_year", year)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def institution_trend(myr: MultiYearReview) -> pd.DataFrame:
    """One row per fiscal year with institution-level totals."""
    rows = []
    for year in myr.years:
        t = myr.results[year].totals()
        rows.append({"fiscal_year": year, **t})
    return pd.DataFrame(rows)


def program_trajectory(myr: MultiYearReview, metric: str = "net_margin") -> pd.DataFrame:
    """Wide frame: program rows, fiscal-year columns, one metric."""
    if metric not in _TREND_METRICS:
        raise ValueError(f"Unknown trend metric {metric!r}; choose {_TREND_METRICS}")
    long = trend_frame(myr)
    wide = long.pivot_table(
        index=["program_code", "program_name"], columns="fiscal_year",
        values=metric, aggfunc="first",
    ).reset_index()
    wide.columns.name = None
    return wide


def _cagr(first: float, last: float, periods: int) -> float:
    if periods <= 0 or first <= 0 or last <= 0:
        return 0.0
    return round((last / first) ** (1 / periods) - 1, 4)


def yoy_summary(myr: MultiYearReview, metric: str = "net_margin") -> pd.DataFrame:
    """First-vs-last comparison per program: delta, % change, and CAGR."""
    first_y, last_y = min(myr.years), max(myr.years)
    traj = program_trajectory(myr, metric)
    if first_y not in traj.columns or last_y not in traj.columns:
        return traj
    out = traj[["program_code", "program_name", first_y, last_y]].copy()
    out = out.rename(columns={first_y: f"{metric}_{first_y}", last_y: f"{metric}_{last_y}"})
    first_col = out[f"{metric}_{first_y}"]
    last_col = out[f"{metric}_{last_y}"]
    out["change"] = (last_col - first_col).round(2)
    out["pct_change"] = (
        (last_col - first_col) / first_col.replace(0, pd.NA)
    ).fillna(0.0).round(4)
    periods = last_y - first_y
    out["cagr"] = [
        _cagr(first, last, periods) for first, last in zip(first_col, last_col)
    ]
    return out.sort_values("change")
