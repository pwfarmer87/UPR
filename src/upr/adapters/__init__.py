"""Adapters for real institutional report exports.

These turn the specific shapes a registrar/finance office actually exports into
UPR's normalized model:

  * ``net_revenue``        — student×term revenue/discounts/fees by major
  * ``course_enrollments`` — student credit hours by course subject × year
  * ``faculty_load``       — faculty teaching load by course subject (PDF)
  * ``assemble``           — combine them into ProgramInputs for a fiscal year

Keying note: revenue is by **student major** (``MAJOR_CDE``) while SCH and
faculty are by **course subject** (department). Those are different units; the
assembler keeps revenue authoritative for the financial model and treats SCH /
faculty as department-side context bridged by an explicit crosswalk.
"""

from upr.adapters.assemble import build_program_inputs, to_import_dataframe
from upr.adapters.course_enrollments import load_course_enrollments, sch_by_subject
from upr.adapters.net_revenue import load_net_revenue, revenue_by_program

__all__ = [
    "load_net_revenue",
    "revenue_by_program",
    "load_course_enrollments",
    "sch_by_subject",
    "build_program_inputs",
    "to_import_dataframe",
]
