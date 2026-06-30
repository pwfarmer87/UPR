"""Domain model for university program (major) financial review.

Three layers:
  * Raw inputs normalized from the source systems (`ProgramInputs`).
  * Institution-level inputs that get allocated to programs (`InstitutionInputs`).
  * Computed results (`ProgramFinancials`) produced by the finance engine.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class ProgramInputs(BaseModel):
    """Normalized facts about a single program for one fiscal year.

    Populated by the connectors:
      * Jenzabar  -> enrollment, credit hours, completions, faculty load
      * NetSuite  -> revenue, institutional aid, instruction & departmental cost
      * Slate     -> admissions pipeline (forward-looking, optional)
    """

    program_code: str
    program_name: str
    college: str
    degree_level: str = "Undergraduate"  # Undergraduate | Graduate

    # --- Enrollment & activity (Jenzabar) ---
    enrolled_majors: int = Field(0, ge=0)
    student_credit_hours: float = Field(0.0, ge=0)  # SCH delivered by program courses
    completions: int = Field(0, ge=0)               # degrees conferred
    sections_taught: int = Field(0, ge=0)
    faculty_fte: float = Field(0.0, ge=0)

    # --- Revenue (NetSuite) ---
    tuition_rate_per_credit_hour: float = Field(0.0, ge=0)
    gross_tuition_revenue: float | None = None       # if set, overrides SCH*rate
    institutional_aid: float = Field(0.0, ge=0)      # discounts/scholarships
    fees_revenue: float = Field(0.0, ge=0)
    other_revenue: float = Field(0.0, ge=0)          # grants, etc. attributable

    # --- Direct cost (NetSuite) ---
    instruction_cost: float = Field(0.0, ge=0)       # faculty+adjunct salary+benefits
    departmental_cost: float = Field(0.0, ge=0)      # staff, supplies, operating

    # --- Admissions pipeline (Slate, optional, for forecasting) ---
    applications: int = Field(0, ge=0)
    admits: int = Field(0, ge=0)
    deposits: int = Field(0, ge=0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def direct_cost(self) -> float:
        return round(self.instruction_cost + self.departmental_cost, 2)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def computed_gross_tuition(self) -> float:
        if self.gross_tuition_revenue is not None:
            return round(self.gross_tuition_revenue, 2)
        return round(self.student_credit_hours * self.tuition_rate_per_credit_hour, 2)


class InstitutionInputs(BaseModel):
    """Institution-wide figures used for overhead allocation and context."""

    fiscal_year: int
    name: str = "Institution"
    # Shared operations pool to spread across programs (facilities, IT, library,
    # administration, student services) — i.e. everything not in a program's
    # direct cost.
    university_operations_cost: float = Field(0.0, ge=0)


class ProgramFinancials(BaseModel):
    """Computed per-program economics. Output of the finance engine."""

    program_code: str
    program_name: str
    college: str
    degree_level: str

    enrolled_majors: int
    student_credit_hours: float
    completions: int

    # Revenue
    gross_tuition_revenue: float
    institutional_aid: float
    net_tuition_revenue: float
    fees_revenue: float
    other_revenue: float
    total_revenue: float

    # Cost
    instruction_cost: float
    departmental_cost: float
    direct_cost: float
    allocated_overhead: float
    total_cost: float

    # Margins
    contribution_margin: float        # revenue − direct cost (before overhead)
    contribution_margin_ratio: float  # contribution_margin / revenue
    net_margin: float                 # revenue − total cost (after overhead)
    net_margin_ratio: float

    # Per-unit economics
    revenue_per_student: float
    cost_per_student: float
    net_margin_per_student: float
    revenue_per_credit_hour: float
    cost_per_credit_hour: float
    cost_per_completion: float

    def as_row(self) -> dict:
        """Flat dict for building a DataFrame."""
        return self.model_dump()
