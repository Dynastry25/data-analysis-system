# Data Analysis Platform — MVP Specification

## 1. Muhtasari wa mradi

Mfumo na App itakayowasaidia watu na biashara kufanya **uchambuzi wa data** kwa urahisi — bila kuhitaji kujua programming au takwimu za kina. Mtumiaji anapakia faili lake la data, mfumo unalisafisha, kulichambua kitakwimu, na kutoa michoro (graphs) na majibu ya haraka — hata kwa data kubwa (big data).

**Tatizo linalotatuliwa:** watu wengi wenye data (wafanyabiashara, watafiti, mashirika) hawana ujuzi wa Excel/Python/R wa kina kuweza kuchambua data zao vizuri, au wanapoteza muda mwingi kufanya kazi za msingi kama kusafisha data na kuchora chati.

**Mmiliki wa mradi:** Data analyst na full-stack developer mwenye Bachelor of Official Statistics.

---

## 2. Malengo ya MVP

- Kuruhusu mtumiaji **kupakia data** (CSV/Excel) na kuiona papo hapo
- Kutoa **kusafisha data** kwa vitufe rahisi (si code)
- Kutoa **uchambuzi wa kitakwimu wa msingi** (descriptive stats, correlation, regression)
- Kuchora **chati zinazoeleweka na zinazovutia**
- Kuwa **haraka** hata kwa faili kubwa
- Kuruhusu **kupakua ripoti** ya matokeo

---

## 3. Watumiaji walengwa

- Wanafunzi na watafiti wanaohitaji kuchambua data ya utafiti
- Wafanyabiashara wadogo na wa kati wanaotaka kuelewa mauzo/wateja wao
- Taasisi/mashirika yenye data lakini bila timu ya data analyst
- Wataalamu wa takwimu wanaotaka zana ya haraka ya kuchambua na kuonyesha data

---

## 4. Vipengele vya MVP (Web App kwanza)

| Kipengele | Maelezo |
|---|---|
| Auth | Kusajili/kuingia (JWT) |
| Upload | CSV na XLSX pekee (awamu ya kwanza) |
| Data preview | Jedwali la rows/columns + data types |
| Data profiling | Missing values, unique values, aina ya kila column |
| Cleaning | Ondoa duplicates, jaza/ondoa missing values, badilisha data type |
| Statistics | Mean, median, mode, std dev, min/max, correlation matrix, regression rahisi |
| Charts | Bar, line, scatter, histogram (interactive) |
| Export | Kupakua ripoti (PDF/Excel) yenye stats + charts zilizochaguliwa |

*(Vipengele nje ya orodha hii — database connections, AI-insights, team collaboration, mobile app — vimewekwa kwenye sehemu ya "Baada ya MVP" chini.)*

---

## 5. Tech stack

- **Backend:** FastAPI (Python) + Pandas/Polars kwa data processing
- **Big-data speed:** Polars au DuckDB badala ya Pandas peke yake kwa faili kubwa
- **Background jobs:** Celery/RQ + Redis — kwa upload/clean/analyze/export za faili kubwa, ili request isizuie UI
- **Frontend:** React/Next.js + Plotly.js kwa charts
- **Database:** PostgreSQL (metadata ya users, datasets, matokeo)
- **Storage:** Local kwa mwanzo → S3 (au sawa) baadaye ukiongeza scale
- **Auth:** JWT tokens

---

## 6. Database schema (muhtasari)

Jedwali 7 zenye uhusiano — schema kamili (SQL) tayari imetolewa kwenye faili `schema.sql`:

1. **users** — akaunti za watumiaji
2. **datasets** — faili zilizopakiwa (zinahusiana na user)
3. **dataset_columns** — metadata ya kila column (aina ya data, missing/unique counts)
4. **cleaning_actions** — historia ya usafishaji (audit trail)
5. **analysis_results** — matokeo ya takwimu (JSONB, flexible)
6. **charts** — settings za chati zilizotengenezwa
7. **exported_reports** — ripoti zilizopakuliwa

---

## 7. API endpoints (muhtasari)

Muundo kamili tayari umetolewa kwenye faili `api_endpoints.md`. Vikundi vikuu:

- **/auth** — register, login
- **/datasets** — upload, orodha, preview/profile, delete
- **/datasets/{id}/clean** — vitendo vya kusafisha + historia
- **/datasets/{id}/analyze** — kuendesha uchambuzi + kuona matokeo yaliyopita
- **/datasets/{id}/charts** — kutengeneza na kupata chati
- **/datasets/{id}/export**, **/reports/{id}/download** — kutengeneza na kupakua ripoti

---

## 8. UI/UX flow (skrini 6 za msingi)

1. **Ingia/Sajili** — akaunti ya mtumiaji
2. **Pakia data** — drag-and-drop, progress bar
3. **Angalia na safisha** — jedwali la data, badge za missing values, vitufe vya cleaning
4. **Chambua takwimu** — dropdown ya aina ya uchambuzi, matokeo kama jedwali/namba
5. **Chora chati** — dropdown za X/Y axis, aina ya chati, live preview
6. **Pakua ripoti** — checklist ya stats/charts za kujumuisha, generate PDF/Excel

*(Mockup ya skrini ya Ingia/Sajili tayari imeonyeshwa hapo juu kwenye mazungumzo.)*

---

## 9. Mahitaji yasiyo ya kiutendaji (Non-functional requirements)

- **Speed:** matumizi ya Polars/DuckDB, background jobs kwa faili kubwa, indexes kwenye database
- **Scalability:** background job queue inayoweza kuongezwa workers zaidi bila kubadilisha architecture
- **Usalama:** JWT auth, kuhifadhi faili za watumiaji kwa faragha (kila user anaona datasets zake tu), validation ya file type/size wakati wa upload
- **Reliability:** audit trail ya cleaning actions (inaruhusu kufuatilia/kurudisha nyuma)

---

## 10. Awamu za ujenzi (Build roadmap)

**Awamu 1 — Msingi**
- Auth (register/login)
- Upload + preview + data profiling
- Cleaning ya msingi (duplicates, missing values)

**Awamu 2 — Uchambuzi**
- Descriptive stats + correlation + regression rahisi
- Charts (bar, line, scatter, histogram)

**Awamu 3 — Kukamilisha MVP**
- Export (PDF/Excel)
- Background jobs kwa faili kubwa
- Uboreshaji wa UI/UX na testing

---

## 11. Vipimo vya mafanikio (Success metrics za MVP)

- Mtumiaji anaweza kupakia data na kuona matokeo ya kwanza (preview + basic stats) kwa chini ya dakika 1
- Mfumo unaweza kuchambua faili la angalau safu (rows) 100,000+ bila kuchelewa (kutumia background job)
- Mtumiaji anaweza kutoka upload hadi kupakua ripoti bila kuandika code yoyote

---

## 12. Baada ya MVP (Future features)

- AI-generated insights (muhtasari wa kiotomatiki wa matokeo ya uchambuzi)
- Database connections (moja kwa moja kutoka MySQL/PostgreSQL ya mtumiaji)
- Team collaboration (kushirikiana kwenye dataset moja)
- Mobile app (Flutter/React Native)
- Aina zaidi za uchambuzi (time series, clustering, forecasting)
- Faili za ziada (JSON, Google Sheets, API integrations)
