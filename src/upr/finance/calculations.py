"""The finance engine: turn normalized inputs into per-program economics."""

from __future__ import annotations

from collections.abc import Sequence

from upr.finance.allocation import allocate_overhead
from upr.models import InstitutionInputs, ProgramFinancials, ProgramInputs


def _safe_div(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 2) if denominator else 0.0


def compute_program_financials(
    program: ProgramInputs,
    allocated_overhead: float,
) -> ProgramFinancials:
    """Compute one program's economics given its share of overhead."""
    gross_tuition = program.computed_gross_tuition
    net_tuition = gross_tuition - program.institutional_aid
    total_revenue = net_tuition + program.fees_revenue + program.other_revenue

    direct_cost = program.direct_cost
    total_cost = direct_cost + allocated_overhead

    contribution_margin = total_revenue - direct_cost
    net_margin = total_revenue - total_cost

    return ProgramFinancials(
        program_code=program.program_code,
        program_name=program.program_name,
        college=program.college,
        department=program.department,
        degree_level=program.degree_level,
        enrolled_majors=program.enrolled_majors,
        student_credit_hours=program.student_credit_hours,
        completions=program.completions,
        # revenue
        gross_tuition_revenue=round(gross_tuition, 2),
        institutional_aid=round(program.institutional_aid, 2),
        net_tuition_revenue=round(net_tuition, 2),
        fees_revenue=round(program.fees_revenue, 2),
        other_revenue=round(program.other_revenue, 2),
        total_revenue=round(total_revenue, 2),
        # cost
        instruction_cost=round(program.instruction_cost, 2),
        departmental_cost=round(program.departmental_cost, 2),
        direct_cost=round(direct_cost, 2),
        allocated_overhead=round(allocated_overhead, 2),
        total_cost=round(total_cost, 2),
        # margins
        contribution_margin=round(contribution_margin, 2),
        contribution_margin_ratio=_safe_div(contribution_margin, total_revenue),
        net_margin=round(net_margin, 2),
        net_margin_ratio=_safe_div(net_margin, total_revenue),
        # per-unit
        revenue_per_student=_safe_div(total_revenue, program.enrolled_majors),
        cost_per_student=_safe_div(total_cost, program.enrolled_majors),
        net_margin_per_student=_safe_div(net_margin, program.enrolled_majors),
        revenue_per_credit_hour=_safe_div(total_revenue, program.student_credit_hours),
        cost_per_credit_hour=_safe_div(total_cost, program.student_credit_hours),
        cost_per_completion=_safe_div(total_cost, program.completions),
    )


def compute_portfolio(
    programs: Sequence[ProgramInputs],
    institution: InstitutionInputs,
    allocation_driver: str = "credit_hours",
) -> list[ProgramFinancials]:
    """Compute economics for every program, allocating shared overhead."""
    overhead = allocate_overhead(
        programs, institution.university_operations_cost, allocation_driver
    )
    return [
        compute_program_financials(p, overhead.get(p.program_code, 0.0))
        for p in programs
    ]


def portfolio_totals(results: Sequence[ProgramFinancials]) -> dict[str, float]:
    """Roll up a computed portfolio into institution-level totals."""
    total_revenue = sum(r.total_revenue for r in results)
    total_cost = sum(r.total_cost for r in results)
    net_margin = total_revenue - total_cost
    return {
        "programs": len(results),
        "enrolled_majors": sum(r.enrolled_majors for r in results),
        "student_credit_hours": round(sum(r.student_credit_hours for r in results), 2),
        "total_revenue": round(total_revenue, 2),
        "direct_cost": round(sum(r.direct_cost for r in results), 2),
        "allocated_overhead": round(sum(r.allocated_overhead for r in results), 2),
        "total_cost": round(total_cost, 2),
        "contribution_margin": round(
            sum(r.contribution_margin for r in results), 2
        ),
        "net_margin": round(net_margin, 2),
        "net_margin_ratio": _safe_div(net_margin, total_revenue),
    }
