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
    "program_code", "program_name", "college", "department", "enrolled_majors",
    "student_credit_hours", "gross_tuition_revenue", "institutional_aid",
    "fees_revenue", "instruction_cost",
]


def build_program_inputs(
    revenue_df: pd.DataFrame,
    year: int,
    *,
    course_df: pd.DataFrame | None = None,
    subject_to_program: dict[str, str] | None = None,
    program_names: dict[str, str] | None = None,
    registrations_df: pd.DataFrame | None = None,
    department_costs: dict[str, float] | None = None,
) -> list[ProgramInputs]:
    """Build ProgramInputs (by major) for ``year`` from adapter outputs.

    ``program_names`` defaults to the bundled official roster (pass {} to
    disable). When ``registrations_df`` is given, SCH is the credit hours each
    major's students actually take (accurate) — preferred over the subject
    crosswalk. With ``department_costs`` too, instruction cost is allocated to
    majors by the SCH each consumes from each department.
    """
    from upr.adapters.programs import load_program_fields, load_program_names
    if program_names is None:
        program_names = load_program_names()
    program_fields = load_program_fields()
    rev = revenue_by_program(revenue_df, year, program_names)
    if rev.empty:
        return []

    sch_by_program: dict[str, float] = {}
    instruction_by_program: dict[str, float] = {}
    if registrations_df is not None:
        from upr.adapters.cost import allocate_instruction_cost
        from upr.adapters.registrations import (
            sch_by_major,
            sch_by_major_department,
        )
        sch_by_program = dict(zip(
            sch_by_major(registrations_df, year)["program_code"],
            sch_by_major(registrations_df, year)["student_credit_hours"],
        ))
        if department_costs:
            matrix = sch_by_major_department(registrations_df, year)
            instruction_by_program = allocate_instruction_cost(matrix, department_costs)
    elif course_df is not None and subject_to_program:
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
            department=program_fields.get(code, ""),
            enrolled_majors=int(r.get("enrolled_majors") or 0),
            student_credit_hours=round(sch_by_program.get(code, 0.0), 1),
            instruction_cost=round(instruction_by_program.get(code, 0.0), 2),
            gross_tuition_revenue=float(r.get("gross_tuition_revenue") or 0.0),
            institutional_aid=float(r.get("institutional_aid") or 0.0),
            fees_revenue=float(r.get("fees_revenue") or 0.0),
        ))
    return programs


def to_import_dataframe(programs: list[ProgramInputs]) -> pd.DataFrame:
    """Render ProgramInputs as a UPR import-template DataFrame."""
    rows = [{c: getattr(p, c) for c in _IMPORT_COLUMNS} for p in programs]
    return pd.DataFrame(rows, columns=_IMPORT_COLUMNS)
