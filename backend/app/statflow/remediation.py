"""One-click remediation of the findings validation reports (plan item 3.1).

Validation already says exactly what is wrong with a file. Preparation
is the part of an analysis project that costs the most time, and most
of what the Validate stage finds is mundane enough to fix mechanically:
a column that is entirely empty, a number column read as text, a
handful of duplicated rows. This module turns each remediable finding
into the cleaning operation that fixes it, so the mundane part becomes
one reviewable action instead of an hour of manual work.

Two rules hold every fix:

1. **Nothing is mutated.** The result is a frame the caller writes as
   a new immutable version. The original file stays exactly as
   uploaded, which is what lets the finding it produced stay
   recomputable from it -- a fix that overwrote its own evidence
   would make the audit trail a claim rather than a record.

2. **A judgment the engine cannot make is offered, never applied.**
   Negative values can be perfectly correct; whether a half-empty
   column should be dropped or explained is the reader's call about
   the analysis, not a defect in the file. Those findings get a
   button and stay out of the "fix everything" default set.

The fixes reuse the operations engine rather than reimplementing it,
so a remediated frame is produced by the same code paths a hand-built
cleaning step uses, and the per-fix summaries are the operation
summaries the history already displays.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from app.statflow.operations import (
    op_cast_types,
    op_drop_columns,
    op_drop_duplicates,
)

#: What each finding code fixes, and the order the fixes must run in.
#:
#: The order is not cosmetic. Renames run first because every later fix
#: addresses columns by name, and a file with repeated or blank names
#: has no stable name to address. Column drops run before casts so a
#: column that is both constant and text-numeric is removed rather
#: than coerced first. Row drops run last: they are the only fix that
#: discards observations rather than a column.
#:
#: Codes deliberately absent from this catalog -- ``negative_values``
#: and ``likely_identifier`` -- are findings whose fix would be a
#: guess: a negative value can be real data and an identifier column
#: is an analysis choice, not a defect.
FIX_CATALOG: Dict[str, Dict[str, Any]] = {
    "duplicate_column_names": {
        "label": "Tambua majina yanayojirudia",
        "priority": 0,
        "default": True,
    },
    "blank_column_names": {
        "label": "Wapa majina columns zisizo na majina",
        "priority": 1,
        "default": True,
    },
    "column_all_missing": {
        "label": "Ondoa column tupu",
        "priority": 2,
        "default": True,
    },
    "constant_column": {
        "label": "Ondoa column yenye thamani moja",
        "priority": 2,
        "default": True,
    },
    "zero_variance": {
        "label": "Ondoa column isiyobadilika",
        "priority": 2,
        "default": True,
    },
    "column_mostly_missing": {
        # Opt-in by design: dropping a half-empty column is a judgment
        # about the analysis, so it needs a click of its own.
        "label": "Ondoa column iliyo tupu kwa kiwango kikubwa",
        "priority": 2,
        "default": False,
    },
    "numeric_stored_as_text": {
        "label": "Badilisha text kuwa nambari",
        "priority": 3,
        "default": True,
    },
    "duplicate_rows": {
        "label": "Ondoa rows zinazojirudia",
        "priority": 4,
        "default": True,
    },
}

_RENAME_CODES = ("duplicate_column_names", "blank_column_names")
_DROP_CODES = ("column_all_missing", "constant_column", "zero_variance", "column_mostly_missing")


class RemediationError(ValueError):
    """A requested fix cannot be applied to this frame (mapped to HTTP 400)."""


def remediable_fixes(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One button per finding the catalog can fix, for the Validate UI.

    Each entry names the finding it would fix (code + column), the
    button label, and whether it belongs to the "fix everything"
    default set -- so the UI can offer one click for the findings
    that are safe without a per-finding decision, and a separate
    button for the ones that are not.
    """
    buttons: List[Dict[str, Any]] = []
    for issue in report.get("issues") or []:
        entry = FIX_CATALOG.get(str(issue.get("code")))
        if entry is None:
            continue
        buttons.append(
            {
                "code": str(issue.get("code")),
                "column": issue.get("column"),
                "label": entry["label"],
                "default": bool(entry["default"]),
                "message": issue.get("message", ""),
            }
        )
    return buttons


def _requested_pairs(
    fixes: Optional[Sequence[Dict[str, Any]]], report: Dict[str, Any]
) -> List[Tuple[str, Optional[str]]]:
    """The (code, column) pairs to fix: the default set when unspecified.

    The default set is the findings the catalog marks safe, so "fix
    everything" means everything *and only* everything the engine
    can fix without making a judgment on the reader's behalf.
    """
    if fixes is None:
        return [
            (str(issue["code"]), issue.get("column"))
            for issue in report.get("issues") or []
            if FIX_CATALOG.get(str(issue.get("code")), {}).get("default")
        ]
    pairs: List[Tuple[str, Optional[str]]] = []
    for fix in fixes:
        pairs.append((str(fix.get("code")), fix.get("column")))
    return pairs


def _apply_renames(
    frame: pd.DataFrame, issues: List[Dict[str, Any]]
) -> Tuple[pd.DataFrame, Optional[Dict[str, Any]]]:
    """Unique names for repeated and blank columns, addressed by position.

    A repeated column name cannot be addressed by name -- pandas
    renames every column that shares it -- so the occurrences are
    counted in order and the second and later ones are renamed. A
    blank or spreadsheet-generated name gets a positional one. Both
    are checked against every name already in the file, so a
    generated name can never collide with a real column.
    """
    positions: Dict[int, str] = {}
    taken = {str(column) for column in frame.columns}
    seen: Dict[str, int] = {}
    for position, column in enumerate(frame.columns):
        name = str(column)
        seen[name] = seen.get(name, 0) + 1
        blank = not name.strip() or name.startswith("Unnamed")
        if not (blank or seen[name] > 1):
            continue
        base = "column" if blank else name
        occurrence = (position + 1) if blank else seen[name]
        candidate = f"{base}_{occurrence}"
        extra = 2
        while candidate in taken:
            candidate = f"{base}_{occurrence}_{extra}"
            extra += 1
        taken.add(candidate)
        positions[position] = candidate

    if not positions:
        return frame, None, []

    labels = [
        positions.get(index, str(column))
        for index, column in enumerate(frame.columns)
    ]
    renamed = frame.set_axis(labels, axis=1).copy()
    summary = {
        "renamed": [
            {"position": position, "from": str(frame.columns[position]), "to": new_name}
            for position, new_name in sorted(positions.items())
        ]
    }
    return renamed, summary, []


def _apply_drops(
    frame: pd.DataFrame, issues: List[Dict[str, Any]]
) -> Tuple[pd.DataFrame, Optional[Dict[str, Any]], List[str]]:
    columns = [
        str(issue["column"])
        for issue in issues
        if issue.get("column") is not None and issue["column"] in frame.columns
    ]
    if not columns:
        return frame, None, []
    cleaned, summary, warnings = op_drop_columns(frame, {"columns": columns})
    return (
        cleaned,
        {
            "dropped_columns": summary["dropped_columns"],
            "dropped_count": summary["dropped_count"],
            "columns_after": int(cleaned.shape[1]),
        },
        warnings,
    )


def _apply_casts(
    frame: pd.DataFrame, issues: List[Dict[str, Any]]
) -> Tuple[pd.DataFrame, Optional[Dict[str, Any]], List[str]]:
    cleaned = frame
    casts: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for issue in issues:
        column = issue.get("column")
        if column not in cleaned.columns:
            continue
        cleaned, summary, cast_warnings = op_cast_types(
            cleaned, {"column": column, "target_type": "numeric"}
        )
        casts.append(summary)
        warnings.extend(cast_warnings)
    if not casts:
        return frame, None, []
    return (
        cleaned,
        {"casts": casts, "values_became_missing": int(sum(c["values_became_missing"] for c in casts))},
        warnings,
    )

def _apply_duplicate_rows(
    frame: pd.DataFrame, issues: List[Dict[str, Any]]
) -> Tuple[pd.DataFrame, Optional[Dict[str, Any]], List[str]]:
    cleaned, summary, warnings = op_drop_duplicates(frame, {"keep": "first"})
    return (
        cleaned,
        {
            "duplicate_rows_removed": summary["duplicate_rows_removed"],
            "rows_after": int(cleaned.shape[0]),
            "rows_before": int(frame.shape[0]),
        },
        warnings,
    )


_HANDLERS = {
    "rename": _apply_renames,
    "drop": _apply_drops,
    "cast": _apply_casts,
    "duplicates": _apply_duplicate_rows,
}


def _handler_for(code: str):
    if code in _RENAME_CODES:
        return _HANDLERS["rename"]
    if code in _DROP_CODES:
        return _HANDLERS["drop"]
    if code == "numeric_stored_as_text":
        return _HANDLERS["cast"]
    if code == "duplicate_rows":
        return _HANDLERS["duplicates"]
    raise RemediationError(f"'{code}' has no fix")  # pragma: no cover - catalog is in step


def _ambiguous(frame: pd.DataFrame, column: Optional[str]) -> bool:
    """True when a name does not identify one column on its own.

    A file with a repeated header names two columns ``age``, and a
    finding that says ``age`` cannot say which one it meant: one may
    be a number and the other text. Casting or dropping by name
    would act on both, or on the wrong one. The duplicate-name fix
    runs first precisely so this clears, and until it does the
    finding is reported as needing that first step rather than
    guessed at.
    """
    if column is None:
        return False
    return [str(name) for name in frame.columns].count(str(column)) > 1


def _matches(request_column: Optional[str], finding_column: Optional[str]) -> bool:
    """A null column in the request means every finding of that code.

    A per-finding button sends the pair as it stands; a per-code
    request ("drop the half-empty columns") has nothing to name, so
    it covers the whole family. Both still re-match against the
    findings of the version actually being fixed, so neither can
    act on a version the reader has not seen.
    """
    return request_column is None or request_column == finding_column


def remediate_frame(
    frame: pd.DataFrame,
    report: Dict[str, Any],
    fixes: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Apply the requested fixes and return the new frame plus a full report.

    ``report`` is the validation report the findings are chosen from,
    so a fix and the finding that motivated it always describe the
    same version of the file. ``fixes`` selects individual findings
    as ``{"code", "column"}`` pairs; omitted, it is the default set.

    Returns the frame to write as a new version, a per-fix report of
    what each fix did, and the requests that matched no finding --
    a stale button is reported as skipped rather than silently
    ignored, because a reader who clicked a fix deserves to know
    nothing happened.
    """
    requested = _requested_pairs(fixes, report)
    matched: Dict[Tuple[str, Optional[str]], Dict[str, Any]] = {}
    for issue in report.get("issues") or []:
        code = str(issue.get("code"))
        column = issue.get("column")
        if any(
            code == requested_code and _matches(requested_column, column)
            for requested_code, requested_column in requested
        ):
            matched[(code, column)] = issue

    skipped: List[Dict[str, Any]] = []
    for code, column in requested:
        if any(
            matched_code == code and _matches(column, matched_column)
            for matched_code, matched_column in matched
        ):
            continue
        if code not in FIX_CATALOG:
            reason = f"'{code}' halirekebishika kiotomatiki"  # not automatically remediable
        else:
            reason = "Tatizo hili halipatikani kwenye toleo la sasa la data"  # not present on this version
        skipped.append({"code": code, "column": column, "reason": reason})

    by_code: Dict[str, List[Dict[str, Any]]] = {}
    for key, issue in matched.items():
        by_code.setdefault(key[0], []).append(issue)

    ordered = sorted(
        by_code.items(),
        key=lambda item: (FIX_CATALOG[item[0]]["priority"], item[0]),
    )

    cleaned = frame
    applied: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for code, issues in ordered:
        # A finding whose column shares its name with another column
        # cannot be acted on: the finding was computed on the original
        # frame, so it could never say which of the two it meant. The
        # duplicate-name fix runs first and the re-validation
        # afterwards names the column unambiguously.
        actionable: List[Dict[str, Any]] = []
        for issue in issues:
            if _ambiguous(frame, issue.get("column")):
                skipped.append(
                    {
                        "code": code,
                        "column": issue.get("column"),
                        "reason": "Column ina jina linalojirudia; rekebisha majina kwanza",
                    }
                )
                continue
            actionable.append(issue)
        if not actionable:
            continue

        handler = _handler_for(code)
        result = handler(cleaned, actionable)
        new_frame, summary, handler_warnings = result
        if summary is None:
            for issue in issues:
                if code in _RENAME_CODES:
                    reason = "Hakuna jina lililobaki kurekebishwa"  # an earlier fix already resolved it
                elif code in _DROP_CODES or code == "numeric_stored_as_text":
                    reason = "Column iliondolewa hatua iliyotangulia"  # an earlier fix removed it
                else:
                    reason = "Hakuna kitu cha kurekebisha"  # nothing to fix
                skipped.append(
                    {
                        "code": code,
                        "column": issue.get("column"),
                        "reason": reason,
                    }
                )
            continue
        cleaned = new_frame
        warnings.extend(handler_warnings)
        applied.append(
            {
                "code": code,
                "column": issues[0].get("column") if len(issues) == 1 else None,
                "columns": [issue.get("column") for issue in issues],
                "label": FIX_CATALOG[code]["label"],
                "summary": summary,
                "warnings": handler_warnings,
            }
        )

    return {
        "frame": cleaned,
        "applied": applied,
        "skipped": skipped,
        "warnings": warnings,
        "rows_before": int(frame.shape[0]),
        "rows_after": int(cleaned.shape[0]),
        "columns_before": int(frame.shape[1]),
        "columns_after": int(cleaned.shape[1]),
        "changed": bool(applied),
    }
