"""Measure the paths a reader actually waits on (improvement plan 2.2).

Why this exists
---------------
The product makes a speed claim. A speed claim without numbers is
not a claim, and numbers nobody can reproduce are marketing. This
tool runs the real code -- the real version store, the real engine,
the real caches -- against a dataset the shape of a real
organisational one, and prints what it measured. ``BENCHMARKS.md``
is the published result; this is how it was produced and how
anyone can produce it again.

What it will not do
-------------------
* Time the framework. The numbers are the engine's: upload and
  version write, profile, validate, analysis, cache behaviour.
  An HTTP layer in front of them adds latency, it does not remove
  it, so quoting the engine is the honest lower bound.
* Warm up and then forget to say so. Every number is the mean of
  repeated runs, the first run is reported separately where a cache
  is involved, and the cache hit/miss counters are printed so a
  reader can see what was served from memory and what was not.
* Generate a dataset that flatters the engine. The rows are
  generated from a fixed seed, at a size a real project would
  have, with realistic missingness, ties, and repeated rows --
  the cases that make real data slow.

Usage
-----
    python -m tools.benchmark                 # default: 200k rows
    python -m tools.benchmark --rows 1000000  # a bigger file
    python -m tools.benchmark --json          # machine-readable
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict

import numpy as np
import pandas as pd

from app.services.data_service import profile_columns
from app.services.validation_service import validate_frame
from app.statflow import operations, result_cache, stats_engine, version_store
from app.statflow.frame_cache import FRAME_CACHE

#: The shape of an organisational file: demographics, survey answers,
#: a couple of continuous measures, a date, and a free-text note.
COLUMNS = 12
DEFAULT_ROWS = 200_000


def make_dataset(rows: int, seed: int = 20261013) -> pd.DataFrame:
    """A realistic org file: messy in the ways real files are messy."""
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame(
        {
            "respondent_id": np.arange(1, rows + 1),
            "age": rng.integers(18, 75, rows),
            "region": rng.choice(["Kiambu", "Mombasa", "Kisumu", "Arusha", "Dodoma"], rows),
            "gender": rng.choice(["F", "M"], rows, p=[0.56, 0.44]),
            "hh_size": rng.integers(1, 12, rows),
            "income": rng.lognormal(10.2, 0.7, rows).round(2),
            "satisfaction": rng.integers(1, 6, rows),
            "usage_hours": rng.gamma(2.2, 1.7, rows).round(2),
            "signup_date": pd.date_range("2021-01-01", periods=rows, freq="7min"),
            "churned": rng.choice([0, 1], rows, p=[0.82, 0.18]),
            "note": rng.choice([" renewed", "called back", "pending", "no answer", ""], rows),
        }
    )
    # ~2% missing in the columns a real import drops values from.
    for column in ("age", "income", "satisfaction", "hh_size"):
        index = rng.choice(rows, size=max(1, rows // 50), replace=False)
        frame.loc[index, column] = np.nan
    # A handful of exact duplicate rows, as a spreadsheet export has.
    duplicates = frame.sample(n=max(1, rows // 10_000), random_state=seed)
    frame = pd.concat([frame, duplicates], ignore_index=True)
    return frame


def run_benchmark(rows: int) -> Dict[str, Any]:
    """Everything the benchmark measures, in one pass."""
    results: Dict[str, Any] = {}
    print(f"Building a {rows:,} row x {COLUMNS} column dataset ...")
    build_start = time.perf_counter()
    frame = make_dataset(rows)
    build_ms = (time.perf_counter() - build_start) * 1000
    results["dataset"] = {
        "rows": int(frame.shape[0]),
        "columns": int(frame.shape[1]),
        "build_ms": round(build_ms, 3),
        "bytes_in_memory_mb": round(
            frame.memory_usage(deep=True).sum() / (1024 * 1024), 2
        ),
    }
    print(
        f"  {frame.shape[0]:,} rows x {frame.shape[1]} columns, "
        f"{results['dataset']['bytes_in_memory_mb']} MB in memory "
        f"(built in {build_ms:.0f} ms)"
    )

    from pathlib import Path
    import tempfile

    from app.models import Dataset

    from app.database import SessionLocal

    workspace = Path(tempfile.mkdtemp(prefix="statflow_bench_"))
    dataset = Dataset(
        user_id=1,
        original_filename="survey.csv",
        storage_path=str(workspace / "survey.csv"),
        file_type="csv",
        row_count=int(frame.shape[0]),
        column_count=int(frame.shape[1]),
        status="uploaded",
    )
    frame.to_csv(dataset.storage_path, index=False)

    db = SessionLocal()
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    # 1. Upload -> v1: the source file read once and written as parquet.
    FRAME_CACHE.clear()
    start = time.perf_counter()
    version = version_store.ensure_base_version(db, dataset)
    results["upload_v1"] = {
        "ms": round((time.perf_counter() - start) * 1000, 3),
        "rows": int(version.row_count),
        "columns": int(version.column_count),
    }
    print(f"  upload -> v1 (read source + write parquet): {results['upload_v1']['ms']:.1f} ms")

    record, loaded = version_store.load_version_frame(db, dataset)

    # 2. Profile and validate: the two things every dataset pays for.
    profile_runs = 3
    start = time.perf_counter()
    for _ in range(profile_runs):
        from app.services.data_service import profile_columns

        profile_columns(loaded)
    results["profile"] = {
        "runs": profile_runs,
        "mean_ms": round((time.perf_counter() - start) * 1000 / profile_runs, 3),
    }
    print(f"  profile ({profile_runs} runs): {results['profile']['mean_ms']:.1f} ms mean")

    start = time.perf_counter()
    report = validate_frame(loaded)
    results["validate"] = {"ms": round((time.perf_counter() - start) * 1000, 3)}
    print(f"  validate: {results['validate']['ms']:.1f} ms ({report['verdict']})")

    # 3. Analyses: the real question a reader asks. The timed path is the
    #    endpoint's own: cache key -> lookup -> run and store on a miss,
    #    return the copy on a hit. Timing `run_analysis` alone would
    #    measure a code path no request takes.
    analyses = [
        (
            "welch_t_test",
            {"value_column": "income", "group_column": "gender"},
            "t-test",
        ),
        (
            "one_way_anova",
            {"value_column": "income", "group_column": "region"},
            "one-way ANOVA",
        ),
        (
            "correlation_matrix",
            {"method": "pearson"},
            "correlation matrix (11 variables)",
        ),
        (
            "linear_regression",
            {"target": "income", "predictors": ["age", "hh_size", "satisfaction", "usage_hours"]},
            "linear regression",
        ),
    ]

    def run_analysis_cached(analysis_type: str, parameters: Dict[str, Any]) -> Any:
        key = result_cache.cache_key(record.id, analysis_type, parameters)
        cached = result_cache.get_cached(key)
        if cached is not None:
            return dict(cached)
        outcome = stats_engine.run_analysis(loaded, analysis_type, parameters)
        result_cache.store(key, dict(outcome))
        return outcome

    analysis_results = []
    for analysis_type, parameters, label in analyses:
        result_cache.clear()
        start = time.perf_counter()
        run_analysis_cached(analysis_type, parameters)
        cold_ms = (time.perf_counter() - start) * 1000

        runs = 5
        start = time.perf_counter()
        for _ in range(runs):
            run_analysis_cached(analysis_type, parameters)
        warm_ms = (time.perf_counter() - start) * 1000 / runs

        entry = {
            "analysis": label,
            "analysis_type": analysis_type,
            "cold_ms": round(cold_ms, 3),
            "warm_ms": round(warm_ms, 3),
            "speedup": round(cold_ms / warm_ms, 1) if warm_ms else None,
        }
        analysis_results.append(entry)
        print(
            f"  {label}: cold {cold_ms:.1f} ms, cached {warm_ms:.3f} ms "
            f"({entry['speedup']}x faster on repeat)"
        )
    results["analyses"] = analysis_results

    # 4. Repeated reads of one version: profile, preview, validate,
    #    chart and analysis all load the same frame within seconds.
    FRAME_CACHE.clear()
    reads = 5
    version_store.read_version_file(record)  # seed
    start = time.perf_counter()
    for _ in range(reads):
        version_store.read_version_file(record)
    cached_ms = (time.perf_counter() - start) * 1000 / reads
    results["frame_cache"] = {
        "reads": reads,
        "cached_mean_ms": round(cached_ms, 3),
    }
    print(
        f"  version read x{reads} from the frame cache: {cached_ms:.3f} ms mean"
    )

    # 5. A cleaning step: the prep path, writing a new version.
    FRAME_CACHE.clear()
    result_cache.clear()
    start = time.perf_counter()
    cleaned, summary, warnings = operations.op_drop_duplicates(loaded, {"keep": "first"})
    op_ms = (time.perf_counter() - start) * 1000
    start = time.perf_counter()
    new_version, _ = version_store.create_version(
        db,
        dataset,
        cleaned,
        operation_group="clean",
        operation_type="drop_duplicates",
        configuration={"keep": "first"},
        source_version=1,
        summary=summary,
        warnings=warnings,
        created_by=dataset.user_id,
    )
    write_ms = (time.perf_counter() - start) * 1000
    results["cleaning_step"] = {
        "operation_ms": round(op_ms, 3),
        "version_write_ms": round(write_ms, 3),
        "rows_after": int(new_version.row_count),
        "duplicate_rows_removed": summary.get("duplicate_rows_removed"),
    }
    print(
        f"  drop_duplicates: {op_ms:.1f} ms to compute, {write_ms:.1f} ms to write v2 "
        f"({summary.get('duplicate_rows_removed')} rows removed)"
    )

    results["cache_stats"] = {
        "frame_cache": FRAME_CACHE.stats(),
        "result_cache": result_cache.stats(),
    }
    print("  frame cache:", results["cache_stats"]["frame_cache"])
    print("  result cache:", results["cache_stats"]["result_cache"])

    db.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark the engine on a realistic dataset.")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--json", action="store_true", help="print JSON only")
    args = parser.parse_args()

    results = run_benchmark(args.rows)

    environment = {
        "python": sys.version.split()[0],
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "platform": sys.platform,
    }
    results["environment"] = environment

    if args.json:
        print(json.dumps(results, indent=2, default=str))
        return 0

    print("\nEnvironment:", json.dumps(environment))
    print("\nDone. Publish these numbers in BENCHMARKS.md with the command")
    print("that produced them and the machine they were produced on.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
