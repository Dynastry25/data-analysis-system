"""Frame cache: repeated reads never re-read the source file (plan 2.1).

An analysis session reads the same version many times -- profile,
preview, validate, chart, analysis -- and each read was decoding
the parquet file again to get the identical frame back. The cache
rests on the fact that makes it safe: a published version file
never changes, and a file replaced underneath its path is caught
by the stat in the cache key.

Four properties are pinned here, in order of how badly breaking
them would hurt:

  * a cached read is the file on disk (identity by path + mtime +
    size, not just path),
  * copies both ways, so neither a writer nor a reader can change
    what the cache holds or hand out,
  * the writer seeds the cache, so the code that produced a
    version never reads it back to find out what it produced, and
  * the budget holds: entry count, total cells, and a frame too
    big for the whole budget is refused rather than stored.

Run it with:  python tests/frame_cache_test.py
"""

import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

TEST_ROOT = Path(tempfile.mkdtemp(prefix="frame_cache_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "frame-cache-test-secret"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.statflow import version_store  # noqa: E402
from app.statflow.frame_cache import FrameCache  # noqa: E402

PASSED = 0


def check(condition: bool, message: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {message}")
    PASSED += 1
    print(f"  [ok] {message}")


def _write(path: Path, frame: pd.DataFrame) -> os.stat_result:
    frame.to_parquet(path, index=False)
    return path.stat()


def _frame(rows: int = 50, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "value": rng.normal(10, 2, rows),
            "group": rng.choice(["a", "b"], rows),
        }
    )


# ------------------------------------------------------------------- tests


def test_a_cached_read_is_the_file_on_disk() -> None:
    print("\n1) The cache serves the file that is actually there")
    cache = FrameCache()
    path = TEST_ROOT / f"identity_{time.time_ns()}.parquet"
    frame = _frame()
    stat_result = _write(path, frame)

    check(cache.get(path, stat_result) is None, "an uncached file is a miss")
    cache.put(path, stat_result, frame)
    again = cache.get(path, stat_result)
    check(again is not None, "the second read is a hit")
    check(again.equals(frame), "and it is the same frame")

    # The same path with new content is a different file: the stat in
    # the key catches it, so a restored or replaced version cannot be
    # served from a stale entry.
    time.sleep(0.01)
    replacement = _frame(rows=80, seed=99)
    new_stat = _write(path, replacement)
    check(
        cache.get(path, new_stat) is None,
        "a replaced file is a miss, not a stale hit",
    )
    fresh = pd.read_parquet(path)
    check(fresh.equals(replacement), "and the fresh read has the new content")


def test_copies_both_ways_protect_the_cache() -> None:
    print("\n2) Neither the writer nor the reader can change the cache")
    cache = FrameCache()
    path = TEST_ROOT / f"copies_{time.time_ns()}.parquet"
    frame = _frame()
    stat_result = _write(path, frame)
    cache.put(path, stat_result, frame)

    # The writer keeps using its own frame; the cache must not move.
    frame["value"] = -999.0
    check(
        not (cache.get(path, stat_result)["value"] == -999.0).all(),
        "a writer's later change does not reach the cache",
    )

    # A reader mutates what it was handed; the next reader must not
    # see it -- this is the failure that would make results change
    # under someone with no way to tell why.
    stolen = cache.get(path, stat_result)
    stolen["group"] = " poisoned"
    check(
        not (cache.get(path, stat_result)["group"] == " poisoned").all(),
        "a reader's mutation does not poison the next reader",
    )


def test_the_writer_seeds_the_cache() -> None:
    print("\n3) The frame that was just written is already cached")
    from app.database import SessionLocal
    from app.models import Dataset

    client_free_db = SessionLocal()
    from fastapi.testclient import TestClient  # noqa: E402

    from app.main import app  # noqa: E402

    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={
                "full_name": "Asha Mwangi",
                "email": "frame.cache@example.com",
                "password": "secret123",
            },
        )
        token = client.post(
            "/api/auth/login",
            json={"email": "frame.cache@example.com", "password": "secret123"},
        ).json()["access_token"]
        import io

        buffer = io.BytesIO()
        _frame(rows=30).to_csv(buffer, index=False)
        buffer.seek(0)
        dataset_id = client.post(
            "/api/datasets/upload",
            files={"file": ("seeded.csv", buffer, "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        ).json()["dataset_id"]

        db = SessionLocal()
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).one()
        version_store.ensure_base_version(db, dataset)
        record = version_store.get_version(db, dataset)

        version_store.read_version_file(record)  # warm it, so v1 is known
        stats = version_store.FRAME_CACHE.stats()
        check(stats["hits"] >= 1, "a repeated read of v1 is a hit")

        # A cleaning step writes v2 and seeds the cache for its file.
        version_store.load_version_frame(db, dataset)
        from app.statflow.operations import op_drop_duplicates

        cleaned, summary, warnings = op_drop_duplicates(
            version_store.read_version_file(record), {"keep": "first"}
        )
        version_store.create_version(
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
        new_record = version_store.get_version(db, dataset)
        hits_before = version_store.FRAME_CACHE.stats()["hits"]
        served = version_store.read_version_file(new_record)
        hits_after = version_store.FRAME_CACHE.stats()["hits"]
        check(
            hits_after > hits_before,
            "the new version is served from the cache, not re-parsed",
        )
        check(
            served.reset_index(drop=True)
            .equals(cleaned.reset_index(drop=True)),
            "and it is exactly the frame the operation produced",
        )
        db.close()

    client_free_db.close()


def test_the_budget_holds() -> None:
    print("\n4) A budget, and a frame too big for it is refused")
    cache = FrameCache(max_entries=2, max_cells=10_000)
    path = TEST_ROOT / f"budget_{time.time_ns()}.parquet"
    stat_result = _write(path, _frame(rows=10))

    cache.put(path, stat_result, _frame(rows=100, seed=1))  # 200 cells
    stat_b = _write(TEST_ROOT / f"budget_b_{time.time_ns()}.parquet", _frame(rows=100, seed=2))
    cache.put(TEST_ROOT / f"budget_b_{time.time_ns()}.parquet", stat_b, _frame(rows=100, seed=2))
    stat_c = _write(TEST_ROOT / f"budget_c_{time.time_ns()}.parquet", _frame(rows=100, seed=3))
    cache.put(TEST_ROOT / f"budget_c_{time.time_ns()}.parquet", stat_c, _frame(rows=100, seed=3))

    stats = cache.stats()
    check(stats["entries"] == 2, "only the budget's worth of frames is held")
    check(stats["evictions"] >= 1, "the least recently used frame was evicted")

    # A frame bigger than the whole budget is refused, so one huge
    # dataset cannot trade the whole session for unbounded memory.
    huge = _frame(rows=10_000)  # 20,000 cells > 10,000
    huge_stat = _write(TEST_ROOT / f"budget_huge_{time.time_ns()}.parquet", huge)
    accepted = cache.put(
        TEST_ROOT / f"budget_huge_{time.time_ns()}.parquet", huge_stat, huge
    )
    check(accepted is False, "an oversized frame is refused")
    check(
        cache.get(TEST_ROOT / f"budget_huge_{time.time_ns()}.parquet", huge_stat)
        is None,
        "and it was never stored",
    )
    check(cache.stats()["refusals"] == 1, "the refusal is counted")


def main() -> int:
    print("FRAME CACHE TESTS")
    test_a_cached_read_is_the_file_on_disk()
    test_copies_both_ways_protect_the_cache()
    test_the_writer_seeds_the_cache()
    test_the_budget_holds()
    print(f"\nALL FRAME CACHE TESTS PASSED ({PASSED} checks)")
    return 0


def test_frame_cache() -> None:
    """pytest entry point: same run as ``python tests/frame_cache_test.py``."""
    main()


if __name__ == "__main__":
    raise SystemExit(main())
