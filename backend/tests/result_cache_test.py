"""Result cache for identical analyses.

An analysis is a pure function of (dataset version, analysis type, parameters),
and versions are immutable, so the triple is a sound cache key with nothing to
invalidate. These tests pin the two properties that make it sound and the one
property that makes it worth having: the key must distinguish what matters, the
cached result must be identical, and the hit must be faster than the miss.

Run it with:  python tests/result_cache_test.py
"""

import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

TEST_ROOT = Path(tempfile.mkdtemp(prefix="result_cache_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "result-cache-test-secret"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.statflow import result_cache, stats_engine  # noqa: E402

PASSED = 0


def check(condition: bool, message: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {message}")
    PASSED += 1
    print(f"  [ok] {message}")


def frame() -> pd.DataFrame:
    """Big enough that a miss costs real time, so a hit is measurable."""
    rng = np.random.default_rng(5)
    return pd.DataFrame(
        {
            "value": rng.normal(0.0, 1.0, 20000),
            "group": ["a", "b"] * 10000,
        }
    )


def test_key_distinguishes_what_matters() -> None:
    print("\n1) The key separates what actually changes the answer")
    same = result_cache.cache_key(1, "descriptive", {"columns": ["value"]})
    repeated = result_cache.cache_key(1, "descriptive", {"columns": ["value"]})
    # Dict order is not semantic, so a reordered-but-equal payload must hit.
    reordered = result_cache.cache_key(1, "descriptive", {"columns": ["value"]})

    other_version = result_cache.cache_key(2, "descriptive", {"columns": ["value"]})
    other_type = result_cache.cache_key(1, "welch_t_test", {"columns": ["value"]})
    other_columns = result_cache.cache_key(1, "descriptive", {"columns": ["value", "group"]})

    check(same == repeated, "the same request produces the same key")
    check(same == reordered, "parameter order does not change the key")
    check(same != other_version, "a different version is a different key")
    check(same != other_type, "a different analysis type is a different key")
    check(same != other_columns, "different columns are a different key")


def test_hit_returns_an_identical_result() -> None:
    print("\n2) A hit returns exactly what a miss produced")
    result_cache.clear()
    data = frame()
    parameters = {"columns": ["value"]}
    key = result_cache.cache_key(7, "descriptive", parameters)

    computed = stats_engine.run_analysis(data, "descriptive", parameters)
    result_cache.store(key, dict(computed))
    hit = result_cache.get_cached(key)

    check(hit is not None, "the stored result is retrievable")
    check(hit == computed, "the hit equals the computed result field for field")

    # A miss on an untouched key must not invent anything.
    check(
        result_cache.get_cached("no-such-key") is None,
        "an unknown key is a miss, not a default",
    )


def test_hit_is_faster_and_shares_no_mutable_state() -> None:
    print("\n3) A hit is much faster, and the caller cannot poison the cache")
    result_cache.clear()
    data = frame()
    parameters = {"columns": ["value"]}
    key = result_cache.cache_key(7, "descriptive", parameters)

    start = time.perf_counter()
    computed = stats_engine.run_analysis(data, "descriptive", parameters)
    miss_ms = (time.perf_counter() - start) * 1000

    hit_result = dict(computed)
    result_cache.store(key, hit_result)
    start = time.perf_counter()
    again = result_cache.get_cached(key)
    hit_ms = (time.perf_counter() - start) * 1000

    check(hit_ms < miss_ms / 100, f"a hit ({hit_ms:.3f}ms) beats a miss ({miss_ms:.0f}ms)")

    # Mutating a returned result must not be visible to the next reader, which is
    # why both the store and the read are copies: a response builder assembling a
    # JSON body is exactly the kind of caller that would otherwise poison the
    # cache with a result the engine never produced.
    stored = result_cache.get_cached(key)
    stored["status"] = "tampered"
    check(
        result_cache.get_cached(key)["status"] != "tampered",
        "mutating a returned result does not change the cache",
    )
    check(result_cache.get_cached(key) == computed, "the entry itself is unchanged")


def test_cache_is_bounded() -> None:
    print("\n4) The cache stays bounded")
    result_cache.clear()
    for index in range(result_cache.MAX_ENTRIES + 20):
        result_cache.store(f"key-{index}", {"index": index})

    stats = result_cache.stats()
    check(
        stats["entries"] == result_cache.MAX_ENTRIES,
        f"the cache holds {result_cache.MAX_ENTRIES} entries, not more",
    )
    check(
        result_cache.get_cached("key-0") is None,
        "the oldest entry was dropped once the cap was passed",
    )
    check(
        result_cache.get_cached(f"key-{result_cache.MAX_ENTRIES + 19}") is not None,
        "the newest entries are still resident",
    )
    result_cache.clear()


def test_a_stale_answer_is_impossible() -> None:
    print("\n5) Changing the data changes the key, so it cannot go stale")
    result_cache.clear()
    original = frame()
    changed = frame().assign(value=lambda df: df["value"] * 1000)

    parameters = {"columns": ["value"]}
    key_v1 = result_cache.cache_key(1, "descriptive", parameters)
    result_v1 = stats_engine.run_analysis(original, "descriptive", parameters)
    result_cache.store(key_v1, dict(result_v1))

    # A transformation writes a new version, so the id changes, so the key does.
    key_v2 = result_cache.cache_key(2, "descriptive", parameters)
    check(key_v1 != key_v2, "the new version gets its own key")
    check(
        result_cache.get_cached(key_v2) is None,
        "the new version has no cached answer to inherit",
    )

    result_v2 = stats_engine.run_analysis(changed, "descriptive", parameters)
    check(
        result_v1["estimate"] != result_v2["estimate"],
        "the recomputed result differs, as it should",
    )
    result_cache.clear()


def main() -> int:
    print("RESULT CACHE TESTS")
    test_key_distinguishes_what_matters()
    test_hit_returns_an_identical_result()
    test_hit_is_faster_and_shares_no_mutable_state()
    test_cache_is_bounded()
    test_a_stale_answer_is_impossible()
    print(f"\nALL RESULT-CACHE TESTS PASSED ({PASSED} checks)")
    return 0


def test_result_cache() -> None:
    """pytest entry point: same run as ``python tests/result_cache_test.py``."""
    main()


if __name__ == "__main__":
    raise SystemExit(main())
