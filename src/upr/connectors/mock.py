"""Mock connector — serves the bundled sample institution.

Used when ``UPR_DATA_SOURCE=mock`` or when a live connector is not yet
authorized, so the whole pipeline and dashboard work end-to-end today.
"""

from __future__ import annotations

from upr.connectors.base import Connector
from upr.models import InstitutionInputs, ProgramInputs
from upr.sample_data import sample_institution, sample_programs


class MockConnector(Connector):
    name = "mock"

    def is_available(self) -> bool:
        return True

    def fetch_programs(self, fiscal_year: int) -> list[ProgramInputs]:
        return sample_programs(fiscal_year)

    def fetch_institution(self, fiscal_year: int) -> InstitutionInputs:
        return sample_institution(fiscal_year)
