"""Import program data from CSV/Excel files (the pre-API path).

Universities can export from Jenzabar/NetSuite/Slate (or hand-build a workbook)
and load it here before any live integration exists. Supports a single unified
file (``source='all'``) or separate per-source files that merge by program code.

Lenient on headers: case/spacing/punctuation are normalized and common aliases
are accepted, so a file that says "Major Code" or "SCH" still maps correctly.
"""

from __future__ import annotations

import io
from collections.abc import Iterable

import pandas as pd

from upr.models import ProgramInputs
from upr.sources import ALL_INPUT_FIELDS, fields_for_source

# Canonical field -> accepted header aliases (in addition to the field name
# itself). Headers are normalized to lower_snake before lookup.
_ALIASES: dict[str, set[str]] = {
    "program_code": {"code", "major_code", "program", "program_id", "major"},
    "program_name": {"name", "major_name", "major_desc", "program_title", "title"},
    "college": {"school", "division", "department", "college_name"},
    "degree_level": {"level", "degree", "award_level"},
    "enrolled_majors": {"majors", "headcount", "enrollment", "enrolled", "students"},
    "student_credit_hours": {"sch", "credit_hours", "credit_hrs", "credithours"},
    "completions": {"degrees", "graduates", "degrees_conferred", "grads"},
    "faculty_fte": {"fte", "faculty"},
    "tuition_rate_per_credit_hour": {
        "tuition_rate", "rate_per_credit_hour", "rate", "tuition_per_credit_hour",
    },
    "gross_tuition_revenue": {"gross_tuition", "tuition_revenue", "tuition"},
    "institutional_aid": {"aid", "discount", "scholarships", "financial_aid"},
    "fees_revenue": {"fees", "fee_revenue"},
    "other_revenue": {"other", "grants", "other_rev"},
    "instruction_cost": {"instructional_cost", "instruction", "faculty_cost"},
    "departmental_cost": {
        "dept_cost", "department_cost", "operating_cost", "departmental",
    },
    "applications": {"apps", "applicants"},
    "admits": {"admitted", "admit"},
    "deposits": {"deposited", "deposit"},
}

# Numeric fields that should be coerced from strings like "$1,200".
_INT_FIELDS = {
    "enrolled_majors", "completions", "applications", "admits", "deposits",
}
_FLOAT_FIELDS = {
    "student_credit_hours", "faculty_fte", "tuition_rate_per_credit_hour",
    "gross_tuition_revenue", "institutional_aid", "fees_revenue",
    "other_revenue", "instruction_cost", "departmental_cost",
}


def _normalize_header(h: str) -> str:
    return (
        str(h).strip().lower()
        .replace("-", "_").replace("/", "_").replace(".", "_")
        .replace("  ", " ").replace(" ", "_")
    )


def _build_header_map() -> dict[str, str]:
    """normalized header -> canonical field."""
    mapping: dict[str, str] = {}
    for field in ALL_INPUT_FIELDS:
        mapping[field] = field
        for alias in _ALIASES.get(field, set()):
            mapping[_normalize_header(alias)] = field
    return mapping


_HEADER_MAP = _build_header_map()


class ImportError_(ValueError):
    """Raised when an import file cannot be parsed into ProgramInputs."""


def _coerce_number(value, as_int: bool):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str):
        value = value.strip().replace("$", "").replace(",", "").replace("%", "")
        if value in ("", "-", "n/a", "na", "none"):
            return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ImportError_(f"Could not read number from {value!r}")
    return int(round(num)) if as_int else num


def _read_dataframe(source_obj, filename: str | None) -> pd.DataFrame:
    """Read CSV or Excel from a path or file-like buffer."""
    name = (filename or getattr(source_obj, "name", "") or "").lower()
    is_excel = name.endswith((".xlsx", ".xls"))
    if isinstance(source_obj, (bytes, bytearray)):
        source_obj = io.BytesIO(source_obj)
    try:
        if is_excel:
            return pd.read_excel(source_obj)
        return pd.read_csv(source_obj)
    except Exception as exc:  # noqa: BLE001
        raise ImportError_(f"Failed to read file {name or '<buffer>'}: {exc}") from exc


def read_programs(
    source_obj,
    *,
    filename: str | None = None,
    source: str = "all",
) -> list[ProgramInputs]:
    """Parse a file into ProgramInputs, keeping only fields ``source`` may set.

    ``source_obj`` may be a path, bytes, or a file-like buffer (e.g. a Streamlit
    upload). ``source`` is 'all' for a unified file or a source name for a
    per-source export.
    """
    df = _read_dataframe(source_obj, filename)
    if df.empty:
        raise ImportError_("File contains no rows.")

    allowed = fields_for_source(source)
    # Map columns -> canonical fields, dropping anything unrecognized.
    col_to_field: dict[str, str] = {}
    for col in df.columns:
        field = _HEADER_MAP.get(_normalize_header(col))
        if field and field in allowed:
            col_to_field[col] = field

    if "program_code" not in col_to_field.values():
        raise ImportError_(
            "Required 'program_code' column not found. Recognized columns: "
            f"{sorted(set(col_to_field.values())) or 'none'}."
        )

    programs: list[ProgramInputs] = []
    for i, row in df.iterrows():
        record: dict = {}
        for col, field in col_to_field.items():
            raw = row[col]
            if field in _INT_FIELDS:
                val = _coerce_number(raw, as_int=True)
            elif field in _FLOAT_FIELDS:
                val = _coerce_number(raw, as_int=False)
            else:
                val = None if pd.isna(raw) else str(raw).strip()
            if val is not None:
                record[field] = val
        code = record.get("program_code")
        if not code:
            continue  # skip blank rows
        try:
            programs.append(ProgramInputs(**record))
        except Exception as exc:  # noqa: BLE001
            raise ImportError_(f"Row {i + 2}: {exc}") from exc

    if not programs:
        raise ImportError_("No valid program rows found.")
    return programs


def template_dataframe(source: str = "all") -> pd.DataFrame:
    """Empty DataFrame whose columns are the importable fields for ``source``.

    Column order is stable and human-friendly (identity first).
    """
    ordered = [
        "program_code", "program_name", "college", "degree_level",
        "enrolled_majors", "student_credit_hours", "completions", "faculty_fte",
        "tuition_rate_per_credit_hour", "gross_tuition_revenue",
        "institutional_aid", "fees_revenue", "other_revenue",
        "instruction_cost", "departmental_cost",
        "applications", "admits", "deposits",
    ]
    allowed = fields_for_source(source)
    cols = [c for c in ordered if c in allowed]
    return pd.DataFrame(columns=cols)


def template_csv(source: str = "all") -> str:
    return template_dataframe(source).to_csv(index=False)


def merge_program_lists(
    contributions: Iterable[tuple[str, list[ProgramInputs]]],
) -> list[ProgramInputs]:
    """Merge several per-source program lists into complete records.

    ``contributions`` is an iterable of (source_name, programs). Reuses the
    pipeline merge so file imports and live connectors behave identically.
    """
    from upr.pipeline import merge_sources  # local import to avoid a cycle

    return merge_sources(contributions)
