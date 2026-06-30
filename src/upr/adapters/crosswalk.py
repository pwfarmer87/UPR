"""Build a course-subject → program (major code) crosswalk.

Reviewing by program means SCH and faculty load (keyed by course subject) must be
attributed to major codes. There's no authoritative subject→major link in the
exports, so this scaffolds one: it auto-seeds subjects whose code exactly matches
a major code and leaves the rest blank (largest-SCH first) for a human to fill.

Workflow:
    python -m upr crosswalk --net-revenue R.xlsx --course-enrollments C.xlsx \
                            --year 2024 --out crosswalk.csv
    # fill in program_code for the remaining subjects, then:
    python -m upr ingest --net-revenue R.xlsx --course-enrollments C.xlsx \
                         --subject-map crosswalk.csv --year 2024 --out programs.csv
"""

from __future__ import annotations

import pandas as pd

from upr.adapters.course_enrollments import sch_by_subject
from upr.adapters.net_revenue import revenue_by_program

# Crosswalk columns: subject first, program_code second (so positional readers
# and named readers both work), then SCH to prioritize the biggest subjects.
CROSSWALK_COLUMNS = ["subject", "program_code", "student_credit_hours", "seeded"]


def auto_seed(subjects: set[str], major_codes: set[str]) -> dict[str, str]:
    """Map subjects whose code exactly matches a major code."""
    return {s: s for s in subjects if s in major_codes}


def build_crosswalk_template(
    course_df: pd.DataFrame, revenue_df: pd.DataFrame, year: int
) -> pd.DataFrame:
    """Scaffold a subject→program_code crosswalk for ``year``."""
    sch = sch_by_subject(course_df, year)
    rev = revenue_by_program(revenue_df, year)
    major_codes = set(rev["program_code"].astype(str)) if not rev.empty else set()

    subjects = sch["subject"].astype(str).tolist() if not sch.empty else []
    seeds = auto_seed(set(subjects), major_codes)
    sch_map = dict(zip(sch["subject"].astype(str), sch["student_credit_hours"])) \
        if not sch.empty else {}

    rows = [
        {
            "subject": s,
            "program_code": seeds.get(s, ""),
            "student_credit_hours": sch_map.get(s, 0.0),
            "seeded": "exact" if s in seeds else "",
        }
        for s in subjects
    ]
    df = pd.DataFrame(rows, columns=CROSSWALK_COLUMNS)
    # unmapped, biggest SCH first — that's what to fill in first
    return df.sort_values(
        ["program_code", "student_credit_hours"],
        ascending=[True, False], ignore_index=True,
    )


def majors_reference(revenue_df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Reference list of valid program codes (majors) to map subjects to."""
    rev = revenue_by_program(revenue_df, year)
    if rev.empty:
        return pd.DataFrame(columns=["program_code", "program_name", "college"])
    cols = [c for c in ("program_code", "program_name", "college") if c in rev.columns]
    return rev[cols].sort_values("program_code", ignore_index=True)


def load_subject_map(source) -> dict[str, str]:
    """Read a crosswalk CSV into {subject: program_code}, ignoring blanks.

    Accepts named columns ('subject', 'program_code') or the first two columns.
    """
    df = source if isinstance(source, pd.DataFrame) else pd.read_csv(source)
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "subject" in df.columns and "program_code" in df.columns:
        subj, prog = df["subject"].tolist(), df["program_code"].tolist()
    else:
        subj, prog = df.iloc[:, 0].tolist(), df.iloc[:, 1].tolist()
    mapping = {}
    for s, p in zip(subj, prog):
        s, p = str(s).strip(), str(p).strip()
        if s and p and s.lower() != "nan" and p.lower() != "nan":
            mapping[s] = p
    return mapping
