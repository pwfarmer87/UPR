"""Technolutions Slate connector (Admissions CRM).

Owns the *forward-looking pipeline* for each program: applications, admits, and
deposits by intended major. This does not change current-year actuals; it feeds
enrollment forecasting and "programs to watch" (e.g. strong margin but shrinking
pipeline).

Live access is via a Slate query published to the web-services / query API,
authenticated with a query key. Each Slate query maps to a program by intended
major code.
"""

from __future__ import annotations

from upr.config import SlateConfig
from upr.connectors.base import Connector
from upr.connectors.netsuite import ConnectorNotConfigured
from upr.models import ProgramInputs


class SlateConnector(Connector):
    name = "slate"

    def __init__(self, config: SlateConfig):
        self.config = config

    def is_available(self) -> bool:
        return self.config.is_configured

    def fetch_programs(self, fiscal_year: int) -> list[ProgramInputs]:
        if not self.is_available():
            raise ConnectorNotConfigured(
                "Slate is not configured. Set SLATE_BASE_URL+SLATE_QUERY_KEY in "
                ".env, then set UPR_DATA_SOURCE=live."
            )
        return self._fetch_live(fiscal_year)  # pragma: no cover

    def _fetch_live(self, fiscal_year: int) -> list[ProgramInputs]:  # pragma: no cover
        raise NotImplementedError(
            "GET the published Slate query (JSON) with the query key and map "
            "applications/admits/deposits onto ProgramInputs by intended major."
        )
