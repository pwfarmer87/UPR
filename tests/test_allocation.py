from upr.finance.allocation import allocate_overhead
from upr.models import ProgramInputs


def _p(code, sch=0.0, majors=0, direct=0.0):
    return ProgramInputs(
        program_code=code,
        program_name=code,
        college="X",
        student_credit_hours=sch,
        enrolled_majors=majors,
        instruction_cost=direct,
    )


def test_allocation_is_proportional_to_credit_hours():
    progs = [_p("A", sch=300), _p("B", sch=100)]
    alloc = allocate_overhead(progs, 4000, "credit_hours")
    assert alloc["A"] == 3000
    assert alloc["B"] == 1000
    assert round(sum(alloc.values()), 2) == 4000


def test_allocation_by_headcount():
    progs = [_p("A", majors=30), _p("B", majors=10)]
    alloc = allocate_overhead(progs, 4000, "headcount")
    assert alloc["A"] == 3000
    assert alloc["B"] == 1000


def test_zero_driver_splits_evenly():
    progs = [_p("A"), _p("B")]
    alloc = allocate_overhead(progs, 1000, "credit_hours")
    assert alloc == {"A": 500, "B": 500}


def test_zero_pool_allocates_nothing():
    progs = [_p("A", sch=300), _p("B", sch=100)]
    assert allocate_overhead(progs, 0, "credit_hours") == {"A": 0.0, "B": 0.0}


def test_unknown_driver_raises():
    try:
        allocate_overhead([_p("A", sch=1)], 100, "bogus")
    except ValueError as e:
        assert "bogus" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_full_pool_is_distributed():
    progs = [_p("A", sch=123), _p("B", sch=77), _p("C", sch=200)]
    alloc = allocate_overhead(progs, 1_000_000, "credit_hours")
    # rounding may leave pennies; should be within a cent-per-program tolerance
    assert abs(sum(alloc.values()) - 1_000_000) < len(progs) * 0.01
