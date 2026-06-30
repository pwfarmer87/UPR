"""Adapter for a student course-registrations export — the keystone for
accurate SCH-by-major.

One row per student-course registration, carrying the student's major. This is
the only source that links course activity (by subject/department) to the
student's program, so it yields:

  * ``sch_by_major``            — total credit hours each major's students take
  * ``sch_by_major_department`` — the major × department matrix used to allocate
    department instruction cost to majors by the SCH each actually consumes
    (correctly spreading gen-ed teaching across all majors)

Expected columns (matched leniently): a student id, the student's ``major_code``,
``credit_hours``, an academic year, and either a ``subject`` or a ``course_code``
to derive it from.
"""

from __future__ import annotations

import pandas as pd

from upr.importing import (
    ImportError_,
    _coerce_number,
    _normalize_header,
    _read_dataframe,
)

_COLS = {
    "student_id": ["student_id", "studentid", "id", "emplid", "student"],
    "program_code": ["major_code", "major_cde", "major", "program_code", "program"],
    "subject": ["subject", "subj", "course_subject"],
    "course_code": ["course_code", "course", "coursecode", "crse"],
    "credit_hours": ["credit_hours", "credits", "sch", "hours", "credit_hrs"],
    "fiscal_year": ["acad_year", "acadyear", "year", "term_year", "fiscal_year"],
}


def _resolve(columns, candidates):
    norm = {_normalize_header(c): c for c in columns}
    for cand in candidates:
        if _normalize_header(cand) in norm:
            return norm[_normalize_header(cand)]
    return None


def load_registrations(source, *, filename: str | None = None) -> pd.DataFrame:
    """Read a registrations export into a tidy frame.

    Columns: student_id, program_code, subject, fiscal_year, credit_hours.
    """
    df = source if isinstance(source, pd.DataFrame) else _read_dataframe(source, filename)
    cols = {canon: _resolve(df.columns, cand) for canon, cand in _COLS.items()}
    required = ["program_code", "credit_hours"]
    missing = [c for c in required if cols[c] is None]
    if missing:
        raise ImportError_(
            f"Registrations export missing required columns {missing}; "
            f"found {sorted(map(str, df.columns))[:12]}…"
        )

    out = pd.DataFrame()
    out["program_code"] = df[cols["program_code"]].astype(str).str.strip()
    out["credit_hours"] = df[cols["credit_hours"]].map(
        lambda v: _coerce_number(v, as_int=False) or 0.0
    )
    out["student_id"] = (
        df[cols["student_id"]].astype(str) if cols["student_id"] else ""
    )
    if cols["subject"]:
        out["subject"] = df[cols["subject"]].astype(str).str.strip()
    elif cols["course_code"]:
        out["subject"] = (
            df[cols["course_code"]].astype(str).str.strip().str.split().str[0]
        )
    else:
        out["subject"] = ""
    out["fiscal_year"] = (
        pd.to_numeric(df[cols["fiscal_year"]], errors="coerce").astype("Int64")
        if cols["fiscal_year"] else pd.NA
    )
    out = out[out["program_code"].str.len() > 0]
    if out.empty:
        raise ImportError_("No valid registration rows found.")
    return out


def sch_by_major(df: pd.DataFrame, year: int | None = None) -> pd.DataFrame:
    """Total credit hours taken by each major's students."""
    if year is not None and df["fiscal_year"].notna().any():
        df = df[df["fiscal_year"] == year]
    grouped = (
        df.groupby("program_code", as_index=False)["credit_hours"].sum()
        .rename(columns={"credit_hours": "student_credit_hours"})
    )
    grouped["student_credit_hours"] = grouped["student_credit_hours"].round(1)
    return grouped.sort_values("student_credit_hours", ascending=False, ignore_index=True)


def sch_by_major_department(df: pd.DataFrame, year: int | None = None) -> pd.DataFrame:
    """Credit hours each major's students consume from each subject (department)."""
    if year is not None and df["fiscal_year"].notna().any():
        df = df[df["fiscal_year"] == year]
    grouped = (
        df.groupby(["program_code", "subject"], as_index=False)["credit_hours"].sum()
        .rename(columns={"credit_hours": "student_credit_hours"})
    )
    grouped["student_credit_hours"] = grouped["student_credit_hours"].round(1)
    return grouped
