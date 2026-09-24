# API Endpoints — Data Analysis Platform (MVP)

Base URL: `/api`
Auth: JWT Bearer token (isipokuwa `/auth/register` na `/auth/login`)

---

## 1. Auth

### POST /auth/register
Sajili user mpya.
**Body:** `{ full_name, email, password }`
**Response:** `{ id, full_name, email, created_at }`

### POST /auth/login
Ingia na kupata token.
**Body:** `{ email, password }`
**Response:** `{ access_token, token_type: "bearer" }`

---

## 2. Datasets

### POST /datasets/upload
Pakia faili (CSV, XLSX, JSON, TSV, TXT, Parquet). Inaunda record katika `datasets` na
`dataset_columns`. Ukubwa wa juu: MB 50.
**Body:** `multipart/form-data` — file
**Response:** `{ dataset_id, row_count, column_count, columns: [...] }`

### GET /datasets
Orodha ya datasets za user aliyeingia.
**Response:** `[{ id, original_filename, status, uploaded_at, row_count }]`

### GET /datasets/{id}
Taarifa kamili za dataset + preview (rows za kwanza, k.m. 20).
**Response:** `{ dataset, columns, preview_rows }`

### GET /datasets/{id}/profile
Uchambuzi wa haraka wa kila column: aina ya data, missing_count, unique_count, min/max (kwa numeric).

### DELETE /datasets/{id}
Futa dataset na faili lake.

---

## 3. Cleaning

### POST /datasets/{id}/clean
Tekeleza kitendo cha kusafisha data. Kila call inarekodiwa kwenye `cleaning_actions`.
**Body:** `{ action_type: "drop_duplicates" | "fill_missing" | "drop_column" | "convert_type", parameters: {...} }`
- `fill_missing` parameters: `{ column, method: "mean"|"median"|"mode"|"value", value? }`
- `drop_column` parameters: `{ column }`
**Response:** `{ dataset_id, status: "cleaned", row_count, applied_action }`

### GET /datasets/{id}/cleaning-history
Orodha ya vitendo vyote vya cleaning vilivyofanyika kwenye dataset hiyo (audit trail).

---

## 4. Analysis

### POST /datasets/{id}/analyze
Endesha uchambuzi wa kitakwimu. Matokeo yanahifadhiwa kwenye `analysis_results`.
**Body:** `{ analysis_type: "descriptive_stats" | "correlation" | "regression" | "hypothesis_test", parameters: {...} }`
- `descriptive_stats`: hauhitaji parameters (au `columns: [...]` kuchagua columns maalum)
- `correlation`: `{ columns: [...], method: "pearson"|"spearman" }`
- `regression`: `{ target, features: [...] }`
**Response:** `{ analysis_id, analysis_type, result_data }`

### GET /datasets/{id}/analysis
Orodha ya matokeo yote ya uchambuzi yaliyofanyika kwa dataset hiyo.

### GET /analysis/{analysis_id}
Pata matokeo maalum ya uchambuzi mmoja.

---

## 5. Charts

### POST /datasets/{id}/charts
Tengeneza chati.
**Body:** `{ chart_type: "bar"|"line"|"scatter"|"histogram", config: { x, y, group_by? } }`
**Response:** `{ chart_id, chart_type, config, chart_data }`

### GET /datasets/{id}/charts
Orodha ya chati zote zilizotengenezwa kwa dataset husika.

### GET /charts/{chart_id}
Pata chati moja (config + data ya kuchora upya frontend).

---

## 6. Export / Reports

### POST /datasets/{id}/export
Tengeneza ripoti (inaunganisha stats + charts zilizochaguliwa).
**Body:** `{ format: "pdf"|"xlsx", include_analysis_ids: [...], include_chart_ids: [...] }`
**Response:** `{ report_id, status: "processing" }` *(async job — kwa faili kubwa)*

### GET /reports/{report_id}/download
Pakua ripoti iliyokamilika (redirect/stream ya faili).

---

## Vidokezo vya utekelezaji
- Endpoints za `upload`, `clean`, `analyze`, na `export` zenye data kubwa zitumie **background tasks** (Celery/RQ) ili zisizuie request — rudisha `job_id` na endpoint ya `GET /jobs/{job_id}` ya kuangalia status.
- Weka **rate limiting** kwenye `/datasets/upload` kuzuia abuse ya storage.
- Tumia **Pydantic models** kwa kila request/response ili FastAPI ijenge docs (`/docs`) kiotomatiki.
