"""Guardrails on p-values (improvement plan item 2.4).

Two rules, both about the gap between running a test and reading one:

1. **A p-value must name its test.** A number with no test attached is
   unreadable -- "p = 0.03" says nothing without "Welch t-test" beside
   it. The engine names its own headline tests; the guardrail walks the
   whole result and attaches the method's name to any p-value that
   arrived without one, so the invariant holds for every table row the
   engine emits, not just the top level.

2. **Many p-values need a correction.** Every test at alpha = 0.05 is a
   5% chance of a false positive, and the chances compound: k tests give
   a family-wise error rate of 1 - (1 - 0.05)**k, which is 14% at k = 3
   and 40% at k = 10. A reader who scans a correlation matrix or a
   coefficient table and remembers the rows with p < 0.05 is making
   exactly the multiple-comparison mistake the analysis guide warns
   about -- without meaning to. The guardrail counts the tests the
   result *reports* and, from three upwards, attaches the family-wise
   rate plus Bonferroni and Benjamini-Hochberg adjusted p-values.

The count deliberately covers only the reported zones -- estimate, test,
confidence interval, effect size and tables. The ``diagnostics`` block
holds assumption checks (Levene, normality): those judge whether the
data supports the method, they are not hypotheses the reader set out to
test, and counting them would put a correction warning on every single
t-test. The same test is often reported twice by design (the strongest
pair appears in the estimate, the test block and the pairs table), so
a sighting is identified by its test name *and* its value; a summary
block that re-reports a named test without naming it counts once more
than it should, which errs on the side of warning.

Like the assumption checks, guardrails never change the estimate. They
add information about how to read it.
"""

import math
from typing import Any, Dict, List, Optional, Sequence

#: How many reported p-values trigger the multiple-comparison warning.
#: Below this the family-wise inflation is small enough that the
#: warning would cost more attention than it saves.
MULTIPLE_COMPARISON_THRESHOLD = 3

#: The significance level the engine tests at, used for the family-wise
#: arithmetic. It is a property of the engine, not of any one method.
FAMILYWISE_ALPHA = 0.05

#: Keys a result may carry a p-value under. Both spellings appear in
#: the codebase; collecting either keeps the walk honest.
P_VALUE_KEYS = ("p_value", "p")

#: Top-level zones that report what the reader asked for. ``diagnostics``
#: is excluded on purpose: see the module docstring.
REPORTED_ZONES = (
    "estimate",
    "test",
    "confidence_interval",
    "effect_size",
    "tables",
)

#: Sibling keys that already name a test, so a p-value beside one needs
#: nothing attached.
TEST_NAME_KEYS = ("test", "method", "test_name")


def _is_p_value(value: Any) -> bool:
    """A finite probability, not a boolean, not NaN, not a statistic."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    number = float(value)
    return math.isfinite(number) and 0.0 <= number <= 1.0


def _row_label(row: Dict[str, Any]) -> Optional[str]:
    """A reader-facing name for the test behind one p-value.

    Correlation pairs say which two variables they joined, coefficient
    rows say which term they estimated, and everything else falls back
    to the first identifying column it has. A p-value with no name at
    all is reported under its path instead of being silently dropped.
    """
    if "x" in row and "y" in row:
        return f"{row['x']} -- {row['y']}"
    for key in ("term", "variable", "column", "name", "group", "feature"):
        if row.get(key) is not None:
            return str(row[key])
    return None


def _walk(
    node: Any,
    path: str,
    found: List[Dict[str, Any]],
    *,
    annotate: Optional[str],
) -> None:
    """Visit every dict, collecting p-values and naming the orphans.

    ``annotate`` is the display name of the test, or None to only
    collect. A dict that carries a p-value without a test name gets
    one attached in place, which is the whole of rule 1: the engine
    refuses to hand back a bare number.
    """
    if isinstance(node, dict):
        p_key = next(
            (key for key in P_VALUE_KEYS if _is_p_value(node.get(key))), None
        )
        if p_key is not None:
            if annotate is not None and not any(
                node.get(key) is not None for key in TEST_NAME_KEYS
            ):
                node["test"] = annotate
            found.append(
                {
                    "path": f"{path}.{p_key}",
                    "p_value": float(node[p_key]),
                    "label": _row_label(node),
                }
            )
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                _walk(value, f"{path}.{key}", found, annotate=annotate)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            if isinstance(item, (dict, list)):
                _walk(item, f"{path}[{index}]", found, annotate=annotate)


def collect_p_values(
    result: Dict[str, Any],
    *,
    reported_only: bool = False,
    annotate: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Every p-value in a result, with where it lives and what it tested.

    With ``reported_only`` the walk starts from each reported zone rather
    than the whole result, which is how the multiple-comparison count
    keeps diagnostics out of the reader's family. With ``annotate`` the
    walk also names any p-value that arrived without a test.
    """
    found: List[Dict[str, Any]] = []
    roots: Sequence[str] = REPORTED_ZONES if reported_only else ("",)
    for zone in roots:
        if zone and zone in result:
            _walk(result[zone], zone, found, annotate=annotate)
        elif not zone:
            _walk(result, "result", found, annotate=annotate)
    return found


def _deduplicated(
    entries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """One entry per distinct (test, value) pair, first sighting kept.

    The engine reports the same test in several places by design --
    the strongest correlation pair appears in the estimate, the test
    block and the pairs table -- so a bare value is not an identity:
    a regression's omnibus F-test and a strong predictor can both
    carry p = 0.0. The test's name plus its value is the identity.
    A summary block that re-reports a named test without naming it
    (the correlation matrix's ``test`` block) then counts once more
    than it should, which can only overstate the family -- a
    guardrail must never hide a test, only risk over-counting one.
    """
    seen = set()
    unique: List[Dict[str, Any]] = []
    for entry in entries:
        identity = (entry["label"], round(entry["p_value"], 6))
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(entry)
    return unique


def bonferroni(p_values: Sequence[float]) -> List[float]:
    """Bonferroni-adjusted p-values: the simplest, most conservative fix.

    Multiply each p-value by the number of tests. It controls the
    family-wise error rate exactly, at the cost of power -- the right
    default when a false positive is expensive.
    """
    count = len(p_values)
    return [min(float(p) * count, 1.0) for p in p_values]


def benjamini_hochberg(p_values: Sequence[float]) -> List[float]:
    """Benjamini-Hochberg step-up adjusted p-values (FDR control).

    Controls the expected *share* of false positives among the rejected
    hypotheses rather than the chance of any false positive, which is
    the better trade-off when a reader is screening many tests and will
    look closer at the survivors.
    """
    values = [float(p) for p in p_values]
    count = len(values)
    order = sorted(range(count), key=lambda index: values[index])
    adjusted = [0.0] * count
    running = 1.0
    for rank in range(count, 0, -1):
        index = order[rank - 1]
        running = min(running, values[index] * count / rank)
        adjusted[index] = min(running, 1.0)
    return adjusted


def display_name(analysis_type: str, parameters: Optional[Dict[str, Any]] = None) -> str:
    """The test's name as the method catalogue spells it.

    The catalogue is the source of truth: one name in the picker, in
    the plan and on the p-value. A few analyses run a test the reader
    chooses in the parameters -- the correlation matrix runs Pearson
    or Spearman per pair -- so those names are resolved from the
    parameters that actually ran. A readable analysis_type is the
    fallback so an unknown analysis still names its numbers rather
    than leaving them orphaned.
    """
    parameters = parameters or {}
    chooser = PARAMETERISED_TEST_NAMES.get(analysis_type)
    if chooser is not None:
        return chooser(parameters)
    try:
        from app.statflow.methods import METHODS

        for method in METHODS:
            if method.get("engine") == analysis_type:
                return str(method.get("label") or analysis_type)
    except Exception:  # pragma: no cover - the catalogue ships with the package
        pass
    readable = str(analysis_type).replace("_", " ")
    return readable[0].upper() + readable[1:] + " test"


#: Test names that depend on how the reader configured the run. The
#: engine itself states the choice in its top-level ``test`` block;
#: these let the guardrail name the same choice on every row.
PARAMETERISED_TEST_NAMES: Dict[str, Any] = {
    "correlation_matrix": lambda parameters: (
        "Pearson r"
        if str(parameters.get("method") or "pearson").lower() == "pearson"
        else "Spearman rho"
    ),
}


def apply_guardrails(
    analysis_type: str,
    result: Dict[str, Any],
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Attach p-value provenance and, when many tests are reported, corrections.

    Returns the block it attached (empty when no correction was needed)
    so a caller or test can inspect what the guardrail decided. The
    result is modified in place, the way the assumption checks are, and
    -- like them -- never changes an estimate.
    """
    name = display_name(analysis_type, parameters)
    # Rule 1 runs over the whole result, diagnostics included: every
    # p-value the engine hands back names its test, wherever it sits.
    collect_p_values(result, annotate=name)

    reported = _deduplicated(
        collect_p_values(result, reported_only=True)
    )
    if len(reported) < MULTIPLE_COMPARISON_THRESHOLD:
        return {}

    values = [entry["p_value"] for entry in reported]
    count = len(values)
    bonferroni_values = bonferroni(values)
    fdr_values = benjamini_hochberg(values)
    familywise = 1.0 - (1.0 - FAMILYWISE_ALPHA) ** count

    block: Dict[str, Any] = {
        "test_count": count,
        "alpha": FAMILYWISE_ALPHA,
        "familywise_error_rate": round(familywise, 4),
        "tests": [
            {
                "label": entry["label"] or entry["path"],
                "path": entry["path"],
                "p_value": entry["p_value"],
                "bonferroni_p_value": round(adjusted, 6),
                "benjamini_hochberg_p_value": round(fdr, 6),
                "significant_after_bonferroni": bool(
                    adjusted < FAMILYWISE_ALPHA
                ),
                "significant_after_bh": bool(fdr < FAMILYWISE_ALPHA),
            }
            for entry, adjusted, fdr in zip(
                reported, bonferroni_values, fdr_values
            )
        ],
    }
    result["multiple_comparisons"] = block
    result.setdefault("warnings", []).append(
        f"{count} hypothesis tests are reported in this result. Testing "
        f"{count} hypotheses at alpha = {FAMILYWISE_ALPHA} carries a "
        f"family-wise error rate of {familywise:.1%} -- the chance that "
        "at least one is a false positive. Bonferroni and "
        "Benjamini-Hochberg adjusted p-values are in "
        "`multiple_comparisons`; a finding is only solid if it survives "
        "the adjustment."
    )
    return block
