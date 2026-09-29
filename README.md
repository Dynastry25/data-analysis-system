# Data Analysis Platform — MVP

Mfumo wa kuchambua data kwa urahisi: **pakia faili lako (CSV/Excel) → safisha → chambua
kitakwimu → chora chati → pakua ripoti** bila kuandika code yoyote.

Hii ni implementesheni ya MVP kwa mujibu wa nyaraka za mradi:

| Faili | Maudhui |
|---|---|
| `MVP.pdf` | Muhtasari wa mradi (source document) |
| `mvp_specification.md` | Spec kamili: vipengele, tech stack, roadmap, success metrics |
| `api_endpoints.md` | API contract (endpoints zote) |
| `schema.sql` | Database schema (PostgreSQL, tables 7) |
| `ui_ux_design_system.md` | Design system (rangi, fonts, vitufe, motion, accessibility) |

---

## 1. Kilichojengwa (status)

| Kipengele cha MVP | Hali | Wapi |
|---|---|---|
| Auth (register/login, JWT) | ✅ | `backend/app/routers/auth.py`, `app/login`, `app/register` |
| **Dashboard home** (metrics, quick actions, recent datasets, workflow guide) | ✅ | `app/dashboard`, AppShell sidebar + `WorkflowStrip` |
| Upload CSV/XLSX (validation + progress) | ✅ | `backend/app/routers/datasets.py`, `app/upload` |
| Data preview (rows, columns, types) | ✅ | `app/datasets/[id]` |
| Data profiling (missing/unique/min/max) | ✅ | `GET /datasets/{id}/profile` |
| Cleaning + transforms with immutable versions + audit trail | ✅ | Data Studio (`app/datasets/[id]/studio`), `POST /api/v1/datasets/{id}/clean|transform`, `dataset_versions` + `dataset_operations` tables |
| Unified statistics (descriptive, correlation, regression, t-test, ANOVA, chi-square…) | ✅ | Statistics page (`app/datasets/[id]/statistics`), `stats_engine.py`, `analysis_runs` table |
| AI statistical assistant (natural-language questions, verified results) | ✅ | Assistant page (`app/datasets/[id]/ask`), `POST /api/v1/assistant/ask` |
| Charts (bar, line, scatter, histogram — interactive) | ✅ | `chart_service.py`, `ChartView.tsx` (Plotly) |
| Export (PDF + Excel) | ✅ | `export_service.py` (reportlab + openpyxl) |
| Hifadhi ya metadata (users, datasets, columns, matokeo, chati, ripoti) | ✅ | `models.py` / `schema.sql` |
| **Mashirika, wanachama na RBAC** (owner > admin > analyst > viewer) | ✅ | `backend/app/rbac.py`, `POST/GET /api/v1/organizations*`, `app/organizations` |
| **Miradi (project folders)** ndani ya mashirika | ✅ | `projects` table, `/api/v1/organizations/{id}/projects`, `app/organizations/[id]` |
| **Migration za database (Alembic)** | ✅ | `backend/migrations/`, `alembic upgrade head` |
| **Ufikiaji wa data kwenye shirika** (dataset iliyo kwenye mradi kufuatwa kwa role) | ✅ | `deps.get_owned_dataset` (`min_role` parameter) |

**Mtiririko wa uendeshaji (UI):** kila dataset inafuata **hatua 11** zilizopangwa katika
**awamu 6** — Data → Prepare → Analyze → Visualize → Explain → Report. Shell ya
mtumiaji ina: sidebar yenye Dashboard/Projects/Data + awamu 5, top bar (tafuta, msaada,
shughuli, akaunti), na `WorkflowStrip` juu ya kila ukurasa. Ndani ya dataset,
`JourneyRail` huonyesha hatua zote 11 kwa ushahidi halisi (si namba tu). Definisi yote
iko `frontend/lib/pipeline.ts` (chanzo kimoja cha kweli).

Awamu zote tatu za roadmap (§10 ya spec) zimefikiwa: **Awamu 1** (auth, upload, preview,
profiling, cleaning), **Awamu 2** (stats, correlation, regression, charts), **Awamu 3**
(export PDF/Excel, background jobs, UI/UX + testing).

---

## 2. Jinsi ya kuiendesha (Windows PowerShell)

**Backend (terminal 1):**

```powershell
cd D:\Project\Data-Analysis-system\backend
.\venv\Scripts\python.exe -m pip install -r requirements.txt   # mara ya kwanza pekee
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

- API: `http://localhost:8000/api` · Docs: `http://localhost:8000/docs`

**Frontend (terminal 2):**

```powershell
cd D:\Project\Data-Analysis-system\frontend
npm install        # mara ya kwanza pekee
npm run dev
```

- App: `http://localhost:3000` (kama backend iko kwenye port nyingine, weka
  `NEXT_PUBLIC_API_URL` kwenye `frontend/.env.local`)

**Kuthibitisha kila kitu kinafanya kazi:**

```powershell
cd D:\Project\Data-Analysis-system\backend
.\venv\Scripts\python.exe tests\smoke_test.py     # end-to-end: 88 checks
.\venv\Scripts\python.exe tests\statflow_test.py  # statflow: 216 checks
.\venv\Scripts\python.exe -m pytest               # zote mbili (fast variant)
```

Nywila ya kuthibitisha format mpya (JSON/TSV/TXT/Parquet) iko ndani ya `smoke_test.py`.

---

## 2b. Docker (production-mfumo wa kwanza)

Kama una Docker, unaweza kuendesha stack nzima (PostgreSQL + backend + frontend)
kwa amri moja:

```powershell
cd D:\Project\Data-Analysis-system
Copy-Item .env.example .env    # kisha badili SECRET_KEY
docker compose up --build
```

- App: `http://localhost:3000` · API: `http://localhost:8000/api` · Docs: `http://localhost:8000/docs`
- Data yote inakaa kwenye volumes `pgdata` na `statflow-data`.

---

## 2c. Kupeleka (Deployment) — Vercel (frontend) + Render (backend)

Mfumo una sehemu mbili, kila moja inapelekwa kwenye mfumo wake:

| Sehemu | Mfumo | Kwa nini |
|---|---|---|
| Frontend (Next.js) | **Vercel** (GitHub integration) | Vercel ni bora kwa Next.js |
| Backend (FastAPI) | **Render** (blueprint `render.yaml`) | Python + Postgres + diski ya kudumu kwa faili za upload |

> **Kumbuka:** Vercel haendeshi FastAPI katika production — backend hii inahitaji Postgres,
> storage ya kudumu na processing za muda mrefu. Kwa hiyo backend inapelekwa kwenye Render.

### Hatua 1 — Backend kwenye Render (fanya kwanza, ili upate URL)

1. Weka repo kwenye GitHub (ikiwa bado haijawekwa).
2. Render → **New → Blueprint** → chagua repo hiyo. Render inasoma `render.yaml`
   (repo root) na inaunda: web service `statflow-api` + Postgres `statflow-db` +
   persistent disk kwa uploads.
3. Baada ya deploy, fungua service → **Environment** na uweke:
   - `FRONTEND_ORIGIN` = URL ya Vercel app (baada ya hatua ya 2) — au `*` kwa muda.
4. Thibitisha: `https://<service-host>/api/health` inarudisha `{"status":"ok"}` inajulikana.
   Docs: `https://<service-host>/docs`.

> **Mipango:** free Postgres inaisha baada ya ~siku 30 (upgrade kwa paid plan kwa DB ya
> kudumu). Diski ya kudumu inahitaji plan **starter** (au zaidi) kwenye web service.

### Hatua 2 — Frontend kwenye Vercel (GitHub integration)

1. Vercel → **Add New → Project** → import GitHub repo hii.
2. Weka **Root Directory** = `frontend` (repo ni monorepo: `backend/` + `frontend/`).
3. Framework itatambulika (Next.js) moja kwa moja; build command default `npm run build`.
4. Weka environment variable:
   - `NEXT_PUBLIC_API_URL` = `https://<render-service-host>/api`
5. Bonyeza **Deploy**. Kila `git push` inadeploy upya moja kwa moja.

> `NEXT_PUBLIC_API_URL` inachomeka wakati wa build — weka kabla ya first deploy.

### Hatua 3 — Kuunganisha (CORS)

`backend/app/config.py` inakubali origins nyingi kwa comma, kwa hiyo unaweza kuweka:

```
FRONTEND_ORIGIN=https://statflow.vercel.app,http://localhost:3000
```

hivyo dev ya ndani na production zote zinafanya kazi kwa API moja.

---

## 3. Mtiririko wa mtumiaji (user journey)

1. **Sajili / ingia** — JWT token huhifadhiwa kwenye browser, kila request ina
   `Authorization: Bearer …`.
2. **Pakia data** — drag & drop CSV, XLSX, JSON, TSV, TXT au Parquet (hadi 50MB).
   Mfumo unathibitisha aina na ukubwa wa faili, kisha unachambua columns zote.
3. **Angalia & safisha** — preview ya rows 20 za kwanza, jedwali la columns (aina, missing,
   unique, min/max), badge za tahadhari kwa missing values, na vitufe 4 vya usafishaji.
   Kila kitendo kinarekodiwa kwenye audit trail.
4. **Chambua takwimu** — descriptive stats, correlation (pearson/spearman), regression
   (OLS) na hypothesis test (t-test). Matokeo yanahifadhiwa na yanaonekana kwenye jedwali.
5. **Chora chati** — chagua X/Y/group_by/aggregate, chati inaonekana papo hapo (Plotly).
6. **Pakua ripoti** — chagua takwimu na chati, kisha PDF au Excel; ripoti inaandaliwa
   nyuma ya pazia (background job) na kupakuliwa.

---

## 4. Muundo wa mfumo

```
Browser (Next.js 14 + Tailwind + Plotly)
        │  JSON + JWT (Authorization: Bearer)
        ▼
FastAPI  /api/auth  /api/datasets  /api/datasets/{id}/charts|export  +  /api/v1/* (versions, analysis, planning, assistant)
        │
        ├── SQLAlchemy ORM  ──►  SQLite (dev) / PostgreSQL (production, schema.sql)
        ├── pandas          ──►  CSV/XLSX processing, profiling, cleaning, statistics
        ├── reportlab/openpyxl ──►  PDF / Excel reports
        └── storage/        ──►  storage/{user_id}/{dataset_id}/data.{csv,xlsx}, reports/
```

Kila dataset, column, kitendo cha usafishaji, matokeo ya uchambuzi, chati na ripoti
vinahifadhiwa — hivyo mtumiaji anaweza kurudi baadaye na kuona kazi yake yote.

---

## 5. Usalama na faragha

- JWT auth kwenye endpoints zote isipokuwa `register`/`login`.
- Kila endpoint ya dataset inahakikisha dataset ni ya mtumiaji aliyeingia (403 vinginevyo).
- Faili huhifadhiwa kwenye folder la mtumiaji (`storage/{user_id}/…`).
- Validation ya aina ya faili na ukubwa (50MB) wakati wa upload.
- Neno la siri huhifadhiwa kwa bcrypt hash (salt ya random).

---

## 6. Vipimo vya mafanikio (kutoka spec §11)

| Kipimo | Hali |
|---|---|
| Kupakia data na kuona preview + stats kwa chini ya dakika 1 | ✅ (faili la kawaida: sekunde chache) |
| Kuchambua safu 100,000+ bila kuzuia UI | ⚠️ Inafanya kazi (bila memory ya ziada — upload inasoma kwa chunks), lakini kwa sasa uchambuzi unafanyika ndani ya request. Awamu inayofuata: kuhamisha `analyze`/`clean` kwenye Celery/RQ worker (API contract haitabadilika) |
| Kutoka upload hadi ripoti bila kuandika code | ✅ |

### 6b. Uamuzi wa utendaji: Polars/DuckDB (spec §5 na §9)

Spec §5/§9 zinadai **Polars au DuckDB badala ya Pandas peke yake kwa faili kubwa**. Ilipimwa
(1,000,000 safu × 14 columns, CSV 211 MB) kabla ya kuamua, na matokeo yalikuwa:

| Njia | muda | Thibitisho |
|---|---|---|
| Sasa (pandas) | 7.94s | msingi |
| DuckDB kwa kuwa na `profile_columns` kwenye SQL | 3.11s (2.7x) | **Haipo salama** — angalia hapa chini |
| DuckDB kwa reader tu (faili ≥ 8 MB) | 6.61s (1.20x) | `data_type`/`missing_count`/`unique_count`/`min` sawana; ~30% ya floats tofauti |

**Kwa nini DuckDB haukubaliwa:**

1. **Aina ya data haisambieni.** Kisha DuckDB iliotua kila kitu kuwa `VARCHAR` ili kuondoa
   kiole, lakini hivyo ndivyo ilivyoharibu upande mwingine: pandas huripoti kipeo
   `numeric` kwa kulinganisha **dtype**, ambayo njia ya VARCHAR haisemi. Matokeo: kila
   algorithm ya SQL itabadilisha utambuzi wa aina.
2. **Faida ndogo sana.** Reader pekee ni 1.20x tu, kwa sababu `profile_columns` (hasa
   `infer_column_type`) ndio bottleneck, si kusoma.
3. **Usahihi wa data.** Kati ya 27-32% ya floats zilizotoka kwenye faili kubwa zinalipwa
   tofauti na pandas (dhamana kubwa 9e-13). DuckDB ndio anayopanga kwa uweli; parser ya
   C ya pandas ndio haipo. Tokeo: thamani zinazohifadhiwa zinabadilika kwa faili kubwa.

**Ilichukuliwa badala yake:** `infer_column_type` ilikuwa ikifanya `astype(str)` mara mbili
kwenye kila column. Kuondoa ile nakala rudufu ni salama kabisa (imehakikiwa kwenye
mifano 10 ya hali magumu) na inaimaliza kwa 1.19x (3.04s → 2.56s) bila kubadilisha
tabia yoyote.

**Ikiwa sasa uamua:** hii si "fanyia polea". Inasema tu kwamba iko hatua moja tu — kupima
kabla ya kuongeza mzigo.

---

## 7. Baada ya MVP (future work — spec §12)

- AI-generated insights (muhtasari wa kiotomatiki wa matokeo).
- Database connections (MySQL/PostgreSQL ya mtumiaji moja kwa moja).
- Team collaboration kwenye dataset moja.
- Mobile app (Flutter/React Native).
- Aina zaidi za uchambuzi: time series, clustering, forecasting.
- Faili za ziada: JSON, Google Sheets, API integrations.
- Miundombinu: kuhama SQLite → PostgreSQL, Celery/RQ + Redis kwa jobs, local storage → S3,
  Alembic migrations, object storage yenye signed URLs.

Ufafanuzi wa kila uamuzi wa MVP (kwa nini SQLite, kwa nini BackgroundTasks, n.k.) uko
kwenye `backend/README.md` §8.
