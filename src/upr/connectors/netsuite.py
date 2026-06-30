"""NetSuite Financials connector (ERP / General Ledger).

Owns the *money* side of each program: actual tuition revenue, institutional
aid, fees, instruction cost (faculty/adjunct salary+benefits), departmental
operating cost, and the university operations pool used for overhead allocation.

Live access uses SuiteQL over the REST web-services endpoint with token-based
auth (OAuth 1.0a TBA). The mapping below is the contract the rest of the app
relies on; wire the actual HTTP/signing once the connector is authorized.

Attribution model
------------------
GL activity is tagged to programs via NetSuite *departments* (or a custom
"Program" segment). The SuiteQL groups expense/revenue by that segment and maps
each segment id to a ``program_code``. Shared/admin departments that are not a
program roll into ``university_operations_cost`` rather than a program's direct
cost. Cross-listed revenue is split upstream by the SCH ratio from Jenzabar.
"""

from __future__ import annotations

from upr.config import NetSuiteConfig
from upr.connectors.base import Connector
from upr.models import InstitutionInputs, ProgramInputs

# Map NetSuite GL account ranges / categories to model fields. Adjust to the
# institution's chart of accounts.
REVENUE_ACCOUNTS = {
    "tuition": "4000",          # gross tuition revenue
    "fees": "4100",             # student fees
    "institutional_aid": "4900",  # contra-revenue: scholarships/discounts
    "other": "4500",            # grants & other program revenue
}
EXPENSE_ACCOUNTS = {
    "instruction": ("5000", "5099"),    # faculty + adjunct salary & benefits
    "departmental": ("5100", "5499"),   # staff, supplies, operating
}
# Departments that represent shared operations rather than an academic program.
OPERATIONS_DEPARTMENTS = {
    "facilities",
    "information_technology",
    "library",
    "administration",
    "student_services",
}

# SuiteQL template that aggregates GL by program segment for a fiscal year.
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
"""


class NetSuiteConnector(Connector):
    name = "netsuite"

    def __init__(self, config: NetSuiteConfig):
        self.config = config

    def is_available(self) -> bool:
        return self.config.is_configured

    def fetch_programs(self, fiscal_year: int) -> list[ProgramInputs]:
        if not self.is_available():
            # Not yet authorized — pipeline will fall back to the mock provider.
            raise ConnectorNotConfigured(
                "NetSuite is not authorized. Set NETSUITE_* credentials in .env "
                "and complete OAuth/token setup, then set UPR_DATA_SOURCE=live."
            )
        rows = self._run_suiteql(SUITEQL_PROGRAM_FINANCIALS, [fiscal_year])
        return self._map_rows_to_programs(rows)

    def fetch_institution(self, fiscal_year: int) -> InstitutionInputs | None:
        if not self.is_available():
            return None
        rows = self._run_suiteql(SUITEQL_PROGRAM_FINANCIALS, [fiscal_year])
        ops = sum(
            r["amount"]
            for r in rows
            if str(r.get("program_code", "")).lower() in OPERATIONS_DEPARTMENTS
        )
        return InstitutionInputs(
            fiscal_year=fiscal_year, university_operations_cost=round(ops, 2)
        )

    # --- live plumbing (to implement once authorized) ---
    def _run_suiteql(self, query: str, params: list) -> list[dict]:  # pragma: no cover
        raise NotImplementedError(
            "Implement SuiteQL POST to "
            "https://<account>.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql"
            " with OAuth1.0a TBA signing."
        )

    def _map_rows_to_programs(self, rows: list[dict]) -> list[ProgramInputs]:  # pragma: no cover
        raise NotImplementedError(
            "Aggregate GL rows by program_code into ProgramInputs revenue/cost "
            "fields using REVENUE_ACCOUNTS / EXPENSE_ACCOUNTS."
        )


class ConnectorNotConfigured(RuntimeError):
    """Raised when a live connector is selected but lacks credentials."""
