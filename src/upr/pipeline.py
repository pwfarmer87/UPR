"""Orchestration: pull from connectors, merge by program, compute economics.

In ``mock`` mode a single MockConnector supplies everything. In ``live`` mode the
Jenzabar (academic), NetSuite (money) and Slate (pipeline) connectors each
contribute their fields and are merged by ``program_code``; any connector that is
not yet authorized is skipped, and if no live connector is available the pipeline
falls back to mock data so the app still renders.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from upr.config import Settings
from upr.connectors.base import Connector
from upr.connectors.jenzabar import JenzabarConnector
from upr.connectors.mock import MockConnector
from upr.connectors.netsuite import ConnectorNotConfigured, NetSuiteConnector
from upr.connectors.slate import SlateConnector
from upr.finance.calculations import compute_portfolio, portfolio_totals
from upr.models import InstitutionInputs, ProgramFinancials, ProgramInputs

# Fields each live connector is responsible for, used when merging partial
# records. A field is overwritten only by its owning source.
_FIELD_OWNERS = {
    "jenzabar": {
        "program_name", "college", "degree_level", "enrolled_majors",
        "student_credit_hours", "completions", "sections_taught", "faculty_fte",
        "tuition_rate_per_credit_hour",
    },
    "netsuite": {
        "gross_tuition_revenue", "institutional_aid", "fees_revenue",
        "other_revenue", "instruction_cost", "departmental_cost",
    },
    "slate": {"applications", "admits", "deposits"},
}


@dataclass
class ReviewResult:
    fiscal_year: int
    institution: InstitutionInputs
    inputs: list[ProgramInputs]
    financials: list[ProgramFinancials]
    sources_used: list[str]

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame([f.as_row() for f in self.financials])

    def totals(self) -> dict:
        return portfolio_totals(self.financials)


def _live_connectors(settings: Settings) -> list[Connector]:
    return [
        JenzabarConnector(settings.jenzabar),
        NetSuiteConnector(settings.netsuite),
        SlateConnector(settings.slate),
    ]


def _merge(records: dict[str, ProgramInputs], source: str,
           contributions: list[ProgramInputs]) -> None:
    """Merge a connector's contributions into the keyed record set in place."""
    owned = _FIELD_OWNERS.get(source, set())
    for contrib in contributions:
        code = contrib.program_code
        if code not in records:
            records[code] = contrib.model_copy()
            continue
        existing = records[code].model_dump()
        incoming = contrib.model_dump()
        for field in owned:
            if field in incoming:
                existing[field] = incoming[field]
        records[code] = ProgramInputs(**existing)


def run_review(settings: Settings | None = None) -> ReviewResult:
    """Run the full review and return inputs + computed financials."""
    settings = settings or Settings.from_env()
    fy = settings.fiscal_year

    records: dict[str, ProgramInputs] = {}
    institution: InstitutionInputs | None = None
    sources_used: list[str] = []

    if settings.data_source == "live":
        for conn in _live_connectors(settings):
            if not conn.is_available():
                continue
            try:
                contributions = conn.fetch_programs(fy)
            except (ConnectorNotConfigured, NotImplementedError):
                continue
            _merge(records, conn.name, contributions)
            inst = conn.fetch_institution(fy)
            if inst is not None:
                institution = inst
            sources_used.append(conn.name)

    if not records:  # mock mode, or no live source authorized yet
        mock = MockConnector()
        _merge(records, mock.name, mock.fetch_programs(fy))
        institution = mock.fetch_institution(fy)
        sources_used = ["mock"]

    if institution is None:
        institution = InstitutionInputs(fiscal_year=fy)

    inputs = sorted(records.values(), key=lambda p: p.program_code)
    financials = compute_portfolio(inputs, institution, settings.allocation_driver)
    return ReviewResult(fy, institution, inputs, financials, sources_used)
