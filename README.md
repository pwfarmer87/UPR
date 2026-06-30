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

- **NetSuite** — **fully implemented** (SuiteQL over REST with OAuth 1.0a TBA
  HMAC-SHA256 signing, pagination, and a tested GL→program mapping). Needs the
  connector authorized + `NETSUITE_*` credentials; until then it falls back to
  mock data. See "NetSuite live integration" below.
- **Slate** — **implemented**: reads a published Slate query (JSON web service)
  with a query key and maps the funnel through the shared importer. Set
  `SLATE_BASE_URL` + `SLATE_QUERY_KEY`.
- **Jenzabar** — **implemented**: REST API (`JENZABAR_BASE_URL` +
  `JENZABAR_API_KEY`) or direct read-only SQL (`JENZABAR_DB_DSN`, via ODBC).

Each source's response is normalized by the **same** importer used for files
(`upr.importing.map_records`), so header aliases and type coercion are identical
across files and APIs. Per-source field ownership (`upr.sources`) keeps a
NetSuite feed from overwriting enrollment, etc., when results merge.

Set credentials in `.env` (see `.env.example`) and flip `UPR_DATA_SOURCE=live`.

### NetSuite live integration

Set the five `NETSUITE_*` values in `.env` (account id, consumer key/secret,
token id/secret from an integration record + access token). The connector then:

1. POSTs `SUITEQL_PROGRAM_FINANCIALS` to
   `https://<account>.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql`,
   signed per request, following `hasMore` pagination.
2. Maps each GL row to a program by **department** (the `program_code`) and each
   account to a revenue/cost bucket via `_BUCKET_SPECS` (tune to your chart of
   accounts). Departments in `OPERATIONS_DEPARTMENTS` roll into the shared
   overhead pool instead of a program's direct cost.

The mapping (`classify_account`, `aggregate_gl_rows`, `operations_pool_from_rows`)
and the OAuth header builder are pure functions with unit tests, so the chart of
accounts can be adjusted and verified without hitting NetSuite.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# run the dashboard (Import / Dashboard / Reports tabs)
streamlit run dashboard/app.py

# run the tests
pytest -q
```

### Command line

```bash
python -m upr summary                              # totals for the current source
python -m upr template --out programs.csv          # blank unified import template
python -m upr summary --file programs.csv --ops-cost 58000000
python -m upr report  --file programs.csv --ops-cost 58000000 \
                      --out review.html --excel review.xlsx
python -m upr trends  --years 2024 2025 2026 --metric net_margin
python -m upr forecast
```

## Importing data (before the APIs)

You don't need the live integrations to start. Export from the source systems
(or fill the template) and load CSV/Excel:

- **Unified file** — one row per program with any of the template columns.
- **Per-source files** — separate Jenzabar / NetSuite / Slate exports that
  **merge by `program_code`**; each file only fills the fields its source owns
  (so a NetSuite export can't accidentally overwrite enrollment, etc.).

Headers are matched leniently — `Major Code`, `SCH`, `Aid`, `Dept Cost` all map
correctly. Blank templates and a filled example live in `data/`
(`import_template.csv`, `sample_programs_2025.csv`). In the dashboard, use the
**Import** tab; on the CLI/env, set `UPR_DATA_SOURCE=file` and the file paths.

## Reporting

From the **Reports** tab or `python -m upr report`:

- **HTML report** — KPIs, *underwater-after-overhead*, a **next-year forecast**
  section (projected enrollment + watch list), an optional **multi-year trend**
  section (institution-by-year + biggest movers with CAGR), a by-college rollup,
  and the full program table. Standalone and **prints cleanly to PDF**.
- **Excel workbook** — `Summary`, `Programs`, `Underwater`, `By College`,
  `Forecast`, and (with `--years`) `Trend by year` + `Net margin movers` sheets.
- **CSV** — the computed program table.

Add the trend section from the CLI with `--years`:

```bash
python -m upr report --years 2024 2025 2026 --out review.html --excel review.xlsx
```

## Multi-year trends & forecast

The **Trends & Forecast** tab (and `upr.trends` / `upr.forecast`):

- **Trends** — runs the review across fiscal years and shows institution totals
  by year, per-program trajectories, and a first-vs-last mover list with CAGR.
- **Forecast** — projects next year's enrollment, revenue, and contribution from
  the **Slate funnel** (applications → admits → deposits) using transparent
  retention/melt assumptions, and flags programs where economics and pipeline
  diverge: *"healthy but shrinking"* (profitable, enrollment falling) and
  *"improving"* (underwater, pipeline growing).

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
  sources.py           which fields each source system owns (merge/import)
  importing.py         CSV/Excel import + templates (the pre-API path)
  reporting.py         HTML + Excel report builders, by-college rollup
  trends.py            multi-year trend analysis (YoY, CAGR, trajectories)
  forecast.py          next-year enrollment/margin forecast from Slate funnel
  pipeline.py          pull/import → merge → compute
  sample_data.py       realistic mock institution
  __main__.py          CLI: summary | template | report | trends | forecast
  connectors/
    base.py            Connector interface
    netsuite.py        NetSuite Financials adapter (auth-pending)
    slate.py           Slate CRM adapter (stub)
    jenzabar.py        Jenzabar SIS adapter (stub)
    mock.py            sample-data provider
  finance/
    allocation.py      overhead allocation strategies
    calculations.py    margin & per-unit metrics
dashboard/app.py       Streamlit dashboard (Import / Dashboard / Reports)
data/                  blank import template + filled sample
tests/                 unit tests for the engine, import, and reporting
```

## Assumptions in this first version

These were chosen to get a working tool quickly; all are easy to revisit:

- Stack: Python + Streamlit, internal-tool scope (no multi-tenant auth yet).
- Overhead allocated by student credit hours by default.
- One fiscal year per snapshot; multi-year trend supported by loading several.
- Revenue/cost figures are program-attributed; cross-listed course splitting is
  handled upstream in the connector mapping (documented per adapter).
