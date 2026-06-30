from upr.config import NetSuiteConfig
from upr.connectors.netsuite import (
    aggregate_gl_rows,
    build_authorization_header,
    classify_account,
    operations_pool_from_rows,
)


def test_classify_account_buckets():
    assert classify_account("4000") == ("gross_tuition_revenue", -1)
    assert classify_account("4900") == ("institutional_aid", 1)
    assert classify_account("5050") == ("instruction_cost", 1)
    assert classify_account("5300") == ("departmental_cost", 1)
    assert classify_account("9999") is None
    assert classify_account(None) is None


def test_aggregate_applies_sign_and_groups():
    rows = [
        # tuition is credit-normal (negative) -> reported positive
        {"program_code": "CSCI", "account": "4000", "amount": -1_000_000},
        {"program_code": "CSCI", "account": "4900", "amount": 200_000},   # aid (debit)
        {"program_code": "CSCI", "account": "5050", "amount": 600_000},   # instruction
        {"program_code": "CSCI", "account": "5200", "amount": 150_000},   # departmental
        {"program_code": "BIOL", "account": "4000", "amount": -500_000},
    ]
    progs = {p.program_code: p for p in aggregate_gl_rows(rows)}
    csci = progs["CSCI"]
    assert csci.gross_tuition_revenue == 1_000_000
    assert csci.institutional_aid == 200_000
    assert csci.instruction_cost == 600_000
    assert csci.departmental_cost == 150_000
    assert csci.direct_cost == 750_000
    assert progs["BIOL"].gross_tuition_revenue == 500_000


def test_operations_departments_excluded_from_programs_and_pooled():
    rows = [
        {"program_code": "CSCI", "account": "5050", "amount": 600_000},
        {"program_code": "facilities", "account": "5200", "amount": 2_000_000},
        {"program_code": "library", "account": "5200", "amount": 800_000},
    ]
    progs = {p.program_code for p in aggregate_gl_rows(rows)}
    assert "facilities" not in progs and "library" not in progs
    assert operations_pool_from_rows(rows) == 2_800_000


def test_negative_expense_is_clamped_not_rejected():
    # a credit memo on an expense account shouldn't push a cost below zero
    rows = [{"program_code": "X", "account": "5050", "amount": -100}]
    progs = aggregate_gl_rows(rows)
    assert progs[0].instruction_cost == 0.0


def _cfg():
    return NetSuiteConfig(
        account_id="1234567_SB1",
        consumer_key="ck",
        consumer_secret="cs",
        token_id="tk",
        token_secret="ts",
    )


def test_oauth_header_structure_and_determinism():
    cfg = _cfg()
    url = "https://1234567-sb1.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql"
    h1 = build_authorization_header(cfg, "POST", url, {"limit": "1000", "offset": "0"},
                                    timestamp="1700000000", nonce="abc123")
    h2 = build_authorization_header(cfg, "POST", url, {"limit": "1000", "offset": "0"},
                                    timestamp="1700000000", nonce="abc123")
    assert h1 == h2  # deterministic given timestamp+nonce
    assert h1.startswith('OAuth realm="1234567_SB1"')
    assert 'oauth_signature_method="HMAC-SHA256"' in h1
    assert "oauth_signature=" in h1
    # a different nonce changes the signature
    h3 = build_authorization_header(cfg, "POST", url, {"limit": "1000", "offset": "0"},
                                    timestamp="1700000000", nonce="different")
    assert h3 != h1
