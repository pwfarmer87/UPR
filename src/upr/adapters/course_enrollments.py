"""Adapter for the "Course enrollments (last 4 years)" export.

Two-row header: the first row carries academic years, the second labels them
``CreditHours``. Each data row is a course section ``SUBJ NNN SEC`` with student
credit hours (SCH) per year. SCH is keyed by **course subject** (department),
which is a different unit from the student-major keying of the revenue export.
"""

from __future__ import annotations

import re

import pandas as pd

_YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def load_course_enrollments(source) -> pd.DataFrame:
    """Read the export into a tidy long frame.

    Columns: course_code, subject, course, section, fiscal_year, credit_hours.
    """
    raw = source if isinstance(source, pd.DataFrame) else pd.read_excel(source, header=None)
    if raw.shape[0] < 3:
        raise ValueError("Course enrollments export has too few rows.")

    header = raw.iloc[0].tolist()
    year_cols = {i: int(v) for i, v in enumerate(header)
                 if _YEAR_RE.match(str(v).strip().replace(".0", ""))}
    if not year_cols:
        raise ValueError("No academic-year columns found in the first header row.")

    code_col = 0  # first column is the CourseCode
    body = raw.iloc[2:].copy()
    records = []
    for _, row in body.iterrows():
        code = str(row[code_col]).strip()
        if not code or code.lower() == "nan":
            continue
        subject, course, section = _split_course_code(code)
        for ci, year in year_cols.items():
            ch = pd.to_numeric(row[ci], errors="coerce")
            if pd.isna(ch):
                continue
            records.append({
                "course_code": code, "subject": subject, "course": course,
                "section": section, "fiscal_year": year, "credit_hours": float(ch),
            })
    return pd.DataFrame.from_records(records)


def _split_course_code(code: str) -> tuple[str, str, str]:
    parts = code.split()
    subject = parts[0] if parts else code
    course = parts[1] if len(parts) > 1 else ""
    section = " ".join(parts[2:]) if len(parts) > 2 else ""
    return subject, course, section


def sch_by_subject(df: pd.DataFrame, year: int | None = None) -> pd.DataFrame:
    """Aggregate SCH and section counts per subject (optionally one year)."""
    if year is not None:
        df = df[df["fiscal_year"] == year]
    if df.empty:
        return pd.DataFrame()
    grouped = (
        df.groupby(["fiscal_year", "subject"])
        .agg(student_credit_hours=("credit_hours", "sum"),
             sections=("course_code", "nunique"))
        .reset_index()
    )
    grouped["student_credit_hours"] = grouped["student_credit_hours"].round(1)
    return grouped.sort_values("student_credit_hours", ascending=False, ignore_index=True)
