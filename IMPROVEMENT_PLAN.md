# StatFlow improvement plan

Grounded in the market research (Excel/Power BI/SPSS/SAS/R weakness data, the
65%-of-project-time data-prep figure, the 87%-low-BI-maturity and 85% project
failure figures) and in what this codebase already implements.

The through-line: **the market does not need more power, it needs trust.** The
incumbents split into *powerful but specialist-only* (R, SAS, SPSS) and
*accessible but statistically shallow and untrustworthy* (Excel, BI dashboards).
Nothing closes that gap. StatFlow can, because the engine, versioning and
assumption checks already exist.

---

## Phase 1 — Trust & guidance (highest leverage, mostly already built)

| # | Item | Why it wins | Status here |
|---|------|-------------|-------------|
| 1.1 | **Progressive-disclosure studio UI** | 156 methods inline buried the task | Done — statistics page + explore page now lead with the task; method guide, stage plan, recommendation and history are dialogs |
| 1.2 | **Assumption gate** | The `fail` state was invisible: it lived only inside the recommendation panel, which is one click away, so a blocking verdict could not stop the run it should stop | Done for the recommendation path — the engine's `fail` checks now render on the statistics page and disable the run when the reader is using the method they refer to. **Still open:** the direct-run path has no checks at all (`StandardResult` does not carry `assumption_checks`; only `Recommendation` does), which needs the engine to compute diagnostics inside `run_analysis` — see 2.3 |
| 1.3 | **Plain-language interpretation per method** | Non-specialists cannot read estimate/CI/effect size | To do — auto-generate "what this means and what it does not mean" from the stage plan |
| 1.4 | **Reproducibility badge on every result** | `.pbix` files and Excel sheets cannot be diffed or rolled back | Half done — `ProvenanceStrip` exists; needs the replay/parameter-hash affordance promoted to a one-click action |
| 1.5 | **Result caching** keyed by `(analysis_type, parameters, dataset_version)` | Free speed win; identical re-runs return instantly | To do |

## Phase 2 — Accuracy & speed

| # | Item | Why |
|---|------|-----|
| 2.1 | Parquet columnar cache + incremental refresh | Repeated analyses must never re-read the source file |
| 2.2 | Publish benchmarks on real datasets | A speed claim without numbers is not a claim |
| 2.3 | Engine validation against textbook results | Accuracy is a legal-grade claim; needs a suite |
| 2.4 | Guardrails: refuse p-values without naming the test; warn on multiple comparisons | Prevents p-hacking by accident |

## Phase 3 — The data-prep moat

| # | Item | Why |
|---|------|-----|
| 3.1 | One-click remediation from validate findings | Prep is >65% of project time and 10–11 hrs/week; automating it is the biggest single saving available |
| 3.2 | Source-to-analysis lineage view | Lets a non-technical user trace where a number came from |
| 3.3 | Templates for common org questions | Donor reporting, program evaluation, crop yield, retention |

## Phase 4 — GTM and positioning

| # | Item | Why |
|---|------|-----|
| 4.1 | Price **per organisation / active use**, not per seat | Power BI Pro ($14/user/mo) and PPU ($24) charge dormant users; SAS is $8k–15k per user/yr |
| 4.2 | Lead with the **Stata/SPSS/R readers** | Migration is the product feature; these are the entry wedge against 76% still in Excel |
| 4.3 | Target: East African NGOs, government statistical offices, universities, cooperatives, agri research | The English + Swahili bilingual UI is a moat no incumbent is competing for |
| 4.4 | Offer R/Python export for the tail | Never try to beat 21,000+ CRAN packages on breadth |

## Do not do

- Do not compete on method breadth with R/Python.
- Do not add a proprietary calculation language (DAX is Power BI's biggest
  weakness — six months to competence, two to three years to expert).
- Do not add a per-seat licensing model.

---

## UI pattern: content behind a click

Established in this cycle and reusable everywhere:

- `Modal` — a centre dialog with backdrop, Escape, focus move/restore and
  scroll lock. For reference material consulted mid-run: the method guide,
  the assumption checks, the stage plan.
- `CollapsibleCard` — content that is *sometimes* wanted on the page, where
  the summary already tells you whether to open it.
- `PanelDrawer` + `PanelCard` — the studio's secondary panels.

**Rule:** the page leads with what the user came to do; every answer to
"what is this / show me more / what happened" is one click away, and each of
those gets the whole viewport.

Applied so far: statistics page (guide, stages, recommendation, history,
question, plus the assumption-gate banner), explore page (per-column
profile), studio (per-column profile table), upload page (prep advice,
closed by default).

Checked and deliberately left alone: the **help** page and the **admin audit**
page. Both are already short, well-structured reference pages — the help page
is a search box plus five small cards, the audit page is a filter plus a table.
Folding either would move content around without removing any.

---

## Known gap: assumption checks on direct runs

`AssumptionCheck` is attached to `Recommendation` only. A `StandardResult`
from a direct analysis carries `warnings` but no assumption verdicts, so the
statistics page cannot gate a run the reader configured by hand.

The engine already has everything needed — `pair_diagnostics()` computes
missingness, sample size, group sizes, normality and outliers, and
`assumption_checks()` turns those into PASS/WARN verdicts. The gap is that
`run_analysis()` dispatches to a handler and never sees which columns were
used, so it has nothing to attach the checks to.

To close it: have each handler (or `run_analysis`, via a declared column
contract) report the columns it consumed, compute diagnostics for that pair,
and attach `assumption_checks` to the standard result. Until then the gate
covers the recommendation path only — which is the path the engine itself
recommends, and the one most readers use.
