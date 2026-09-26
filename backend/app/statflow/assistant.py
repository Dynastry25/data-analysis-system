"""MVP-21 (foundation): Statistical assistant.

Contract (per the spec):
  - The assistant **plans and explains**; it never performs statistical
    calculations itself. Every number in the answer comes from the
    ``stats_engine`` (verified result) — the explanation layer only formats it.
  - Flow: question -> intent parser -> statistical planner (planning engine)
    -> variable mapping -> method check -> analysis engine -> verified result
    -> explanation -> answer + tables + charts.

The intent parser and explanation generator are rule-based in this MVP; the
interfaces (``parse_intent``, ``explain``) are isolated so an LLM can be plugged
in later without touching the engines.
"""

import re
from typing import Any, Dict, List, Optional

import pandas as pd

from app.statflow import planning

INTENT_KEYWORDS: Dict[str, List[str]] = {
    "difference": [
        "differ", "different", "difference", "inatofautiana", "tofauti",
        "zaidi ya", "compare", "compared", "versus",
        " vs ", "higher", "lower", "bigger", "smaller",
    ],
    "association": [
        "relationship", "uhusiano", "relate", "correlate", "correlation",
        "associated", "association", "linked", "inategemea", "influenced",
        "influence", "athiri", "connected", "in relation to",
    ],
    "prediction": [
        "predict", "tabiri", "prediction", "forecast", "regress", "regression",
        "estimate", "model", "effect of", "athari ya",
    ],
    "distribution": [
        "distribution", "mgawanyo", "spread", "describe", "summary", "summarise",
        "summarize", "muhtasari", "overview", "profile", "average", "wastani",
        "mean", "median",
    ],
}

VARIABLE_SYNONYMS: Dict[str, List[str]] = {
    "income": ["income", "mapato", "salary", "mshahara", "earnings", "malipo", "pesa"],
    "gender": ["gender", "jinsia", "sex", "wanaume", "wanawake", "male", "female"],
    "age": ["age", "umri"],
    "sales": ["sales", "mauzo", "revenue"],
    "price": ["price", "bei"],
    "region": ["region", "mkoa", "area", "eneo"],
    "score": ["score", "alama", "grade", "points"],
}

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "does", "do", "did", "of",
    "in", "on", "at", "to", "for", "and", "or", "with", "by", "between",
    "what", "which", "how", "this", "that", "there", "their",
    "je", "ni", "ya", "wa", "kwenye", "kati", "na", "kwa", "hili", "ile",
    "kuna", "katika", "juu", "wana", "wenye",
}


def _find_phrase(text: str, phrase: str) -> Optional[re.Match[str]]:
    term = " ".join(str(phrase).lower().split())
    if not term:
        return None
    return re.search(rf"(?<!\w){re.escape(term)}(?:e?s)?(?!\w)", text)


def parse_intent(question: str) -> Dict[str, Any]:
    text = question.lower()
    scores: Dict[str, int] = {}
    hits: Dict[str, List[str]] = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        matched = [keyword for keyword in keywords if _find_phrase(text, keyword)]
        if matched:
            scores[intent] = sum(len(keyword.split()) for keyword in matched)
            hits[intent] = matched

    if not scores:
        return {"intent": None, "confidence": 0.0, "keywords": []}
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    return {
        "intent": best,
        "confidence": round(scores[best] / total, 2) if total else 0.0,
        "keywords": hits[best],
    }


def _column_terms(column: str) -> List[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", column.lower()).strip()
    return list(dict.fromkeys([column.lower(), normalized]))


def extract_variable_mentions(
    question: str, frame: pd.DataFrame
) -> List[Dict[str, Any]]:
    text = question.lower()
    candidates: List[Dict[str, Any]] = []
    for column in frame.columns:
        column_text = str(column)
        matches: List[Dict[str, Any]] = []
        for term in _column_terms(column_text):
            match = _find_phrase(text, term)
            if match:
                matches.append(
                    {
                        "start": match.start(),
                        "end": match.end(),
                        "matched": term,
                        "via": "name",
                    }
                )
        if not matches:
            for synonym in VARIABLE_SYNONYMS.get(column_text.lower().strip(), []):
                match = _find_phrase(text, synonym)
                if match:
                    matches.append(
                        {
                            "start": match.start(),
                            "end": match.end(),
                            "matched": synonym,
                            "via": "synonym",
                        }
                    )
        if matches:
            selected = sorted(matches, key=lambda item: (item["start"], -item["end"]))[
                0
            ]
            candidates.append({"column": column_text, **selected})

    filtered: List[Dict[str, Any]] = []
    for candidate in candidates:
        contained = any(
            other["start"] <= candidate["start"]
            and other["end"] >= candidate["end"]
            and (
                other["end"] - other["start"] > candidate["end"] - candidate["start"]
                or other["column"] == candidate["column"]
            )
            for other in candidates
            if other is not candidate
        )
        if not contained:
            filtered.append(candidate)
    return sorted(filtered, key=lambda item: (item["start"], item["column"]))


def _resolve_explicit(
    frame: pd.DataFrame, reference: Optional[str], label: str
) -> Optional[str]:
    if not reference:
        return None
    resolved = planning.find_variable(frame, reference)
    if resolved is None:
        available = ", ".join(str(column) for column in frame.columns)
        raise planning.PlanningError(
            f"Could not resolve the {label} variable '{reference}'. "
            f"Choose one of: {available}"
        )
    return resolved


def _prediction_roles(
    mentions: List[Dict[str, Any]], question: str
) -> Dict[str, Optional[str]]:
    text = question.lower()
    ordered = sorted(mentions, key=lambda item: item["start"])
    prediction = _find_phrase(text, "predict") or _find_phrase(text, "prediction")
    if prediction:
        separator = re.search(
            r"\b(?:from|using|based on|with)\b", text[prediction.end():]
        )
        if separator:
            split = prediction.end() + separator.start()
            outcome = next(
                (item for item in ordered if prediction.end() <= item["start"] < split),
                None,
            )
            predictor = next(
                (item for item in ordered if item["start"] >= prediction.end() + separator.end()),
                None,
            )
            if outcome and predictor and outcome["column"] != predictor["column"]:
                return {
                    "outcome": outcome["column"],
                    "predictor": predictor["column"],
                }
        before = [item for item in ordered if item["start"] < prediction.start()]
        after = [item for item in ordered if item["start"] > prediction.end()]
        if before and after:
            return {"outcome": after[0]["column"], "predictor": before[-1]["column"]}

    effect = re.search(
        r"\b(?:effect|impact|influence)\s+of\b|\b(?:affects|influences|predicts)\b",
        text,
    )
    if effect:
        if text[effect.start() : effect.start() + 1] and re.match(
            r"\b(?:effect|impact|influence)", effect.group(0)
        ):
            on = re.search(r"\bon\b", text[effect.end() :])
            if on:
                split = effect.end() + on.start()
                predictor = next(
                    (item for item in ordered if effect.end() <= item["start"] < split),
                    None,
                )
                outcome = next(
                    (item for item in ordered if item["start"] > effect.end() + on.end()),
                    None,
                )
                if predictor and outcome and predictor["column"] != outcome["column"]:
                    return {
                        "outcome": outcome["column"],
                        "predictor": predictor["column"],
                    }
        else:
            before = [item for item in ordered if item["start"] < effect.start()]
            after = [item for item in ordered if item["start"] > effect.end()]
            if before and after:
                return {"outcome": after[0]["column"], "predictor": before[-1]["column"]}

    raise planning.PlanningError(
        "The prediction question must identify an outcome and a predictor, for example "
        "'predict income from age'."
    )


def _roles_from_mentions(
    frame: pd.DataFrame,
    question: str,
    mentions: List[Dict[str, Any]],
    types: Dict[str, str],
    intent: Optional[str],
) -> Dict[str, Optional[str]]:
    if len(mentions) > 2:
        raise planning.PlanningError(
            "Name at most two dataset variables in a question, or use the explicit "
            "outcome and predictor selectors."
        )
    if not mentions:
        raise planning.PlanningError(
            "Name at least one dataset variable, or select an outcome in the form."
        )

    if intent == "distribution" or (intent is None and len(mentions) == 1):
        if len(mentions) == 1:
            return {"outcome": mentions[0]["column"], "predictor": None}
    if len(mentions) != 2:
        raise planning.PlanningError(
            "This question needs two dataset variables. Name the outcome and the "
            "predictor explicitly."
        )

    if intent == "prediction":
        return _prediction_roles(mentions, question)

    first, second = mentions
    first_type = types[first["column"]]
    second_type = types[second["column"]]
    numeric = [
        mention["column"]
        for mention in (first, second)
        if types[mention["column"]] == "numeric"
    ]
    categorical = [
        mention["column"]
        for mention in (first, second)
        if types[mention["column"]] in {"categorical", "boolean"}
    ]
    if intent == "difference" and (len(numeric) != 1 or len(categorical) != 1):
        raise planning.PlanningError(
            "A difference question needs one numeric outcome and one categorical group."
        )
    if len(numeric) == 2:
        return {"outcome": second["column"], "predictor": first["column"]}
    if len(categorical) == 2:
        return {"outcome": first["column"], "predictor": second["column"]}
    if len(numeric) == 1 and len(categorical) == 1:
        return {"outcome": numeric[0], "predictor": categorical[0]}
    raise planning.PlanningError(
        "The selected variable types do not support this statistical question."
    )


def plan_question(
    frame: pd.DataFrame,
    question: str,
    outcome: Optional[str] = None,
    predictor: Optional[str] = None,
) -> Dict[str, Any]:
    parsed = parse_intent(question)
    mentions = extract_variable_mentions(question, frame)
    types = {str(column): planning.semantic_type(frame[column]) for column in frame.columns}
    explicit_outcome = _resolve_explicit(frame, outcome, "outcome")
    explicit_predictor = _resolve_explicit(frame, predictor, "predictor")

    if not (explicit_outcome and explicit_predictor):
        mention_groups: Dict[tuple[int, int, str], List[str]] = {}
        for mention in mentions:
            key = (mention["start"], mention["end"], mention["matched"].lower())
            mention_groups.setdefault(key, []).append(mention["column"])
        ambiguous = [columns for columns in mention_groups.values() if len(columns) > 1]
        if ambiguous:
            columns = ", ".join(
                sorted({column for group in ambiguous for column in group})
            )
            raise planning.PlanningError(
                f"The question matches more than one dataset variable ({columns}). "
                "Select the intended variables explicitly."
            )

    if explicit_predictor and not explicit_outcome:
        raise planning.PlanningError(
            "Select the outcome as well as the predictor, or leave both selectors on automatic."
        )
    if explicit_outcome and explicit_predictor and explicit_outcome == explicit_predictor:
        raise planning.PlanningError("Outcome and predictor must be different variables.")
    if explicit_predictor and parsed["intent"] == "distribution":
        raise planning.PlanningError(
            "A distribution question uses one outcome variable and no predictor."
        )
    if explicit_outcome and not explicit_predictor and parsed["intent"] in {
        "difference",
        "association",
        "prediction",
    }:
        raise planning.PlanningError(
            "This question needs a predictor; select one or name two variables."
        )

    if explicit_outcome or explicit_predictor:
        roles = {
            "outcome": explicit_outcome,
            "predictor": explicit_predictor,
        }
    else:
        roles = _roles_from_mentions(
            frame, question, mentions, types, parsed["intent"]
        )

    plan_parameters: Dict[str, Any] = {
        "intent": parsed["intent"],
        "question": question,
        "run": True,
    }
    if roles["outcome"]:
        plan_parameters["outcome"] = roles["outcome"]
    if roles["predictor"]:
        plan_parameters["predictor"] = roles["predictor"]

    return {
        "question": question,
        "parsed_intent": parsed,
        "mentions": mentions,
        "variables": roles,
        "types": types,
        "plan_parameters": plan_parameters,
    }


# ----------------------------------------------------------------- explainer


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.4f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _p_phrase(
    result: Dict[str, Any], p_value: Optional[float] = None
) -> str:
    test = result.get("test") or {}
    if p_value is None:
        p_value = test.get("p_value")
    if p_value is None:
        return ""
    if p_value < 0.001:
        return "p < 0.001"
    return f"p = {p_value:.4f}"


def _alpha(test: Dict[str, Any]) -> float:
    try:
        return float(test.get("alpha", 0.05))
    except (TypeError, ValueError):
        return 0.05


def _decision_sentence(p_value: Optional[float], alpha: float, subject: str) -> str:
    if p_value is None:
        return f"No p-value was available, so no significance decision is made for {subject}."
    if p_value < alpha:
        return (
            f"At alpha = {alpha:g}, the test rejects the null hypothesis for {subject} "
            "in this sample."
        )
    return (
        f"At alpha = {alpha:g}, the test does not reject the null hypothesis for {subject}; "
        "this is not proof that the groups or variables are equivalent."
    )


def _effect_sentence(effect: Dict[str, Any]) -> str:
    if effect.get("value") is None:
        return ""
    name = effect.get("name") or "effect size"
    interpretation = effect.get("interpretation")
    suffix = f" ({interpretation})" if interpretation else ""
    return f"{name} = {_fmt(effect.get('value'))}{suffix}."


def _ci_sentence(result: Dict[str, Any], label: str) -> str:
    interval = result.get("confidence_interval") or {}
    if interval.get("lower") is None or interval.get("upper") is None:
        return ""
    level = int(float(interval.get("level", 0.95)) * 100)
    return (
        f"The {level}% confidence interval for {label} is "
        f"[{_fmt(interval.get('lower'))}, {_fmt(interval.get('upper'))}]."
    )


# --- ASSISTANT_PART_3 ---
def explain(plan: Dict[str, Any], result: Optional[Dict[str, Any]]) -> str:
    if result is None:
        return (
            "I could not compute a numeric result for this question yet — the "
            "recommendation belongs to the visualisation layer."
        )
    if result.get("status") != "success":
        warnings = result.get("warnings") or []
        detail = f" {warnings[0]}" if warnings else ""
        return (
            "The analysis was not completed for the selected data."
            f"{detail} No significance decision is made."
        )

    analysis_type = result.get("analysis_type")
    estimate = result.get("estimate") or {}
    test = result.get("test") or {}
    effect = result.get("effect_size") or {}
    warnings = result.get("warnings") or []
    alpha = _alpha(test)
    p_value = test.get("p_value")
    if analysis_type in {"chi_square", "fisher_exact"} and test.get("fisher_exact_p_value") is not None:
        p_value = test.get("fisher_exact_p_value")
    p_text = _p_phrase(result, p_value)
    method = test.get("method") or analysis_type
    sentences: List[str] = []

    if analysis_type in {"welch_t_test", "mann_whitney"}:
        means = estimate.get("group_means") or {}
        grouping = test.get("grouping") or estimate.get("grouping") or ""
        difference = estimate.get("mean_difference", estimate.get("median_difference"))
        if analysis_type == "welch_t_test" and means:
            labels = list(means.keys())
            sentences.append(
                f"Comparing {labels[0]} and {labels[1]}: the means are "
                f"{_fmt(means[labels[0]])} and {_fmt(means[labels[1]])} — a difference "
                f"of {_fmt(difference)} ({method}, {p_text})."
            )
        else:
            sentences.append(
                f"Comparing the groups ({grouping}) by rank: the observed medians are "
                f"{_fmt(estimate.get('median_group_a'))} and "
                f"{_fmt(estimate.get('median_group_b'))} ({method}, {p_text})."
            )
        sentences.append(_decision_sentence(p_value, alpha, "the group difference"))
        effect_text = _effect_sentence(effect)
        if effect_text:
            sentences.append(f"The reported effect size is {effect_text}")
        ci_text = _ci_sentence(result, "the mean difference")
        if ci_text:
            sentences.append(ci_text)
    elif analysis_type in {"pearson", "spearman"}:
        sentences.append(
            f"Between {estimate.get('x')} and {estimate.get('y')}: "
            f"{effect.get('name')} = {_fmt(estimate.get('correlation'))} — a "
            f"{estimate.get('strength')} {estimate.get('direction')} association "
            f"({p_text})."
        )
        sentences.append(_decision_sentence(p_value, alpha, "the association"))
        ci = result.get("confidence_interval") or {}
        if ci.get("lower") is not None:
            sentences.append(
                f"The {int(float(ci.get('level', 0.95)) * 100)}% confidence interval for "
                f"the correlation is [{_fmt(ci.get('lower'))}, {_fmt(ci.get('upper'))}]."
            )
    elif analysis_type == "one_way_anova":
        sentences.append(
            f"Comparing the means across the {estimate.get('groups')} groups of "
            f"'{estimate.get('grouping_variable')}': F({test.get('df_between')}, "
            f"{test.get('df_within')}) = {_fmt(test.get('statistic'))}, {p_text}."
        )
        sentences.append(_decision_sentence(p_value, alpha, "a difference among group means"))
        sentences.append(_effect_sentence(effect))
    elif analysis_type == "kruskal_wallis":
        sentences.append(
            f"Comparing the distributions across groups: H = "
            f"{_fmt(test.get('statistic'))}, {p_text}."
        )
        sentences.append(_decision_sentence(p_value, alpha, "a difference among group distributions"))
        sentences.append(_effect_sentence(effect))
    elif analysis_type in {"chi_square", "fisher_exact"}:
        prefix = "Fisher's exact test" if analysis_type == "fisher_exact" else "Chi-square test"
        sentences.append(
            f"Between {estimate.get('row_variable')} and "
            f"{estimate.get('column_variable')}: {prefix}, {p_text}."
        )
        if test.get("pearson_p_value") is not None:
            sentences.append(
                f"The Pearson chi-square p-value was {_fmt(test.get('pearson_p_value'))}; "
                "the reported decision uses the exact p-value for this small table."
            )
        sentences.append(_decision_sentence(p_value, alpha, "the association"))
        sentences.append(_effect_sentence(effect))
    elif analysis_type == "linear_regression":
        sentences.append(f"Model: {estimate.get('equation')}.")
        sentences.append(
            f"In-sample R² = {_fmt((estimate.get('r_squared') or 0) * 100)}% "
            f"(adjusted R² = {_fmt(estimate.get('adjusted_r_squared'))}); this describes "
            "fit in the selected observations, not validated predictive performance. "
            f"Overall F = {_fmt(test.get('statistic'))}, {p_text}."
        )
        sentences.append(_decision_sentence(p_value, alpha, "the regression model"))
        coefficients = (result.get("tables") or {}).get("coefficients") or []
        coefficient_text = []
        for row in coefficients:
            if row.get("variable") == "(intercept)":
                continue
            interval = ""
            if row.get("ci_lower") is not None and row.get("ci_upper") is not None:
                interval = (
                    f", 95% CI [{_fmt(row.get('ci_lower'))}, {_fmt(row.get('ci_upper'))}]"
                )
            coefficient_text.append(
                f"{row.get('variable')} estimate = {_fmt(row.get('estimate'))}{interval}"
            )
        if coefficient_text:
            sentences.append("Coefficients: " + "; ".join(coefficient_text) + ".")
        diagnostics = result.get("diagnostics") or {}
        if diagnostics.get("aic") is not None:
            sentences.append(
                f"AIC = {_fmt(diagnostics.get('aic'))}, BIC = "
                f"{_fmt(diagnostics.get('bic'))}, Durbin-Watson = "
                f"{_fmt(diagnostics.get('durbin_watson'))}."
            )
    elif analysis_type == "descriptive":
        variables = estimate.get("variables") or {}
        for name, stats in list(variables.items())[:4]:
            interval = stats.get("confidence_interval_95")
            interval_text = (
                f", 95% mean CI [{_fmt(interval[0])}, {_fmt(interval[1])}]"
                if isinstance(interval, (list, tuple)) and len(interval) == 2
                else ""
            )
            sentences.append(
                f"{name}: mean {_fmt(stats.get('mean'))}, median "
                f"{_fmt(stats.get('median'))}, SD {_fmt(stats.get('sd'))}, range "
                f"[{_fmt(stats.get('min'))} — {_fmt(stats.get('max'))}] (n = "
                f"{stats.get('count')}{interval_text})."
            )
    elif analysis_type == "frequency":
        sentences.append("Distribution of the selected categories is in the table below.")
    else:
        sentences.append(
            f"Analysis '{analysis_type}' completed; see the result table below."
        )

    if analysis_type not in {"descriptive", "frequency"}:
        sentences.append(
            "This conclusion is limited to the selected dataset version and does not "
            "establish a population-wide effect without a suitable study design."
        )
        causal_patterns = (
            r"\bcause\b",
            r"\bcausal\b",
            r"\beffect of\b",
            r"\bimpact of\b",
            r"\binfluence\b",
            r"\bathiri\b",
        )
        question_text = str(plan.get("question", "")).lower()
        if any(re.search(pattern, question_text) for pattern in causal_patterns):
            sentences.append(
                "This observational analysis estimates association; it does not identify "
                "a causal effect."
            )

    if warnings:
        sentences.append("Note: " + " ".join(warnings))

    return " ".join(sentence for sentence in sentences if sentence)


def ask(
    frame: pd.DataFrame,
    question: str,
    outcome: Optional[str] = None,
    predictor: Optional[str] = None,
) -> Dict[str, Any]:
    plan = plan_question(frame, question, outcome, predictor)
    recommendation = planning.recommend(frame, plan["plan_parameters"])
    result = recommendation.get("result")
    method = recommendation["recommendation"]["analysis_type"]
    if result is None and method not in {"descriptive", "frequency"}:
        raise planning.PlanningError(
            f"'{recommendation['recommendation']['label']}' has no numeric engine "
            "implementation yet. Choose a supported method or provide a clearer question."
        )
    explanation = explain(plan, result)

    return {
        "question": question,
        "intent": plan["parsed_intent"],
        "plan": {
            "variables": plan["variables"],
            "mentions": plan["mentions"],
            "method": recommendation["recommendation"]["analysis_type"],
            "method_label": recommendation["recommendation"]["label"],
            "parameters": recommendation["recommendation"]["parameters"],
            "why": recommendation["recommendation"]["why"],
            "assumptions": recommendation["recommendation"]["assumptions"],
            "alternatives": recommendation["recommendation"]["alternatives"],
        },
        "validation": recommendation["validation"],
        "diagnostics": recommendation["diagnostics"],
        "result": result,
        "explanation": explanation,
        "meta": {
            "engine": "statflow v1 (rule-based assistant)",
            "note": "The assistant plans and explains; the statistical engine computes.",
        },
    }
