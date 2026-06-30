"""Technolutions Slate connector (Admissions CRM).

Owns the *forward-looking pipeline* for each program: applications, admits, and
deposits by intended major. Feeds the next-year forecast (upr.forecast); does
not change current-year actuals.

Live access reads a **published Slate query** exposed as a JSON web service.
Build the query in Slate to return one row per program with the funnel counts,
e.g. columns ``program_code, applications, admits, deposits`` (a GROUP BY on
intended major). Publish it for "Web Service" output and authenticate with the
query key.

    SLATE_BASE_URL = https://<host>/manage/query/run?id=<query-guid>
    SLATE_QUERY_KEY = <key>     # passed as the `h` parameter

The JSON envelope (`{"row": [...]}`) is parsed leniently and each row is mapped
through the shared importer so header aliases and type coercion match file
imports exactly.
"""

from __future__ import annotations

from upr.config import SlateConfig
from upr.connectors.base import Connector
from upr.connectors.netsuite import ConnectorNotConfigured
from upr.models import ProgramInputs


def extract_rows(payload) -> list[dict]:
    """Pull the list-of-records out of a JSON web-service payload.

    Slate uses ``{"row": [...]}``; other systems use ``rows``/``items``/etc.
    Falls back to the first list-of-dicts found, or a bare top-level list.
    """
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("row", "rows", "items", "results", "data", "value"):
            value = payload.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
        for value in payload.values():  # first list-of-dicts anywhere
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
    return []


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
        rows = self._fetch_rows()
        from upr.importing import map_records  # local import to avoid a cycle

        return map_records(rows, source="slate")

    def _fetch_rows(self) -> list[dict]:
        import requests  # lazy: keep the module importable without requests

        resp = requests.get(
            self.config.base_url,
            params={"h": self.config.query_key, "cmd": "service", "output": "json"},
            timeout=60,
        )
        resp.raise_for_status()
        return extract_rows(resp.json())
