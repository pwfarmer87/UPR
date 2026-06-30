"""Reporting: turn a ReviewResult into shareable reports.

  * ``build_html_report``  -> a standalone, print-to-PDF-friendly HTML string.
  * ``build_excel_report`` -> a multi-sheet .xlsx workbook (bytes).
  * ``by_college``         -> college-level rollup DataFrame (also used by the UI).

No template engine — the HTML is assembled from f-strings so the package stays
dependency-light (Excel needs only openpyxl, already a pandas extra).
"""

from __future__ import annotations

import html
import io

import pandas as pd

from upr.pipeline import ReviewResult

_REPORT_COLUMNS = [
    "program_code", "program_name", "college", "degree_level",
    "enrolled_majors", "student_credit_hours", "completions",
    "total_revenue", "direct_cost", "allocated_overhead", "total_cost",
    "contribution_margin", "net_margin", "net_margin_ratio",
    "revenue_per_student", "cost_per_student", "cost_per_credit_hour",
]


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def by_college(result: ReviewResult) -> pd.DataFrame:
    """Aggregate the portfolio to one row per college."""
    df = result.to_frame()
    grouped = (
        df.groupby("college", as_index=False)
        .agg(
            programs=("program_code", "count"),
            enrolled_majors=("enrolled_majors", "sum"),
            total_revenue=("total_revenue", "sum"),
            total_cost=("total_cost", "sum"),
            net_margin=("net_margin", "sum"),
        )
        .sort_values("net_margin", ascending=False)
    )
    grouped["net_margin_ratio"] = (
        grouped["net_margin"] / grouped["total_revenue"].replace(0, pd.NA)
    ).fillna(0.0)
    return grouped


# --------------------------------------------------------------------------- #
# Excel
# --------------------------------------------------------------------------- #
def build_excel_report(result: ReviewResult) -> bytes:
    """Multi-sheet workbook: Summary, Programs, Underwater, By College."""
    df = result.to_frame()
    totals = result.totals()
    summary = pd.DataFrame(
        {
            "Metric": [
                "Fiscal year", "Data source", "Programs", "Enrolled majors",
                "Student credit hours", "Total revenue", "Direct cost",
                "Allocated overhead", "Total cost", "Contribution margin",
                "Net margin", "Net margin ratio",
            ],
            "Value": [
                result.fiscal_year, ", ".join(result.sources_used),
                totals["programs"], totals["enrolled_majors"],
                totals["student_credit_hours"], totals["total_revenue"],
                totals["direct_cost"], totals["allocated_overhead"],
                totals["total_cost"], totals["contribution_margin"],
                totals["net_margin"], totals["net_margin_ratio"],
            ],
        }
    )
    programs = df[_REPORT_COLUMNS].sort_values("net_margin", ascending=False)
    underwater = programs[programs["net_margin"] < 0]
    college = by_college(result)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        programs.to_excel(writer, sheet_name="Programs", index=False)
        underwater.to_excel(writer, sheet_name="Underwater", index=False)
        college.to_excel(writer, sheet_name="By College", index=False)
        for sheet in writer.sheets.values():
            for column_cells in sheet.columns:
                width = max(len(str(c.value or "")) for c in column_cells) + 2
                sheet.column_dimensions[column_cells[0].column_letter].width = min(
                    width, 40
                )
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
_CSS = """
body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
       color: #1a1a1a; margin: 32px; }
h1 { margin-bottom: 4px; } .sub { color: #666; margin-top: 0; }
.kpis { display: flex; gap: 16px; flex-wrap: wrap; margin: 24px 0; }
.kpi { border: 1px solid #e3e3e3; border-radius: 10px; padding: 14px 18px; min-width: 150px; }
.kpi .label { font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: .04em; }
.kpi .value { font-size: 22px; font-weight: 600; margin-top: 4px; }
.pos { color: #1e7d3c; } .neg { color: #b03030; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 28px; font-size: 13px; }
th, td { border-bottom: 1px solid #ececec; padding: 7px 10px; text-align: right; }
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align: left; }
thead th { border-bottom: 2px solid #ccc; background: #fafafa; }
tr.under td { background: #fdf3f3; }
h2 { margin-top: 28px; border-bottom: 2px solid #eee; padding-bottom: 4px; }
.note { color: #777; font-size: 12px; }
@media print { body { margin: 0; } .kpi { break-inside: avoid; } }
"""


def _rows_html(df: pd.DataFrame, underwater_flag: bool = True) -> str:
    out = []
    for _, r in df.iterrows():
        cls = " class=\"under\"" if underwater_flag and r["net_margin"] < 0 else ""
        nm_cls = "neg" if r["net_margin"] < 0 else "pos"
        out.append(
            f"<tr{cls}>"
            f"<td>{html.escape(str(r['program_code']))}</td>"
            f"<td>{html.escape(str(r['program_name']))}</td>"
            f"<td>{html.escape(str(r['college']))}</td>"
            f"<td>{r['enrolled_majors']:,}</td>"
            f"<td>{r['student_credit_hours']:,.0f}</td>"
            f"<td>{_money(r['total_revenue'])}</td>"
            f"<td>{_money(r['direct_cost'])}</td>"
            f"<td>{_money(r['allocated_overhead'])}</td>"
            f"<td>{_money(r['total_cost'])}</td>"
            f"<td class=\"{nm_cls}\">{_money(r['net_margin'])}</td>"
            f"<td class=\"{nm_cls}\">{_pct(r['net_margin_ratio'])}</td>"
            f"<td>{_money(r['cost_per_student'])}</td>"
            "</tr>"
        )
    return "\n".join(out)


_TABLE_HEAD = (
    "<thead><tr><th>Code</th><th>Program</th><th>College</th><th>Majors</th>"
    "<th>SCH</th><th>Revenue</th><th>Direct cost</th><th>Overhead</th>"
    "<th>Total cost</th><th>Net margin</th><th>Margin %</th>"
    "<th>Cost/student</th></tr></thead>"
)


def build_html_report(result: ReviewResult, *, title: str = "Program Financial Review") -> str:
    df = result.to_frame().sort_values("net_margin", ascending=False)
    totals = result.totals()
    underwater = df[df["net_margin"] < 0]
    college = by_college(result)
    nm_cls = "pos" if totals["net_margin"] >= 0 else "neg"

    def kpi(label: str, value: str, cls: str = "") -> str:
        return (
            f'<div class="kpi"><div class="label">{label}</div>'
            f'<div class="value {cls}">{value}</div></div>'
        )

    kpis = "".join([
        kpi("Total revenue", _money(totals["total_revenue"])),
        kpi("Total cost", _money(totals["total_cost"])),
        kpi("Net margin", _money(totals["net_margin"]), nm_cls),
        kpi("Net margin %", _pct(totals["net_margin_ratio"]), nm_cls),
        kpi("Enrolled majors", f"{totals['enrolled_majors']:,}"),
        kpi("Programs", str(totals["programs"])),
    ])

    college_rows = "".join(
        f"<tr><td>{html.escape(str(r['college']))}</td>"
        f"<td>{int(r['programs'])}</td>"
        f"<td>{int(r['enrolled_majors']):,}</td>"
        f"<td>{_money(r['total_revenue'])}</td>"
        f"<td>{_money(r['total_cost'])}</td>"
        f"<td class=\"{'pos' if r['net_margin'] >= 0 else 'neg'}\">{_money(r['net_margin'])}</td>"
        f"<td>{_pct(r['net_margin_ratio'])}</td></tr>"
        for _, r in college.iterrows()
    )

    underwater_section = ""
    if not underwater.empty:
        underwater_section = (
            "<h2>Programs underwater after overhead</h2>"
            "<p class='note'>Positive contribution margin but negative net margin: "
            "covers direct costs but not its share of university operations.</p>"
            f"<table>{_TABLE_HEAD}<tbody>{_rows_html(underwater)}</tbody></table>"
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{html.escape(title)}</title><style>{_CSS}</style></head>
<body>
<h1>{html.escape(title)}</h1>
<p class="sub">Fiscal year {result.fiscal_year} &middot; overhead allocated by
{html.escape(result.allocation_driver.replace('_', ' '))}
&middot; source: {html.escape(', '.join(result.sources_used))}</p>
<div class="kpis">{kpis}</div>
{underwater_section}
<h2>By college</h2>
<table><thead><tr><th>College</th><th>Programs</th><th>Majors</th><th>Revenue</th>
<th>Total cost</th><th>Net margin</th><th>Margin %</th></tr></thead>
<tbody>{college_rows}</tbody></table>
<h2>All programs</h2>
<table>{_TABLE_HEAD}<tbody>{_rows_html(df)}</tbody></table>
<p class="note">Generated by UPR — University Program (Margin) Review.</p>
</body></html>"""
