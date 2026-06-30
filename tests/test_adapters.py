"""Adapter tests use synthetic fixtures that mirror the real export headers.

No real institutional data (which is student-level PII) is committed.
"""

import pandas as pd

from upr.adapters import (
    build_program_inputs,
    load_course_enrollments,
    load_net_revenue,
    revenue_by_program,
    sch_by_subject,
    to_import_dataframe,
)
from upr.adapters.faculty_load import faculty_subject_load
from upr.importing import read_programs


def _net_revenue_fixture() -> pd.DataFrame:
    # mirrors the real columns; two students in BMTS, one in BIOL, across a year
    return pd.DataFrame([
        {"StudentID": 1, "AcadYear": 2024, "MAJOR_CDE": "BMTS",
         "MAJOR_1": "BMTS - Business Management", "MajorSchool": "Business",
         "AY_REVENUE": 20000, "TDiscounts": 8000, "AY_NET_REVENUE": 12000, "AY_FEES": 500},
        {"StudentID": 1, "AcadYear": 2024, "MAJOR_CDE": "BMTS",
         "MAJOR_1": "BMTS - Business Management", "MajorSchool": "Business",
         "AY_REVENUE": 20000, "TDiscounts": 8000, "AY_NET_REVENUE": 12000, "AY_FEES": 500},
        {"StudentID": 2, "AcadYear": 2024, "MAJOR_CDE": "BMTS",
         "MAJOR_1": "BMTS - Business Management", "MajorSchool": "Business",
         "AY_REVENUE": 18000, "TDiscounts": 6000, "AY_NET_REVENUE": 12000, "AY_FEES": 400},
        {"StudentID": 3, "AcadYear": 2024, "MAJOR_CDE": "BIOL",
         "MAJOR_1": "BIOL - Biology", "MajorSchool": "Arts & Sciences",
         "AY_REVENUE": 22000, "TDiscounts": 9000, "AY_NET_REVENUE": 13000, "AY_FEES": 600},
        {"StudentID": 4, "AcadYear": 2023, "MAJOR_CDE": "BMTS",
         "MAJOR_1": "BMTS - Business Management", "MajorSchool": "Business",
         "AY_REVENUE": 19000, "TDiscounts": 7000, "AY_NET_REVENUE": 12000, "AY_FEES": 450},
    ])


def test_revenue_by_program_aggregates_by_major_and_year():
    tidy = load_net_revenue(_net_revenue_fixture())
    rev = revenue_by_program(tidy, 2024)
    bmts = rev[rev["program_code"] == "BMTS"].iloc[0]
    # gross sums all 3 BMTS-2024 rows; headcount = 2 distinct students
    assert bmts["gross_tuition_revenue"] == 58000
    assert bmts["institutional_aid"] == 22000
    assert bmts["enrolled_majors"] == 2
    assert bmts["program_name"] == "Business Management"   # code prefix stripped
    assert bmts["college"] == "Business"


def test_revenue_year_filter_excludes_other_years():
    tidy = load_net_revenue(_net_revenue_fixture())
    assert revenue_by_program(tidy, 2024)["program_code"].tolist().count("BMTS") == 1
    # 2023 has only the one BMTS student
    rev23 = revenue_by_program(tidy, 2023)
    assert rev23["enrolled_majors"].sum() == 1


def _course_fixture() -> pd.DataFrame:
    # raw, header=None shape: row0 years, row1 labels, then sections
    return pd.DataFrame([
        ["AcadYear", 2023, 2024, "Total"],
        ["CourseCode", "CreditHours", "CreditHours", "CreditHours"],
        ["BUSN 101  01", 90, 120, 210],
        ["BUSN 201  01", 60, 30, 90],
        ["BIOL 110  01", 45, 75, 120],
    ])


def test_course_enrollments_long_and_subject_rollup():
    df = load_course_enrollments(_course_fixture())
    assert set(df["subject"]) == {"BUSN", "BIOL"}
    sch = sch_by_subject(df, 2024)
    busn = sch[sch["subject"] == "BUSN"].iloc[0]
    assert busn["student_credit_hours"] == 150   # 120 + 30
    assert busn["sections"] == 2


def test_build_program_inputs_with_sch_crosswalk():
    tidy = load_net_revenue(_net_revenue_fixture())
    course = load_course_enrollments(_course_fixture())
    programs = build_program_inputs(
        tidy, 2024, course_df=course,
        subject_to_program={"BUSN": "BMTS", "BIOL": "BIOL"},
    )
    by_code = {p.program_code: p for p in programs}
    assert by_code["BMTS"].gross_tuition_revenue == 58000
    assert by_code["BMTS"].student_credit_hours == 150   # BUSN SCH mapped to BMTS
    assert by_code["BIOL"].student_credit_hours == 75


def test_import_dataframe_roundtrips_through_importer():
    tidy = load_net_revenue(_net_revenue_fixture())
    programs = build_program_inputs(tidy, 2024)
    csv = to_import_dataframe(programs).to_csv(index=False).encode("utf-8")
    reloaded = read_programs(csv, filename="ingested.csv", source="all")
    assert {p.program_code for p in reloaded} == {"BMTS", "BIOL"}


def test_faculty_subject_load_counts_sections():
    text = "Contract Load:3.00BUSN 101  OLA1B1...EDUC 282  01SP...BUSN 201  02SP"
    fac = faculty_subject_load(text)
    busn = fac[fac["subject"] == "BUSN"].iloc[0]
    assert busn["sections"] == 2
    assert busn["distinct_courses"] == 2
