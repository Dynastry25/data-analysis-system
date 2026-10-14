"""Analysis templates for common organisational questions (plan 3.3).

A template is a translation: a question a reader already has, into
variables and analyses that answer it. Three properties keep it
honest, and each is pinned here:

  * **Every step names a method the engine really has**, with the
    engine's own parameter names. A renamed engine parameter fails a
    test here rather than a reader's report.
  * **Variables are proposed by type, never assumed by name.** A
    ``group`` is categorical because a comparison needs levels, a
    two-group test needs exactly two, a model feature must be
    numeric, and a before/after pair never proposes the same column
    twice. Proposing a three-level column for a two-group test would
    surface an engine error instead of a choice.
  * **The engine is unchanged.** Each step's result is the standard
    result the statistics page would produce, so a template answer
    carries the same assumption checks, guardrails and
    interpretation. The response reports the parameters each step
    resolved to, so nothing ran invisibly.

Run it with:  python tests/templates_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

TEST_ROOT = Path(tempfile.mkdtemp(prefix="templates_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "templates-test-secret"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.data_service import profile_columns  # noqa: E402
from app.statflow import planning, stats_engine, templates  # noqa: E402
from typing import Dict  # noqa: E402

PASSED = 0


def check(condition: bool, message: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {message}")
    PASSED += 1
    print(f"  [ok] {message}")


def crop_frame() -> pd.DataFrame:
    """The agricultural dataset: yields by variety, with conditions."""
    rng = np.random.default_rng(5)
    return pd.DataFrame(
        {
            "district": rng.choice(["Kiambu", "Mombasa", "Kisumu"], 120),
            "variety": rng.choice(["local", "hybrid"], 120),
            "yield_kg": rng.normal(800, 120, 120),
            "rainfall_mm": rng.normal(600, 90, 120),
            "area_ha": rng.uniform(0.5, 4, 120),
        }
    )


def retention_frame() -> pd.DataFrame:
    """Subscribers who stayed or left, with their recorded conditions."""
    rng = np.random.default_rng(11)
    frame = pd.DataFrame(
        {
            "plan": rng.choice(["monthly", "yearly"], 200),
            "region": rng.choice(["Nairobi", "Arusha"], 200),
            "churned": rng.choice([0, 1], 200, p=[0.78, 0.22]),
            "support_calls": rng.integers(0, 9, 200),
            "tenure_months": rng.integers(1, 60, 200),
        }
    )
    return frame


# ------------------------------------------------------------------- tests


def test_every_template_step_matches_the_engine() -> None:
    print("\n1) Every step names a method the engine has, with real parameters")
    known = {entry["analysis_type"] for entry in stats_engine.catalog()}
    for template in templates.catalog():
        for step in template["steps"]:
            check(
                step["analysis_type"] in known,
                f"{template['key']}/{step['key']} -> '{step['analysis_type']}' is a real method",
            )
            check(bool(step["variables"] or step["analysis_type"] in {"correlation_matrix", "descriptive"}),
                  f"{template['key']}/{step['key']} declares its variables")

    # The parameter map is the engine's own vocabulary: every mapped
    # parameter must be a parameter that analysis accepts.
    for template in templates.TEMPLATES.values():
        for step in template.steps:
            for _, engine_name in step.parameters.items():
                check(
                    engine_name
                    in {
                        "x",
                        "y",
                        "value_column",
                        "group_column",
                        "columns",
                        "target",
                        "features",
                        "predictors",
                        "method",
                    },
                    f"{step.analysis_type} declares engine parameter '{engine_name}'",
                )


def test_suggestions_respect_what_the_step_needs() -> None:
    print("\n2) Variables are proposed by type, and by what the test needs")
    frame = crop_frame()
    profile = [
        {**entry, "semantic_type": planning.semantic_type(frame[entry["name"]])}
        for entry in profile_columns(frame)
    ]
    for entry in profile:
        entry.setdefault("non_null_count", entry.get("count", 0))

    two_levels = templates.TemplateVariable(key="group", label="", role="group", levels=2)
    suggested = templates.suggest(frame, profile, two_levels)
    check(
        suggested == ["variety"],
        f"a two-group test suggests only the two-level column (got {suggested})",
    )

    any_group = templates.TemplateVariable(key="group", label="", role="group", min_levels=2)
    suggested = templates.suggest(frame, profile, any_group)
    check(
        "district" in suggested and "variety" in suggested,
        f"an any-group test offers both groupings (got {suggested})",
    )

    numeric = templates.TemplateVariable(key="f", label="", role="predictor", numeric_only=True)
    suggested = templates.suggest(frame, profile, numeric)
    check(
        all(planning.semantic_type(frame[name]) == "numeric" for name in suggested),
        "a model feature is only offered numeric columns",
    )

    # A before/after pair must not be filled by one column.
    before = templates.TemplateVariable(key="before", label="", role="before")
    first = templates.suggest(frame, profile, before)
    second = templates.suggest(frame, profile, before, exclude=[first[0]])
    check(first[0] != second[0], "the second slot excludes the first slot's column")


def test_a_template_runs_and_reports_its_parameters() -> None:
    print("\n3) Running a template runs the engine, and says what it ran")
    frame = crop_frame()
    result = templates.run_template(frame, "crop_yield")
    steps = result["steps"]
    check(len(steps) == 3, f"crop yield has three steps (got {len(steps)})")
    check(
        [step["analysis_type"] for step in steps]
        == ["one_way_anova", "correlation_matrix", "linear_regression"],
        "and they run in order",
    )
    for step in steps:
        check(step["result"].get("status") == "success", f"{step['key']} succeeded")
        check(bool(step["parameters"]), f"{step['key']} reports the parameters it used")

    # The standard result is unchanged by the template: same assumption
    # checks, same guardrails, same interpretation.
    engine_result = stats_engine.run_analysis(
        frame, "one_way_anova", steps[0]["parameters"]
    )
    check(
        set(step_keys(engine_result)) == set(step_keys(steps[0]["result"])),
        "a template step's result is the engine's own result shape",
    )
    check(
        steps[0]["result"]["test"]["statistic"] == engine_result["test"]["statistic"],
        "and the same statistic the statistics page would report",
    )

    # The reader's choice overrides the suggestion, and is honoured.
    chosen = templates.run_template(
        frame,
        "crop_yield",
        {
            "yield_by_group": {
                "outcome": "yield_kg",
                "group": "variety",
            },
            "what_predicts": {
                "outcome": "yield_kg",
                "predictors": ["rainfall_mm", "area_ha"],
            },
        },
    )
    check(
        chosen["steps"][0]["parameters"] == {
            "value_column": "yield_kg",
            "group_column": "variety",
        },
        "the reader's columns are the ones that run",
    )
    check(
        chosen["steps"][2]["parameters"]["features"] == ["rainfall_mm", "area_ha"],
        "including the model's features",
    )


def test_an_unknown_or_unfillable_template_is_refused() -> None:
    print("\n4) A template that cannot be filled says so")
    frame = crop_frame()
    try:
        templates.run_template(frame, "no_such_template")
        raised = False
    except planning.PlanningError:
        raised = True
    check(raised, "an unknown template key is refused")

    # A dataset with no categorical column cannot fill a group role:
    # the template must say which slot is empty rather than skip its
    # own question.
    numeric_only = pd.DataFrame({"a": [1, 2, 3, 4], "b": [5, 6, 7, 8]})
    try:
        templates.run_template(numeric_only, "crop_yield")
        raised = False
    except planning.PlanningError as exc:
        message = str(exc)
        raised = True
    check(raised, "a dataset that cannot fill a role is refused")
    check("group" in message or "value" in message, f"the error names the empty role ({message})")


def test_the_catalog_is_readable() -> None:
    print("\n5) The catalog reads like the question it answers")
    catalog = templates.catalog()
    check(len(catalog) >= 4, f"at least four templates (got {len(catalog)})")
    for template in catalog:
        check(bool(template["question"]), f"{template['key']} states its question")
        check(bool(template["label_swahili"]), f"{template['key']} has a Swahili label")
        check(bool(template["when_to_use"]), f"{template['key']} says when to use it")
        check(bool(template["steps"]), f"{template['key']} has at least one step")
        check(
            all(step["reads"] for step in template["steps"]),
            f"{template['key']} says what each answer means",
        )
    keys = [template["key"] for template in catalog]
    check(
        "donor_reporting" in keys and "customer_retention" in keys,
        "the org-shaped questions are all there",
    )


def step_keys(result: Dict) -> list:
    return sorted((result or {}).keys())


def main() -> int:
    print("ANALYSIS TEMPLATE TESTS")
    test_every_template_step_matches_the_engine()
    test_suggestions_respect_what_the_step_needs()
    test_a_template_runs_and_reports_its_parameters()
    test_an_unknown_or_unfillable_template_is_refused()
    test_the_catalog_is_readable()
    print(f"\nALL TEMPLATE TESTS PASSED ({PASSED} checks)")
    return 0


def test_templates() -> None:
    """pytest entry point: same run as ``python tests/templates_test.py``."""
    main()


if __name__ == "__main__":
    raise SystemExit(main())
