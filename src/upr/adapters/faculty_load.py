"""Adapter for the Faculty Load PDF (e.g. "GREENVILLE FACULTY LOAD 2025 SP").

The report lists each faculty member, their contract load, and the course
sections they teach with load credits and enrolled counts. Course subjects are
the department key (same unit as the SCH export).

PDF text extraction here is dependency-free (decompress content streams, read
text-show operators) because heavyweight PDF libraries aren't always available.
The structured parser works on extracted text; an Excel export of the same
report is more reliable and can go straight through ``map_faculty_records`` /
``read_faculty`` instead.
"""

from __future__ import annotations

import re
import zlib

import pandas as pd

# Subject + course number, e.g. "BUSN 101" / "EDUC 282". No word-boundary anchors
# because the extracted text is de-spaced (".00BUSN 101").
_COURSE_RE = re.compile(r"([A-Z]{3,4})\s*(\d{3})")


def extract_pdf_text(path: str) -> str:
    """Best-effort text extraction from a simple PDF (no external deps)."""
    data = open(path, "rb").read()
    chunks: list[str] = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        try:
            dec = zlib.decompress(m.group(1))
        except Exception:
            continue
        parts = re.findall(rb"\((?:[^()\\]|\\.)*\)", dec)
        if parts:
            s = b"".join(p[1:-1] for p in parts).decode("latin-1", "ignore")
            chunks.append(re.sub(r"\\([()\\])", r"\1", s))
    return "\n".join(chunks)


def faculty_subject_load(text: str) -> pd.DataFrame:
    """Tally course mentions per subject from extracted load text.

    Robust to the PDF's de-spaced text: counts each "SUBJ NNN" occurrence as a
    section taught and distinct course numbers per subject. (Per-faculty salary
    is not in a load report — pair this with payroll for cost.)
    """
    sections: dict[str, int] = {}
    courses: dict[str, set[str]] = {}
    for subj, num in _COURSE_RE.findall(text):
        sections[subj] = sections.get(subj, 0) + 1
        courses.setdefault(subj, set()).add(num)
    rows = [
        {"subject": subj, "sections": sections[subj], "distinct_courses": len(courses[subj])}
        for subj in sorted(sections)
    ]
    return pd.DataFrame(rows, columns=["subject", "sections", "distinct_courses"])


def load_faculty_load_pdf(path: str) -> pd.DataFrame:
    """Extract + roll up a faculty load PDF to sections-by-subject."""
    return faculty_subject_load(extract_pdf_text(path))
