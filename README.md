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

### macOS / Linux

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# run the dashboard (Import / Dashboard / Reports tabs)
streamlit run dashboard/app.py

# run the tests
pytest -q
```

### Windows (PowerShell)

Use a virtual environment and run tools via `python -m`. Calling the venv's
Python directly avoids the PowerShell execution-policy prompt that blocks
`Activate.ps1`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# run the dashboard (opens http://localhost:8501)
.\.venv\Scripts\python.exe -m streamlit run dashboard/app.py

# run the tests
.\.venv\Scripts\python.exe -m pytest -q
```

**Why a venv?** Installing into the global `C:\PythonXX\Scripts` often fails with
`OSError: [WinError 2] ... watchmedo.exe.deleteme` (antivirus/permission lock on
the global Scripts dir), which rolls back the whole install — that's why
`streamlit`/`pytest` end up "not recognized". A venv has its own writable
`Scripts` dir and sidesteps it. Running as `python -m streamlit` / `python -m
pytest` also avoids needing those tools on your PATH. No need to set
`PYTHONPATH`: the dashboard adds `src` itself and pytest reads it from
`pyproject.toml`.

### Command line

```bash
python -m upr summary                              # totals for the current source
python -m upr template --out programs.csv          # blank unified import template
python -m upr summary --file programs.csv --ops-cost 58000000
python -m upr report  --file programs.csv --ops-cost 58000000 \
                      --out review.html --excel review.xlsx
python -m upr trends  --years 2024 2025 2026 --metric net_margin
python -m upr forecast
python -m upr scenario --tuition 0.05 --enrollment -0.10 --operations 0.05
python -m upr crosswalk --net-revenue R.xlsx --course-enrollments C.xlsx --year 2024 --out xw.csv
python -m upr ingest --net-revenue Net_Revenue_by_Term.xlsx --year 2024 --out programs.csv
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

## Bringing in real exports (`upr.adapters`)

Adapters parse the actual report shapes a registrar/finance office exports and
turn them into a UPR import CSV:

- **Net Revenue / Discounts / Fees by Term** (xlsx) → per-major gross tuition,
  institutional aid (discounts), fees, and headcount (distinct students).
- **Course enrollments (last N years)** (xlsx) → student credit hours by course
  subject × year.
- **Faculty load** (PDF) → sections taught by subject (dependency-free text
  extraction; an Excel export is more reliable).

```bash
python -m upr ingest --net-revenue "Net_Revenue_by_Term.xlsx" --year 2024 \
                     --out programs.csv
python -m upr summary --file programs.csv --driver headcount --ops-cost 8000000
```

**Reviewing by program (major code).** The program key is the **major code**
(`MAJOR_CDE`). Revenue/headcount are major-native. SCH and faculty load are keyed
by **course subject** (department), so to attribute them to majors you supply a
`subject → program` crosswalk. UPR scaffolds one for you — auto-seeding subjects
whose code matches a major code (e.g. `BIOL`, `ENGL`, `MATH`) and leaving the
rest blank, largest-SCH first:

```bash
python -m upr crosswalk --net-revenue R.xlsx --course-enrollments C.xlsx \
                        --year 2024 --out crosswalk.csv --majors-out majors.csv
# fill program_code for the remaining subjects (majors.csv lists valid codes), then:
python -m upr ingest --net-revenue R.xlsx --course-enrollments C.xlsx \
                     --subject-map crosswalk.csv --year 2024 --out programs.csv
```

Each subject's SCH is credited to exactly one program (no double counting).
Without a crosswalk, programs still carry headcount + revenue; allocate overhead
**by headcount**. Instruction/department **cost** isn't in these academic
exports — it comes from NetSuite GL or faculty payroll, keyed to the same major
codes via `config/mapping.yaml`.

**Department rollups.** The bundled roster also carries each program's
**field of study** (department), so the by-program review rolls up into the
departments the institution actually uses — the dashboard and Excel report show
**By department** beside By college (e.g. 60 majors → 23 departments, with
Business and Education spanning many program codes). SCH-by-major still needs
student registrations; the department dimension is for grouping, not for
splitting service/gen-ed teaching cost.

**Authoritative program names.** Programs are named from the institution's
official `program_code → program_name` roster (bundled at
`src/upr/adapters/program_codes.csv`), not the messy parsed text. Codes that
share a name (e.g. several "Education" codes, or the same program offered in
multiple delivery modes) are disambiguated by code — `Elementary Education
(EELM)` vs `Elementary Education (UTEL)`. Codes absent from the roster (e.g.
non-degree) keep their parsed name. Override the roster with
`ingest --program-codes my_roster.csv`.

> Privacy: the net-revenue export is student-level PII. UPR processes it
> in-memory to aggregate; nothing student-level is written except the
> program-level CSV you ask for. Tests run on synthetic fixtures — no real data
> is committed.

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
  the **Slate funnel** (applications → admits → deposits), and flags programs
  where economics and pipeline diverge: *"healthy but shrinking"* (profitable,
  enrollment falling) and *"improving"* (underwater, pipeline growing).
- **Estimated retention** (`upr.retention`) — instead of a single flat retention
  assumption, retention is **estimated per program** from year-over-year
  enrollment when ≥2 years of data exist (sample, snapshots, or live history):

  ```
  retention ≈ (enrolled_N − new_entrants) / (enrolled_{N-1} − completions_{N-1})
  ```

  Each program's estimate feeds the forecast; programs without history fall back
  to the flat rate. This matters — a 1-year graduate program retains very
  differently year-over-year than a large service major, and a flat rate hides
  that. Toggle it in the Trends & Forecast tab or `forecast --estimate-retention`.

## Faculty payroll

`upr.faculty` rebuilds **instruction cost** and **faculty FTE** from per-faculty
compensation instead of trusting a single GL lump — making instruction cost
auditable and surfacing faculty metrics (headcount, FTE, **cost per FTE**,
benefits load, adjunct mix). Load a payroll file (one row per faculty-program
assignment; joint appointments split by `effort`), see the **Faculty** tab, and
optionally toggle *"Use payroll-derived instruction cost"* to drive the model
with it. Source: a NetSuite SuitePeople / HR-payroll export or any payroll
spreadsheet; headers are matched leniently. Set `UPR_FACULTY_FILE` to apply it
on the CLI/env. Templates and a filled sample are in `data/`.

## Scenario modeling

The **Scenario** tab (and `upr.scenario` / `python -m upr scenario`) applies
global what-if levers to the baseline and shows the margin impact live:
tuition rate, enrollment, institutional aid (or a **target discount rate**),
instruction/departmental cost, and the operations pool. Enrollment changes scale
the activity that moves with students (credit hours, aid, fees, funnel); cost
levers are modeled independently (faculty/department costs are sticky short-term).
Nothing is persisted — it's a live comparison against the current baseline.

## Saved history (snapshots)

`upr.storage.SnapshotStore` (SQLite, stdlib) saves a computed review — institution
totals plus every program's financials — so **trends come from real saved
history** instead of a synthetic re-run. Save from the Trends tab; the store
backs a by-year trend and a per-program trajectory. DB path: `UPR_DB_PATH`
(default `data/upr.db`, git-ignored).

## Authentication & roles

Optional. If a user store exists (`config/users.yaml`, or `UPR_USERS_FILE`), the
dashboard requires login and gates actions by role:

| Role | Can |
|------|-----|
| `viewer`  | view dashboard, trends, reports |
| `analyst` | + import data, run scenarios, save snapshots |
| `admin`   | + manage mapping config / view users |

Passwords are salted PBKDF2-HMAC-SHA256. With no user store the app runs **open**
(single-team prototype). Add a user:

```bash
python -m upr.auth add pfarmer "Patrick Farmer" admin   # prints a YAML entry
```

## Mapping configuration (no-code remapping)

`config/mapping.yaml` (or `UPR_MAPPING_FILE`) remaps source data without touching
code — extra **column aliases** for the importer/Slate/Jenzabar, and NetSuite
**GL account buckets** + **operations departments**. See
`config/mapping.example.yaml`. Admins can view the active config in the Admin tab.

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
  faculty.py           faculty payroll import + roll-up (auditable instruction cost)
  trends.py            multi-year trend analysis (YoY, CAGR, trajectories)
  forecast.py          next-year enrollment/margin forecast from Slate funnel
  retention.py         per-program retention estimated from YoY enrollment
  scenario.py          what-if levers (tuition/enrollment/aid/cost) + compare
  storage.py           SQLite snapshot store (saved history → trends)
  auth.py              optional login + role-based capabilities (PBKDF2)
  mapping_config.py    YAML remapping of columns / GL accounts (no-code)
  pipeline.py          pull/import → merge → compute
  sample_data.py       realistic mock institution
  __main__.py          CLI: summary|template|report|trends|forecast|scenario
config/                mapping.example.yaml + users.example.yaml
  adapters/            parse real report exports (net revenue, enrollments,
                       faculty load) into ProgramInputs / an import CSV
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
