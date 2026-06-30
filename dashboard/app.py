"""Streamlit dashboard for university program financial review.

Run:  streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Make the src package importable when run via `streamlit run`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from upr.config import Settings  # noqa: E402
from upr.pipeline import run_review  # noqa: E402

st.set_page_config(page_title="UPR — Program Financial Review", layout="wide")

CURRENCY = "${:,.0f}"


def money(x: float) -> str:
    return CURRENCY.format(x)


@st.cache_data(show_spinner=False)
def load(fiscal_year: int, driver: str, data_source: str):
    settings = Settings.from_env()
    settings.fiscal_year = fiscal_year
    settings.allocation_driver = driver
    settings.data_source = data_source
    result = run_review(settings)
    return result.to_frame(), result.totals(), result.sources_used


# ---- Sidebar controls ----
st.sidebar.title("UPR")
st.sidebar.caption("University Program (Margin) Review")
base_settings = Settings.from_env()
fiscal_year = st.sidebar.selectbox(
    "Fiscal year", [2024, 2025, 2026], index=1
)
driver = st.sidebar.selectbox(
    "Overhead allocation driver",
    ["credit_hours", "headcount", "direct_cost"],
    index=["credit_hours", "headcount", "direct_cost"].index(
        base_settings.allocation_driver
    )
    if base_settings.allocation_driver in {"credit_hours", "headcount", "direct_cost"}
    else 0,
    help="How the shared university operations pool is spread across programs.",
)
data_source = st.sidebar.radio(
    "Data source", ["mock", "live"],
    index=0 if base_settings.data_source != "live" else 1,
    help="`live` uses authorized connectors; falls back to sample data if none.",
)

df, totals, sources = load(fiscal_year, driver, data_source)
st.sidebar.success("Sources: " + ", ".join(sources))
if "mock" in sources:
    st.sidebar.info(
        "Showing **sample data**. Authorize NetSuite/Slate/Jenzabar and switch "
        "to `live` for real figures."
    )

# ---- Header KPIs ----
st.title("Program Financial Review")
st.caption(f"Fiscal year {fiscal_year} · overhead allocated by {driver.replace('_', ' ')}")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total revenue", money(totals["total_revenue"]))
c2.metric("Total cost", money(totals["total_cost"]))
c3.metric(
    "Net margin",
    money(totals["net_margin"]),
    f"{totals['net_margin_ratio']*100:.1f}%",
)
c4.metric("Enrolled majors", f"{totals['enrolled_majors']:,}")
c5.metric("Programs", totals["programs"])

st.divider()

# ---- Margin by program ----
left, right = st.columns([3, 2])

with left:
    st.subheader("Net margin by program")
    chart_df = df.sort_values("net_margin")
    fig = px.bar(
        chart_df,
        x="net_margin",
        y="program_name",
        orientation="h",
        color="net_margin",
        color_continuous_scale=["#c0392b", "#f1c40f", "#27ae60"],
        labels={"net_margin": "Net margin ($)", "program_name": ""},
    )
    fig.update_layout(coloraxis_showscale=False, height=520, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Contribution vs. net margin")
    st.caption("Above the line earns its overhead; below it does not.")
    scatter = px.scatter(
        df,
        x="contribution_margin",
        y="net_margin",
        size="total_revenue",
        color="college",
        hover_name="program_name",
        labels={
            "contribution_margin": "Contribution margin ($)",
            "net_margin": "Net margin ($)",
        },
    )
    scatter.add_hline(y=0, line_dash="dash", line_color="gray")
    scatter.update_layout(height=520, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(scatter, use_container_width=True)

st.divider()

# ---- Programs that lose money after overhead ----
underwater = df[df["net_margin"] < 0].sort_values("net_margin")
if not underwater.empty:
    st.subheader("⚠️ Programs underwater after overhead")
    st.caption(
        "Positive contribution margin but negative net margin means the program "
        "covers its own direct costs but not its share of university operations."
    )
    st.dataframe(
        underwater[
            ["program_name", "college", "enrolled_majors", "total_revenue",
             "direct_cost", "allocated_overhead", "net_margin", "net_margin_per_student"]
        ].style.format({
            "total_revenue": "${:,.0f}", "direct_cost": "${:,.0f}",
            "allocated_overhead": "${:,.0f}", "net_margin": "${:,.0f}",
            "net_margin_per_student": "${:,.0f}",
        }),
        use_container_width=True, hide_index=True,
    )

# ---- Full detail table ----
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
    use_container_width=True, hide_index=True, height=500,
)

st.download_button(
    "Download as CSV",
    df.to_csv(index=False).encode("utf-8"),
    file_name=f"program_financial_review_{fiscal_year}.csv",
    mime="text/csv",
)
