# Backend — Data Analysis Platform (MVP)

FastAPI + SQLAlchemy + pandas service that powers the whole MVP flow:
**register/login → upload CSV/XLSX → preview & profile → clean → analyse → chart → export.**

Full API description: `../api_endpoints.md` (this backend implements it, plus a few
additions listed at the bottom).

---

## 1. Setup (Windows PowerShell)

```powershell
cd D:\Project\Data-Analysis-system\backend
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

> The venv used during development is already in this folder. Recreate it with the
> commands above on another machine.

## 2. Run the API

```powershell
cd D:\Project\Data-Analysis-system\backend
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

- API base URL: `http://localhost:8000/api`
- Interactive docs (auto-generated from the Pydantic models): `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/health`

## 3. Run the tests

```powershell
cd D:\Project\Data-Analysis-system\backend
.\venv\Scripts\python.exe tests\smoke_test.py     # end-to-end journey (90 checks)
.\venv\Scripts\python.exe tests\statflow_test.py  # statflow engines (216 checks)
.\venv\Scripts\python.exe tests\orgs_test.py      # organizations + RBAC matrix (38 checks)
.\venv\Scripts\python.exe -m pytest               # same journeys, pytest runner
```

Each test creates a temporary database + storage folder, generates sample files and walks
the whole journey (auth → upload → clean → stats → charts → xlsx/pdf export → download →
privacy checks → delete). A full log is written to `smoke_test_out.log` /
`statflow_test_out.log`.

`smoke_test.py` also uploads **JSON / TSV / TXT / Parquet** datasets and checks preview +
versioned cleaning for each format. `formats_test.py` does the same for the statistical
package formats — Stata `.dta`, SPSS `.sav`/`.por` — plus the error contract for
broken R files and for files whose extension does not match their contents.

Result with the current code: **all checks pass**.

## 3b. Database migrations (Alembic)

The schema also lives as Alembic migrations (`backend/migrations/`). `create_all` in the
app lifespan stays as a local-dev convenience; **use migrations for shared/production
databases** (e.g. Render Postgres). Run from `backend/`:

```powershell
# point at the target database for the run, e.g.:
$env:DATABASE_URL = "postgresql+psycopg2://user:pass@host:5432/data_analysis"
.\venv\Scripts\python.exe -m alembic upgrade head          # apply all migrations
.\venv\Scripts\python.exe -m alembic revision --autogenerate -m "describe change"  # new migration
```

`migrations/env.py` wires the app's engine + metadata, so model changes are captured
automatically. The initial migration `5215fbda1c26` creates every table (MVP + Phase 1).

### 3c. Bringing an older local database onto the chain

`create_all` on startup only creates tables that are **missing**. It never alters a table
that already exists, and it never writes an `alembic_version` row. So a `app.db` created
before a new migration still looks healthy to the app while missing every new column, and
the failure shows up as a query error rather than a migration message:

```
sqlite3.OperationalError: no such column: users.system_role
```

Do not "fix" this with `create_all`, and do not run `upgrade head` on an unstamped
database, because Alembic would try to create tables that already exist. Inspect first,
then adopt the database:

```powershell
# report only: revision, row counts, which columns are missing
.\venv\Scripts\python.exe -m tools.adopt_existing_db --db app.db --verify

# adopt, with a backup, then verify the result
.\venv\Scripts\python.exe -m tools.adopt_existing_db --db app.db --stamp 7c3d9f2a41b8 --apply
```

The stamp revision is the last one whose schema the data **actually** matches, not simply
the previous one in the chain. The tool refuses to stamp when the answer would be wrong,
and it refuses a `--db` that is not the database the app is configured to use, so a report
and the migration cannot describe different files. It writes `app.db.<stamp>.bak` first.

`app.database` binds its engine when it is imported, so `DATABASE_URL` has to be set
**before** any `app.*` import. `migrations/env.py` reads that engine too, which is why
`alembic.ini`'s `sqlalchemy.url` is empty and ignored.

`backend/tests/migration_test.py` covers the admin migration on three histories: a
database built only by migrations, a database whose `create_all` added `audit_logs` while
the older tables stayed as they were, and an upgrade/downgrade/upgrade round trip. Run it
with `.\venv\Scripts\python.exe tests\migration_test.py`.

Known limitation: revision `b6e1f0a9c743` cannot run against a `dataset_versions` table
that was built by `create_all` from a *current* model, because the self-referencing
`parent_version` foreign key makes Alembic's batch copy fail with a circular dependency.
No real database has that history, since `create_all` never rebuilds an existing table,
but a hand-built scratch database might.

### 3d. Checking the running server

`tests/live_admin_check.py` logs in over HTTP and walks every admin endpoint against a
real database. It is here because a `TestClient` suite cannot see a wrong column name in
a list serializer if the fixture list happens to be empty, and that is exactly the kind of
bug that otherwise reaches the browser. It refuses to run without `--confirm` or against a
non-localhost URL, and it deletes the super admin it promotes.

```powershell
# terminal 1
.\venv\Scripts\python.exe -m uvicorn app.main:app --port 8123
# terminal 2
$env:PYTHONPATH = "."
.\venv\Scripts\python.exe tests\live_admin_check.py --confirm
```

---

## 4. Configuration (environment variables)

Vile `backend/.env` inasoma na **python-dotenv** (tazama `backend/.env.example`).
Haiitiisha variable zilizowekwa tayari kwenye environment (dokezo la dotenv), kwa hiyo
Render / Docker zinauwetanga juu ya `.env` kila wakati. **Bila `.env` na bila env vars,
local inabaki sqlite default** — hivyo huna haja ya kufanya lolote kwa dev.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///backend/app.db` | SQLAlchemy URL. Point it at PostgreSQL for production, e.g. `postgresql+psycopg2://user:pass@localhost:5432/data_analysis` — au Render Postgres URL (
`render.yaml` inauwekea kwa `fromDatabase`) |
| `SECRET_KEY` | dev placeholder | JWT signing key — **change in production** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT lifetime |
| `STORAGE_DIR` | `backend/storage` | Where dataset files and reports are stored |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | Allowed CORS origin(s), comma-separated |

## 5. Project layout

```
backend/
├── app/
│   ├── main.py            # FastAPI app, CORS, router registration, table creation

## 6. What each endpoint does (short version)

- **Upload**: validates the extension (`.csv`, `.xlsx`, `.json`, `.tsv`, `.txt`,
  `.parquet`, plus the statistical package group `.dta`, `.sav`, `.zsav`, `.por`,
  `.RData`/`.rda`, `.rds`) and a 50MB ceiling *while* streaming the file to
  `storage/{user_id}/{dataset_id}/data{ext}`; profiles every column
  (type, missing count, unique count, min/max) and stores it in `dataset_columns`.
  `.txt` delimiter is auto-sniffed; every format shares the same `read_dataframe`
  path (and the version store), so cleaning, statistics, charts and exports work
  identically for all of them. The package formats are opened by
  `app/services/stat_file_readers.py` (`pyreadstat` for Stata/SPSS, `pyreadr` for
  R) with value labels kept as their numeric codes, and a file those libraries
  cannot parse becomes a 400 rather than a 500.
- **Profile**: recomputes the profile from the latest immutable version and returns it
  as a read-only response, so profiling never changes database state.
- **Clean / transform (versioned)**: every operation on
  `POST /api/v1/datasets/{id}/clean|transform` writes a complete temporary file,
  atomically publishes it, then commits a new immutable `dataset_versions` row plus a
  `dataset_operations` audit entry. Dataset locks and bounded retries serialize writers;
  each version records its creator and exact parent.
  Cleaning: `drop_duplicates`, `drop_missing`, `fill_missing`
  (drop/mean/median/mode/zero/constant), `rename_columns`, `cast_types`
  (numeric/integer/text/date/boolean). Transforms: `select_columns`,
  `filter`, `sort`, `calculate_column`, `group_by`, … (see
  `GET /api/v1/datasets/operations/catalog`).
- **Analyse (unified engine)**: `POST /api/v1/datasets/{id}/analysis` runs
  `descriptive`, `frequency`, `pearson`/`spearman`, `welch_t_test`,
  `mann_whitney`, `chi_square`, `fisher_exact`, `one_way_anova`, `kruskal_wallis` or
  `linear_regression` and always returns the same standard-result structure
  (status / estimate / test / confidence interval / effect size / diagnostics
  / tables). Saved runs record the exact dataset version in `analysis_runs` and feed
  version-consistent exports. A sparse 2x2 chi-square reports Fisher's exact
  p-value as the primary result and keeps the Pearson p-value separately.
- **Planning + assistant**: `POST /api/v1/planning/profile|recommend`
  detects variables and recommends a method; `POST /api/v1/assistant/ask`
  answers plain-language questions with a verified engine result. The assistant
  fails closed on ambiguous or unresolved variables, requires both roles for a
  comparative question, and reports p-values, effect sizes, confidence intervals
  and observational limitations without making causal claims.
- **Organizations (Phase 1)**: `POST/GET /api/v1/organizations` create and list
  organizations; `/api/v1/organizations/{id}/members` manages membership with an RBAC
  role ladder **owner > admin > analyst > viewer** (the role rules live in
  `app/rbac.py` and each route re-checks them server-side); `/api/v1/organizations/{id}/projects`
  manages project folders. Datasets with a `project_id` are reachable by org members
  according to their role (`deps.get_owned_dataset`), while personal datasets stay
  private to their owner.
- **Charts**: returns Plotly-ready `chart_data` (`series[]` with x/y plus axis labels),
  stores the exact source version, and caps categories (50) and scatter points (5000)
  so big files stay responsive.
- **Export**: `POST` returns `202` with `{report_id, status: "processing"}` and builds the
  PDF/XLSX in a FastAPI `BackgroundTasks` job. The report and every selected artifact
  must share one dataset version; poll `GET /reports/{id}/status`, then
  `GET /reports/{id}/download` streams the finished file.

## 7. Additions to `api_endpoints.md`

These were added because the UI screens need them (the documented endpoints are unchanged):

| Endpoint | Why |
|---|---|
| `GET /auth/me` | restore the session on page reload |
| `GET /reports/{id}/status` | poll an async export before downloading |
| `GET /datasets/{id}/reports` | list previous reports on the export screen |
| `GET /api/health` | quick deploy/health check |
| `status` + `error_message` columns on `exported_reports` | track the async export outcome |

## 8. MVP simplifications (documented, on purpose)

1. **SQLite by default** so the MVP runs with zero infrastructure. The models mirror
   `schema.sql`, so production only needs `DATABASE_URL` pointing at PostgreSQL and
   `Base.metadata.create_all()` (dev) or **Alembic migrations** (`alembic upgrade head`,
   see §3b) to apply the schema.
2. **FastAPI `BackgroundTasks` instead of Celery/RQ + Redis.** The API contract
   (`report_id` + status polling) is identical, so swapping in a real queue later is a
   backend-only change - the frontend keeps working.
3. **Local disk instead of S3**: `STORAGE_DIR` is a single setting; moving to S3 later
   means replacing `store_upload_file` and the report paths.
4. **bcrypt directly instead of passlib** (passlib 1.7.4 is incompatible with
   bcrypt >= 4.1/5.x).
5. Large-file analysis runs synchronously inside the request; with Celery/Redis the same
   service functions move into workers without API changes.
6. **Dev helper** `check_import.py` prints whether the FastAPI app imports cleanly (and
   writes `import_error.log` with the traceback if it does not).

│   ├── config.py          # env-driven settings, storage paths, upload limits
│   ├── database.py        # SQLAlchemy engine / session / Base
│   ├── models.py          # tables (User, Dataset, DatasetColumn, Chart,
│   │                      #  ExportedReport, DatasetVersion, DatasetOperation,
│   │                      #  AnalysisRun, Organization, OrganizationMember,
│   │                      #  Project)
│   ├── schemas.py         # Pydantic request/response models (drive /docs)
│   ├── security.py        # bcrypt password hashing + JWT create/decode
│   ├── deps.py            # get_current_user + dataset ownership checks
│   ├── rbac.py            # org role ladder helpers (owner/admin/analyst/viewer)
│   ├── routers/           # auth, datasets, charts, reports, organizations
│   └── services/
│       ├── data_service.py     # upload storage, reading, profiling
│       ├── chart_service.py    # Plotly-ready chart data (bar/line/scatter/histogram)
│       └── export_service.py   # XLSX workbook + PDF document writers
│   └── statflow/          # unified engines: versioning, operations,
│                          # statistics, planning, assistant (+ v1 routers)
├── migrations/            # Alembic: env.py + versions/ (initial, teams, provenance)
├── alembic.ini
├── tests/smoke_test.py
├── tests/orgs_test.py
├── requirements.txt
└── storage/               # uploads: storage/{user_id}/{dataset_id}/data.{csv,xlsx}
                           # reports: storage/reports/report_{id}_{name}.{pdf,xlsx}
```
