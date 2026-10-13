# Benchmarks

A speed claim without numbers is not a claim. Everything below was measured
on this machine with the tool that ships in the repo, and every number can be
reproduced by running one command.

**How it was measured**

| | |
|---|---|
| Machine | Intel Core i7-8650U @ 1.90GHz, 4 cores, 8 GB RAM |
| OS | Windows 11 Pro 10.0.26300 |
| Python | 3.14.6 |
| pandas | 3.0.6 |
| numpy | 2.5.3 |
| Dataset | 200,020 rows x 11 columns, 19.5 MB in memory (fixed seed `20261013`) |
| Command | `python -m tools.benchmark --rows 200000` |

The dataset is generated, not curated: demographics, a free-text note, a date
column, ~2% missing values in four columns, and 20 exact duplicate rows — the
shape and the mess of an organisational file. The timings cover the engine's
own code paths (version store, profile, validate, statistics), not an HTTP
layer in front of them, so they are a lower bound on what a request costs.

## Results

| Path | Time | Notes |
|---|---|---|
| Upload -> v1 (read CSV, write parquet) | **2,813 ms** | once per upload |
| Profile (per-column type, missing, unique, min/max) | **3,478 ms** | mean of 3 runs |
| Validate (all data-quality findings) | **3,587 ms** | verdict `warnings` |
| Welch t-test | **1,193 ms** cold / **0.015 ms** cached | 77,000x faster on repeat |
| One-way ANOVA | **1,964 ms** cold / **0.048 ms** cached | 40,000x faster on repeat |
| Correlation matrix (11 variables) | **1,023 ms** cold / **0.028 ms** cached | 36,000x faster on repeat |
| Linear regression (4 predictors) | **1,840 ms** cold / **0.029 ms** cached | 63,000x faster on repeat |
| Version read, repeated | **9.8 ms** | from the frame cache |
| drop_duplicates (compute + write v2) | **438 ms + 663 ms** | removes 20 rows |

## What the caches do and do not fix

**Repeat a run and it is free.** The result cache is keyed by
`(dataset_version_id, analysis_type, parameters)`. A reader who changes the
confidence level and runs again, or who goes back to a result they already
have open, gets the stored result in ~0.03 ms rather than a full recompute.
Versions are immutable, so the key can never describe stale data.

**Reading the same file five times costs one read.** Profile, preview, validate,
a chart and an analysis all load the same version within seconds of each other.
The frame cache decodes the parquet once (189 ms for this file) and hands out
copies; five warm reads total ~50 ms instead of ~950 ms.

**What is not cached, and should not be.** A different version, different
parameters, or a different analysis is different work and is recomputed. The
caches are keyed correctly or not at all: an entry is never reused for anything
it does not exactly describe.

## Reproducing this

```bash
cd backend
python -m tools.benchmark --rows 200000   # or --rows 50000 for a faster run
python -m tools.benchmark --json          # machine-readable
```

Expect different absolute numbers on different hardware — the ratios are what
travel (a cached repeat is microseconds; a cold analysis is seconds; an upload
is seconds). Run it before claiming a number.

## Notes and limits

* Single process, SQLite, warm OS cache, no concurrency. The numbers are the
  engine's cost, not a server's throughput; a busy multi-user deployment adds
  contention this benchmark does not measure.
* The first run of anything in a fresh process is slower (imports, page faults).
  Where that matters the table separates the cold path from the cached one.
* `profile` and `validate` scale with row count and are the two slowest
  per-row paths that run on every upload. They are the first place to look if
  the engine gets faster.
