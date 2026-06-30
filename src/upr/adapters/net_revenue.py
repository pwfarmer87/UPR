"""Adapter for the "Net Revenue, Discounts and Fees by Academic Term" export.

Student×term rows (one per student per term) with revenue, discounts, fees, and
funded aid, keyed by the student's major (``MAJOR_CDE``). The first rows are a
title/filter banner, so the real header is on the third row by default.

Aggregates to one row per major per academic year:
    gross_tuition_revenue = sum(AY_REVENUE)
    institutional_aid     = sum(TDiscounts)
    fees_revenue          = sum(AY_FEES)
    enrolled_majors       = distinct StudentID
"""

from __future__ import annotations

import re

import pandas as pd

# canonical -> candidate source headers (matched case-insensitively, trimmed)
_COLS = {
    "major_code": ["MAJOR_CDE"],
    "major_name": ["MAJOR_1"],
    "college": ["MajorSchool", "StudentDivDesc"],
    "student_id": ["StudentID"],
    "fiscal_year": ["AcadYear"],
    "gross": ["AY_REVENUE"],
    "discounts": ["TDiscounts"],
    "net": ["AY_NET_REVENUE"],
    "fees": ["AY_FEES"],
    "funded_aid": ["AY_FUNDED_AID"],
}


def _find(columns: list[str], candidates: list[str]) -> str | None:
    lower = {str(c).strip().lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def _clean_major_name(value) -> str:
    s = str(value).strip()
    s = re.sub(r"^[A-Z0-9]{2,6}\s*-\s*", "", s)  # drop a leading code token
    s = re.sub(r"^-\s*", "", s)
    return s.strip()


def load_net_revenue(source, *, header: int = 2) -> pd.DataFrame:
    """Read the export into a tidy student-term frame with canonical columns."""
    df = pd.read_excel(source, header=header) if not isinstance(source, pd.DataFrame) \
        else source.copy()
    df.columns = [str(c).strip() for c in df.columns]

    rename = {}
    for canon, candidates in _COLS.items():
        col = _find(list(df.columns), candidates)
        if col is not None:
            rename[col] = canon
    missing = {"major_code", "fiscal_year", "gross"} - set(rename.values())
    if missing:
        raise ValueError(
            f"Net revenue export missing required columns {sorted(missing)}; "
            f"found {sorted(df.columns)[:12]}…"
        )
    out = df[list(rename)].rename(columns=rename)
    out = out[out["major_code"].notna()].copy()
    for num in ("gross", "discounts", "net", "fees", "funded_aid"):
        if num in out.columns:
            out[num] = pd.to_numeric(out[num], errors="coerce").fillna(0.0)
    out["fiscal_year"] = pd.to_numeric(out["fiscal_year"], errors="coerce").astype("Int64")
    return out


def revenue_by_program(df: pd.DataFrame, year: int | None = None) -> pd.DataFrame:
    """Aggregate the tidy frame to one row per major (optionally one year)."""
    if year is not None:
        df = df[df["fiscal_year"] == year]
    if df.empty:
        return pd.DataFrame()

    agg = {
        "gross": ("gross", "sum"),
        "discounts": ("discounts", "sum") if "discounts" in df else ("gross", "size"),
        "fees": ("fees", "sum") if "fees" in df else ("gross", "size"),
        "enrolled_majors": ("student_id", "nunique") if "student_id" in df
        else ("gross", "size"),
    }
    grouped = df.groupby(["fiscal_year", "major_code"], dropna=True).agg(**agg).reset_index()

    # Attach a representative name/college per major (most common).
    def _mode(s: pd.Series):
        m = s.dropna()
        return m.mode().iat[0] if not m.mode().empty else ""

    meta_cols = [c for c in ("major_name", "college") if c in df.columns]
    if meta_cols:
        meta = (
            df.groupby("major_code")[meta_cols].agg(_mode).reset_index()
        )
        grouped = grouped.merge(meta, on="major_code", how="left")
    if "major_name" in grouped.columns:
        grouped["major_name"] = grouped["major_name"].map(_clean_major_name)

    grouped = grouped.rename(columns={
        "gross": "gross_tuition_revenue",
        "discounts": "institutional_aid",
        "fees": "fees_revenue",
        "major_code": "program_code",
        "major_name": "program_name",
    })
    for c in ("gross_tuition_revenue", "institutional_aid", "fees_revenue"):
        if c in grouped.columns:
            grouped[c] = grouped[c].round(2)
    return grouped.sort_values("gross_tuition_revenue", ascending=False, ignore_index=True)
