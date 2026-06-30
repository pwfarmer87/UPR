"""Streamlit dashboard for university program financial review.

Run:  streamlit run dashboard/app.py

Tabs: Import · Dashboard · Trends & Forecast · Faculty · Scenario · Reports (+ Admin).
Optional login + roles gate the action tabs when a user store is configured.
"""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

# Make the src package importable when run via `streamlit run`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from upr import auth  # noqa: E402
from upr.config import Settings  # noqa: E402
from upr.faculty import (  # noqa: E402
    aggregate_faculty,
    apply_faculty_to_inputs,
    faculty_template_csv,
    read_faculty,
    rollup_frame,
)
from upr.forecast import ForecastAssumptions, forecast_frame, forecast_totals  # noqa: E402
from upr.importing import ImportError_, read_programs, template_csv  # noqa: E402
from upr.mapping_config import get_mapping  # noqa: E402
from upr.models import InstitutionInputs  # noqa: E402
from upr.pipeline import compute_review, merge_sources, run_review  # noqa: E402
from upr.reporting import (  # noqa: E402
    build_excel_report,
    build_html_report,
    by_college,
    by_department,
)
from upr.retention import (  # noqa: E402
    estimate_from_multiyear,
    retention_frame,
    retention_map,
)
from upr.sample_data import sample_faculty  # noqa: E402
from upr.scenario import Scenario, compare, compare_totals, run_scenario  # noqa: E402
from upr.storage import SnapshotStore  # noqa: E402
from upr.trends import (  # noqa: E402
    MultiYearReview,
    institution_trend,
    run_multiyear,
    trend_frame,
    yoy_summary,
)

st.set_page_config(page_title="UPR — Program Financial Review", layout="wide")


def money(x: float) -> str:
    return f"${x:,.0f}"


# --------------------------------------------------------------------------- #
# Authentication gate (active only when a user store is configured)
# --------------------------------------------------------------------------- #
def _login_gate():
    """Return the current User, or None when auth is disabled (open mode)."""
    if not auth.auth_enabled():
        return None
    if "user" in st.session_state:
        return st.session_state["user"]
    st.title("UPR — sign in")
    users = auth.load_users(auth.users_file_path())
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in"):
            user = auth.authenticate(username, password, users)
            if user:
                st.session_state["user"] = user
                st.rerun()
            else:
                st.error("Invalid username or password.")
    st.stop()


USER = _login_gate()


def can(capability: str) -> bool:
    """Capability check — always True in open mode, role-based when auth is on."""
    return USER is None or USER.can(capability)


class _SkipImport(Exception):
    """Internal: skip the import block when the role lacks the capability."""


# --------------------------------------------------------------------------- #
# Sidebar — shared settings
# --------------------------------------------------------------------------- #
st.sidebar.title("UPR")
st.sidebar.caption("University Program (Margin) Review")

if USER is not None:
    st.sidebar.success(f"{USER.name} · {USER.role}")
    if st.sidebar.button("Sign out"):
        del st.session_state["user"]
        st.rerun()

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


def _faculty_payroll():
    """Uploaded faculty payroll if present, else the sample roster."""
    return st.session_state.get("faculty_payroll") or sample_faculty(fiscal_year)


def _current_review():
    """Return a ReviewResult from imported data if present, else sample data.

    When 'use payroll cost' is on, instruction cost & faculty FTE are rebuilt
    from the faculty payroll before computing.
    """
    imported = st.session_state.get("imported_inputs")
    use_payroll = st.session_state.get("use_payroll_cost", False)
    if imported:
        inst = InstitutionInputs(
            fiscal_year=fiscal_year, university_operations_cost=float(ops_cost)
        )
        inputs = imported
        sources = list(st.session_state.get("imported_sources", ["import"]))
        if use_payroll:
            inputs = apply_faculty_to_inputs(inputs, _faculty_payroll())
            sources.append("faculty")
        return compute_review(inputs, inst, _settings("file", float(ops_cost)),
                              sources_used=sources)

    base_result = run_review(_settings("mock", None))
    if use_payroll:
        inputs = apply_faculty_to_inputs(base_result.inputs, _faculty_payroll())
        return compute_review(
            inputs, base_result.institution, _settings("mock", None),
            sources_used=[*base_result.sources_used, "faculty"],
        )
    return base_result


_tab_labels = ["📥 Import", "📊 Dashboard", "📈 Trends & Forecast",
               "👤 Faculty", "🔮 Scenario", "📄 Reports"]
if can("admin"):
    _tab_labels.append("⚙️ Admin")
_tabs = st.tabs(_tab_labels)
tab_import, tab_dash, tab_trends, tab_faculty, tab_scenario, tab_reports = _tabs[:6]
tab_admin = _tabs[6] if can("admin") else None

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

    if not can("import"):
        st.warning("Your role can view results but not import data.")
    try:
        if not can("import"):
            raise _SkipImport
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
    except _SkipImport:
        pass
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

    st.divider()
    st.subheader("Faculty payroll (optional)")
    st.write(
        "Upload per-faculty payroll to rebuild **instruction cost** and "
        "**faculty FTE** from real compensation (one row per faculty-program "
        "assignment; joint appointments split by `effort`). See the **Faculty** tab."
    )
    st.download_button(
        "faculty_template.csv", faculty_template_csv().encode("utf-8"),
        file_name="upr_faculty_template.csv", mime="text/csv", key="tmpl_faculty",
    )
    if can("import"):
        fac_up = st.file_uploader(
            "Faculty payroll (CSV or Excel)", type=["csv", "xlsx", "xls"],
            key="up_faculty",
        )
        if fac_up is not None:
            try:
                payroll = read_faculty(fac_up.getvalue(), filename=fac_up.name)
                st.session_state["faculty_payroll"] = payroll
                st.success(f"Loaded payroll for {len(payroll)} faculty assignments.")
            except ImportError_ as exc:
                st.error(f"Faculty import failed: {exc}")
        if st.session_state.get("faculty_payroll") and st.button("Clear faculty payroll"):
            st.session_state.pop("faculty_payroll", None)
            st.rerun()
    st.checkbox(
        "Use payroll-derived instruction cost in the model",
        key="use_payroll_cost",
        help="Overrides each program's instruction cost & faculty FTE with the "
        "faculty payroll roll-up (uploaded payroll, or the sample roster).",
    )

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

    _fmt = {
        "total_revenue": "${:,.0f}", "total_cost": "${:,.0f}",
        "net_margin": "${:,.0f}", "net_margin_ratio": "{:.1%}",
    }
    dept = by_department(result)
    has_dept = dept["department"].astype(str).str.strip().any()
    if has_dept:
        gcol, gdep = st.columns(2)
        gcol.subheader("By college")
        gcol.dataframe(by_college(result).style.format(_fmt),
                       use_container_width=True, hide_index=True)
        gdep.subheader("By department")
        gdep.dataframe(dept.style.format(_fmt),
                       use_container_width=True, hide_index=True)
    else:
        st.subheader("By college")
        st.dataframe(by_college(result).style.format(_fmt),
                     use_container_width=True, hide_index=True)

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
# Trends & Forecast tab
# --------------------------------------------------------------------------- #
with tab_trends:
    st.title("Trends & Forecast")
    imported = bool(st.session_state.get("imported_inputs"))

    st.subheader("Multi-year trend")
    if imported:
        st.info(
            "Multi-year trends need a per-year history. Imported data is a single "
            "snapshot, so only the current year is shown. Load files for several "
            "years (or connect the live sources) to see year-over-year movement."
        )
        myr = MultiYearReview(years=[fiscal_year], results={fiscal_year: result})
    else:
        myr = run_multiyear([2024, 2025, 2026], _settings("mock", None))

    inst = institution_trend(myr)
    m1, m2 = st.columns([2, 3])
    with m1:
        st.caption("Institution net margin by year")
        st.dataframe(
            inst[["fiscal_year", "total_revenue", "total_cost", "net_margin",
                  "net_margin_ratio"]].style.format({
                "total_revenue": "${:,.0f}", "total_cost": "${:,.0f}",
                "net_margin": "${:,.0f}", "net_margin_ratio": "{:.1%}",
            }),
            use_container_width=True, hide_index=True,
        )
    with m2:
        metric = st.selectbox(
            "Trajectory metric",
            ["net_margin", "enrolled_majors", "total_revenue", "net_margin_ratio"],
        )
        if len(myr.years) > 1:
            long = trend_frame(myr)
            line = px.line(
                long, x="fiscal_year", y=metric, color="program_name", markers=True,
                labels={"fiscal_year": "Fiscal year", "program_name": "Program"},
            )
            line.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(line, use_container_width=True)
        else:
            st.caption("Add more years to see trajectories.")

    if len(myr.years) > 1:
        st.caption("Biggest movers")
        st.dataframe(
            yoy_summary(myr, metric).head(10), use_container_width=True, hide_index=True
        )

    st.divider()
    st.subheader("Next-year forecast (from the Slate admissions pipeline)")
    fc1, fc2 = st.columns(2)
    retention = fc1.slider(
        "Fallback retention rate (continuing majors kept)", 0.5, 1.0, 0.82, 0.01,
        help="Used for programs without an estimate.",
    )
    melt = fc2.slider("Summer melt (deposits that don't enroll)", 0.0, 0.4, 0.12, 0.01)
    assumptions = ForecastAssumptions(retention_rate=retention, melt_rate=melt)

    can_estimate = len(myr.years) >= 2
    use_estimated = st.checkbox(
        "Estimate retention per program from history (last two years)",
        value=can_estimate, disabled=not can_estimate,
        help="Derives each program's retention from year-over-year enrollment "
        "instead of one flat rate. Needs ≥2 years of data.",
    )
    retention_by_program = None
    if use_estimated and can_estimate:
        estimates = estimate_from_multiyear(myr, melt_rate=melt)
        retention_by_program = retention_map(estimates)
        est_df = retention_frame(estimates)
        avg = est_df["retention_rate"].mean()
        st.caption(
            f"Estimated retention from FY{min(myr.years)}→FY{max(myr.years)} · "
            f"average {avg*100:.1f}% (range {est_df['retention_rate'].min()*100:.0f}–"
            f"{est_df['retention_rate'].max()*100:.0f}%)"
        )
        with st.expander("Per-program estimated retention"):
            st.dataframe(
                est_df[["program_code", "program_name", "prior_enrolled",
                        "prior_completions", "new_students", "retained",
                        "retention_rate"]].sort_values("retention_rate").style.format({
                    "new_students": "{:,.0f}", "retained": "{:,.0f}",
                    "retention_rate": "{:.1%}",
                }),
                use_container_width=True, hide_index=True,
            )
    elif not can_estimate:
        st.caption("Single year of data — using the flat fallback rate. Load "
                   "multiple years (or snapshots) to estimate retention per program.")

    ftot = forecast_totals(result, assumptions, retention_by_program)
    g1, g2, g3, g4 = st.columns(4)
    g1.metric("Current majors", f"{ftot['current_majors']:,}")
    g2.metric("Projected majors", f"{ftot['projected_majors']:,}",
              f"{ftot['projected_pct_change']*100:+.1f}%")
    g3.metric("Projected revenue", money(ftot["projected_revenue"]))
    g4.metric("Programs to watch",
              f"{ftot['programs_shrinking'] + ftot['programs_improving']}")

    fc_df = forecast_frame(result, assumptions, retention_by_program)
    watch = fc_df[fc_df["watch_flag"] != "Stable"]
    if not watch.empty:
        st.caption("⚠️ Economics and pipeline pointing in opposite directions")
        st.dataframe(
            watch[["program_name", "college", "watch_flag", "enrolled_majors",
                   "projected_majors", "projected_pct_change", "yield_rate",
                   "net_margin"]].style.format({
                "projected_pct_change": "{:+.1%}", "yield_rate": "{:.1%}",
                "net_margin": "${:,.0f}",
            }),
            use_container_width=True, hide_index=True,
        )

    st.caption("All programs — projection")
    st.dataframe(
        fc_df[["program_code", "program_name", "enrolled_majors", "admits",
               "deposits", "yield_rate", "retention_rate", "projected_majors",
               "projected_pct_change", "projected_revenue",
               "projected_contribution_margin", "watch_flag"]].style.format({
            "yield_rate": "{:.1%}", "retention_rate": "{:.1%}",
            "projected_pct_change": "{:+.1%}",
            "projected_revenue": "${:,.0f}",
            "projected_contribution_margin": "${:,.0f}",
        }),
        use_container_width=True, hide_index=True, height=420,
    )

    st.divider()
    st.subheader("Saved history (snapshots)")
    st.caption(
        "Save the current review to build trends from **real saved history** "
        "instead of re-running a synthetic year."
    )
    store = SnapshotStore(base.db_path)
    sc1, sc2 = st.columns([3, 1])
    label = sc1.text_input("Snapshot label", value=f"FY{fiscal_year}")
    if sc2.button("💾 Save snapshot", disabled=not can("snapshot")):
        sid = store.save(result, label=label)
        st.success(f"Saved snapshot #{sid}: {label}")
    if not can("snapshot"):
        st.caption("Your role can view history but not save snapshots.")

    saved = store.trend()
    if not saved.empty:
        st.dataframe(
            saved[["id", "label", "fiscal_year", "created_at", "total_revenue",
                   "net_margin", "net_margin_ratio"]].style.format({
                "total_revenue": "${:,.0f}", "net_margin": "${:,.0f}",
                "net_margin_ratio": "{:.1%}",
            }),
            use_container_width=True, hide_index=True,
        )
        if len(saved) > 1:
            saved_line = px.line(
                saved.sort_values("fiscal_year"), x="fiscal_year", y="net_margin",
                markers=True, labels={"fiscal_year": "Fiscal year",
                                      "net_margin": "Net margin ($)"},
            )
            saved_line.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(saved_line, use_container_width=True)
    else:
        st.caption("No snapshots saved yet.")

# --------------------------------------------------------------------------- #
# Faculty tab
# --------------------------------------------------------------------------- #
with tab_faculty:
    st.title("Faculty & payroll")
    payroll = _faculty_payroll()
    using_uploaded = bool(st.session_state.get("faculty_payroll"))
    st.caption(
        ("Uploaded payroll" if using_uploaded else "Sample faculty roster")
        + f" · {len(payroll)} assignments · upload your own in the Import tab."
    )
    if st.session_state.get("use_payroll_cost"):
        st.success("Payroll-derived instruction cost is **on** (driving the model).")
    else:
        st.info("Payroll view is informational. Enable *Use payroll-derived "
                "instruction cost* in the Import tab to drive the model with it.")

    rollups = aggregate_faculty(payroll)
    roll_df = rollup_frame(rollups)

    total_fac = int(sum(r.faculty_headcount for r in rollups))
    total_cost = sum(r.instruction_cost for r in rollups)
    total_fte = sum(r.faculty_fte for r in rollups)
    adjuncts = int(sum(r.adjunct_headcount for r in rollups))
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Faculty (assignments)", f"{total_fac:,}")
    f2.metric("Faculty FTE", f"{total_fte:,.1f}")
    f3.metric("Instruction cost", money(total_cost))
    f4.metric("Cost / FTE", money(total_cost / total_fte) if total_fte else "—")

    fc1, fc2 = st.columns([3, 2])
    with fc1:
        st.subheader("Cost per faculty FTE by program")
        chart = roll_df.sort_values("cost_per_fte", ascending=False)
        bar = px.bar(
            chart, x="cost_per_fte", y="program_code", orientation="h",
            color="benefits_rate",
            labels={"cost_per_fte": "Cost per FTE ($)", "program_code": "",
                    "benefits_rate": "Benefits rate"},
        )
        bar.update_layout(height=460, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(bar, use_container_width=True)
    with fc2:
        st.subheader("Adjunct mix")
        mix = roll_df[["program_code", "faculty_headcount", "adjunct_headcount"]].copy()
        mix["full_time"] = mix["faculty_headcount"] - mix["adjunct_headcount"]
        pie = px.bar(
            mix.sort_values("faculty_headcount", ascending=False),
            x="program_code", y=["full_time", "adjunct_headcount"],
            labels={"value": "Faculty", "program_code": "", "variable": ""},
        )
        pie.update_layout(height=460, margin=dict(l=0, r=0, t=10, b=0),
                          legend=dict(orientation="h"))
        st.plotly_chart(pie, use_container_width=True)

    st.subheader("Per-program faculty roll-up")
    st.dataframe(
        roll_df.style.format({
            "faculty_fte": "{:,.1f}", "instruction_cost": "${:,.0f}",
            "total_salary": "${:,.0f}", "total_benefits": "${:,.0f}",
            "benefits_rate": "{:.1%}", "cost_per_fte": "${:,.0f}",
            "avg_compensation": "${:,.0f}",
        }),
        use_container_width=True, hide_index=True,
    )
    st.download_button(
        "⬇️ Faculty roll-up (CSV)", roll_df.to_csv(index=False).encode("utf-8"),
        file_name=f"faculty_rollup_{fiscal_year}.csv", mime="text/csv",
    )

# --------------------------------------------------------------------------- #
# Scenario tab
# --------------------------------------------------------------------------- #
with tab_scenario:
    st.title("Scenario modeling")
    st.write(
        "Adjust the levers and see the margin impact against the current "
        "baseline. Nothing here changes saved data."
    )
    if not can("scenario"):
        st.warning("Your role can view results but not run scenarios.")
    else:
        s1, s2, s3 = st.columns(3)
        tuition = s1.slider("Tuition rate change", -0.20, 0.20, 0.0, 0.01,
                            format="%+.0f%%")
        enrollment = s2.slider("Enrollment change", -0.30, 0.30, 0.0, 0.01,
                               format="%+.0f%%")
        use_target = s3.checkbox("Set target discount rate")
        if use_target:
            target_discount = s3.slider("Target discount rate", 0.0, 0.7, 0.45, 0.01)
            aid_change = 0.0
        else:
            target_discount = None
            aid_change = s3.slider("Institutional aid change", -0.30, 0.30, 0.0, 0.01,
                                   format="%+.0f%%")

        s4, s5, s6 = st.columns(3)
        instr = s4.slider("Instruction cost change", -0.20, 0.20, 0.0, 0.01,
                          format="%+.0f%%")
        dept = s5.slider("Departmental cost change", -0.20, 0.20, 0.0, 0.01,
                         format="%+.0f%%")
        ops = s6.slider("Operations pool change", -0.20, 0.20, 0.0, 0.01,
                        format="%+.0f%%")

        scenario = Scenario(
            tuition_change_pct=tuition, enrollment_change_pct=enrollment,
            aid_change_pct=aid_change, target_discount_rate=target_discount,
            instruction_cost_change_pct=instr, departmental_cost_change_pct=dept,
            operations_cost_change_pct=ops,
        )
        scen_result = run_scenario(result, scenario)
        ct = compare_totals(result, scen_result)

        st.divider()
        k1, k2, k3 = st.columns(3)
        k1.metric("Revenue", money(ct["revenue_scenario"]),
                  money(ct["revenue_delta"]))
        k2.metric("Net margin", money(ct["net_margin_scenario"]),
                  money(ct["net_margin_delta"]))
        k3.metric("Net margin %",
                  f"{ct['net_margin_ratio_scenario']*100:.1f}%",
                  f"{(ct['net_margin_ratio_scenario']-ct['net_margin_ratio_base'])*100:+.1f} pts")

        cmp_df = compare(result, scen_result)
        st.caption("Biggest net-margin swings by program")
        st.dataframe(
            cmp_df[["program_name", "college", "net_margin_base",
                    "net_margin_scenario", "net_margin_delta",
                    "revenue_delta"]].style.format({
                "net_margin_base": "${:,.0f}", "net_margin_scenario": "${:,.0f}",
                "net_margin_delta": "${:,.0f}", "revenue_delta": "${:,.0f}",
            }),
            use_container_width=True, hide_index=True, height=440,
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

    include_trend = st.checkbox(
        "Include multi-year trend section", value=not bool(
            st.session_state.get("imported_inputs")
        ),
        help="Adds institution-by-year and biggest-movers tables (sample data "
        "spans FY2024–FY2026).",
    )
    report_myr = (
        run_multiyear([2024, 2025, 2026], _settings("mock", None))
        if include_trend and not st.session_state.get("imported_inputs")
        else None
    )
    report_html = build_html_report(result, multiyear=report_myr)
    include_faculty = st.checkbox(
        "Include a Faculty sheet in the Excel workbook",
        value=bool(st.session_state.get("faculty_payroll")),
    )
    report_faculty = (
        rollup_frame(aggregate_faculty(_faculty_payroll())) if include_faculty else None
    )

    c1, c2, c3 = st.columns(3)
    c1.download_button(
        "⬇️ HTML report", report_html.encode("utf-8"),
        file_name=f"{fname}.html", mime="text/html",
    )
    c2.download_button(
        "⬇️ Excel workbook",
        build_excel_report(result, multiyear=report_myr, faculty=report_faculty),
        file_name=f"{fname}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    c3.download_button(
        "⬇️ CSV (programs)", df.to_csv(index=False).encode("utf-8"),
        file_name=f"{fname}.csv", mime="text/csv",
    )

    st.divider()
    st.subheader("Report preview")
    st.components.v1.html(report_html, height=600, scrolling=True)

# --------------------------------------------------------------------------- #
# Admin tab (only when the signed-in user is an admin)
# --------------------------------------------------------------------------- #
if tab_admin is not None:
    with tab_admin:
        st.title("Admin")
        st.subheader("Active mapping configuration")
        st.caption(
            "Remap source columns / GL accounts without code by setting "
            "`UPR_MAPPING_FILE` (see config/mapping.example.yaml)."
        )
        mapping = get_mapping()
        st.write(f"**Source:** {mapping.source_path or 'built-in defaults'}")
        if mapping.column_aliases:
            st.write("**Extra column aliases**")
            st.json(mapping.column_aliases)
        st.write("**NetSuite account buckets**")
        st.json(mapping.netsuite_buckets or "built-in defaults (4000/4900/5000…)")
        st.write("**Operations departments**")
        st.json(sorted(mapping.operations_departments) if mapping.operations_departments
                else "built-in defaults")

        st.divider()
        st.subheader("Users")
        if auth.auth_enabled():
            users = auth.load_users(auth.users_file_path())
            st.dataframe(
                [{"username": u.username, "name": u.name, "role": u.role}
                 for u in users.values()],
                use_container_width=True, hide_index=True,
            )
            st.caption(
                'Add a user: `python -m upr.auth add <username> "<name>" <role>` '
                "and append the output to your users file."
            )
        else:
            st.info(
                "Auth is disabled (open mode). Create config/users.yaml "
                "(see config/users.example.yaml) to enable login and roles."
            )
