import pandas as pd

from upr.adapters import load_course_enrollments, load_net_revenue, revenue_by_program
from upr.adapters.crosswalk import (
    auto_seed,
    build_crosswalk_template,
    load_subject_map,
    majors_reference,
)


def _revenue():
    return load_net_revenue(pd.DataFrame([
        {"StudentID": 1, "AcadYear": 2024, "MAJOR_CDE": "BIOL",
         "MAJOR_1": "BIOL - Biology", "MajorSchool": "Arts & Sciences",
         "AY_REVENUE": 20000, "TDiscounts": 8000, "AY_FEES": 500},
        {"StudentID": 2, "AcadYear": 2024, "MAJOR_CDE": "BMTS",
         "MAJOR_1": "BMTS - Business Management", "MajorSchool": "Business",
         "AY_REVENUE": 18000, "TDiscounts": 6000, "AY_FEES": 400},
        # two different codes sharing a cleaned name -> must be disambiguated
        {"StudentID": 3, "AcadYear": 2024, "MAJOR_CDE": "EELM",
         "MAJOR_1": "EELM - Education", "MajorSchool": "Education",
         "AY_REVENUE": 15000, "TDiscounts": 5000, "AY_FEES": 300},
        {"StudentID": 4, "AcadYear": 2024, "MAJOR_CDE": "EMAE",
         "MAJOR_1": "EMAE - Education", "MajorSchool": "Education",
         "AY_REVENUE": 15000, "TDiscounts": 5000, "AY_FEES": 300},
    ]))


def _courses():
    return load_course_enrollments(pd.DataFrame([
        ["AcadYear", 2024, "Total"],
        ["CourseCode", "CreditHours", "CreditHours"],
        ["BIOL 110  01", 120, 120],   # exact match to BIOL major
        ["BUSN 101  01", 200, 200],   # no exact major match -> blank
        ["EDUC 282  01", 90, 90],     # no exact major match -> blank
    ]))


def test_duplicate_major_names_are_disambiguated_by_code():
    rev = revenue_by_program(_revenue(), 2024)
    names = dict(zip(rev["program_code"], rev["program_name"]))
    assert names["EELM"] == "Education (EELM)"
    assert names["EMAE"] == "Education (EMAE)"
    assert names["BIOL"] == "Biology"  # unique name untouched


def test_auto_seed_matches_subject_to_same_major_code():
    assert auto_seed({"BIOL", "BUSN"}, {"BIOL", "BMTS"}) == {"BIOL": "BIOL"}


def test_crosswalk_template_seeds_exact_and_blanks_rest():
    cw = build_crosswalk_template(_courses(), _revenue(), 2024)
    by_subj = {r["subject"]: r for _, r in cw.iterrows()}
    assert by_subj["BIOL"]["program_code"] == "BIOL"
    assert by_subj["BIOL"]["seeded"] == "exact"
    assert by_subj["BUSN"]["program_code"] == ""
    assert by_subj["EDUC"]["program_code"] == ""
    # SCH carried through for prioritization
    assert by_subj["BUSN"]["student_credit_hours"] == 200


def test_majors_reference_lists_valid_codes():
    ref = majors_reference(_revenue(), 2024)
    assert set(ref["program_code"]) == {"BIOL", "BMTS", "EELM", "EMAE"}


def test_load_subject_map_named_and_positional_and_blanks():
    named = pd.DataFrame({"subject": ["BUSN", "EDUC", "X"],
                          "program_code": ["BMTS", "EELM", ""]})
    assert load_subject_map(named) == {"BUSN": "BMTS", "EDUC": "EELM"}
    # extra columns / order-independent by name
    extra = pd.DataFrame({"subject": ["BIOL"], "student_credit_hours": [10],
                          "program_code": ["BIOL"]})
    assert load_subject_map(extra) == {"BIOL": "BIOL"}
