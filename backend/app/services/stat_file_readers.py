"""Readers for the statistical package formats: Stata, SPSS and R.

These formats live in their own module because they are the only ones whose
parsers are not bundled with pandas. Stata ships inside pandas, SPSS needs
``pyreadstat`` and R needs ``pyreadr``, so both optional packages are imported
lazily inside the reader that needs them: a deployment built without them still
boots and answers CSV/Excel uploads, and the person who picks a ``.sav`` file
gets a 400 that names the missing package instead of a 500 traceback.

Value labels are deliberately **not** expanded. Stata and SPSS files routinely
code categorical data as numbers (``1 = kiume``, ``2 = dame``) and keep the words
as labels; applying them would turn those columns into text and quietly remove
them from every descriptive statistic, correlation and regression the platform
computes. The raw stored values are kept, exactly like ``pyreadstat`` and
``haven::read_dta`` return them by default.
"""

from pathlib import Path
from typing import Dict

import pandas as pd

STATA_SUFFIXES = {".dta"}
SPSS_SUFFIXES = {".sav", ".zsav", ".por"}
R_SUFFIXES = {".rdata", ".rda", ".rds"}

#: Every extension handled by this module, so callers can branch on it.
STAT_SUFFIXES = STATA_SUFFIXES | SPSS_SUFFIXES | R_SUFFIXES

#: ``pyreadr`` names the row-name column of an R data.frame this way.
R_INDEX_COLUMN = "(index)"


# --------------------------------------------------------------------- Stata


def read_stata_file(path: Path) -> pd.DataFrame:
    """Read a Stata ``.dta`` file (any release from 3 to 19).

    ``convert_categoricals=False`` keeps the numeric codes of labelled variables
    (see the module docstring) so measurable columns stay measurable.
    """
    try:
        return pd.read_stata(path, convert_categoricals=False)
    except ValueError as exc:  # pandas reports a malformed/encrypted file this way
        raise ValueError(f"Could not read the Stata file: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - binary readers raise broadly
        raise ValueError(f"Could not read the Stata file: {exc}") from exc


# ---------------------------------------------------------------------- SPSS


def read_spss_file(path: Path) -> pd.DataFrame:
    """Read an SPSS ``.sav``/``.zsav`` (or ``.por``) file through pyreadstat.

    ``apply_value_formats=False`` is passed explicitly: with formats applied,
    pyreadstat replaces the stored codes of a labelled variable with its labels,
    which is precisely the numeric-to-text conversion the module docstring rules
    out (verified on pyreadstat 1.3.6: ``gender`` turns into a string Categorical).
    SPSS date variables still come back as date objects, and the profiler types
    those columns ``date`` from their values, so keeping codes costs nothing.

    ``.zsav`` (the zip-compressed successor of ``.sav``) is read by the same
    reader. pyreadstat cannot write one, so no test in this repository covers a
    genuine ``.zsav`` file - only the compressed ``.sav`` variant it is built on.
    """
    pyreadstat = _require("pyreadstat", "SPSS files (.sav, .zsav, .por)")
    reader = pyreadstat.read_por if path.suffix.lower() == ".por" else pyreadstat.read_sav
    try:
        frame, _metadata = reader(path, apply_value_formats=False)
    except Exception as exc:  # noqa: BLE001 - the Cython reader raises broadly
        raise ValueError(f"Could not read the SPSS file: {exc}") from exc
    return frame


# ------------------------------------------------------------------------- R


def read_r_file(path: Path) -> pd.DataFrame:
    """Read an R workspace/``.rds`` file through pyreadr and return one table.

    An ``.RData`` workspace can hold many objects while this platform stores a
    single table per dataset, so the largest stored ``data.frame`` wins (largest
    by cells, then rows, then name — deterministic). Objects that are not
    tables (vectors, lists, models) are ignored.
    """
    pyreadr = _require("pyreadr", "R files (.RData, .rda, .rds)")
    try:
        stored = pyreadr.read_r(str(path))
    except Exception as exc:  # noqa: BLE001 - the Cython reader raises broadly
        raise ValueError(f"Could not read the R file: {exc}") from exc

    tables: Dict[str, pd.DataFrame] = {
        name: obj for name, obj in stored.items() if isinstance(obj, pd.DataFrame)
    }
    if not tables:
        raise ValueError(
            "The R file holds no data.frame to analyse — save the table itself, "
            "e.g. saveRDS(my_data, \"my_data.rds\")"
        )
    _, frame = max(
        tables.items(),
        key=lambda item: (item[1].shape[0] * item[1].shape[1], item[1].shape[0], item[0]),
    )
    if R_INDEX_COLUMN in frame.columns:
        frame = frame.drop(columns=[R_INDEX_COLUMN])
    return frame


# ------------------------------------------------------------------ dispatch


def read_stat_file(path: Path) -> pd.DataFrame:
    """Read any statistical package file into a DataFrame.

    Raises ``ValueError`` (same convention as the rest of the read layer, so the
    upload route turns it into a clean 400) for unsupported, unreadable or
    dependency-less files.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in STATA_SUFFIXES:
        return read_stata_file(path)
    if suffix in SPSS_SUFFIXES:
        return read_spss_file(path)
    if suffix in R_SUFFIXES:
        return read_r_file(path)
    raise ValueError(f"'{suffix}' is not a statistical package format")


def _require(module_name: str, what: str) -> object:
    """Import an optional reader, or explain how to get it."""
    try:
        module = __import__(module_name)
    except ImportError as exc:  # pragma: no cover - exercised only without the dep
        raise ValueError(
            f"Reading {what} needs the '{module_name}' package, which this server "
            f"does not have. Install it with: pip install {module_name}"
        ) from exc
    return module
