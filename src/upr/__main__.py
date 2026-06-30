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
    result = run_review(_settings_from_args(args))
    t = forecast_totals(result)
    print(f"Source: {', '.join(result.sources_used)}  FY{result.fiscal_year} "
          f"-> FY{result.fiscal_year + 1} projection")
    print(f"Majors: {t['current_majors']:,} -> {t['projected_majors']:,}  "
          f"({t['projected_pct_change']*100:+.1f}%)")
    print(f"Projected revenue: ${t['projected_revenue']:,.0f}  "
          f"contribution ${t['projected_contribution_margin']:,.0f}")
    watch = watch_list(result)
    if not watch.empty:
        print("\nWatch list:")
        for _, r in watch.iterrows():
            print(f"  [{r['watch_flag']}] {r['program_name']:<28} "
                  f"majors {r['enrolled_majors']} -> {r['projected_majors']} "
                  f"({r['projected_pct_change']*100:+.1f}%)  "
                  f"net ${r['net_margin']:,.0f}")
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
    p_fc.set_defaults(func=cmd_forecast)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
