import io

import pytest

from upr.importing import (
    ImportError_,
    read_programs,
    template_csv,
    template_dataframe,
)
from upr.pipeline import merge_sources


def _csv_buffer(text: str, name: str = "f.csv"):
    buf = io.BytesIO(text.encode("utf-8"))
    buf.name = name
    return buf


def test_unified_import_maps_aliases_and_coerces():
    csv = (
        "Major Code,Program Name,College,Majors,SCH,Aid,Instruction Cost,Dept Cost\n"
        "CSCI,Computer Science,Arts & Sciences,200,\"6,000\",\"$1,500,000\",1200000,250000\n"
    )
    progs = read_programs(_csv_buffer(csv), source="all")
    assert len(progs) == 1
    p = progs[0]
    assert p.program_code == "CSCI"
    assert p.program_name == "Computer Science"
    assert p.enrolled_majors == 200
    assert p.student_credit_hours == 6000
    assert p.institutional_aid == 1_500_000
    assert p.direct_cost == 1_450_000  # 1.2M + 250k


def test_missing_program_code_raises():
    csv = "name,college\nFoo,Bar\n"
    with pytest.raises(ImportError_):
        read_programs(_csv_buffer(csv), source="all")


def test_per_source_restricts_fields_then_merges():
    # NetSuite file has only code + money; name/college backfilled then overridden.
    sis = "program_code,program_name,college,enrolled_majors,student_credit_hours\nA,Art,Fine Arts,40,1200\n"
    fin = "program_code,instruction_cost,departmental_cost,fees_revenue\nA,500000,80000,20000\n"

    sis_p = read_programs(_csv_buffer(sis), source="jenzabar")
    fin_p = read_programs(_csv_buffer(fin), source="netsuite")

    # A finance-only row should ignore any stray name column, but here there is none
    assert fin_p[0].program_name == "A"  # backfilled from code
    merged = merge_sources([("jenzabar", sis_p), ("netsuite", fin_p)])
    assert len(merged) == 1
    m = merged[0]
    assert m.program_name == "Art"          # from SIS (owns identity)
    assert m.enrolled_majors == 40          # from SIS
    assert m.instruction_cost == 500_000    # from NetSuite
    assert m.fees_revenue == 20_000


def test_netsuite_file_cannot_set_enrollment():
    # enrolled_majors belongs to Jenzabar; a NetSuite import must not set it.
    fin = "program_code,enrolled_majors,instruction_cost\nA,999,500000\n"
    progs = read_programs(_csv_buffer(fin), source="netsuite")
    assert progs[0].enrolled_majors == 0      # ignored, not 999
    assert progs[0].instruction_cost == 500_000


def test_blank_rows_are_skipped():
    csv = "program_code,instruction_cost\nA,100\n,\nB,200\n"
    progs = read_programs(_csv_buffer(csv), source="all")
    assert {p.program_code for p in progs} == {"A", "B"}


def test_template_has_expected_columns():
    assert "program_code" in template_dataframe("all").columns
    assert "instruction_cost" in template_dataframe("netsuite").columns
    assert "instruction_cost" not in template_dataframe("slate").columns
    assert template_csv("slate").startswith("program_code")
