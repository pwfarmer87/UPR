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
from upr.sources import SOURCE_FIELDS

# Fields each source is responsible for when merging partial records. A field is
# overwritten only by its owning source. (Single source of truth: upr.sources.)
_FIELD_OWNERS = SOURCE_FIELDS


@dataclass
class ReviewResult:
    fiscal_year: int
    institution: InstitutionInputs
    inputs: list[ProgramInputs]
    financials: list[ProgramFinancials]
    sources_used: list[str]
    allocation_driver: str = "credit_hours"

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


def merge_sources(
    contributions,
) -> list[ProgramInputs]:
    """Merge (source_name, programs) contributions into complete records.

    Used by both the live pipeline and file imports so they behave identically.
    """
    records: dict[str, ProgramInputs] = {}
    for source, programs in contributions:
        _merge(records, source, programs)
    return sorted(records.values(), key=lambda p: p.program_code)


def compute_review(
    inputs: list[ProgramInputs],
    institution: InstitutionInputs,
    settings: Settings | None = None,
    sources_used: list[str] | None = None,
) -> ReviewResult:
    """Compute a ReviewResult from already-assembled inputs.

    The single funnel for every entry path (connectors, file import, tests).
    """
    settings = settings or Settings.from_env()
    inputs = sorted(inputs, key=lambda p: p.program_code)
    financials = compute_portfolio(inputs, institution, settings.allocation_driver)
    return ReviewResult(
        institution.fiscal_year, institution, inputs, financials,
        sources_used or ["inputs"], settings.allocation_driver,
    )


def run_review(settings: Settings | None = None) -> ReviewResult:
    """Run the full review and return inputs + computed financials."""
    settings = settings or Settings.from_env()
    fy = settings.fiscal_year

    records: dict[str, ProgramInputs] = {}
    institution: InstitutionInputs | None = None
    sources_used: list[str] = []

    if settings.data_source == "file":
        records, institution, sources_used = _load_from_files(settings, fy)

    elif settings.data_source == "live":
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

    if not records:  # mock mode, or no live/file source available yet
        mock = MockConnector()
        _merge(records, mock.name, mock.fetch_programs(fy))
        institution = mock.fetch_institution(fy)
        sources_used = ["mock"]

    if institution is None:
        institution = InstitutionInputs(fiscal_year=fy)
    if settings.operations_cost is not None:
        institution = institution.model_copy(
            update={"university_operations_cost": settings.operations_cost}
        )

    inputs = sorted(records.values(), key=lambda p: p.program_code)
    financials = compute_portfolio(inputs, institution, settings.allocation_driver)
    return ReviewResult(
        fy, institution, inputs, financials, sources_used, settings.allocation_driver
    )


def _load_from_files(settings: Settings, fy: int):
    """Load program inputs from configured CSV/Excel files (UPR_DATA_SOURCE=file)."""
    from upr.importing import read_programs  # local import to avoid a cycle

    records: dict[str, ProgramInputs] = {}
    sources_used: list[str] = []

    if settings.import_file:  # one unified file
        _merge(records, "jenzabar", read_programs(settings.import_file, source="all"))
        sources_used.append("file")
    else:  # optional per-source files
        for source, path in (
            ("jenzabar", settings.jenzabar_file),
            ("netsuite", settings.netsuite_file),
            ("slate", settings.slate_file),
        ):
            if path:
                _merge(records, source, read_programs(path, source=source))
                sources_used.append(f"file:{source}")

    institution = InstitutionInputs(
        fiscal_year=fy,
        university_operations_cost=settings.operations_cost or 0.0,
    )
    return records, institution, sources_used
