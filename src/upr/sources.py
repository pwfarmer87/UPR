"""Which model fields each source system owns.

Single source of truth shared by the pipeline (merging connector contributions)
and the importer (restricting a per-source file to the columns it should fill).
"""

from __future__ import annotations

# Identity columns — present in every source, used to key/merge programs.
KEY_FIELDS = {"program_code", "program_name", "college", "degree_level"}

# Academic facts — Jenzabar One (SIS).
ACADEMIC_FIELDS = {
    "enrolled_majors",
    "student_credit_hours",
    "completions",
    "faculty_fte",
    "tuition_rate_per_credit_hour",
}

# Money — NetSuite Financials (GL).
FINANCE_FIELDS = {
    "gross_tuition_revenue",
    "institutional_aid",
    "fees_revenue",
    "other_revenue",
    "instruction_cost",
    "departmental_cost",
}

# Admissions pipeline — Technolutions Slate (CRM).
PIPELINE_FIELDS = {"applications", "admits", "deposits"}

# Fields each connector/source is responsible for (keys go to the academic
# source so program identity rides with the SIS by default).
SOURCE_FIELDS: dict[str, set[str]] = {
    "jenzabar": KEY_FIELDS | ACADEMIC_FIELDS,
    "netsuite": FINANCE_FIELDS,
    "slate": PIPELINE_FIELDS,
}

# Every field a unified ("all") import may set.
ALL_INPUT_FIELDS = KEY_FIELDS | ACADEMIC_FIELDS | FINANCE_FIELDS | PIPELINE_FIELDS


def fields_for_source(source: str) -> set[str]:
    """Columns an import of ``source`` is allowed to populate.

    ``all`` -> every input field. A named source -> its owned fields plus
    ``program_code`` (always needed to key the row).
    """
    if source == "all":
        return set(ALL_INPUT_FIELDS)
    if source not in SOURCE_FIELDS:
        raise ValueError(
            f"Unknown source {source!r}; choose 'all' or one of {sorted(SOURCE_FIELDS)}"
        )
    return SOURCE_FIELDS[source] | {"program_code"}
