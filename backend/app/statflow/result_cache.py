"""In-process cache for identical analyses.

An analysis is a pure function of (dataset version, analysis type, parameters).
Versions are immutable in this system — every transformation writes a new one
and never overwrites — so the result of a given analysis on a given version can
never change. That makes the triple a sound cache key with no invalidation
problem: when the data changes, the version id changes, and the key simply
stops matching.

This matters more than it sounds. Re-running the same analysis is the single
most common action in the product: a reader changes the confidence level, looks
at the numbers, changes it back, and presses run again. Each of those presses
currently re-reads the version file from disk and recomputes from scratch.

The cache is deliberately small and in-process. It is not shared between
workers and it does not survive a restart, so a cold start costs one run per
distinct analysis — and a stale result is impossible, because the only way the
answer could change is the thing the key is made of.
"""

import json
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional

_LOCK = threading.Lock()
_CACHE: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

# Bounded so a long session cannot grow without limit. The oldest entry is
# dropped once the cap is passed, which keeps the working set of a session --
# the last few hundred distinct analyses -- resident, and discards the rest.
MAX_ENTRIES = 256


def cache_key(
    dataset_version_id: Optional[int],
    analysis_type: str,
    parameters: Dict[str, Any],
) -> str:
    """A stable key for an analysis of one immutable dataset version.

    Parameters are canonicalised with sorted keys so that two dictionaries
    holding the same values in a different order hit the same entry. List values
    are deliberately *not* reordered: `["b", "a"]` and `["a", "b"]` are different
    keys, which costs a cache hit but never a wrong answer.
    """
    canonical = json.dumps(
        parameters or {}, sort_keys=True, separators=(",", ":"), default=str
    )
    return f"{dataset_version_id}|{analysis_type}|{canonical}"


def get_cached(key: str) -> Optional[Dict[str, Any]]:
    """The cached result, or None on a miss.

    The copy is the point rather than an optimisation. A caller that mutates the
    dict it was handed -- and a response builder assembling a JSON body is
    exactly that -- would otherwise poison every later reader with a result the
    engine never produced. Copying on read costs a shallow dict copy, which is
    nothing next to the computation being avoided.
    """
    with _LOCK:
        stored = _CACHE.get(key)
        return dict(stored) if stored is not None else None


def store(key: str, result: Dict[str, Any]) -> None:
    """Keep a computed result, dropping the oldest entry past the cap."""
    with _LOCK:
        _CACHE[key] = result
        _CACHE.move_to_end(key)
        while len(_CACHE) > MAX_ENTRIES:
            _CACHE.popitem(last=False)


def stats() -> Dict[str, int]:
    """For tests and the benchmark harness."""
    with _LOCK:
        return {"entries": len(_CACHE), "max_entries": MAX_ENTRIES}


def clear() -> None:
    with _LOCK:
        _CACHE.clear()
