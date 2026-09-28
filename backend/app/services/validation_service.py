"""Data-quality validation for the Validate stage of the journey.

This runs in the backend, on the statistical side of the line. The assistant
never sees the raw frame, so it cannot invent a finding here, and a finding is
always a number a reviewer can recompute from the same file.

The checks are deliberately boring and specific: a user who fixes every issue
listed here has a dataset that will not surprise them later. Anything that would
need a domain rule we do not have (is 200ms a plausible latency? is 999999 a
valid postcode?) is left to the user rather than guessed at.
"""

from typing import Any, Dict, List, Optional

import pandas as pd

# A column that is this empty is a problem; a few missing cells usually are not.
HIGH_MISSING_RATIO = 0.5
CONSTANT_UNIQUE_LIMIT = 1

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def _issue(
    code: str,
    severity: str,
    message: str,
    *,
    column: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "column": column,
        "detail": detail or {},
    }


def _check_duplicates(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    duplicated = int(frame.duplicated().sum())
    if duplicated == 0:
        return []
    return [
        _issue(
            "duplicate_rows",
            "warning",
            f"{duplicated} rows zinajirufu. Zinaweza kuingiza mwanguko mara mbili kwenye matokeo.",
            detail={"duplicate_row_count": duplicated, "row_count": int(frame.shape[0])},
        )
    ]


def _check_columns(
    frame: pd.DataFrame, profiles: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    row_count = int(frame.shape[0])

    seen: Dict[str, int] = {}
    for position, name in enumerate(frame.columns):
        seen[str(name)] = seen.get(str(name), 0) + 1
    duplicated_names = sorted(name for name, count in seen.items() if count > 1)
    if duplicated_names:
        issues.append(
            _issue(
                "duplicate_column_names",
                "error",
                "Majina ya columns yana marudio: "
                + ", ".join(duplicated_names)
                + ". Renaming inahitajika kabla ya kufanya chochotezi.",
                detail={"columns": duplicated_names},
            )
        )

    blank_names = [
        str(name) for name in frame.columns if not str(name).strip() or str(name).startswith("Unnamed")
    ]
    if blank_names:
        issues.append(
            _issue(
                "blank_column_names",
                "warning",
                f"{len(blank_names)} columns hazina jina. Zitaonekana kama Unnamed: 0.",
                detail={"column_count": len(blank_names)},
            )
        )

    for profile in profiles:
        name = profile["name"]
        missing = int(profile.get("missing_count") or 0)
        unique = profile.get("unique_count")
        data_type = profile.get("data_type")

        if row_count == 0:
            issues.append(
                _issue(
                    "empty_dataset",
                    "error",
                    "Faili haina rows. Hakuna data ya kuchambua.",
                    detail={"row_count": 0},
                )
            )
            break

        if missing == row_count:
            issues.append(
                _issue(
                    "column_all_missing",
                    "error",
                    f"Column '{name}' ni tupu kabisa. Inaweza kuwa column isiyotumika.",
                    column=name,
                    detail={"missing_count": missing, "row_count": row_count},
                )
            )
        elif row_count and missing / row_count >= HIGH_MISSING_RATIO:
            ratio = round(missing / row_count, 3)
            issues.append(
                _issue(
                    "column_mostly_missing",
                    "warning",
                    f"Column '{name}' ina {ratio:.0%} ya rows zikiwa hazina thamani. "
                    "Fikira kama hiyo ndiyo unayotaka.",
                    column=name,
                    detail={"missing_count": missing, "row_count": row_count, "missing_ratio": ratio},
                )
            )

        if unique is not None and unique <= CONSTANT_UNIQUE_LIMIT and missing < row_count:
            issues.append(
                _issue(
                    "constant_column",
                    "warning",
                    f"Column '{name}' ina thamani moja tu. Haiwezi kusaidia kwenye uchambuzi.",
                    column=name,
                    detail={"unique_count": unique},
                )
            )

        if data_type in ("numeric", "integer") and profile.get("min") is not None:
            minimum = profile.get("min")
            maximum = profile.get("max")
            if minimum == maximum:
                issues.append(
                    _issue(
                        "zero_variance",
                        "warning",
                        f"Column '{name}' ni constant kati ya {minimum} na {maximum}, "
                        "mtihani wa asili hautatoa matokeo.",
                        column=name,
                        detail={"min": minimum, "max": maximum},
                    )
                )
            elif isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)) and minimum < 0:
                issues.append(
                    _issue(
                        "negative_values",
                        "info",
                        f"Column '{name}' ina thamani hasi. Hiyo inaweza kuwa sahihi, "
                        "lakini uthibitisha maana yake.",
                        column=name,
                        detail={"min": minimum, "max": maximum},
                    )
                )

    return issues


def _check_identifiers(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    """A column that is unique and complete is probably the row identifier."""
    row_count = int(frame.shape[0])
    if row_count == 0:
        return []
    identifiers = []
    for name in frame.columns:
        series = frame[name]
        if series.isna().any():
            continue
        if series.nunique(dropna=True) == row_count:
            identifiers.append(str(name))
    if not identifiers:
        return []
    return [
        _issue(
            "likely_identifier",
            "info",
            "Column(s) " + ", ".join(identifiers) + " zina thamani moja kwa kila row. "
            "Weka kama identifier ili zisichukuliwe kama variable.",
            detail={"columns": identifiers},
        )
    ]


def _check_mixed_types(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    """Text columns that look numeric or date-like but were read as text."""
    issues: List[Dict[str, Any]] = []
    for name in frame.columns:
        series = frame[name].dropna()
        if series.empty or not all(isinstance(value, str) for value in series.head(200)):
            continue
        sample = series.head(200)
        if pd.to_numeric(sample, errors="coerce").notna().mean() >= 0.95:
            issues.append(
                _issue(
                    "numeric_stored_as_text",
                    "warning",
                    f"Column '{name}' ina nambari zilizohifadhiwa kama text. "
                    "Hii inazuia hesabu za kawaida.",
                    column=name,
                    detail={"sample_size": int(len(sample))},
                )
            )
    return issues


def validate_frame(frame: pd.DataFrame) -> Dict[str, Any]:
    """Run every check and return findings ordered by severity."""
    row_count, column_count = int(frame.shape[0]), int(frame.shape[1])
    issues: List[Dict[str, Any]] = []

    if column_count == 0:
        issues.append(
            _issue(
                "no_columns",
                "error",
                "Faili haina columns. Hakuna data ya kuchambua.",
                detail={"row_count": row_count},
            )
        )
    if row_count == 0:
        issues.append(
            _issue(
                "empty_dataset",
                "error",
                "Faili haina rows. Hakuna data ya kuchambua.",
                detail={"row_count": 0, "column_count": column_count},
            )
        )

    profiles: List[Dict[str, Any]] = []
    if row_count and column_count:
        from app.services.data_service import profile_columns

        profiles = profile_columns(frame)
        issues.extend(_check_columns(frame, profiles))
        issues.extend(_check_duplicates(frame))
        issues.extend(_check_identifiers(frame))
        issues.extend(_check_mixed_types(frame))

    issues.sort(key=lambda issue: SEVERITY_ORDER.get(issue["severity"], 3))

    errors = sum(1 for issue in issues if issue["severity"] == "error")
    warnings = sum(1 for issue in issues if issue["severity"] == "warning")
    infos = sum(1 for issue in issues if issue["severity"] == "info")

    if errors:
        verdict = "blocked"
    elif warnings:
        verdict = "warnings"
    else:
        verdict = "clean"

    return {
        "row_count": row_count,
        "column_count": column_count,
        "issues": issues,
        "error_count": errors,
        "warning_count": warnings,
        "info_count": infos,
        "verdict": verdict,
        "summary": _summarise(verdict, errors, warnings, infos, row_count, column_count),
    }


def _summarise(
    verdict: str, errors: int, warnings: int, infos: int, row_count: int, column_count: int
) -> str:
    size = f"{row_count:,} rows x {column_count} columns"
    if verdict == "blocked":
        return (
            f"Data haijaweza kuendelea: {errors} makosa. Sahihisha makosa haya "
            f"kabla ya kufanya uchambuzi ({size})."
        )
    if verdict == "warnings":
        return (
            f"Data inaweza kutumika: {warnings} tahadhari. Kagua kama zinakutosha "
            f"({size})."
        )
    if infos:
        return f"Data iko safi ({size}). {infos} maelezo ya kuangalia."
    return f"Hakuna tatizo lililopatikana ({size})."
