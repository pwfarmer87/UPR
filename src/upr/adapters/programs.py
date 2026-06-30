"""Canonical program (major code) roster.

The institution's official ``program_code -> program_name`` list, bundled with
the package, so ingested programs get authoritative names rather than the parsed
``MAJOR_1`` text. Override with your own CSV (columns ``program_code``,
``program_name``) when codes change.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

BUNDLED_ROSTER = Path(__file__).with_name("program_codes.csv")


def load_program_names(source=None) -> dict[str, str]:
    """Return {program_code: program_name}. Defaults to the bundled roster."""
    if isinstance(source, pd.DataFrame):
        df = source.copy()
    else:
        df = pd.read_csv(source or BUNDLED_ROSTER)
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    code_col = "program_code" if "program_code" in df.columns else df.columns[0]
    name_col = "program_name" if "program_name" in df.columns else df.columns[1]
    out: dict[str, str] = {}
    for code, name in zip(df[code_col], df[name_col]):
        code, name = str(code).strip(), str(name).strip()
        if code and code.lower() != "nan":
            out[code] = name
    return out
