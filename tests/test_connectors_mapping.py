import pytest

from upr.connectors.slate import extract_rows
from upr.importing import ImportError_, map_records


def test_extract_rows_handles_slate_and_other_envelopes():
    assert extract_rows({"row": [{"a": 1}]}) == [{"a": 1}]
    assert extract_rows({"items": [{"b": 2}]}) == [{"b": 2}]
    assert extract_rows([{"c": 3}]) == [{"c": 3}]
    # first list-of-dicts anywhere
    assert extract_rows({"meta": 1, "payload": [{"d": 4}]}) == [{"d": 4}]
    assert extract_rows({"nothing": 5}) == []


def test_slate_mapping_keeps_only_funnel_fields():
    rows = [
        {"Program": "CSCI", "Applications": 700, "Admits": 430, "Deposits": 110,
         "instruction_cost": 999999},  # finance field must be ignored
    ]
    progs = map_records(rows, source="slate")
    assert len(progs) == 1
    p = progs[0]
    assert p.program_code == "CSCI"
    assert (p.applications, p.admits, p.deposits) == (700, 430, 110)
    assert p.instruction_cost == 0.0  # not owned by slate -> ignored


def test_jenzabar_mapping_maps_academic_aliases():
    rows = [
        {"Major Code": "BIOL", "Major Desc": "Biology", "College": "Arts & Sciences",
         "Enrolled": 210, "SCH": 8400, "Degrees": 44, "fees_revenue": 12345},
    ]
    progs = map_records(rows, source="jenzabar")
    p = progs[0]
    assert p.program_code == "BIOL"
    assert p.program_name == "Biology"
    assert p.enrolled_majors == 210
    assert p.student_credit_hours == 8400
    assert p.completions == 44
    assert p.fees_revenue == 0.0  # finance field not owned by jenzabar


def test_map_records_requires_program_code():
    with pytest.raises(ImportError_):
        map_records([{"applications": 10, "admits": 5}], source="slate")


def test_map_records_coerces_money_strings():
    rows = [{"program_code": "X", "deposits": "1,200"}]
    assert map_records(rows, source="slate")[0].deposits == 1200
