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
.\venv\Scripts\python.exe tests\smoke_test.py     # end-to-end journey (88 checks)
.\venv\Scripts\python.exe tests\statflow_test.py  # statflow engines (216 checks)
.\venv\Scripts\python.exe -m pytest               # same journeys, pytest runner
```

Each test creates a temporary database + storage folder, generates sample files and walks
the whole journey (auth → upload → clean → stats → charts → xlsx/pdf export → download →
privacy checks → delete). A full log is written to `smoke_test_out.log` /
`statflow_test_out.log`.

`smoke_test.py` also uploads **JSON / TSV / TXT / Parquet** datasets and checks preview +
versioned cleaning for each format.

Result with the current code: **all checks pass**.

---

## 4. Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///backend/app.db` | SQLAlchemy URL. Point it at PostgreSQL for production, e.g. `postgresql+psycopg2://user:pass@localhost:5432/data_analysis` |
| `SECRET_KEY` | dev placeholder | JWT signing key — **change in production** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT lifetime |
| `STORAGE_DIR` | `backend/storage` | Where dataset files and reports are stored |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | Allowed CORS origin |

## 5. Project layout

```
backend/
├── app/
│   ├── main.py            # FastAPI app, CORS, router registration, table creation

## 6. What each endpoint does (short version)

- **Upload**: validates the extension (`.csv`, `.xlsx`, `.json`, `.tsv`, `.txt`,
  `.parquet`) and a 50MB ceiling *while* streaming the file to
  `storage/{user_id}/{dataset_id}/data{ext}`; profiles every column
  (type, missing count, unique count, min/max) and stores it in `dataset_columns`.
  `.txt` delimiter is auto-sniffed; every format shares the same `read_dataframe`
  path (and the version store), so cleaning, statistics, charts and exports work
  identically for all of them.
- **Profile**: recomputes the profile from the file on disk and refreshes the stored
  metadata, so it always matches the current (cleaned) data.
- **Clean / transform (versioned)**: every operation on
  `POST /api/v1/datasets/{id}/clean|transform` writes a new immutable
  `dataset_versions` row (parquet) plus a `dataset_operations` audit entry.
  Cleaning: `drop_duplicates`, `drop_missing`, `fill_missing`
  (drop/mean/median/mode/zero/constant), `rename_columns`, `cast_types`
  (numeric/integer/text/date/boolean). Transforms: `select_columns`,
  `filter`, `sort`, `calculate_column`, `group_by`, … (see
  `GET /api/v1/datasets/operations/catalog`).
- **Analyse (unified engine)**: `POST /api/v1/datasets/{id}/analysis` runs
  `descriptive`, `frequency`, `pearson`/`spearman`, `welch_t_test`,
  `mann_whitney`, `chi_square`, `one_way_anova`, `kruskal_wallis` or
  `linear_regression` and always returns the same standard-result structure
  (status / estimate / test / confidence interval / effect size / diagnostics
  / tables). Saved runs live in `analysis_runs` and feed the export.
- **Planning + assistant**: `POST /api/v1/planning/profile|recommend`
  detects variables and recommends a method; `POST /api/v1/assistant/ask`
  answers plain-language questions with a verified engine result.
- **Charts**: returns Plotly-ready `chart_data` (`series[]` with x/y plus axis labels),
  capping categories (50) and scatter points (5000) so big files stay responsive.
- **Export**: `POST` returns `202` with `{report_id, status: "processing"}` and builds the
  PDF/XLSX in a FastAPI `BackgroundTasks` job; poll `GET /reports/{id}/status`, then
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
   `Base.metadata.create_all()` (or Alembic) to apply the schema.
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
│   │                      #  AnalysisRun)
│   ├── schemas.py         # Pydantic request/response models (drive /docs)
│   ├── security.py        # bcrypt password hashing + JWT create/decode
│   ├── deps.py            # get_current_user + dataset ownership checks
│   ├── routers/           # auth, datasets, charts, reports
│   └── services/
│       ├── data_service.py     # upload storage, reading, profiling
│       ├── chart_service.py    # Plotly-ready chart data (bar/line/scatter/histogram)
│       └── export_service.py   # XLSX workbook + PDF document writers
│   └── statflow/          # unified engines: versioning, operations,
│                          # statistics, planning, assistant (+ v1 routers)
├── tests/smoke_test.py
├── requirements.txt
└── storage/               # uploads: storage/{user_id}/{dataset_id}/data.{csv,xlsx}
                           # reports: storage/reports/report_{id}_{name}.{pdf,xlsx}
```
