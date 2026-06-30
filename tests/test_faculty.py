import io

import pytest

from upr.config import Settings
from upr.faculty import (
    FacultyPayroll,
    aggregate_faculty,
    apply_faculty_to_inputs,
    map_faculty_records,
    read_faculty,
)
from upr.importing import ImportError_
from upr.models import ProgramInputs
from upr.pipeline import run_review
from upr.sample_data import sample_faculty, sample_programs


def _csv(text, name="faculty.csv"):
    buf = io.BytesIO(text.encode("utf-8"))
    buf.name = name
    return buf


def test_payroll_attribution_and_effort():
    f = FacultyPayroll(
        faculty_id="A1", program_code="CSCI", base_salary=100_000,
        benefits=28_000, fte=1.0, effort=0.5,
    )
    assert f.total_compensation == 128_000
    assert f.attributed_cost == 64_000
    assert f.attributed_fte == 0.5


def test_aggregate_rollup_math():
    payroll = [
        FacultyPayroll(faculty_id="A", program_code="CSCI",
                       base_salary=90_000, benefits=30_000, fte=1.0),
        FacultyPayroll(faculty_id="B", program_code="CSCI", appointment="Adjunct",
                       base_salary=20_000, benefits=2_000, fte=0.5),
    ]
    r = aggregate_faculty(payroll)[0]
    assert r.faculty_headcount == 2
    assert r.adjunct_headcount == 1
    assert r.faculty_fte == 1.5
    assert r.instruction_cost == 142_000        # 120k + 22k
    assert r.total_salary == 110_000
    assert r.cost_per_fte == round(142_000 / 1.5, 2)


def test_joint_appointment_splits_by_effort():
    payroll = [
        FacultyPayroll(faculty_id="A", program_code="CSCI",
                       base_salary=100_000, benefits=0, fte=1.0, effort=0.6),
        FacultyPayroll(faculty_id="A", program_code="MATH",
                       base_salary=100_000, benefits=0, fte=1.0, effort=0.4),
    ]
    rollups = {r.program_code: r for r in aggregate_faculty(payroll)}
    assert rollups["CSCI"].instruction_cost == 60_000
    assert rollups["MATH"].instruction_cost == 40_000
    assert rollups["CSCI"].faculty_fte == 0.6


def test_apply_overrides_instruction_cost_and_fte():
    inputs = [ProgramInputs(program_code="CSCI", program_name="CS", college="A&S",
                            instruction_cost=999, faculty_fte=1.0)]
    payroll = [FacultyPayroll(faculty_id="A", program_code="CSCI",
                              base_salary=80_000, benefits=20_000, fte=2.0)]
    out = apply_faculty_to_inputs(inputs, payroll)
    assert out[0].instruction_cost == 100_000
    assert out[0].faculty_fte == 2.0


def test_import_maps_aliases_and_percent_effort():
    csv = (
        "Employee ID,Instructor,Major Code,Type,FTE,Salary,Fringe,Effort\n"
        "E1,Jane Doe,CSCI,Adjunct,0.5,\"$60,000\",\"$12,000\",50%\n"
    )
    rows = read_faculty(_csv(csv))
    assert len(rows) == 1
    f = rows[0]
    assert f.faculty_id == "E1"
    assert f.program_code == "CSCI"
    assert f.is_adjunct
    assert f.base_salary == 60_000
    assert f.effort == 0.5  # "50%" -> 0.5


def test_import_requires_faculty_id():
    with pytest.raises(ImportError_):
        map_faculty_records([{"program_code": "CSCI", "salary": 1}])


def test_sample_faculty_reconciles_to_program_instruction_cost():
    progs = {p.program_code: p for p in sample_programs(2025)}
    rollups = {r.program_code: r for r in aggregate_faculty(sample_faculty(2025))}
    # payroll roll-up should be within a few percent of the GL instruction cost
    for code, p in progs.items():
        r = rollups[code]
        if p.instruction_cost > 0:
            assert abs(r.instruction_cost - p.instruction_cost) / p.instruction_cost < 0.15


def test_pipeline_with_faculty_file(tmp_path):
    # write the sample faculty to a CSV and feed it through the pipeline
    from upr.faculty import faculty_frame

    path = tmp_path / "faculty.csv"
    faculty_frame(sample_faculty(2025)).to_csv(path, index=False)
    settings = Settings(data_source="mock", fiscal_year=2025, faculty_file=str(path))
    result = run_review(settings)
    assert "faculty" in result.sources_used
