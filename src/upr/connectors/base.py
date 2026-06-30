"""Connector interface.

A connector pulls raw data from one source system and contributes its slice of
the normalized model. Programs are keyed by ``program_code`` so the pipeline can
merge contributions from several connectors into complete ``ProgramInputs``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from upr.models import InstitutionInputs, ProgramInputs


class Connector(ABC):
    """Base class for all source-system connectors."""

    name: str = "connector"

    @abstractmethod
    def is_available(self) -> bool:
        """Whether this connector has the credentials/config to pull live data."""

    @abstractmethod
    def fetch_programs(self, fiscal_year: int) -> list[ProgramInputs]:
        """Return this source's contribution to each program's inputs.

        A connector only fills the fields it owns (e.g. Jenzabar fills
        enrollment/credit hours, NetSuite fills revenue/cost). The pipeline
        merges partial records by ``program_code``.
        """

    def fetch_institution(self, fiscal_year: int) -> InstitutionInputs | None:
        """Optionally return institution-level figures (e.g. operations pool)."""
        return None
