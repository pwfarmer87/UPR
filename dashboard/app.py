"""Streamlit dashboard for university program financial review.

Run:  streamlit run dashboard/app.py

Three tabs:
  * Import   — upload CSV/Excel (unified or per-source) or use sample data
  * Dashboard — KPIs, charts, underwater programs, detail table
  * Reports  — download formatted HTML / Excel reports
"""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

# Make the src package importable when run via `streamlit run`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from upr.config import Settings  # noqa: E402
from upr.importing import ImportError_, read_programs, template_csv  # noqa: E402
from upr.models import InstitutionInputs  # noqa: E402
from upr.pipeline import compute_review, merge_sources, run_review  # noqa: E402
from upr.reporting import (  # noqa: E402
    build_excel_report,
    build_html_report,
    by_college,
)

st.set_page_config(page_title="UPR — Program Financial Review", layout="wide")


def money(x: float) -> str:
    return f"${x:,.0f}"


# --------------------------------------------------------------------------- #
# Sidebar — shared settings
# --------------------------------------------------------------------------- #
st.sidebar.title("UPR")
st.sidebar.caption("University Program (Margin) Review")

base = Settings.from_env()
drivers = ["credit_hours", "headcount", "direct_cost"]
fiscal_year = st.sidebar.selectbox("Fiscal year", [2024, 2025, 2026], index=1)
driver = st.sidebar.selectbox(
    "Overhead allocation driver", drivers,
    index=drivers.index(base.allocation_driver) if base.allocation_driver in drivers else 0,
    help="How the shared university operations pool is spread across programs.",
)
ops_cost = st.sidebar.number_input(
    "University operations pool ($)", min_value=0, value=58_000_000, step=1_000_000,
    help="Shared facilities/IT/library/admin/student-services cost to allocate. "
    "Used for imported data; sample data supplies its own.",
)


def _settings(data_source: str, operations_cost: float | None) -> Settings:
    s = Settings.from_env()
    s.fiscal_year = fiscal_year
    s.allocation_driver = driver
    s.data_source = data_source
    s.operations_cost = operations_cost
    return s


def _current_review():
    """Return a ReviewResult from imported data if present, else sample data."""
    imported = st.session_state.get("imported_inputs")
    if imported:
        inst = InstitutionInputs(
            fiscal_year=fiscal_year, university_operations_cost=float(ops_cost)
        )
        return compute_review(
            imported, inst, _settings("file", float(ops_cost)),
            sources_used=st.session_state.get("imported_sources", ["import"]),
        )
    return run_review(_settings("mock", None))


tab_import, tab_dash, tab_reports = st.tabs(["📥 Import", "📊 Dashboard", "📄 Reports"])

# --------------------------------------------------------------------------- #
# Import tab
# --------------------------------------------------------------------------- #
with tab_import:
    st.header("Import program data")
    st.write(
        "Upload spreadsheet exports before the live APIs are connected. Use one "
        "**unified** file, or separate **per-source** files that merge by program "
        "code. Headers are matched leniently (e.g. `SCH`, `Major Code` work)."
    )

    mode = st.radio("File layout", ["Unified file", "Per-source files"], horizontal=True)

    with st.expander("Download blank templates"):
        cols = st.columns(4)
        for col, kind in zip(cols, ["all", "jenzabar", "netsuite", "slate"]):
            col.download_button(
                f"{kind}.csv", template_csv(kind).encode("utf-8"),
                file_name=f"upr_template_{kind}.csv", mime="text/csv",
                key=f"tmpl_{kind}",
            )

    def _ingest(uploaded, source):
        return read_programs(uploaded.getvalue(), filename=uploaded.name, source=source)

    try:
        if mode == "Unified file":
            up = st.file_uploader("Unified file (CSV or Excel)", type=["csv", "xlsx", "xls"])
            if up is not None:
                programs = _ingest(up, "all")
                st.session_state["imported_inputs"] = programs
                st.session_state["imported_sources"] = [f"import:{up.name}"]
                st.success(f"Loaded {len(programs)} programs from {up.name}.")
        else:
            contributions = []
            for source in ["jenzabar", "netsuite", "slate"]:
                up = st.file_uploader(
                    f"{source.title()} export (CSV or Excel)",
                    type=["csv", "xlsx", "xls"], key=f"up_{source}",
                )
                if up is not None:
                    contributions.append((source, _ingest(up, source)))
            if contributions:
                merged = merge_sources(contributions)
                st.session_state["imported_inputs"] = merged
                st.session_state["imported_sources"] = [
                    f"import:{s}" for s, _ in contributions
                ]
                st.success(
                    f"Merged {len(merged)} programs from "
                    f"{', '.join(s for s, _ in contributions)}."
                )
    except ImportError_ as exc:
        st.error(f"Import failed: {exc}")

    if st.session_state.get("imported_inputs"):
        st.info("Using **imported data** across the Dashboard and Reports tabs.")
        if st.button("Clear imported data (revert to sample)"):
            st.session_state.pop("imported_inputs", None)
            st.session_state.pop("imported_sources", None)
            st.rerun()
    else:
        st.caption("No file loaded — Dashboard and Reports show **sample data**.")

# Build the review once for the remaining tabs.
result = _current_review()
df = result.to_frame()
totals = result.totals()

# --------------------------------------------------------------------------- #
# Dashboard tab
# --------------------------------------------------------------------------- #
with tab_dash:
    st.title("Program Financial Review")
    st.caption(
        f"Fiscal year {fiscal_year} · overhead by {driver.replace('_', ' ')} · "
        f"source: {', '.join(result.sources_used)}"
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total revenue", money(totals["total_revenue"]))
    c2.metric("Total cost", money(totals["total_cost"]))
    c3.metric("Net margin", money(totals["net_margin"]),
              f"{totals['net_margin_ratio']*100:.1f}%")
    c4.metric("Enrolled majors", f"{totals['enrolled_majors']:,}")
    c5.metric("Programs", totals["programs"])
    st.divider()

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Net margin by program")
        chart_df = df.sort_values("net_margin")
        fig = px.bar(
            chart_df, x="net_margin", y="program_name", orientation="h",
            color="net_margin",
            color_continuous_scale=["#c0392b", "#f1c40f", "#27ae60"],
            labels={"net_margin": "Net margin ($)", "program_name": ""},
        )
        fig.update_layout(coloraxis_showscale=False, height=520,
                          margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Contribution vs. net margin")
        st.caption("Above the line earns its overhead; below it does not.")
        scatter = px.scatter(
            df, x="contribution_margin", y="net_margin", size="total_revenue",
            color="college", hover_name="program_name",
            labels={"contribution_margin": "Contribution margin ($)",
                    "net_margin": "Net margin ($)"},
        )
        scatter.add_hline(y=0, line_dash="dash", line_color="gray")
        scatter.update_layout(height=520, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(scatter, use_container_width=True)

    st.divider()
    underwater = df[df["net_margin"] < 0].sort_values("net_margin")
    if not underwater.empty:
        st.subheader("⚠️ Programs underwater after overhead")
        st.caption(
            "Positive contribution margin but negative net margin: covers direct "
            "costs but not its share of university operations."
        )
        st.dataframe(
            underwater[[
                "program_name", "college", "enrolled_majors", "total_revenue",
                "direct_cost", "allocated_overhead", "net_margin",
                "net_margin_per_student",
            ]].style.format({
                "total_revenue": "${:,.0f}", "direct_cost": "${:,.0f}",
                "allocated_overhead": "${:,.0f}", "net_margin": "${:,.0f}",
                "net_margin_per_student": "${:,.0f}",
            }),
            use_container_width=True, hide_index=True,
        )

    st.subheader("By college")
    college = by_college(result)
    st.dataframe(
        college.style.format({
            "total_revenue": "${:,.0f}", "total_cost": "${:,.0f}",
            "net_margin": "${:,.0f}", "net_margin_ratio": "{:.1%}",
        }),
        use_container_width=True, hide_index=True,
    )

    st.subheader("All programs")
    display_cols = [
        "program_code", "program_name", "college", "degree_level",
        "enrolled_majors", "student_credit_hours", "completions",
        "total_revenue", "direct_cost", "allocated_overhead", "total_cost",
        "contribution_margin", "net_margin", "net_margin_ratio",
        "revenue_per_student", "cost_per_student", "cost_per_credit_hour",
    ]
    st.dataframe(
        df[display_cols].sort_values("net_margin", ascending=False).style.format({
            "student_credit_hours": "{:,.0f}",
            "total_revenue": "${:,.0f}", "direct_cost": "${:,.0f}",
            "allocated_overhead": "${:,.0f}", "total_cost": "${:,.0f}",
            "contribution_margin": "${:,.0f}", "net_margin": "${:,.0f}",
            "net_margin_ratio": "{:.1%}",
            "revenue_per_student": "${:,.0f}", "cost_per_student": "${:,.0f}",
            "cost_per_credit_hour": "${:,.0f}",
        }),
        use_container_width=True, hide_index=True, height=480,
    )

# --------------------------------------------------------------------------- #
# Reports tab
# --------------------------------------------------------------------------- #
with tab_reports:
    st.header("Reports")
    st.write(
        "Generate a shareable report for the current fiscal year, driver, and "
        "data source. The HTML report prints cleanly to PDF from your browser."
    )
    fname = f"program_financial_review_{fiscal_year}"

    c1, c2, c3 = st.columns(3)
    c1.download_button(
        "⬇️ HTML report", build_html_report(result).encode("utf-8"),
        file_name=f"{fname}.html", mime="text/html",
    )
    c2.download_button(
        "⬇️ Excel workbook", build_excel_report(result),
        file_name=f"{fname}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    c3.download_button(
        "⬇️ CSV (programs)", df.to_csv(index=False).encode("utf-8"),
        file_name=f"{fname}.csv", mime="text/csv",
    )

    st.divider()
    st.subheader("Report preview")
    st.components.v1.html(build_html_report(result), height=600, scrolling=True)
