import pandas as pd

from upr.adapters import load_net_revenue, load_program_names, revenue_by_program
from upr.adapters.assemble import build_program_inputs


def test_bundled_roster_loads_official_names():
    roster = load_program_names()
    assert roster["BMTS"] == "Business Management"
    assert roster["EELM"] == "Elementary Education"
    assert roster["MBAD"] == "Business Administration"
    assert len(roster) >= 60


def _revenue():
    return load_net_revenue(pd.DataFrame([
        {"StudentID": 1, "AcadYear": 2024, "MAJOR_CDE": "BMTS",
         "MAJOR_1": "BMTS - whatever messy text", "MajorSchool": "Business",
         "AY_REVENUE": 20000, "TDiscounts": 8000, "AY_FEES": 500},
        # two Education codes -> same official name -> disambiguated by code
        {"StudentID": 2, "AcadYear": 2024, "MAJOR_CDE": "EELM",
         "MAJOR_1": "EELM - x", "MajorSchool": "Education",
         "AY_REVENUE": 15000, "TDiscounts": 5000, "AY_FEES": 300},
        {"StudentID": 3, "AcadYear": 2024, "MAJOR_CDE": "UTEL",
         "MAJOR_1": "UTEL - y", "MajorSchool": "Education",
         "AY_REVENUE": 15000, "TDiscounts": 5000, "AY_FEES": 300},
        # code absent from roster -> keeps parsed name
        {"StudentID": 4, "AcadYear": 2024, "MAJOR_CDE": "ZZZZ",
         "MAJOR_1": "ZZZZ - Custom Program", "MajorSchool": "Other",
         "AY_REVENUE": 10000, "TDiscounts": 2000, "AY_FEES": 100},
    ]))


def test_roster_names_override_parsed_and_disambiguate():
    rev = revenue_by_program(_revenue(), 2024, load_program_names())
    names = dict(zip(rev["program_code"], rev["program_name"]))
    assert names["BMTS"] == "Business Management"             # official, not parsed
    assert names["EELM"] == "Elementary Education (EELM)"     # disambiguated
    assert names["UTEL"] == "Elementary Education (UTEL)"
    assert names["ZZZZ"] == "Custom Program"                  # fallback to parsed


def test_build_program_inputs_uses_bundled_roster_by_default():
    progs = {p.program_code: p for p in build_program_inputs(_revenue(), 2024)}
    assert progs["BMTS"].program_name == "Business Management"
