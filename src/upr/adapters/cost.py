"""Allocate department instruction cost to majors by SCH consumed.

The rigorous program-cost step. Given:
  * department (subject) instruction cost in dollars — from the NetSuite GL by
    department, or faculty payroll aggregated by department, and
  * the major × department SCH matrix (from registrations),
each department's cost is spread across majors in proportion to the credit hours
that major's students actually take from it. This correctly distributes
general-education / service teaching (English, Math, University core) across
every major that consumes it, instead of dumping it on the host department's own
(often tiny) major.

    cost_to_major(dept) = dept_cost * sch[major, dept] / total_sch[dept]
    instruction_cost[major] = sum over departments
"""

from __future__ import annotations

import pandas as pd

from upr.importing import _coerce_number, _normalize_header, _read_dataframe


def load_department_costs(source, *, filename: str | None = None) -> dict[str, float]:
    """Read a department/subject → instruction-cost CSV/Excel into a dict.

    Accepts headers like ``department``/``subject`` and
    ``instruction_cost``/``cost``/``amount``.
    """
    df = source if isinstance(source, pd.DataFrame) else _read_dataframe(source, filename)
    norm = {_normalize_header(c): c for c in df.columns}

    def pick(cands):
        for c in cands:
            if _normalize_header(c) in norm:
                return norm[_normalize_header(c)]
        return None

    key = pick(["department", "subject", "subj", "dept", "field_of_study"])
    val = pick(["instruction_cost", "cost", "amount", "instructional_cost", "salary"])
    if key is None or val is None:
        raise ValueError(
            "Department-cost file needs a department/subject column and a "
            "cost column."
        )
    out: dict[str, float] = {}
    for k, v in zip(df[key], df[val]):
        k = str(k).strip()
        amount = _coerce_number(v, as_int=False)
        if k and amount is not None:
            out[k] = out.get(k, 0.0) + amount
    return out


def allocate_instruction_cost(
    sch_major_department: pd.DataFrame, department_costs: dict[str, float]
) -> dict[str, float]:
    """Return {program_code: instruction_cost} from the SCH matrix + dept costs."""
    if sch_major_department.empty:
        return {}
    dept_totals = (
        sch_major_department.groupby("subject")["student_credit_hours"].sum().to_dict()
    )
    allocation: dict[str, float] = {}
    for _, row in sch_major_department.iterrows():
        subject = str(row["subject"])
        dept_cost = department_costs.get(subject)
        total = dept_totals.get(subject, 0.0)
        if not dept_cost or total <= 0:
            continue
        share = row["student_credit_hours"] / total
        code = str(row["program_code"])
        allocation[code] = allocation.get(code, 0.0) + dept_cost * share
    return {k: round(v, 2) for k, v in allocation.items()}
