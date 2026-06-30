import pandas as pd

from upr.adapters.cost import allocate_instruction_cost, load_department_costs
from upr.adapters.registrations import (
    load_registrations,
    sch_by_major,
    sch_by_major_department,
)


def _reg(sid, major, course):
    return {"StudentID": sid, "MAJOR_CDE": major, "course_code": course,
            "Credits": 3, "AcadYear": 2024}


def _regs() -> pd.DataFrame:
    # 2 BMTS students and 1 ENGL student; a BMTS student also takes ENGL (gen-ed)
    return load_registrations(pd.DataFrame([
        _reg(1, "BMTS", "BUSN 101"),
        _reg(1, "BMTS", "ENGL 100"),
        _reg(2, "BMTS", "BUSN 201"),
        _reg(3, "ENGL", "ENGL 200"),
    ]))


def test_sch_by_major_sums_credit_hours():
    s = dict(zip(*[sch_by_major(_regs(), 2024)[c] for c in
                   ["program_code", "student_credit_hours"]]))
    assert s["BMTS"] == 9   # 3+3+3
    assert s["ENGL"] == 3


def test_subject_derived_from_course_code():
    df = _regs()
    assert set(df["subject"]) == {"BUSN", "ENGL"}


def test_matrix_captures_cross_department_consumption():
    m = sch_by_major_department(_regs(), 2024)
    cell = m[(m["program_code"] == "BMTS") & (m["subject"] == "ENGL")]
    assert cell.iloc[0]["student_credit_hours"] == 3   # BMTS students took ENGL


def test_allocation_spreads_gened_across_consumers():
    # ENGL dept costs $90k; BMTS students took 3 of the 6 total ENGL credits.
    matrix = sch_by_major_department(_regs(), 2024)
    alloc = allocate_instruction_cost(matrix, {"BUSN": 60000, "ENGL": 90000})
    # ENGL total SCH = 3 (BMTS) + 3 (ENGL) = 6 -> each gets half = 45k
    # BUSN total SCH = 6, all BMTS -> 60k to BMTS
    assert round(alloc["BMTS"]) == 60000 + 45000
    assert round(alloc["ENGL"]) == 45000


def test_load_department_costs_reads_dict():
    costs = load_department_costs(pd.DataFrame(
        {"subject": ["ENGL", "BUSN"], "instruction_cost": [90000, 60000]}))
    assert costs == {"ENGL": 90000.0, "BUSN": 60000.0}


def test_registrations_requires_major_and_credits():
    import pytest

    from upr.importing import ImportError_
    with pytest.raises(ImportError_):
        load_registrations(pd.DataFrame({"foo": [1]}))
