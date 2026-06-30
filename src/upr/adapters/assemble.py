"""Assemble adapter outputs into UPR ProgramInputs for a fiscal year.

Revenue is authoritative for the financial model: each major becomes a program
with actual gross tuition, institutional aid (discounts), fees, and headcount.
Costs (instruction/departmental) come from NetSuite GL or faculty payroll, not
these academic exports, so they start at zero here.

SCH is keyed by course subject (department), not major, so it is only attached
when an explicit ``subject_to_program`` crosswalk maps subjects to programs;
otherwise programs carry headcount but no SCH (allocate overhead by headcount).
"""

from __future__ import annotations

import pandas as pd

from upr.adapters.course_enrollments import sch_by_subject
from upr.adapters.net_revenue import revenue_by_program
from upr.models import ProgramInputs

_IMPORT_COLUMNS = [
    "program_code", "program_name", "college", "enrolled_majors",
    "student_credit_hours", "gross_tuition_revenue", "institutional_aid",
    "fees_revenue",
]


def build_program_inputs(
    revenue_df: pd.DataFrame,
    year: int,
    *,
    course_df: pd.DataFrame | None = None,
    subject_to_program: dict[str, str] | None = None,
) -> list[ProgramInputs]:
    """Build ProgramInputs (by major) for ``year`` from adapter outputs."""
    rev = revenue_by_program(revenue_df, year)
    if rev.empty:
        return []

    sch_by_program: dict[str, float] = {}
    if course_df is not None and subject_to_program:
        sch = sch_by_subject(course_df, year)
        for _, r in sch.iterrows():
            prog = subject_to_program.get(str(r["subject"]))
            if prog:
                sch_by_program[prog] = sch_by_program.get(prog, 0.0) + float(
                    r["student_credit_hours"]
                )

    programs: list[ProgramInputs] = []
    for _, r in rev.iterrows():
        code = str(r["program_code"])
        programs.append(ProgramInputs(
            program_code=code,
            program_name=str(r.get("program_name") or code),
            college=str(r.get("college") or "Unassigned"),
            enrolled_majors=int(r.get("enrolled_majors") or 0),
            student_credit_hours=round(sch_by_program.get(code, 0.0), 1),
            gross_tuition_revenue=float(r.get("gross_tuition_revenue") or 0.0),
            institutional_aid=float(r.get("institutional_aid") or 0.0),
            fees_revenue=float(r.get("fees_revenue") or 0.0),
        ))
    return programs


def to_import_dataframe(programs: list[ProgramInputs]) -> pd.DataFrame:
    """Render ProgramInputs as a UPR import-template DataFrame."""
    rows = [{c: getattr(p, c) for c in _IMPORT_COLUMNS} for p in programs]
    return pd.DataFrame(rows, columns=_IMPORT_COLUMNS)
