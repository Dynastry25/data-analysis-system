# Market research: who collects data, why they analyse it, and what they get

Grounding for StatFlow's positioning. Every figure below is sourced; where a
claim is a vendor's own marketing it is labelled as such, because a plan built
on vendor case-study numbers is a plan built on sand.

---

## 1. The headline finding: data is collected and not analysed

This is the single most important number in the research, and it is not a
vendor figure — it is national statistics.

| Survey | Finding |
|---|---|
| UK Business Data Survey 2026 (GOV.UK) | **86% of UK businesses handle digitised data**, but only **25% analyse it to generate new insights.** Large businesses: 69%. Businesses using AI: 37%, vs **17%** for those that do not |
| Canadian Business Privacy Survey 2026 (OPC) | **86% use customer information to provide service**, 34% to personalise, but only **18% for data analytics**. 16% use AI at all |
| ICO Data Controller Study 2025 | 51% of organisations say processing personal data is *essential to their core business functions* — but **36% do it for no stated analytical purpose** beyond product/service operations |

Read together: **roughly three quarters of organisations collect data they never analyse.** The gap is not data availability, tooling budgets, or appetite. It is the capability to turn a file into a defensible answer.

That gap, not "more charts", is the product.

### What they expect to get

The ICO's ranking of *why* organisations process data at all, which doubles as
the list of what they expect analysis to return:

| Purpose | Share of organisations |
|---|---|
| Product and service analytics | **36%** |
| Regulatory or statutory requirements | **27%** |
| Responding to government authorities | 13% |
| Direct marketing | 22% |

And what they expect analysis to *deliver*, from the use-case literature:

- **Evidence instead of intuition** — a number with its method, confidence
  interval and effect size attached
- **Risk caught before it is a loss** — fraud, churn, readmission, equipment
  failure, non-repayment
- **Efficiency** — waste, downtime, inventory carrying cost, cycle time
- **Accountability** — a record of why a decision was made
- **Reproducibility** — the same run, the same answer, next quarter

The last two are consistently the weakest in incumbent tooling (see
§3), and they are exactly what StatFlow already guarantees through versioning
and the standard result format.

---

## 2. Industry map

Organisation types, what they collect, and the decision the analysis serves.
The "typical StatFlow user" column is the honest read on who inside the
organisation would actually use this — it is rarely a data scientist.

### Retail & e-commerce (Walmart, Amazon, MOL, Marriott)
- **Collects:** transactions, prices, inventory, returns, promotions,
  loyalty-programme activity, web/app behaviour
- **Analyses for:** profitable products, stockouts, micro-segmentation,
  dynamic pricing, churn
- **Measured outcomes:** MOL's loyalty micro-segments returned **3× the response**
  of general communications (+20% NPS vs competitors) — *IBM case study*.
  Marriott's dynamic pricing: **$126M incremental revenue** in year one
  (*vendor claim*). Syren AI copilots cut "walked sales" 25%
  (*vendor claim*)
- **Typical StatFlow user:** category manager, merchandiser

### Financial services & insurance (JP Morgan, Bank of America)
- **Collects:** transactions, applications, credit history, alternative
  data (utility/rent payments), claims
- **Analyses for:** fraud, credit risk, compliance, pricing
- **Measured outcomes:** JP Morgan's real-time fraud detection cut
  fraud losses **50% in its first year** (*IBM*). BofA's models using
  alternative data: **15% more loan approvals** in underserved segments and
  **40% fewer non-performing loans** (*vendor claim*). Fraud-mitigation
  accuracy ~95% in one vendor deployment (*vendor claim*)
- **Typical StatFlow user:** risk analyst, credit officer

### Healthcare (Kansas Health System, Mass General Brigham)
- **Collects:** EHR records, claims, device/telemetry, scheduling, forms
- **Analyses for:** readmission risk, deterioration, resource planning,
  documentation burden
- **Measured outcomes:** Kansas Health System cut 30-day readmissions
  **39%** (52% for heart failure) — the strongest number in this research
  because it is a named, verifiable deployment. 71% of US acute-care
  hospitals had predictive AI in their EHR by end-2024 (*industry data*)
- **Typical StatFlow user:** clinical informatics, quality lead

### Manufacturing & industrials (PepsiCo, FleetPride, automotive OEMs)
- **Collects:** IIoT sensor data, production logs, quality inspections,
  supplier and logistics records
- **Analyses for:** predictive maintenance, quality control, supply-chain
  disruption, throughput
- **Measured outcomes:** PepsiCo+Frito-Lay computer-vision quality checks
  **>$300,000 saved** (*IBM*); PepsiCo digital twins **+20% throughput**,
  10–15% lower capex (*vendor claim*); an automotive OEM's graph-ML
  supplier-risk twin avoided **~$80M** in annual losses (*vendor claim*)
- **Typical StatFlow user:** operations engineer, quality manager

### Government & official statistics (US federal CDO Council, smart cities)
- **Collects:** administrative records, census and survey data, service
  delivery, permits, compliance filings
- **Analyses for:** policy impact, fraud in benefits, urban planning,
  service allocation, statutory reporting
- **Measured outcomes:** the US CDO Council's NLP analysis of millions of
  regulatory comments was reported as more efficient with better insight,
  but published **no effect size** — typical of public sector
- **Typical StatFlow user:** statistician, programme evaluator — StatFlow's
  bilingual UI and assumption gate map directly onto this user

### NGOs, donors & development
- **Collects:** household and field surveys, programme M&E data, baseline and
  endline measurements
- **Analyses for:** programme effect, targeting, donor reporting, survey
  weighting
- **StatFlow advantage:** this is where `permanent_crop.dta`-style survey
  data, weighted frequencies, Likert analysis and Cronbach's alpha actually
  matter — and where the incumbents price them out. The bilingual UI is a
  moat here, not a nicety

### Telecom, SaaS & subscriptions
- **Collects:** usage, billing, support tickets, churn signals
- **Analyses for:** churn prediction, pricing, capacity
- **Measured outcomes:** one vendor reports **$100M retention value** from
  churn prediction (*vendor claim*) — treat the figure as illustrative, not
  typical

---

## 3. Where StatFlow should compete, given all this

Three findings drive the plan:

**1. The market is mostly small organisations.* The UK data shows analysis
concentrates in large businesses (69%) while the population sits at 25%.
Small and micro businesses collect data, cannot analyse it, and cannot afford
a SAS licence or a data scientist. Per-organisation pricing and the
Stata/SPSS/R readers are aimed here.

**2. Data quality is their stated pain.** The ICO found **53%** of
organisations struggle to keep data current and **49%** to keep it accurate,
and 35% lack expertise in the legal requirements. That is the data-prep and
governance moat, and it is a *bigger* reported problem than tooling.

**3. The "AI" numbers are vendor claims.** The $100M, $126M, $80M and 95%
figures are all from vendors selling the thing they measured. The verifiable
numbers — Kansas readmissions, JP Morgan fraud, MOL segment response — are
the credible ones, and they all share a shape: **a measurable operational
decision, not a dashboard.** StatFlow's reproducibility and decision-support
framing is aimed at that.

---

## 4. What this means for the product, concretely

| Finding | Product consequence |
|---|---|
| 75% collect, don't analyse | The product must work **without a statistician**. Interpretation and assumption gating are not polish — they are the whole pitch |
| Analysis skews to large orgs | **Per-organisation pricing**, and a free tier that is genuinely usable |
| 49% struggle with data accuracy | Prep guidance and validation are the acquisition wedge |
| Stata/SPSS/R users exist in government and academia | The readers are already built — **lead with them** |
| 36% do no analysis at all | Templates for the question they already ask beat an empty studio |
| Vendor numbers are unverifiable | **Publish benchmarks and reproducible runs.** Being the tool that shows its work is defensible; being the tool with a big number is not |

---

## Sources

- UK Business Data Survey 2026, GOV.UK — business data handling, analysis
  rates, sector variation
- ICO / IFF Research Data Controller Study 2025 — purposes of processing,
  acquisition routes, data-accuracy challenges
- Survey of Canadian Businesses on Privacy-Related Issues 2026, OPC — use of
  customer information, AI adoption
- IBM, "What are big data use cases?" — JP Morgan, Frito-Lay, MOL
- LatentView, AI predictive analytics ROI across industries — cross-industry
  case studies (vendor source, labelled)
- AI Agent Corps, AI agent ROI by industry 2026 (vendor source, labelled)
- ainformat, Industry Solutions 2026 — hospital and financial services
  adoption rates
