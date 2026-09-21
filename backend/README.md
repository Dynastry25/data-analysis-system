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

## 3. Run the smoke test

```powershell
cd D:\Project\Data-Analysis-system\backend
.\venv\Scripts\python.exe tests\smoke_test.py
```

It creates a temporary database + storage folder, generates a sample CSV and walks the
whole journey (auth → upload → clean → stats → charts → xlsx/pdf export → download →
privacy checks → delete). A full log is written to `smoke_test_out.log`.

Result with the current code: **68 checks passed**.

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

- **Upload**: validates the extension (`.csv`, `.xlsx`) and a 50MB ceiling *while
  streaming* the file to `storage/{user_id}/{dataset_id}/data{ext}`; profiles every column
  (type, missing count, unique count, min/max) and stores it in `dataset_columns`.
- **Profile**: recomputes the profile from the file on disk and refreshes the stored
  metadata, so it always matches the current (cleaned) data.
- **Clean**: every action mutates the stored file, refreshes the column metadata, updates
  `row_count`/`column_count`/`status` and appends a row to `cleaning_actions` (audit
  trail). Actions: `drop_duplicates`, `fill_missing` (mean/median/mode/value),
  `drop_column`, `convert_type` (numeric/integer/text/date/boolean).
- **Analyse**: results are stored in `analysis_results.result_data` (JSON) and returned
  immediately. Types: `descriptive_stats`, `correlation` (pearson/spearman), `regression`
  (OLS with coefficients, R squared, adjusted R squared, std. error and the fitted
  equation) and `hypothesis_test` (one-sample or Welch two-sample t-test; the p-value
  comes from the regularized incomplete beta function, so scipy is not required).
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
│   ├── models.py          # 7 tables from schema.sql (User, Dataset, DatasetColumn,
│   │                      #  CleaningAction, AnalysisResult, Chart, ExportedReport)
│   ├── schemas.py         # Pydantic request/response models (drive /docs)
│   ├── security.py        # bcrypt password hashing + JWT create/decode
│   ├── deps.py            # get_current_user + dataset ownership checks
│   ├── routers/           # auth, datasets, cleaning, analysis, charts, reports
│   └── services/
│       ├── data_service.py     # upload storage, read/write, profiling, cleaning actions
│       ├── analysis_service.py # descriptive stats, correlation, regression, t-test
│       ├── chart_service.py    # Plotly-ready chart data (bar/line/scatter/histogram)
│       └── export_service.py   # XLSX workbook + PDF document writers
├── tests/smoke_test.py
├── requirements.txt
└── storage/               # uploads: storage/{user_id}/{dataset_id}/data.{csv,xlsx}
                           # reports: storage/reports/report_{id}_{name}.{pdf,xlsx}
```
