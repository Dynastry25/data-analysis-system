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

The labels themselves are **kept and reported** by the readers rather than
discarded. A file that codes gender as 1/2 is not readable without them, and
throwing the metadata away made the platform show a column called ``gender``
holding 1 and 2 as if that were the whole story. Codes stay codes; the words
travel beside them in :class:`VariableLabels`.
"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

STATA_SUFFIXES = {".dta"}
SPSS_SUFFIXES = {".sav", ".zsav", ".por"}
R_SUFFIXES = {".rdata", ".rda", ".rds"}

#: Every extension handled by this module, so callers can branch on it.
STAT_SUFFIXES = STATA_SUFFIXES | SPSS_SUFFIXES | R_SUFFIXES

#: ``pyreadr`` names the row-name column of an R data.frame this way.
R_INDEX_COLUMN = "(index)"

#: Value-label maps longer than this are not worth storing: they are a lookup
#: table mistaken for a variable, and the platform cannot render them anyway.
MAX_VALUE_LABELS = 500


class VariableLabels:
    """The label metadata read alongside a table, per column.

    ``variable_labels`` maps a column name to the question it answers
    ("Sex of respondent"). ``value_labels`` maps a column name to its code
    lookup (``{"1": "Male", "2": "Female"}``).

    Codes are normalised to strings on the way in. Stata gives ``np.int32``,
    SPSS gives ``float`` and JSON object keys are always strings, so keeping the
    original type would make ``1``, ``1.0`` and ``"1"`` three different keys
    depending on which reader produced the file.
    """

    __slots__ = ("file_label", "variable_labels", "value_labels", "source")

    def __init__(
        self,
        file_label: Optional[str] = None,
        variable_labels: Optional[Dict[str, str]] = None,
        value_labels: Optional[Dict[str, Dict[str, str]]] = None,
        source: Optional[str] = None,
    ) -> None:
        self.file_label = file_label or None
        self.variable_labels = variable_labels or {}
        self.value_labels = value_labels or {}
        self.source = source

    def is_empty(self) -> bool:
        return not (self.file_label or self.variable_labels or self.value_labels)

    def for_column(self, name: str) -> Tuple[Optional[str], Optional[Dict[str, str]]]:
        return self.variable_labels.get(name), self.value_labels.get(name)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"VariableLabels(source={self.source!r}, file_label={self.file_label!r}, "
            f"variable_labels={len(self.variable_labels)}, "
            f"value_labeled_columns={len(self.value_labels)})"
        )


def _clean_text(value: Any) -> Optional[str]:
    """A label that is a real string, not an empty or missing placeholder."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _code_key(value: Any) -> Optional[str]:
    """Normalise a stored code to the string used as a JSON key.

    ``1`` and ``1.0`` and ``"1"`` are the same code: Stata hands back
    ``np.int32(1)`` and SPSS a ``float(1.0)`` for the same file.
    """
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) or (
        isinstance(value, float) and float(value).is_integer()
    ):
        try:
            return str(int(value))
        except (ValueError, OverflowError):
            return None
    if isinstance(value, float):
        return repr(value)
    text = str(value).strip()
    return text or None


def _normalise_value_labels(raw: Any) -> Dict[str, Dict[str, str]]:
    """Turn a reader's code/word mapping into ``{column: {code: word}}``.

    Anything that is not a per-column mapping of code to a non-empty string is
    dropped rather than half-converted, so a malformed entry cannot reach the
    database as a column that appears labelled but renders as blanks.
    """
    result: Dict[str, Dict[str, str]] = {}
    if not isinstance(raw, dict):
        return result
    for column, mapping in raw.items():
        if not isinstance(mapping, dict):
            continue
        if len(mapping) > MAX_VALUE_LABELS:
            continue
        cleaned: Dict[str, str] = {}
        for code, word in mapping.items():
            key = _code_key(code)
            text = _clean_text(word)
            if key is None or text is None:
                continue
            cleaned[key] = text
        if cleaned:
            result[str(column)] = cleaned
    return result


def _normalise_variable_labels(raw: Any) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    result: Dict[str, str] = {}
    for column, text in raw.items():
        cleaned = _clean_text(text)
        if cleaned is not None:
            result[str(column)] = cleaned
    return result


def _drop_labels_for_absent_columns(
    frame: pd.DataFrame,
    variable_labels: Dict[str, str],
    value_labels: Dict[str, Dict[str, str]],
) -> Tuple[Dict[str, str], Dict[str, Dict[str, str]]]:
    """Keep only labels whose column actually made it into the table.

    A label naming a column the reader dropped (a duplicate name, an unsupported
    type) would otherwise be stored against a column that does not exist.
    """
    present = set(frame.columns)
    return (
        {k: v for k, v in variable_labels.items() if k in present},
        {k: v for k, v in value_labels.items() if k in present},
    )


# --------------------------------------------------------------------- Stata


def read_stata_file(path: Path) -> Tuple[pd.DataFrame, VariableLabels]:
    """Read a Stata ``.dta`` file (any release from 3 to 19) and its labels.

    ``convert_categoricals=False`` keeps the numeric codes of labelled variables
    (see the module docstring) so measurable columns stay measurable.

    The labels are read from ``StataReader`` rather than the frame, because
    ``read_stata`` returns only the data. Both were verified against a file
    written by this repository's own test: ``variable_labels()`` returns the
    question each column answers, ``value_labels()`` the code lookup, and the
    codes in the frame stay ``int64``.

    A file with no value-label block makes ``value_labels()`` raise inside
    pandas; that is a valid file, so it is treated as "no labels" rather than
    as a corrupt upload. ``StataReader`` has no ``close()`` in pandas 3, so the
    reader is simply left to the garbage collector once its data is in hand.
    """
    try:
        # ``convert_categoricals=False`` is the whole point of reading a Stata
        # file this way: with it left on, a value-labelled variable arrives as
        # a pandas Categorical of the *words* and stops being numeric, which
        # silently removes it from every statistic the platform computes. With
        # it off, the frame keeps the codes as int32. Verified on pandas 3.0.6.
        reader = pd.io.stata.StataReader(path, convert_categoricals=False)
        frame = reader.read()
        # ``data_label`` is a property here; ``variable_labels()`` and
        # ``value_labels()`` are methods. Verified on pandas 3.0.6.
        file_label = reader.data_label
    except ValueError as exc:  # pandas reports a malformed/encrypted file this way
        raise ValueError(f"Could not read the Stata file: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - binary readers raise broadly
        raise ValueError(f"Could not read the Stata file: {exc}") from exc

    try:
        value_labels = _normalise_value_labels(reader.value_labels())
    except Exception:  # noqa: BLE001 - a file with no value-label block
        value_labels = {}
    variable_labels = _normalise_variable_labels(reader.variable_labels())

    variable_labels, value_labels = _drop_labels_for_absent_columns(
        frame, variable_labels, value_labels
    )
    return frame, VariableLabels(
        file_label=file_label,
        variable_labels=variable_labels,
        value_labels=value_labels,
        source="stata",
    )


# ---------------------------------------------------------------------- SPSS


def read_spss_file(path: Path) -> Tuple[pd.DataFrame, VariableLabels]:
    """Read an SPSS ``.sav``/``.zsav`` (or ``.por``) file through pyreadstat.

    ``apply_value_formats=False`` is passed explicitly: with formats applied,
    pyreadstat replaces the stored codes of a labelled variable with its labels,
    which is precisely the numeric-to-text conversion the module docstring rules
    out (verified on pyreadstat 1.3.6: ``gender`` turns into a string
    Categorical). SPSS date variables still come back as date objects, and the
    profiler types those columns ``date`` from their values, so keeping codes
    costs nothing.

    The second element of pyreadstat's return value — the metadata — used to be
    discarded here, which is how a ``.sav`` full of value labels arrived as bare
    codes. ``column_names_to_labels`` and ``variable_value_labels`` are now kept
    and normalised. Verified on a file this repository's tests write: codes
    arrive as ``float64`` and the labels come back complete.

    ``.zsav`` (the zip-compressed successor of ``.sav``) is read by the same
    reader. pyreadstat cannot write one, so no test in this repository covers a
    genuine ``.zsav`` file - only the compressed ``.sav`` variant it is built on.
    """
    pyreadstat = _require("pyreadstat", "SPSS files (.sav, .zsav, .por)")
    reader = pyreadstat.read_por if path.suffix.lower() == ".por" else pyreadstat.read_sav
    try:
        frame, metadata = reader(path, apply_value_formats=False)
    except Exception as exc:  # noqa: BLE001 - the Cython reader raises broadly
        raise ValueError(f"Could not read the SPSS file: {exc}") from exc

    variable_labels = _normalise_variable_labels(
        getattr(metadata, "column_names_to_labels", None)
    )
    value_labels = _normalise_value_labels(
        getattr(metadata, "variable_value_labels", None)
    )
    variable_labels, value_labels = _drop_labels_for_absent_columns(
        frame, variable_labels, value_labels
    )
    return frame, VariableLabels(
        file_label=_clean_text(getattr(metadata, "file_label", None)),
        variable_labels=variable_labels,
        value_labels=value_labels,
        source="spss",
    )


# ------------------------------------------------------------------------- R


def read_r_file(path: Path) -> Tuple[pd.DataFrame, VariableLabels]:
    """Read an R workspace/``.rds`` file through pyreadr and return one table.

    An ``.RData`` workspace can hold many objects while this platform stores a
    single table per dataset, so the largest stored ``data.frame`` wins (largest
    by cells, then rows, then name — deterministic). Objects that are not
    tables (vectors, lists, models) are ignored.

    R labels are handled differently from Stata and SPSS, and the difference is
    in the library rather than in this code. ``pyreadr`` exposes only
    ``read_r``/``write_r*`` — there is no metadata accessor, so the ``label``
    attribute R attaches to a variable cannot be read through it. Rather than
    invent one, this reports what genuinely arrives: an R ``factor`` becomes a
    pandas Categorical, and its *levels* are the words the researcher wrote, so
    those are recoverable and are returned as the value labels for that column.
    A labelled-but-not-factored R column therefore comes back with no label,
    and the platform says so rather than showing a guessed one.
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

    value_labels = _factor_levels(frame)
    variable_labels, value_labels = _drop_labels_for_absent_columns(
        frame, {}, value_labels
    )
    return frame, VariableLabels(value_labels=value_labels, source="r")


# ------------------------------------------------------------------ dispatch


def _factor_levels(frame: pd.DataFrame) -> Dict[str, Dict[str, str]]:
    """R factors, read out as a code/word lookup.

    ``pyreadr`` turns an R ``factor`` into a pandas Categorical whose *categories*
    are the R levels — the words the researcher typed, in R's own order. That is
    the one piece of R label metadata that genuinely survives the read, so it is
    returned as ``{column: {level: level}}``: the category is both the code and
    the word, and callers only need to know a column has a known set of levels.
    """
    result: Dict[str, Dict[str, str]] = {}
    for name in frame.columns:
        series = frame[name]
        if not isinstance(series.dtype, pd.CategoricalDtype):
            continue
        levels = [str(level) for level in series.cat.categories]
        if not levels or len(levels) > MAX_VALUE_LABELS:
            continue
        result[str(name)] = {level: level for level in levels}
    return result


def read_stat_file(path: Path) -> Tuple[pd.DataFrame, VariableLabels]:
    """Read any statistical package file into a DataFrame and its labels.

    Returns ``(frame, labels)``. ``labels`` is empty rather than absent for the
    formats that carry none, so a caller never has to ask whether the file type
    supports labels before looking.

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
