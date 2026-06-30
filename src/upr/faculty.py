"""Faculty payroll: build program instruction cost from real compensation.

Instead of trusting a single GL lump for ``instruction_cost``, load per-faculty
payroll (salary + benefits, appointment, FTE) and roll it up to each program.
That makes instruction cost auditable and unlocks faculty metrics — headcount,
FTE, cost per FTE, benefits load, and adjunct mix.

Data shape (one row per **faculty-program assignment**, so joint appointments
are just multiple rows for the same ``faculty_id`` with an ``effort`` split):

    faculty_id, name, program_code, appointment, fte, base_salary, benefits, effort

Source: a NetSuite SuitePeople / HR-payroll export, or any payroll spreadsheet.
Headers are matched leniently, like the program importer.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from upr.importing import (
    ImportError_,
    _coerce_number,
    _normalize_header,
    _read_dataframe,
)
from upr.models import ProgramInputs

# SuiteQL template for pulling payroll from NetSuite SuitePeople (paychecks by
# employee + department). Tune to the payroll item / department setup; this is
# the contract the importer expects once the live path is wired.
SUITEQL_FACULTY_PAYROLL = """
SELECT  e.entityid                AS faculty_id,
        e.firstname || ' ' || e.lastname AS name,
        d.name                    AS program_code,
        e.employeestatus          AS appointment,
        e.fulltimeequivalent      AS fte,
        SUM(pl.basesalary)        AS base_salary,
        SUM(pl.benefits)          AS benefits
FROM    paycheckline pl
JOIN    employee e   ON e.id = pl.employee
JOIN    department d  ON d.id = e.department
WHERE   pl.fiscalyear = ?
GROUP BY e.entityid, e.firstname, e.lastname, d.name,
         e.employeestatus, e.fulltimeequivalent
""".strip()

_FIELDS = {
    "faculty_id", "name", "program_code", "appointment", "fte",
    "base_salary", "benefits", "effort",
}
_ALIASES: dict[str, set[str]] = {
    "faculty_id": {"id", "employee_id", "emplid", "faculty", "instructor_id"},
    "name": {"faculty_name", "employee_name", "instructor", "employee"},
    "program_code": {"major_code", "program", "department_code", "dept", "department"},
    "appointment": {"appointment_type", "type", "status", "employment_type"},
    "fte": {"appointment_fte", "load_fte"},
    "base_salary": {"salary", "base_pay", "annual_salary", "base", "wages"},
    "benefits": {"fringe", "benefit_cost", "fringe_benefits"},
    "effort": {"allocation", "pct_effort", "effort_pct", "load"},
}
_NUMERIC = {"fte", "base_salary", "benefits", "effort"}
_ADJUNCT_TERMS = {"adjunct", "part-time", "part time", "parttime", "contingent"}


class FacultyPayroll(BaseModel):
    """One faculty member's assignment to a program (salary is the full salary;
    ``effort`` splits it across programs for joint appointments)."""

    faculty_id: str
    name: str = ""
    program_code: str
    appointment: str = "Full-time"
    fte: float = Field(1.0, ge=0)
    base_salary: float = Field(0.0, ge=0)
    benefits: float = Field(0.0, ge=0)
    effort: float = Field(1.0, ge=0, le=1)  # share of this person to the program

    @property
    def total_compensation(self) -> float:
        return round(self.base_salary + self.benefits, 2)

    @property
    def attributed_cost(self) -> float:
        return round((self.base_salary + self.benefits) * self.effort, 2)

    @property
    def attributed_fte(self) -> float:
        return round(self.fte * self.effort, 4)

    @property
    def is_adjunct(self) -> bool:
        return self.appointment.strip().lower() in _ADJUNCT_TERMS


class FacultyRollup(BaseModel):
    """Program-level faculty summary derived from payroll."""

    program_code: str
    faculty_headcount: int
    adjunct_headcount: int
    faculty_fte: float
    instruction_cost: float
    total_salary: float
    total_benefits: float
    benefits_rate: float
    cost_per_fte: float
    avg_compensation: float


def _build_header_map() -> dict[str, str]:
    mapping = {f: f for f in _FIELDS}
    for field, aliases in _ALIASES.items():
        for alias in aliases:
            mapping[_normalize_header(alias)] = field
    return mapping


_HEADER_MAP = _build_header_map()


def map_faculty_records(records: list[dict]) -> list[FacultyPayroll]:
    """Map parsed dict rows (CSV/Excel/API) into FacultyPayroll records."""
    rows: list[FacultyPayroll] = []
    saw_id = False
    for i, raw in enumerate(records):
        record: dict = {}
        for key, value in raw.items():
            field = _HEADER_MAP.get(_normalize_header(key))
            if not field:
                continue
            if field == "faculty_id":
                saw_id = True
            if field in _NUMERIC:
                val = _coerce_number(value, as_int=False)
                if field == "effort" and val is not None and val > 1:
                    val = val / 100.0  # accept "50" or "50%" as 0.5
            else:
                val = None if value is None else str(value).strip()
            if val is not None and val != "":
                record[field] = val
        if not record.get("faculty_id") or not record.get("program_code"):
            continue
        try:
            rows.append(FacultyPayroll(**record))
        except Exception as exc:  # noqa: BLE001
            raise ImportError_(f"Faculty row {i + 2}: {exc}") from exc
    if not saw_id:
        raise ImportError_("Required 'faculty_id' column not found.")
    if not rows:
        raise ImportError_("No valid faculty rows found.")
    return rows


def read_faculty(source_obj, *, filename: str | None = None) -> list[FacultyPayroll]:
    """Parse a faculty payroll CSV/Excel file into FacultyPayroll records."""
    df = _read_dataframe(source_obj, filename)
    if df.empty:
        raise ImportError_("File contains no rows.")
    return map_faculty_records(df.to_dict("records"))


def aggregate_faculty(payroll: list[FacultyPayroll]) -> list[FacultyRollup]:
    """Roll faculty payroll up to one summary per program."""
    by_program: dict[str, dict] = {}
    for f in payroll:
        b = by_program.setdefault(
            f.program_code,
            {"ids": set(), "adjuncts": set(), "fte": 0.0,
             "salary": 0.0, "benefits": 0.0},
        )
        b["ids"].add(f.faculty_id)
        if f.is_adjunct:
            b["adjuncts"].add(f.faculty_id)
        b["fte"] += f.attributed_fte
        b["salary"] += f.base_salary * f.effort
        b["benefits"] += f.benefits * f.effort

    rollups: list[FacultyRollup] = []
    for code, b in sorted(by_program.items()):
        cost = b["salary"] + b["benefits"]
        headcount = len(b["ids"])
        fte = b["fte"]
        rollups.append(FacultyRollup(
            program_code=code,
            faculty_headcount=headcount,
            adjunct_headcount=len(b["adjuncts"]),
            faculty_fte=round(fte, 2),
            instruction_cost=round(cost, 2),
            total_salary=round(b["salary"], 2),
            total_benefits=round(b["benefits"], 2),
            benefits_rate=round(b["benefits"] / b["salary"], 4) if b["salary"] else 0.0,
            cost_per_fte=round(cost / fte, 2) if fte else 0.0,
            avg_compensation=round(cost / headcount, 2) if headcount else 0.0,
        ))
    return rollups


def apply_faculty_to_inputs(
    inputs: list[ProgramInputs], payroll: list[FacultyPayroll]
) -> list[ProgramInputs]:
    """Override each program's instruction_cost and faculty_fte from payroll.

    Programs without payroll rows are left untouched.
    """
    rollups = {r.program_code: r for r in aggregate_faculty(payroll)}
    out: list[ProgramInputs] = []
    for p in inputs:
        r = rollups.get(p.program_code)
        if r is None:
            out.append(p)
            continue
        data = p.model_dump()
        data["instruction_cost"] = r.instruction_cost
        data["faculty_fte"] = r.faculty_fte
        out.append(ProgramInputs(**data))
    return out


def rollup_frame(rollups: list[FacultyRollup]):
    """Build a DataFrame from rollups (lazy pandas import to keep this light)."""
    import pandas as pd

    return pd.DataFrame([r.model_dump() for r in rollups])


def faculty_frame(payroll: list[FacultyPayroll]):
    import pandas as pd

    return pd.DataFrame([
        {
            "faculty_id": f.faculty_id, "name": f.name,
            "program_code": f.program_code, "appointment": f.appointment,
            "fte": f.fte, "effort": f.effort, "base_salary": f.base_salary,
            "benefits": f.benefits, "total_compensation": f.total_compensation,
            "attributed_cost": f.attributed_cost,
        }
        for f in payroll
    ])


def faculty_template_csv() -> str:
    ordered = ["faculty_id", "name", "program_code", "appointment", "fte",
               "base_salary", "benefits", "effort"]
    return ",".join(ordered) + "\n"
