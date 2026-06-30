"""Jenzabar One connector (Student Information System).

Owns the *academic* side of each program: enrolled majors, student credit hours
(SCH) delivered by the program's courses, sections taught, faculty FTE, and
degree completions. These drive the per-student / per-credit-hour economics and
the default overhead allocation (by SCH).

Live access is via the Jenzabar API (or a read-only SQL view against the EX/SONIS
database). The mapping below is the contract; wire the HTTP/SQL once available.
"""

from __future__ import annotations

from upr.config import JenzabarConfig
from upr.connectors.base import Connector
from upr.connectors.netsuite import ConnectorNotConfigured
from upr.models import ProgramInputs

# Read-only SQL that produces one row per program for a term/year. Column names
# map directly onto ProgramInputs fields.
SQL_PROGRAM_ACTIVITY = """
SELECT  m.major_code              AS program_code,
        m.major_desc              AS program_name,
        m.college                 AS college,
        m.degree_level            AS degree_level,
        COUNT(DISTINCT e.student_id)            AS enrolled_majors,
        SUM(r.credit_hours)                     AS student_credit_hours,
        COUNT(DISTINCT s.section_id)            AS sections_taught,
        SUM(f.fte)                              AS faculty_fte,
        COUNT(DISTINCT g.degree_id)             AS completions
FROM    majors m
LEFT JOIN enrollment e   ON e.major_code = m.major_code AND e.year = ?
LEFT JOIN registration r ON r.major_code = m.major_code AND r.year = ?
LEFT JOIN sections s      ON s.major_code = m.major_code AND s.year = ?
LEFT JOIN faculty_load f  ON f.major_code = m.major_code AND f.year = ?
LEFT JOIN degrees g       ON g.major_code = m.major_code AND g.year = ?
GROUP BY m.major_code, m.major_desc, m.college, m.degree_level
"""


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
        return self._fetch_live(fiscal_year)  # pragma: no cover

    def _fetch_live(self, fiscal_year: int) -> list[ProgramInputs]:  # pragma: no cover
        raise NotImplementedError(
            "Run SQL_PROGRAM_ACTIVITY against the Jenzabar DB (or call the API) "
            "and build ProgramInputs with enrollment/SCH/completions fields."
        )
