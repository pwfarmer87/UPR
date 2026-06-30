import pandas as pd

from upr.adapters import load_program_names
from upr.adapters.assemble import build_program_inputs
from upr.adapters.programs import load_program_fields
from upr.config import Settings
from upr.importing import read_programs
from upr.pipeline import compute_review
from upr.reporting import by_department


def test_roster_has_field_of_study():
    fields = load_program_fields()
    assert fields["BMTS"] == "Business"
    assert fields["EELM"] == "Education"
    assert fields["PSYS"] == "Psychology"
    assert len(fields) >= 60
    # name roster still works alongside
    assert load_program_names()["BMTS"] == "Business Management"


def _revenue():
    from upr.adapters import load_net_revenue
    return load_net_revenue(pd.DataFrame([
        {"StudentID": 1, "AcadYear": 2024, "MAJOR_CDE": "BMTS",
         "MAJOR_1": "BMTS - x", "MajorSchool": "College of Business",
         "AY_REVENUE": 20000, "TDiscounts": 8000, "AY_FEES": 500},
        {"StudentID": 2, "AcadYear": 2024, "MAJOR_CDE": "MBAD",
         "MAJOR_1": "MBAD - y", "MajorSchool": "College of Business",
         "AY_REVENUE": 30000, "TDiscounts": 9000, "AY_FEES": 600},
        {"StudentID": 3, "AcadYear": 2024, "MAJOR_CDE": "PSYS",
         "MAJOR_1": "PSYS - z", "MajorSchool": "College of A&S",
         "AY_REVENUE": 18000, "TDiscounts": 6000, "AY_FEES": 400},
    ]))


def test_build_program_inputs_populates_department():
    progs = {p.program_code: p for p in build_program_inputs(_revenue(), 2024)}
    assert progs["BMTS"].department == "Business"
    assert progs["MBAD"].department == "Business"
    assert progs["PSYS"].department == "Psychology"


def test_by_department_rolls_up_majors():
    progs = build_program_inputs(_revenue(), 2024)
    from upr.models import InstitutionInputs
    inst = InstitutionInputs(fiscal_year=2024, university_operations_cost=0)
    result = compute_review(progs, inst, Settings(allocation_driver="headcount"))
    dept = by_department(result)
    business = dept[dept["department"] == "Business"].iloc[0]
    assert business["programs"] == 2          # BMTS + MBAD grouped
    assert business["enrolled_majors"] == 2


def test_department_roundtrips_through_importer():
    progs = build_program_inputs(_revenue(), 2024)
    from upr.adapters.assemble import to_import_dataframe
    csv = to_import_dataframe(progs).to_csv(index=False).encode("utf-8")
    reloaded = {p.program_code: p for p in read_programs(csv, filename="x.csv")}
    assert reloaded["BMTS"].department == "Business"   # survived the round trip
