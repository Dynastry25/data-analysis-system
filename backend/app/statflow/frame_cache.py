"""In-memory cache of parsed version frames (improvement plan item 2.1).

An analysis session reads the same version over and over: the
profile, the preview, the Validate report, the chart and the
analysis itself each load it, within seconds of each other, and
each read was re-opening the parquet file, re-reading its footer
and re-decoding every column chunk -- all to get the identical
frame back, because versions are immutable and the file cannot
have changed.

So the parse is cached per file, and correctness rests on the same
fact that makes the cache worth having: a published version file
never changes. Each entry is keyed by the file's *stat* -- path,
mtime in nanoseconds, size -- and one ``stat`` call, far cheaper
than a read, decides whether the entry is the file currently on
disk. A version written underneath a cached path (the writer
publishes a new file at a new path, so this cannot happen today,
but a restore or a manual copy could) is detected as a miss.

Two rules keep the cache from becoming a correctness risk:

* **Copies both ways.** ``put`` stores a deep copy, so a caller
  that keeps using its own frame cannot change what the cache
  holds; ``get`` returns a deep copy, so a caller that mutates a
  result frame cannot poison the next reader. The cache is an
  optimisation and nothing else -- a poisoned frame would make
  results change under a reader with no way to tell why.
* **A budget.** Both entry count and total cell count are bounded,
  and a frame larger than the whole budget is simply not cached:
  the common case is a modest table read many times, and caching a
  frame too big to evict would trade a fast session for an
  unbounded server.

The writer seeds the cache with the frame it just wrote, so the
code that produced a version never reads it back to find out what
it produced -- the incremental half of "cache + incremental
refresh".
"""

import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

#: How many frames to hold. A session touches a handful of versions
#: (the current one, plus an older one for a comparison), so this is
#: already generous before the cell budget is considered.
MAX_ENTRIES = 24

#: Total cells across all entries. A float64 cell is 8 bytes, so the
#: budget is ~320MB of decoded data at most -- a real cost, and the
#: reason a frame larger than the whole budget is not cached.
MAX_TOTAL_CELLS = 40_000_000


class FrameCache:
    """Bounded, stat-validated, copy-on-both-ways cache of version frames."""

    def __init__(
        self, max_entries: int = MAX_ENTRIES, max_cells: int = MAX_TOTAL_CELLS
    ) -> None:
        self._lock = threading.Lock()
        self._entries: "OrderedDict[Tuple[str, int, int], Tuple[pd.DataFrame, int]]" = (
            OrderedDict()
        )
        self._max_entries = max(1, max_entries)
        self._max_cells = max(1, max_cells)
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._refusals = 0

    @staticmethod
    def _key(path: Path, stat_result: os.stat_result) -> Tuple[str, int, int]:
        return (
            str(path),
            int(stat_result.st_mtime_ns),
            int(stat_result.st_size),
        )

    @staticmethod
    def _cells(frame: pd.DataFrame) -> int:
        if frame.empty:
            return 0
        return int(frame.shape[0]) * int(frame.shape[1])

    def get(self, path: Path, stat_result: os.stat_result) -> Optional[pd.DataFrame]:
        """A copy of the cached frame, or None when the file is not cached.

        The caller owns the returned frame: mutating it cannot reach
        the cache, and the next reader gets the file as it was parsed.
        """
        key = self._key(path, stat_result)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            self._entries.move_to_end(key)
            self._hits += 1
            frame, _ = entry
        return frame.copy(deep=True)

    def put(
        self, path: Path, stat_result: os.stat_result, frame: pd.DataFrame
    ) -> bool:
        """Cache a frame for this exact file identity.

        Returns whether the frame was cached: a frame too large for
        the whole budget is refused rather than stored, because
        evicting everything else to hold one huge frame would trade a
        fast session for an unbounded server.
        """
        cells = self._cells(frame)
        if cells > self._max_cells:
            with self._lock:
                self._refusals += 1
            return False

        key = self._key(path, stat_result)
        stored = frame.copy(deep=True)
        with self._lock:
            self._entries.pop(key, None)
            self._entries[key] = (stored, cells)
            total = cells + sum(count for _, count in self._entries.values())
            while self._entries and (
                len(self._entries) > self._max_entries or total > self._max_cells
            ):
                _, (_, evicted) = self._entries.popitem(last=False)
                total -= evicted
                self._evictions += 1
        return True

    def stats(self) -> Dict[str, int]:
        """Hit/miss counters, for the benchmark the plan asks to publish."""
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "entries": len(self._entries),
                "evictions": self._evictions,
                "refusals": self._refusals,
                "cached_cells": sum(count for _, count in self._entries.values()),
            }

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


#: The process-wide cache. Frames are large, so one instance shared by
#: every version is already the budget; a second one would double it.
FRAME_CACHE = FrameCache()
