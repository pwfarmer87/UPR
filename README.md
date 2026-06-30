# UPR — University Program (Margin) Review

A tool to speed up **program / major financial review** for universities. It pulls
together what a program *costs*, what *revenue* it brings in, and the share of
*university operations* it consumes, then reports per-program **contribution
margin**, **net margin**, and **per-student / per-credit-hour** economics so
provost and finance offices can compare programs on a consistent basis.

## Data sources

| Source | System | What it provides |
|--------|--------|------------------|
| **Jenzabar One** | Student Information System | Enrolled majors, student credit hours (SCH), course sections, faculty load, completions |
| **NetSuite Financials** | ERP / General Ledger | Actual tuition revenue, institutional aid, salaries & benefits, departmental and operations expense |
| **Technolutions Slate** | Admissions CRM | Recruitment funnel by intended major (applications → admits → deposits → yield) |

The engine **joins** these: Jenzabar tells you *who and how many credit hours*,
NetSuite tells you *the money*, and Slate tells you the *pipeline* for forecasting.

## Status of integrations

This build runs end-to-end on **realistic sample data** (`upr.sample_data`) so the
model and dashboard are usable today. Each live connector is a pluggable adapter:

- **NetSuite** — connector present; needs OAuth authorization before it returns
  live data (SuiteQL/REST). Until then it falls back to the mock provider.
- **Slate** — integrates via Slate web services (query API); adapter stubbed.
- **Jenzabar** — integrates via Jenzabar API / direct SQL; adapter stubbed.

Set credentials in `.env` (see `.env.example`) and flip `UPR_DATA_SOURCE=live`.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# run the dashboard
streamlit run dashboard/app.py

# run the tests
pytest -q
```

## The financial model (per program, per fiscal year)

```
gross_tuition       = student_credit_hours × tuition_rate_per_credit_hour
net_tuition         = gross_tuition − institutional_aid
total_revenue       = net_tuition + fees + other_revenue

direct_cost         = instruction_cost (faculty+adjunct salary+benefits)
                      + departmental_cost (staff, supplies, operating)

contribution_margin = total_revenue − direct_cost          # before overhead
allocated_overhead  = university_operations_pool × driver_share(program)
total_cost          = direct_cost + allocated_overhead
net_margin          = total_revenue − total_cost           # after overhead

cost_per_student        = total_cost / enrolled_majors
revenue_per_student     = total_revenue / enrolled_majors
cost_per_credit_hour    = total_cost / student_credit_hours
```

**University operations** (facilities, IT, library, administration, student
services) are a shared pool allocated across programs by a configurable driver:
student credit hours (default), headcount, or direct cost. See
`upr/finance/allocation.py`.

## Layout

```
src/upr/
  models.py            domain model (Program, ProgramFinancials, metrics)
  config.py            settings / source selection (.env)
  pipeline.py          pull → normalize → compute
  sample_data.py       realistic mock institution
  connectors/
    base.py            Connector interface
    netsuite.py        NetSuite Financials adapter (auth-pending)
    slate.py           Slate CRM adapter (stub)
    jenzabar.py        Jenzabar SIS adapter (stub)
    mock.py            sample-data provider
  finance/
    allocation.py      overhead allocation strategies
    calculations.py    margin & per-unit metrics
dashboard/app.py       Streamlit dashboard
tests/                 unit tests for the engine
```

## Assumptions in this first version

These were chosen to get a working tool quickly; all are easy to revisit:

- Stack: Python + Streamlit, internal-tool scope (no multi-tenant auth yet).
- Overhead allocated by student credit hours by default.
- One fiscal year per snapshot; multi-year trend supported by loading several.
- Revenue/cost figures are program-attributed; cross-listed course splitting is
  handled upstream in the connector mapping (documented per adapter).
