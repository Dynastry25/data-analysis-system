"""Analysis templates for the questions organisations actually ask (plan 3.3).

A reader who knows their question -- "my donor wants to know whether
the programme reached the districts we said it would" -- still has to
translate it into variables and methods, and that translation is
where a first-time user stalls. These templates carry that
translation: each one names the question shape, the variables it
needs by role, and the sequence of analyses that answers it, all in
the language the reader asked in.

The rules that keep a template honest:

* **A template runs the same engine, not a shortcut.** Every step is
  an ordinary analysis from the statistics catalogue with ordinary
  parameters, so a template result is a standard result: same
  assumption checks, same guardrails, same interpretation, same
  reproducibility record. Nothing here computes a number the engine
  does not also compute on the statistics page.
* **Variables are proposed, never assumed.** A template's variables
  are picked by *role* -- outcome, predictor, group, time -- and
  resolved against the reader's dataset by semantic type. A column
  named `region` is offered as the group because it is categorical,
  not because a string matched. If two columns fit a role the
  reader chooses, because a wrong choice is a wrong answer, and the
  engine cannot tell their intention from a dtype.
* **Every template is checked against the catalogue.** The tests
  assert each step's analysis type exists and each variable's
  expected type is one the planner can classify, so a template can
  never name a method the engine does not have.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.statflow import planning, stats_engine
from app.statflow.planning import PlanningError

#: The variable roles a step can ask for, with the semantic type that
#: satisfies each. `time` has no planner type of its own, so a step
#: that needs it says `date` and the resolver looks for a date column.
SEMANTIC_ROLES = {
    "outcome": "numeric",
    "predictor": "any",
    "group": "categorical",
    "before": "numeric",
    "after": "numeric",
    "date": "date",
}


@dataclass(frozen=True)
class TemplateVariable:
    """One variable a step needs, described by role, not by name."""

    key: str
    label: str
    role: str  # outcome | predictor | group | before | after | date
    optional: bool = False
    levels: Optional[int] = None  # exactly this many distinct levels
    min_levels: Optional[int] = None  # at least this many
    binary: bool = False  # the column must hold a yes/no outcome
    numeric_only: bool = False  # a model feature, so text columns cannot serve it

    def as_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "role": self.role,
            "expected_type": SEMANTIC_ROLES[self.role],
            "optional": self.optional,
            "levels": self.levels,
            "min_levels": self.min_levels,
            "binary": self.binary,
            "numeric_only": self.numeric_only,
        }


@dataclass(frozen=True)
class TemplateStep:
    """One analysis in the sequence that answers the question."""

    key: str
    label: str
    description: str
    analysis_type: str
    variables: tuple  # of TemplateVariable
    reads: str = ""  # what the answer tells the reader, in one line
    parameters: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "analysis_type": self.analysis_type,
            "reads": self.reads,
            "variables": [
                variable.as_dict() for variable in self.variables
            ],
        }

    def engine_parameter(self, variable_key: str) -> str:
        """The engine's own name for one of this step's variables.

        The engine is the source of truth for parameter names: a
        ``welch_t_test`` wants ``value_column``, a ``paired_t_test``
        wants ``x`` and ``y``. Every step states the mapping rather
        than assuming the template's vocabulary is the engine's,
        because a renamed engine parameter must fail a test here
        rather than break a reader's report.
        """
        return self.parameters.get(variable_key, variable_key)


@dataclass(frozen=True)
class Template:
    """A question shape an organisation asks, and how the engine answers it."""

    key: str
    label: str
    label_swahili: str
    category: str
    question: str
    when_to_use: str
    steps: tuple  # of TemplateStep

    def as_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "label_swahili": self.label_swahili,
            "category": self.category,
            "question": self.question,
            "when_to_use": self.when_to_use,
            "steps": [step.as_dict() for step in self.steps],
        }


def _variable(
    key: str,
    label: str,
    role: str,
    optional: bool = False,
    levels: Optional[int] = None,
    min_levels: Optional[int] = None,
    binary: bool = False,
    numeric_only: bool = False,
) -> TemplateVariable:
    return TemplateVariable(
        key=key,
        label=label,
        role=role,
        optional=optional,
        levels=levels,
        min_levels=min_levels,
        binary=binary,
        numeric_only=numeric_only,
    )


TEMPLATES: Dict[str, Template] = {
    "donor_reporting": Template(
        key="donor_reporting",
        label="Donor reporting",
        label_swahili="Ripoti kwa wafadhili",
        category="Reporting",
        question="Did the programme reach the people and places we reported?",
        when_to_use="When a funder asks for evidence about reach, outcomes or value for money.",
        steps=(
            TemplateStep(
                key="profile",
                label="Profile of the reported group",
                description="Who the data actually covers, before any claim is made about them.",
                analysis_type="descriptive",
                variables=(_variable("columns", "Variables za kuripoti", "outcome", optional=True),),
                reads="The shape of the population the numbers describe.",
            ),
            TemplateStep(
                key="by_group",
                label="The reported measure by group",
                description="How the headline number differs across the group the donor asked about.",
                analysis_type="one_way_anova",
                variables=(
                    _variable("outcome", "Kipimo cha ripoti", "outcome"),
                    _variable(
                        "group",
                        "Kikundi (mkoa, programu, mwaka)",
                        "group",
                        min_levels=2,
                    ),
                ),
                reads="Whether the reach differs by group, and by how much.",
                parameters={"outcome": "value_column", "group": "group_column"},
            ),
            TemplateStep(
                key="what_travels_with_it",
                label="What travels with the measure",
                description="Which other reported numbers move with it -- the associations a report can honestly claim.",
                analysis_type="correlation_matrix",
                variables=(_variable("columns", "Variables za kulinganisha", "outcome", optional=True),),
                reads="Associations between reported measures, never causes.",
            ),
        ),
    ),
    "program_evaluation": Template(
        key="program_evaluation",
        label="Programme evaluation",
        label_swahili="Tathmini ya programu",
        category="Evaluation",
        question="Did the participants change more than a comparison group did?",
        when_to_use="When a programme has a start and an end, and a group that can be compared.",
        steps=(
            TemplateStep(
                key="before_after",
                label="Change within participants",
                description="The same people measured twice: the difference each person made is the difference that remains.",
                analysis_type="paired_t_test",
                variables=(
                    _variable("before", "Kipimo cha mwanzo", "before"),
                    _variable("after", "Kipimo cha mwisho", "after"),
                ),
                reads="The average change, with its uncertainty.",
                parameters={"before": "x", "after": "y"},
            ),
            TemplateStep(
                key="groups",
                label="Participants against the comparison group",
                description="Two independent groups at one point in time.",
                analysis_type="welch_t_test",
                variables=(
                    _variable("outcome", "Kipimo cha mwisho", "outcome"),
                    _variable(
                        "group",
                        "Kikundi (programme / kulinganisha)",
                        "group",
                        levels=2,
                    ),
                ),
                reads="Whether the difference between groups survives a test.",
                parameters={"outcome": "value_column", "group": "group_column"},
            ),
            TemplateStep(
                key="across_sites",
                label="Across sites or cohorts",
                description="More than two groups, where a single comparison would hide the pattern.",
                analysis_type="one_way_anova",
                variables=(
                    _variable("outcome", "Kipimo", "outcome"),
                    _variable(
                        "group",
                        "Tovuti au kundi",
                        "group",
                        min_levels=2,
                    ),
                ),
                reads="Whether at least one site differs from the rest.",
                parameters={"outcome": "value_column", "group": "group_column"},
            ),
        ),
    ),
    "crop_yield": Template(
        key="crop_yield",
        label="Crop yield analysis",
        label_swahili="Uchambuzi wa mazao",
        category="Agriculture",
        question="Which conditions move the yield, and by how much?",
        when_to_use="When a farm, cooperative or extension service wants to know what drives production.",
        steps=(
            TemplateStep(
                key="yield_by_group",
                label="Yield by variety, region or season",
                description="Average yield across the groupings the farm already records.",
                analysis_type="one_way_anova",
                variables=(
                    _variable("outcome", "Mazao (kilo kwa ekari)", "outcome"),
                    _variable(
                        "group",
                        "Aina, mkoa au msimu",
                        "group",
                        min_levels=2,
                    ),
                ),
                reads="Whether a grouping is associated with different yields.",
                parameters={"outcome": "value_column", "group": "group_column"},
            ),
            TemplateStep(
                key="drivers",
                label="What the yield moves with",
                description="Rainfall, inputs and area against yield -- the continuous conditions.",
                analysis_type="correlation_matrix",
                variables=(_variable("columns", "Variables za mazao", "outcome", optional=True),),
                reads="Linear associations among yield and its conditions.",
            ),
            TemplateStep(
                key="what_predicts",
                label="What predicts the yield",
                description="A model over the conditions, with each one's contribution and its uncertainty.",
                analysis_type="linear_regression",
                variables=(
                    _variable("outcome", "Mazao", "outcome"),
                    _variable(
                        "predictors",
                        "Vigezo (mvua, pembejeo, ukubwa)",
                        "predictor",
                        numeric_only=True,
                    ),
                ),
                reads="How much of the variation a set of conditions explains.",
                parameters={"outcome": "target", "predictors": "features"},
            ),
        ),
    ),
    "customer_retention": Template(
        key="customer_retention",
        label="Customer retention",
        label_swahili="Kukaa kwa wateja",
        category="Growth",
        question="Who leaves, and what separates them from those who stay?",
        when_to_use="When a subscriber, member or customer base is churning and the reason is not obvious.",
        steps=(
            TemplateStep(
                key="who_leaves",
                label="Churn rate by segment",
                description="Two proportions across the segments that matter.",
                analysis_type="two_proportion_z_test",
                variables=(
                    _variable("outcome", "Aliondoka (0/1)", "outcome", binary=True),
                    _variable(
                        "group",
                        "Kikundi (mpango, mkoa)",
                        "group",
                        levels=2,
                    ),
                ),
                reads="Whether a segment leaves at a different rate, statistically.",
                parameters={"outcome": "value_column", "group": "group_column"},
            ),
            TemplateStep(
                key="profile_leavers",
                label="Profile of those who left",
                description="What the leavers looked like, in the numbers the business already has.",
                analysis_type="descriptive",
                variables=(_variable("columns", "Variables za kuchambua", "outcome", optional=True),),
                reads="The shape of the leaving group, before a model is trusted.",
            ),
            TemplateStep(
                key="what_predicts_leaving",
                label="What predicts leaving",
                description="A logistic model over the recorded conditions.",
                analysis_type="logistic_regression",
                variables=(
                    _variable("outcome", "Aliondoka (0/1)", "outcome", binary=True),
                    _variable("predictors", "Vigezo", "predictor", numeric_only=True),
                ),
                reads="Which recorded conditions are associated with leaving.",
                parameters={"outcome": "target", "predictors": "features"},
            ),
        ),
    ),
}

#: Categories in the order the templates page shows them.
CATEGORY_ORDER = ("Reporting", "Evaluation", "Agriculture", "Growth")


# --------------------------------------------------------------- resolution


def _fits_levels(column, variable: TemplateVariable) -> bool:
    """Whether a column has the number of distinct levels the step needs.

    A two-group test cannot take a three-level column, and a
    difference test needs a categorical group; proposing one anyway
    would surface a confusing engine error instead of a readable
    choice. The constraint is the analysis's, stated once here rather
    than discovered by the reader as a 400.
    """
    distinct = int(column.dropna().nunique())
    if variable.levels is not None and distinct != variable.levels:
        return False
    if variable.min_levels is not None and distinct < variable.min_levels:
        return False
    if variable.binary and distinct != 2:
        return False
    return True


def suggest(
    frame,
    profile: List[Dict[str, Any]],
    variable: TemplateVariable,
    exclude: Optional[List[str]] = None,
) -> List[str]:
    """The columns that can fill a role, best fit first.

    A role is satisfied by semantic type, not by name: an ``outcome``
    is numeric because the statistics need a scale, a ``group`` is
    categorical because a comparison needs two or more levels. The
    order is deterministic (most complete first) so the same dataset
    always proposes the same columns and the reader's choice is never
    a lottery. ``exclude`` keeps a step from proposing the same column
    twice -- a before/after pair needs two different measurements, and
    a suggestion that fills both slots with one column is not a
    suggestion.
    """
    expected = SEMANTIC_ROLES[variable.role]
    if variable.numeric_only:
        expected = "numeric"
    taken = set(exclude or [])
    by_name = {str(entry["name"]): entry for entry in profile}
    candidates: List[str] = []
    for column in frame.columns:
        name = str(column)
        if name in taken:
            continue
        entry = by_name.get(name)
        semantic = entry.get("semantic_type") if entry else None
        if semantic is None:
            semantic = planning.semantic_type(frame[column])
        if expected != "any" and semantic != expected:
            continue
        if not _fits_levels(frame[column], variable):
            continue
        candidates.append(name)
    if variable.role in {"outcome", "before", "after"}:
        # Stable order: most complete first, so a column that is half
        # empty is not the first proposal for a headline number.
        candidates.sort(
            key=lambda name: (
                -(by_name.get(name, {}).get("non_null_count") or 0),
                name,
            )
        )
    return candidates


def _role_parameters(
    analysis_type: str,
    step: TemplateStep,
    choices: Dict[str, Any],
    frame,
    profile: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Turn the reader's choices into engine parameters for one step."""
    parameters: Dict[str, Any] = {}
    choices = choices or {}
    already_chosen: List[str] = []
    for variable in step.variables:
        engine_key = step.engine_parameter(variable.key)
        if variable.role == "predictor":
            predictions = choices.get(variable.key) or suggest(
                frame, profile, variable, exclude=already_chosen
            )
            if isinstance(predictions, str):
                predictions = [predictions]
            parameters[engine_key] = list(predictions)
            already_chosen.extend(parameters[engine_key])
            continue
        options = suggest(frame, profile, variable, exclude=already_chosen)
        chosen = choices.get(variable.key)
        if chosen is None and not variable.optional:
            chosen = options[0] if options else None
        if chosen is None:
            if variable.optional:
                # An optional slot means the engine's own default is
                # fine -- a descriptive step with no columns profiles
                # every numeric one, which is what the question asks.
                continue
            raise PlanningError(
                f"Step '{step.label}' needs a {variable.role} column; none was chosen and none could be suggested."
            )
        parameters[engine_key] = chosen
        already_chosen.append(chosen)

    if analysis_type == "descriptive":
        # A descriptive step with no explicit columns profiles every
        # numeric column, which is what "the shape of the group" means.
        columns = parameters.pop("columns", None) or parameters.get("value_column")
        if isinstance(columns, str):
            columns = [columns]
        if columns:
            parameters["columns"] = list(columns)
        else:
            parameters["columns"] = suggest(
                frame,
                profile,
                TemplateVariable(key="columns", label="", role="outcome"),
            )
    if analysis_type == "correlation_matrix":
        columns = parameters.pop("columns", None)
        if columns:
            parameters["columns"] = list(columns)
        parameters.setdefault("method", "pearson")
    return parameters


def run_template(
    frame,
    template_key: str,
    choices: Optional[Dict[str, Dict[str, Any]]] = None,
    profile: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run a template's steps against a dataset, in order.

    Returns the step results plus the parameters each step resolved
    to, so the reader can see exactly what ran -- a template is a
    convenience over the ordinary engine, never a black box. A step
    whose variables cannot be resolved raises, because a template
    that silently skips its own question is worse than an error.
    """
    template = TEMPLATES.get(template_key)
    if template is None:
        raise PlanningError(
            f"Unknown template '{template_key}'. Known: " + ", ".join(sorted(TEMPLATES))
        )
    if profile is None:
        from app.services.data_service import profile_columns

        raw = profile_columns(frame)
        profile = [
            {**entry, "semantic_type": planning.semantic_type(frame[entry["name"]])}
            for entry in raw
        ]
        for entry in profile:
            entry.setdefault("non_null_count", entry.get("count", 0))

    steps: List[Dict[str, Any]] = []
    for step in template.steps:
        step_choices = (choices or {}).get(step.key, {})
        parameters = _role_parameters(step.analysis_type, step, step_choices, frame, profile)
        result = stats_engine.run_analysis(frame, step.analysis_type, parameters)
        steps.append(
            {
                "key": step.key,
                "label": step.label,
                "reads": step.reads,
                "analysis_type": step.analysis_type,
                "parameters": parameters,
                "result": result,
                "suggested": {
                    variable.key: suggest(frame, profile, variable)
                    for variable in step.variables
                },
            }
        )

    return {
        "template": template.as_dict(),
        "steps": steps,
        "meta": {
            "rows": int(frame.shape[0]),
            "columns": int(frame.shape[1]),
        },
    }


def catalog() -> List[Dict[str, Any]]:
    """Every template, in the order the page shows them."""
    ordered = sorted(
        TEMPLATES.values(),
        key=lambda template: (
            CATEGORY_ORDER.index(template.category)
            if template.category in CATEGORY_ORDER
            else len(CATEGORY_ORDER),
            template.key,
        ),
    )
    return [template.as_dict() for template in ordered]
