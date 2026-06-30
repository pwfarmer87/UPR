"""A realistic sample institution so the app works end-to-end without live data.

Figures are hand-set to be plausible for a small-to-mid private university and to
exercise the full range of outcomes: strongly profitable programs (large
lower-division service teaching), thin-margin programs, and programs that lose
money after overhead (small, faculty-heavy majors). Numbers are illustrative,
not benchmarks.

Deterministic: the same fiscal year always yields the same data, with a mild
year-over-year growth factor so multi-year trends render.
"""

from __future__ import annotations

from upr.models import InstitutionInputs, ProgramInputs

# Per-credit-hour tuition by level (sticker rate before institutional aid).
_UG_RATE = 1180.0
_GR_RATE = 1450.0

# program_code, name, college, level, majors, SCH, completions, faculty_fte,
# aid, fees, other_rev, instruction_cost, departmental_cost,
# applications, admits, deposits
_BASE: list[tuple] = [
    ("NURS", "Nursing", "Health Sciences", "Undergraduate",
     310, 9300, 78, 18.0, 3_250_000, 410_000, 120_000, 3_100_000, 720_000, 880, 470, 132),
    ("BIOL", "Biology", "Arts & Sciences", "Undergraduate",
     210, 8400, 44, 12.0, 2_700_000, 250_000, 380_000, 1_650_000, 360_000, 640, 410, 96),
    ("CSCI", "Computer Science", "Arts & Sciences", "Undergraduate",
     245, 7350, 52, 11.0, 2_050_000, 300_000, 60_000, 1_480_000, 300_000, 720, 430, 110),
    ("BUSN", "Business Administration", "Business", "Undergraduate",
     420, 12600, 96, 16.0, 3_900_000, 520_000, 90_000, 2_050_000, 540_000, 980, 660, 188),
    ("PSYC", "Psychology", "Arts & Sciences", "Undergraduate",
     360, 10080, 84, 12.0, 3_050_000, 300_000, 40_000, 1_320_000, 280_000, 700, 520, 150),
    ("ENGL", "English", "Arts & Sciences", "Undergraduate",
     95, 8550, 22, 11.0, 1_900_000, 120_000, 30_000, 1_180_000, 210_000, 240, 200, 44),
    ("EDUC", "Education", "Education", "Undergraduate",
     160, 5760, 60, 10.0, 1_650_000, 220_000, 210_000, 1_240_000, 360_000, 360, 280, 78),
    ("ENGR", "Engineering", "Engineering", "Undergraduate",
     185, 6660, 36, 14.0, 2_100_000, 380_000, 540_000, 2_180_000, 620_000, 560, 300, 84),
    ("MUSI", "Music", "Fine Arts", "Undergraduate",
     70, 3150, 16, 12.0, 1_150_000, 140_000, 70_000, 1_320_000, 290_000, 180, 150, 34),
    ("HIST", "History", "Arts & Sciences", "Undergraduate",
     80, 5600, 18, 8.0, 1_350_000, 90_000, 20_000, 760_000, 150_000, 190, 165, 36),
    ("CHEM", "Chemistry", "Arts & Sciences", "Undergraduate",
     90, 6300, 20, 10.0, 1_700_000, 200_000, 260_000, 1_240_000, 410_000, 230, 175, 40),
    ("MATH", "Mathematics", "Arts & Sciences", "Undergraduate",
     85, 7650, 19, 9.0, 1_600_000, 110_000, 50_000, 980_000, 170_000, 200, 170, 38),
    ("MBA", "Master of Business Administration", "Business", "Graduate",
     130, 3120, 88, 7.0, 980_000, 180_000, 60_000, 1_120_000, 260_000, 410, 300, 140),
    ("MSN", "Master of Science in Nursing", "Health Sciences", "Graduate",
     85, 2040, 54, 6.0, 720_000, 150_000, 90_000, 980_000, 240_000, 260, 180, 92),
]

# Shared facilities/IT/library/administration/student-services pool. Sized so the
# sample institution runs a believable ~10% surplus and a few faculty/lab-heavy
# programs land underwater once they carry their full share of overhead.
_OPERATIONS_POOL = 58_000_000.0


def _growth(fiscal_year: int) -> float:
    """Mild deterministic YoY factor so trends render (2025 = 1.00)."""
    return 1.0 + 0.03 * (fiscal_year - 2025)


def sample_programs(fiscal_year: int = 2025) -> list[ProgramInputs]:
    g = _growth(fiscal_year)
    programs: list[ProgramInputs] = []
    for (
        code, name, college, level, majors, sch, completions, fac_fte,
        aid, fees, other, instr, dept, apps, admits, deposits,
    ) in _BASE:
        rate = _GR_RATE if level == "Graduate" else _UG_RATE
        programs.append(
            ProgramInputs(
                program_code=code,
                program_name=name,
                college=college,
                degree_level=level,
                enrolled_majors=round(majors * g),
                student_credit_hours=round(sch * g, 1),
                completions=round(completions * g),
                faculty_fte=fac_fte,
                tuition_rate_per_credit_hour=rate,
                institutional_aid=round(aid * g, 2),
                fees_revenue=round(fees * g, 2),
                other_revenue=round(other * g, 2),
                instruction_cost=round(instr * g, 2),
                departmental_cost=round(dept * g, 2),
                applications=apps,
                admits=admits,
                deposits=deposits,
            )
        )
    return programs


def sample_institution(fiscal_year: int = 2025) -> InstitutionInputs:
    return InstitutionInputs(
        fiscal_year=fiscal_year,
        name="Sample University",
        university_operations_cost=round(_OPERATIONS_POOL * _growth(fiscal_year), 2),
    )
