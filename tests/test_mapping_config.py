import textwrap

import pytest

from upr.connectors.netsuite import aggregate_gl_rows, classify_account
from upr.importing import map_records
from upr.mapping_config import load_mapping, reset_mapping, set_mapping


@pytest.fixture(autouse=True)
def _reset_mapping_cache():
    reset_mapping()
    yield
    reset_mapping()


def _write(tmp_path, text):
    path = tmp_path / "mapping.yaml"
    path.write_text(textwrap.dedent(text))
    return str(path)


def test_column_aliases_from_config_apply_to_importer(tmp_path):
    cfg = load_mapping(_write(tmp_path, """
        column_aliases:
          program_code: ["PROG_CD"]
          student_credit_hours: ["SCH_TOTAL"]
    """))
    set_mapping(cfg)
    rows = [{"PROG_CD": "CSCI", "SCH_TOTAL": 6000}]
    progs = map_records(rows, source="jenzabar")
    assert progs[0].program_code == "CSCI"
    assert progs[0].student_credit_hours == 6000


def test_netsuite_buckets_from_config(tmp_path):
    cfg = load_mapping(_write(tmp_path, """
        netsuite:
          account_buckets:
            - { field: gross_tuition_revenue, exact: "7000", sign: -1 }
            - { field: instruction_cost, range: ["8000", "8099"], sign: 1 }
          operations_departments: [central_it]
    """))
    set_mapping(cfg)
    # default 4000 no longer maps; configured 7000 does
    assert classify_account("4000") is None
    assert classify_account("7000") == ("gross_tuition_revenue", -1)
    assert classify_account("8050") == ("instruction_cost", 1)

    rows = [
        {"program_code": "CSCI", "account": "7000", "amount": -1_000_000},
        {"program_code": "central_it", "account": "8050", "amount": 500_000},
    ]
    progs = {p.program_code for p in aggregate_gl_rows(rows)}
    assert progs == {"CSCI"}  # central_it treated as operations, excluded


def test_defaults_when_no_config():
    set_mapping(None)
    assert classify_account("4000") == ("gross_tuition_revenue", -1)
