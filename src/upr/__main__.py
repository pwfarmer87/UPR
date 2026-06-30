"""Command-line interface.

    python -m upr summary                       # print portfolio totals
    python -m upr template --out programs.csv   # write an import template
    python -m upr report --out report.html --excel report.xlsx

Source selection mirrors the env settings; ``--file`` imports a unified CSV/Excel
without touching the environment.
"""

from __future__ import annotations

import argparse
import sys

from upr.config import Settings
from upr.forecast import forecast_totals, watch_list
from upr.importing import template_csv
from upr.pipeline import run_review
from upr.reporting import build_excel_report, build_html_report
from upr.scenario import Scenario, compare_totals, run_scenario
from upr.trends import institution_trend, run_multiyear, yoy_summary


def _settings_from_args(args) -> Settings:
    s = Settings.from_env()
    if args.source:
        s.data_source = args.source
    if args.fy:
        s.fiscal_year = args.fy
    if args.driver:
        s.allocation_driver = args.driver
    if args.ops_cost is not None:
        s.operations_cost = args.ops_cost
    if getattr(args, "file", None):
        s.data_source = "file"
        s.import_file = args.file
    return s


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--source", choices=["mock", "file", "live"])
    p.add_argument("--file", help="unified CSV/Excel to import (sets source=file)")
    p.add_argument("--fy", type=int, help="fiscal year")
    p.add_argument("--driver", choices=["credit_hours", "headcount", "direct_cost"])
    p.add_argument("--ops-cost", type=float, dest="ops_cost",
                   help="university operations pool override")


def cmd_summary(args) -> int:
    result = run_review(_settings_from_args(args))
    t = result.totals()
    print(f"Source: {', '.join(result.sources_used)}  FY{result.fiscal_year}  "
          f"driver={result.allocation_driver}")
    print(f"Programs: {t['programs']}   Majors: {t['enrolled_majors']:,}")
    print(f"Revenue:  ${t['total_revenue']:,.0f}")
    print(f"Cost:     ${t['total_cost']:,.0f}  "
          f"(direct ${t['direct_cost']:,.0f} + overhead ${t['allocated_overhead']:,.0f})")
    print(f"Net:      ${t['net_margin']:,.0f}  ({t['net_margin_ratio']*100:.1f}%)")
    underwater = [f for f in result.financials if f.net_margin < 0]
    if underwater:
        print("Underwater after overhead: "
              + ", ".join(f.program_name for f in underwater))
    return 0


def cmd_template(args) -> int:
    csv = template_csv(args.source_kind)
    if args.out:
        with open(args.out, "w", newline="") as fh:
            fh.write(csv)
        print(f"Wrote {args.source_kind} import template -> {args.out}")
    else:
        sys.stdout.write(csv)
    return 0


def cmd_report(args) -> int:
    settings = _settings_from_args(args)
    result = run_review(settings)
    multiyear = run_multiyear(args.years, settings) if args.years else None
    html = build_html_report(result, multiyear=multiyear)
    with open(args.out, "w") as fh:
        fh.write(html)
    print(f"Wrote HTML report -> {args.out}")
    if args.excel:
        with open(args.excel, "wb") as fh:
            fh.write(build_excel_report(result, multiyear=multiyear))
        print(f"Wrote Excel report -> {args.excel}")
    return 0


def cmd_trends(args) -> int:
    settings = _settings_from_args(args)
    myr = run_multiyear(args.years, settings)
    print(f"Source: {', '.join(myr.latest.sources_used)}  "
          f"years: {', '.join(map(str, myr.years))}")
    it = institution_trend(myr)
    print("\nInstitution totals by year:")
    for _, r in it.iterrows():
        print(f"  FY{int(r['fiscal_year'])}: revenue ${r['total_revenue']:,.0f}  "
              f"net ${r['net_margin']:,.0f}  ({r['net_margin_ratio']*100:.1f}%)")
    summary = yoy_summary(myr, args.metric)
    print(f"\nBiggest movers by {args.metric} "
          f"(FY{min(myr.years)}→FY{max(myr.years)}):")
    for _, r in summary.head(5).iterrows():
        print(f"  {r['program_name']:<30} change {r['change']:>14,.0f}  "
              f"CAGR {r['cagr']*100:>6.1f}%")
    return 0


def cmd_forecast(args) -> int:
    settings = _settings_from_args(args)
    result = run_review(settings)
    rmap = None
    if args.estimate_retention:
        from dataclasses import replace

        from upr.retention import estimate_retention, retention_map
        prev = run_review(replace(settings, fiscal_year=result.fiscal_year - 1))
        rmap = retention_map(estimate_retention(prev, result))
    t = forecast_totals(result, retention_by_program=rmap)
    print(f"Source: {', '.join(result.sources_used)}  FY{result.fiscal_year} "
          f"-> FY{result.fiscal_year + 1} projection"
          + ("  (retention estimated from prior year)" if rmap else ""))
    print(f"Majors: {t['current_majors']:,} -> {t['projected_majors']:,}  "
          f"({t['projected_pct_change']*100:+.1f}%)")
    print(f"Projected revenue: ${t['projected_revenue']:,.0f}  "
          f"contribution ${t['projected_contribution_margin']:,.0f}")
    watch = watch_list(result, retention_by_program=rmap)
    if not watch.empty:
        print("\nWatch list:")
        for _, r in watch.iterrows():
            print(f"  [{r['watch_flag']}] {r['program_name']:<28} "
                  f"majors {r['enrolled_majors']} -> {r['projected_majors']} "
                  f"({r['projected_pct_change']*100:+.1f}%)  "
                  f"net ${r['net_margin']:,.0f}")
    return 0


def cmd_crosswalk(args) -> int:
    from upr.adapters import load_course_enrollments, load_net_revenue
    from upr.adapters.crosswalk import build_crosswalk_template, majors_reference

    revenue = load_net_revenue(args.net_revenue)
    course_df = load_course_enrollments(args.course_enrollments)
    template = build_crosswalk_template(course_df, revenue, args.year)
    template.to_csv(args.out, index=False)

    seeded = int((template["seeded"] == "exact").sum())
    total = len(template)
    print(f"Crosswalk template FY{args.year}: {total} subjects -> {args.out}")
    print(f"  auto-seeded (exact code match): {seeded}; "
          f"fill in the remaining {total - seeded}.")
    unmapped = template[template["program_code"] == ""].head(8)
    if not unmapped.empty:
        print("  Largest unmapped subjects (by SCH):")
        for _, r in unmapped.iterrows():
            print(f"    {r['subject']:6} {r['student_credit_hours']:>8,.0f} SCH")
    if args.majors_out:
        majors_reference(revenue, args.year).to_csv(args.majors_out, index=False)
        print(f"  Wrote valid program codes -> {args.majors_out}")
    return 0


def cmd_scenario(args) -> int:
    baseline = run_review(_settings_from_args(args))
    scenario = Scenario(
        tuition_change_pct=args.tuition,
        enrollment_change_pct=args.enrollment,
        aid_change_pct=args.aid,
        instruction_cost_change_pct=args.instruction,
        departmental_cost_change_pct=args.departmental,
        operations_cost_change_pct=args.operations,
    )
    result = run_scenario(baseline, scenario)
    ct = compare_totals(baseline, result)
    print(f"Source: {', '.join(baseline.sources_used)}  FY{baseline.fiscal_year}")
    print(f"Revenue:    ${ct['revenue_base']:,.0f} -> ${ct['revenue_scenario']:,.0f}"
          f"  ({ct['revenue_delta']:+,.0f})")
    print(f"Net margin: ${ct['net_margin_base']:,.0f} -> ${ct['net_margin_scenario']:,.0f}"
          f"  ({ct['net_margin_delta']:+,.0f})")
    print(f"Margin %:   {ct['net_margin_ratio_base']*100:.1f}% -> "
          f"{ct['net_margin_ratio_scenario']*100:.1f}%")
    return 0


def cmd_ingest(args) -> int:
    from upr.adapters import (
        build_program_inputs,
        load_course_enrollments,
        load_net_revenue,
        load_program_names,
        to_import_dataframe,
    )
    from upr.adapters.crosswalk import load_subject_map

    revenue = load_net_revenue(args.net_revenue)
    names = load_program_names(args.program_codes) if args.program_codes \
        else load_program_names()
    course_df = None
    subject_map = None
    if args.course_enrollments and args.subject_map:
        course_df = load_course_enrollments(args.course_enrollments)
        subject_map = load_subject_map(args.subject_map)

    registrations = dept_costs = None
    if args.registrations:
        from upr.adapters.registrations import load_registrations
        registrations = load_registrations(args.registrations)
    if args.department_costs:
        from upr.adapters.cost import load_department_costs
        dept_costs = load_department_costs(args.department_costs)

    programs = build_program_inputs(
        revenue, args.year, course_df=course_df, subject_to_program=subject_map,
        program_names=names, registrations_df=registrations,
        department_costs=dept_costs,
    )
    out_df = to_import_dataframe(programs)
    out_df.to_csv(args.out, index=False)
    net = (out_df["gross_tuition_revenue"] - out_df["institutional_aid"]).sum()
    print(f"Ingested FY{args.year}: {len(programs)} programs -> {args.out}")
    print(f"  headcount rows: {int(out_df['enrolled_majors'].sum()):,}  "
          f"gross ${out_df['gross_tuition_revenue'].sum():,.0f}  "
          f"aid ${out_df['institutional_aid'].sum():,.0f}  net ${net:,.0f}")
    print("  Load it with: python -m upr summary --file "
          f"{args.out} --driver headcount --ops-cost <pool>")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="upr", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_sum = sub.add_parser("summary", help="print portfolio totals")
    _add_common(p_sum)
    p_sum.set_defaults(func=cmd_summary)

    p_tmpl = sub.add_parser("template", help="write a CSV import template")
    p_tmpl.add_argument("--source", dest="source_kind", default="all",
                        choices=["all", "jenzabar", "netsuite", "slate"])
    p_tmpl.add_argument("--out", help="output path (default: stdout)")
    p_tmpl.set_defaults(func=cmd_template)

    p_rep = sub.add_parser("report", help="generate HTML (and optional Excel) report")
    _add_common(p_rep)
    p_rep.add_argument("--out", required=True, help="HTML output path")
    p_rep.add_argument("--excel", help="also write an .xlsx workbook here")
    p_rep.add_argument("--years", type=int, nargs="+",
                       help="include a multi-year trend section for these years")
    p_rep.set_defaults(func=cmd_report)

    p_tr = sub.add_parser("trends", help="multi-year trend summary")
    _add_common(p_tr)
    p_tr.add_argument("--years", type=int, nargs="+", default=[2024, 2025, 2026])
    p_tr.add_argument("--metric", default="net_margin")
    p_tr.set_defaults(func=cmd_trends)

    p_fc = sub.add_parser("forecast", help="next-year enrollment/margin forecast")
    _add_common(p_fc)
    p_fc.add_argument("--estimate-retention", action="store_true",
                      dest="estimate_retention",
                      help="estimate per-program retention from the prior year")
    p_fc.set_defaults(func=cmd_forecast)

    p_in = sub.add_parser(
        "ingest", help="build a UPR import CSV from institutional report exports")
    p_in.add_argument("--net-revenue", required=True, dest="net_revenue",
                      help="Net Revenue/Discounts/Fees by Term export (xlsx)")
    p_in.add_argument("--year", type=int, required=True, help="academic year")
    p_in.add_argument("--course-enrollments", dest="course_enrollments",
                      help="Course enrollments export (xlsx), for SCH")
    p_in.add_argument("--subject-map", dest="subject_map",
                      help="CSV mapping course subject -> program_code (for SCH)")
    p_in.add_argument("--program-codes", dest="program_codes",
                      help="override the bundled program_code->name roster (CSV)")
    p_in.add_argument("--registrations", dest="registrations",
                      help="student course-registrations export (accurate SCH-by-major)")
    p_in.add_argument("--department-costs", dest="department_costs",
                      help="department/subject -> instruction cost CSV (GL or payroll)")
    p_in.add_argument("--out", required=True, help="output import CSV path")
    p_in.set_defaults(func=cmd_ingest)

    p_cw = sub.add_parser(
        "crosswalk", help="scaffold a subject -> program (major code) crosswalk")
    p_cw.add_argument("--net-revenue", required=True, dest="net_revenue",
                      help="Net Revenue export (xlsx) — source of valid major codes")
    p_cw.add_argument("--course-enrollments", required=True, dest="course_enrollments",
                      help="Course enrollments export (xlsx) — source of subjects")
    p_cw.add_argument("--year", type=int, required=True, help="academic year")
    p_cw.add_argument("--out", required=True, help="output crosswalk CSV path")
    p_cw.add_argument("--majors-out", dest="majors_out",
                      help="also write the valid program-code reference here")
    p_cw.set_defaults(func=cmd_crosswalk)

    p_sc = sub.add_parser("scenario", help="what-if margin impact of global levers")
    _add_common(p_sc)
    for name in ("tuition", "enrollment", "aid", "instruction", "departmental",
                 "operations"):
        p_sc.add_argument(f"--{name}", type=float, default=0.0,
                          help=f"{name} change as a fraction (e.g. 0.05 = +5%%)")
    p_sc.set_defaults(func=cmd_scenario)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
