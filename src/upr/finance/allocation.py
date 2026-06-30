"""Overhead allocation strategies.

The university operations pool (facilities, IT, library, administration, student
services) is shared and must be spread across programs. We allocate it
proportional to a *driver* — the thing that best approximates how much of the
shared services each program consumes.
"""

from __future__ import annotations

from collections.abc import Sequence

from upr.models import ProgramInputs

# Driver name -> function returning the per-program weight.
_DRIVERS = {
    "credit_hours": lambda p: p.student_credit_hours,
    "headcount": lambda p: float(p.enrolled_majors),
    "direct_cost": lambda p: p.direct_cost,
}


def allocate_overhead(
    programs: Sequence[ProgramInputs],
    operations_pool: float,
    driver: str = "credit_hours",
) -> dict[str, float]:
    """Return {program_code: allocated_overhead}.

    Each program gets ``operations_pool * (driver_i / sum(driver))``. If every
    program has a zero driver value (or the pool is zero), the pool is split
    evenly so nothing is silently dropped.
    """
    if driver not in _DRIVERS:
        raise ValueError(
            f"Unknown allocation driver {driver!r}; "
            f"choose one of {sorted(_DRIVERS)}"
        )
    weight_fn = _DRIVERS[driver]
    weights = {p.program_code: max(0.0, weight_fn(p)) for p in programs}
    total = sum(weights.values())

    if not programs or operations_pool <= 0:
        return {p.program_code: 0.0 for p in programs}

    if total <= 0:
        even = operations_pool / len(programs)
        return {p.program_code: round(even, 2) for p in programs}

    return {
        code: round(operations_pool * (w / total), 2) for code, w in weights.items()
    }
