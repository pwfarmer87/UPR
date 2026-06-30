"""Jenzabar One connector (Student Information System).

Owns the *academic* side of each program: enrolled majors, student credit hours
(SCH), faculty FTE, and degree completions. These drive the per-student /
per-credit-hour economics and the default overhead allocation (by SCH).

Two live paths, picked by what's configured in ``.env``:

  * **REST API** — ``JENZABAR_BASE_URL`` + ``JENZABAR_API_KEY``. GETs a JSON
    feed (one row per program) and maps it through the shared importer.
  * **Direct SQL** — ``JENZABAR_DB_DSN``. Runs ``SQL_PROGRAM_ACTIVITY`` against
    a read-only view of the EX/SONIS database via ODBC (pyodbc) and maps rows.

Either way the query/endpoint should return one row per program for the year,
with columns that map onto the model (``program_code``, ``enrolled_majors``,
``student_credit_hours``, ``completions``, ...). Header aliases are handled by
the shared importer, so ``Major Code``/``SCH`` work.
"""

from __future__ import annotations

from upr.config import JenzabarConfig
from upr.connectors.base import Connector
from upr.connectors.netsuite import ConnectorNotConfigured
from upr.connectors.slate import extract_rows
from upr.models import ProgramInputs

# Read-only SQL that produces one row per program for a year. Column names map
# directly onto ProgramInputs fields (lenient aliases handle the rest).
SQL_PROGRAM_ACTIVITY = """
SELECT  m.major_code              AS program_code,
        m.major_desc              AS program_name,
        m.college                 AS college,
        m.degree_level            AS degree_level,
        COUNT(DISTINCT e.student_id)            AS enrolled_majors,
        SUM(r.credit_hours)                     AS student_credit_hours,
        SUM(f.fte)                              AS faculty_fte,
        COUNT(DISTINCT g.degree_id)             AS completions
FROM    majors m
LEFT JOIN enrollment e   ON e.major_code = m.major_code AND e.year = ?
LEFT JOIN registration r ON r.major_code = m.major_code AND r.year = ?
LEFT JOIN faculty_load f  ON f.major_code = m.major_code AND f.year = ?
LEFT JOIN degrees g       ON g.major_code = m.major_code AND g.year = ?
GROUP BY m.major_code, m.major_desc, m.college, m.degree_level
""".strip()


class JenzabarConnector(Connector):
    name = "jenzabar"

    def __init__(self, config: JenzabarConfig):
        self.config = config

    def is_available(self) -> bool:
        return self.config.is_configured

    def fetch_programs(self, fiscal_year: int) -> list[ProgramInputs]:
        if not self.is_available():
            raise ConnectorNotConfigured(
                "Jenzabar is not configured. Set JENZABAR_BASE_URL+JENZABAR_API_KEY "
                "or JENZABAR_DB_DSN in .env, then set UPR_DATA_SOURCE=live."
            )
        if self.config.db_dsn:
            rows = self._fetch_rows_sql(fiscal_year)
        else:
            rows = self._fetch_rows_api(fiscal_year)
        from upr.importing import map_records  # local import to avoid a cycle

        return map_records(rows, source="jenzabar")

    def _fetch_rows_api(self, fiscal_year: int) -> list[dict]:
        import requests  # lazy import

        resp = requests.get(
            self.config.base_url,
            params={"year": fiscal_year},
            headers={"Authorization": f"Bearer {self.config.api_key}"},
            timeout=60,
        )
        resp.raise_for_status()
        return extract_rows(resp.json())

    def _fetch_rows_sql(self, fiscal_year: int) -> list[dict]:
        import pyodbc  # lazy import; only needed for the SQL path

        conn = pyodbc.connect(self.config.db_dsn, readonly=True, timeout=60)
        try:
            cursor = conn.cursor()
            cursor.execute(SQL_PROGRAM_ACTIVITY, [fiscal_year] * 4)
            columns = [c[0] for c in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            conn.close()
