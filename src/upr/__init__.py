"""UPR — University Program (Margin) Review."""

from upr.config import Settings
from upr.models import InstitutionInputs, ProgramFinancials, ProgramInputs
from upr.pipeline import ReviewResult, run_review

__version__ = "0.1.0"

__all__ = [
    "Settings",
    "ProgramInputs",
    "ProgramFinancials",
    "InstitutionInputs",
    "ReviewResult",
    "run_review",
]
