"""NetSuite Financials connector (ERP / General Ledger).

Owns the *money* side of each program: actual tuition revenue, institutional
aid, fees, instruction cost (faculty/adjunct salary+benefits), departmental
operating cost, and the university operations pool used for overhead allocation.

Live access uses SuiteQL over the REST web-services endpoint with token-based
auth (OAuth 1.0a TBA, HMAC-SHA256). Two layers, separated so the mapping is
testable without a network:

  * ``aggregate_gl_rows`` / ``classify_account`` — pure: GL rows -> ProgramInputs.
  * ``_run_suiteql`` — the signed, paginated HTTP call (needs authorization).

Attribution model
------------------
GL activity is tagged to programs via NetSuite *departments* (or a custom
"Program" segment). The SuiteQL groups revenue/expense by that segment; each
segment name is the ``program_code``. Departments in ``OPERATIONS_DEPARTMENTS``
are shared services and roll into ``university_operations_cost`` instead of a
program's direct cost. Cross-listed revenue is split upstream by the SCH ratio
from Jenzabar.

Sign convention
---------------
NetSuite ``transactionline.amount`` is signed: debits positive, credits
negative. Income accounts are credit-normal (negative), so revenue buckets use
sign ``-1`` to report a positive figure; expense and contra-revenue (aid)
buckets are debit-normal and use ``+1``. Adjust ``_BUCKET_SPECS`` to the
institution's chart of accounts.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import quote

from upr.config import NetSuiteConfig
from upr.connectors.base import Connector
from upr.models import InstitutionInputs, ProgramInputs

# Departments that represent shared operations rather than an academic program.
OPERATIONS_DEPARTMENTS = {
    "facilities",
    "information_technology",
    "library",
    "administration",
    "student_services",
}

# Bucket spec: ProgramInputs field <- (account matcher, sign). ``exact`` matches
# a single account number; ``range`` matches an inclusive [lo, hi] string range.
_BUCKET_SPECS: list[dict] = [
    {"field": "gross_tuition_revenue", "exact": "4000", "sign": -1},
    {"field": "fees_revenue", "exact": "4100", "sign": -1},
    {"field": "other_revenue", "exact": "4500", "sign": -1},
    {"field": "institutional_aid", "exact": "4900", "sign": +1},  # contra-revenue
    {"field": "instruction_cost", "range": ("5000", "5099"), "sign": +1},
    {"field": "departmental_cost", "range": ("5100", "5499"), "sign": +1},
]

# Fields that must stay >= 0 (ProgramInputs enforces this); we clamp to avoid a
# stray opposite-signed line aborting the whole import.
_CLAMP_NONNEGATIVE = {
    "fees_revenue", "other_revenue", "institutional_aid",
    "instruction_cost", "departmental_cost",
}

# SuiteQL that aggregates GL by program segment for a fiscal year.
SUITEQL_PROGRAM_FINANCIALS = """
SELECT  d.name           AS program_code,
        a.acctnumber     AS account,
        SUM(tl.amount)    AS amount
FROM    transactionline tl
JOIN    transaction t  ON t.id = tl.transaction
JOIN    account a       ON a.id = tl.account
JOIN    department d     ON d.id = tl.department
WHERE   t.postingperiod IN (SELECT id FROM accountingperiod WHERE fiscalyear = ?)
GROUP BY d.name, a.acctnumber
""".strip()


class ConnectorNotConfigured(RuntimeError):
    """Raised when a live connector is selected but lacks credentials."""


# --------------------------------------------------------------------------- #
# Pure mapping (unit-testable without a network)
# --------------------------------------------------------------------------- #
def _active_buckets() -> list[dict]:
    """Bucket specs from the mapping config if present, else the built-ins."""
    from upr.mapping_config import get_mapping  # local import to avoid a cycle

    return get_mapping().netsuite_buckets or _BUCKET_SPECS


def _active_operations_departments() -> set[str]:
    from upr.mapping_config import get_mapping  # local import to avoid a cycle

    return get_mapping().operations_departments or OPERATIONS_DEPARTMENTS


def classify_account(
    acctnumber: str | int | None, specs: list[dict] | None = None
) -> tuple[str, int] | None:
    """Return (program_field, sign) for a GL account number, or None to ignore."""
    if acctnumber is None:
        return None
    acct = str(acctnumber).strip()
    if not acct:
        return None
    for spec in specs if specs is not None else _active_buckets():
        sign = int(spec.get("sign", 1))
        if "exact" in spec and acct == str(spec["exact"]):
            return spec["field"], sign
        if "range" in spec:
            lo, hi = (str(x) for x in spec["range"])
            if lo <= acct <= hi:
                return spec["field"], sign
    return None


def _is_operations(program_code: str | None) -> bool:
    return (
        str(program_code or "").strip().lower()
        in _active_operations_departments()
    )


def aggregate_gl_rows(rows: list[dict]) -> list[ProgramInputs]:
    """Aggregate ``{program_code, account, amount}`` rows into ProgramInputs.

    Operations departments are excluded here (they belong to the institution
    pool, see ``operations_pool_from_rows``).
    """
    by_program: dict[str, dict[str, float]] = {}
    for r in rows:
        code = str(r.get("program_code") or "").strip()
        if not code or _is_operations(code):
            continue
        mapped = classify_account(r.get("account"))
        if mapped is None:
            continue
        field, sign = mapped
        amount = float(r.get("amount") or 0.0) * sign
        bucket = by_program.setdefault(code, {})
        bucket[field] = bucket.get(field, 0.0) + amount

    programs: list[ProgramInputs] = []
    for code, fields in sorted(by_program.items()):
        record: dict = {"program_code": code}
        for field, value in fields.items():
            if field in _CLAMP_NONNEGATIVE:
                value = max(0.0, value)
            record[field] = round(value, 2)
        programs.append(ProgramInputs(**record))
    return programs


def operations_pool_from_rows(rows: list[dict]) -> float:
    """Sum expense in operations departments into the shared overhead pool."""
    total = 0.0
    for r in rows:
        if not _is_operations(r.get("program_code")):
            continue
        mapped = classify_account(r.get("account"))
        sign = mapped[1] if mapped else 1  # expenses are +1
        total += float(r.get("amount") or 0.0) * (sign if mapped else 1)
    return round(max(0.0, total), 2)


# --------------------------------------------------------------------------- #
# OAuth 1.0a TBA signing (pure given timestamp + nonce)
# --------------------------------------------------------------------------- #
def _q(value: str) -> str:
    return quote(str(value), safe="")


def build_authorization_header(
    config: NetSuiteConfig,
    method: str,
    url: str,
    query_params: dict[str, str] | None,
    timestamp: str,
    nonce: str,
) -> str:
    """Build the OAuth1.0a HMAC-SHA256 Authorization header for a request.

    Pure: deterministic given ``timestamp`` and ``nonce`` (injected so it can be
    tested and so a single signed value is reused across a retry).
    """
    oauth_params = {
        "oauth_consumer_key": config.consumer_key or "",
        "oauth_token": config.token_id or "",
        "oauth_signature_method": "HMAC-SHA256",
        "oauth_timestamp": timestamp,
        "oauth_nonce": nonce,
        "oauth_version": "1.0",
    }
    # Signature base includes oauth params + any query-string params.
    all_params = {**oauth_params, **(query_params or {})}
    param_string = "&".join(
        f"{_q(k)}={_q(v)}" for k, v in sorted(all_params.items())
    )
    base_string = "&".join([method.upper(), _q(url), _q(param_string)])
    signing_key = f"{_q(config.consumer_secret or '')}&{_q(config.token_secret or '')}"
    digest = hmac.new(
        signing_key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha256
    ).digest()
    signature = base64.b64encode(digest).decode("ascii")

    realm = (config.account_id or "").upper().replace("-", "_")
    header_params = {**oauth_params, "oauth_signature": signature}
    parts = ", ".join(f'{k}="{_q(v)}"' for k, v in sorted(header_params.items()))
    return f'OAuth realm="{_q(realm)}", {parts}'


# --------------------------------------------------------------------------- #
# Connector
# --------------------------------------------------------------------------- #
class NetSuiteConnector(Connector):
    name = "netsuite"
    PAGE_SIZE = 1000

    def __init__(self, config: NetSuiteConfig):
        self.config = config

    def is_available(self) -> bool:
        return self.config.is_configured

    def _base_url(self) -> str:
        account = (self.config.account_id or "").lower().replace("_", "-")
        return (
            f"https://{account}.suitetalk.api.netsuite.com"
            "/services/rest/query/v1/suiteql"
        )

    def fetch_programs(self, fiscal_year: int) -> list[ProgramInputs]:
        if not self.is_available():
            raise ConnectorNotConfigured(
                "NetSuite is not authorized. Set NETSUITE_* credentials in .env "
                "and complete OAuth/token setup, then set UPR_DATA_SOURCE=live."
            )
        rows = self._run_suiteql(self._sql_for_year(fiscal_year))
        return aggregate_gl_rows(rows)

    def fetch_institution(self, fiscal_year: int) -> InstitutionInputs | None:
        if not self.is_available():
            return None
        rows = self._run_suiteql(self._sql_for_year(fiscal_year))
        return InstitutionInputs(
            fiscal_year=fiscal_year,
            university_operations_cost=operations_pool_from_rows(rows),
        )

    @staticmethod
    def _sql_for_year(fiscal_year: int) -> str:
        # SuiteQL params bind positionally via '?'; inline the integer year here
        # since the value is internally generated (not user input).
        return SUITEQL_PROGRAM_FINANCIALS.replace("?", str(int(fiscal_year)))

    def _run_suiteql(self, query: str) -> list[dict]:
        """POST the SuiteQL query, signed, following pagination."""
        import requests  # lazy: keep the module importable without requests

        url = self._base_url()
        rows: list[dict] = []
        offset = 0
        while True:
            params = {"limit": str(self.PAGE_SIZE), "offset": str(offset)}
            auth = build_authorization_header(
                self.config, "POST", url, params,
                timestamp=str(int(time.time())),
                nonce=secrets.token_hex(16),
            )
            resp = requests.post(
                url,
                params=params,
                json={"q": query},
                headers={
                    "Authorization": auth,
                    "Content-Type": "application/json",
                    "Prefer": "transient",
                },
                timeout=60,
            )
            resp.raise_for_status()
            payload = resp.json()
            rows.extend(payload.get("items", []))
            if not payload.get("hasMore"):
                break
            offset += self.PAGE_SIZE
        return rows
