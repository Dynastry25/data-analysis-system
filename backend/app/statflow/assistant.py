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
        "zaidi ya", "compare", "compared", "between", "kati ya", "versus",
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
    "income": ["income", "mapato", "salary", "mshahara", "earnings"],
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


def parse_intent(question: str) -> Dict[str, Any]:
    """Rule-based intent detection: difference/association/prediction/distribution."""
    text = question.lower()
    scores: Dict[str, int] = {}
    hits: Dict[str, List[str]] = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        matched = [keyword for keyword in keywords if keyword in text]
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


def extract_variable_mentions(
    question: str, frame: pd.DataFrame
) -> List[Dict[str, Any]]:
    """Find which dataset variables are mentioned in the question."""
    mentions: List[Dict[str, Any]] = []
    lowered = question.lower()
    for column in frame.columns:
        column_text = str(column)
        tokens = {
            column_text.lower(),
            re.sub(r"[^a-z0-9]+", " ", column_text.lower()).strip(),
        }
        matched = next((token for token in tokens if token and token in lowered), None)
        synonyms = VARIABLE_SYNONYMS.get(column_text.lower().strip(), [])
        matched = matched or next(
            (synonym for synonym in synonyms if synonym in lowered), None
        )
        if matched:
            mentions.append(
                {
                    "column": column_text,
                    "via": "name" if column_text.lower() in lowered else "synonym",
                    "matched": matched,
                }
            )
    return mentions


def _assign_roles(
    mentions: List[Dict[str, Any]], types: Dict[str, str]
) -> Dict[str, Optional[str]]:
    """Choose the outcome and predictor from the mentioned variables."""
    outcome = predictor = None
    for mention in mentions:
        kind = types.get(mention["column"])
        if kind == "numeric" and outcome is None:
            outcome = mention["column"]
        elif kind in {"categorical", "boolean"} and predictor is None:
            predictor = mention["column"]
        elif kind == "numeric" and predictor is None:
            predictor = mention["column"]
    return {"outcome": outcome, "predictor": predictor}


def plan_question(frame: pd.DataFrame, question: str) -> Dict[str, Any]:
    """Intent -> variable mapping -> statistical plan (no calculations here)."""
    parsed = parse_intent(question)
    mentions = extract_variable_mentions(question, frame)
    types = {str(column): planning.semantic_type(frame[column]) for column in frame.columns}

    roles = _assign_roles(mentions, types)
    outcome, predictor = roles["outcome"], roles["predictor"]

    # If the question only pinned one variable, pick the most informative counterpart.
    if outcome is None and predictor is not None:
        numeric_rest = [c for c, k in types.items() if k == "numeric" and c != predictor]
        outcome = numeric_rest[0] if numeric_rest else None
    if predictor is None and outcome is not None:
        grouping = [c for c, k in types.items() if k in {"categorical", "boolean"} and c != outcome]
        numeric_rest = [c for c, k in types.items() if k == "numeric" and c != outcome]
        predictor = (grouping or numeric_rest or [None])[0]
    if outcome is None and predictor is None:
        # No variable mentioned: default to the first numeric variable that is not
        # an identifier column (id-like + unique), then the first numeric column.
        numeric = [c for c, k in types.items() if k == "numeric"]
        non_identifiers = [
            c
            for c in numeric
            if not ("id" in c.lower() and frame[c].nunique(dropna=True) == frame.shape[0])
        ]
        if non_identifiers:
            outcome = non_identifiers[0]
        elif numeric:
            outcome = numeric[0]
        elif frame.shape[1]:
            outcome = str(frame.columns[0])

    plan_parameters: Dict[str, Any] = {
        "intent": parsed["intent"],
        "question": question,
        "run": True,
    }
    if outcome:
        plan_parameters["outcome"] = outcome
    if predictor:
        plan_parameters["predictor"] = predictor

    return {
        "question": question,
        "parsed_intent": parsed,
        "mentions": mentions,
        "variables": {"outcome": outcome, "predictor": predictor},
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


def _p_phrase(result: Dict[str, Any]) -> str:
    test = result.get("test") or {}
    p_value = test.get("p_value")
    if p_value is None:
        return ""
    if p_value < 0.001:
        return "p < 0.001"
    return f"p = {p_value:.4f}"


# --- ASSISTANT_PART_3 ---
def explain(plan: Dict[str, Any], result: Optional[Dict[str, Any]]) -> str:
    """Write the final explanation. Uses only numbers from the engine result."""
    if result is None:
        return (
            "I could not compute a numeric result for this question yet — the "
            "recommendation belongs to the visualisation layer."
        )

    analysis_type = result.get("analysis_type")
    estimate = result.get("estimate") or {}
    test = result.get("test") or {}
    effect = result.get("effect_size") or {}
    warnings = result.get("warnings") or []
    p_text = _p_phrase(result)
    significant = bool(test.get("significant"))
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
                f"Comparing the groups ({grouping}): the medians are "
                f"{_fmt(estimate.get('median_group_a'))} and "
                f"{_fmt(estimate.get('median_group_b'))} ({method}, {p_text})."
            )
        if significant:
            sentences.append(
                f"The difference is statistically significant at alpha = 0.05, with a "
                f"{effect.get('interpretation', '')} effect size "
                f"({effect.get('name')} = {_fmt(effect.get('value'))})."
            )
        else:
            sentences.append(
                "The difference is NOT statistically significant at alpha = 0.05 — with "
                "this sample we cannot conclude the groups differ."
            )
        ci = result.get("confidence_interval") or {}
        if ci.get("lower") is not None:
            sentences.append(
                f"The {int(float(ci.get('level', 0.95)) * 100)}% confidence interval for "
                f"the mean difference is [{_fmt(ci.get('lower'))}, "
                f"{_fmt(ci.get('upper'))}]."
            )
    elif analysis_type in {"pearson", "spearman"}:
        sentences.append(
            f"Between {estimate.get('x')} and {estimate.get('y')}: "
            f"{effect.get('name')} = {_fmt(estimate.get('correlation'))} — a "
            f"{effect.get('strength')} {estimate.get('direction')} association "
            f"({p_text})."
        )
        if not significant and test.get("p_value") is not None:
            sentences.append(
                "Because p > 0.05, the observed association could be consistent with "
                "chance; with this sample we cannot confirm a real relationship."
            )
    elif analysis_type == "one_way_anova":
        sentences.append(
            f"Comparing the means across the {estimate.get('groups')} groups of "
            f"'{estimate.get('grouping_variable')}': F({test.get('df_between')}, "
            f"{test.get('df_within')}) = {_fmt(test.get('statistic'))}, {p_text}. "
            + (
                "There IS a significant difference between the groups."
                if significant
                else "No significant difference between the groups."
            )
        )
        sentences.append(
            f"Effect size eta² = {_fmt(effect.get('value'))} "
            f"({effect.get('interpretation')})."
        )
    elif analysis_type == "kruskal_wallis":
        sentences.append(
            f"Comparing the distributions across groups: H = "
            f"{_fmt(test.get('statistic'))}, {p_text}. "
            + (
                "The groups differ significantly."
                if significant
                else "No significant difference between the groups."
            )
        )

    elif analysis_type == "chi_square":
        sentences.append(
            f"Between {estimate.get('row_variable')} and "
            f"{estimate.get('column_variable')}: chi² = "
            f"{_fmt(test.get('statistic'))}, df = {test.get('df')}, {p_text}. "
            + (
                "The variables are significantly associated."
                if significant
                else "No significant association between the variables."
            )
        )
        if effect.get("value") is not None:
            sentences.append(
                f"Cramér's V = {_fmt(effect.get('value'))} "
                f"({effect.get('interpretation')} effect)."
            )
        if test.get("fisher_exact_p_value") is not None:
            sentences.append(
                f"Fisher's exact p = {_fmt(test.get('fisher_exact_p_value'))} "
                "(reported because some expected counts were small)."
            )
    elif analysis_type == "linear_regression":
        sentences.append(f"Model: {estimate.get('equation')}.")
        sentences.append(
            f"The model explains {_fmt((estimate.get('r_squared') or 0) * 100)}% of the "
            f"variance in {estimate.get('target')} (adjusted R² = "
            f"{_fmt(estimate.get('adjusted_r_squared'))}). Overall F = "
            f"{_fmt(test.get('statistic'))}, {p_text}."
        )
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
            sentences.append(
                f"{name}: mean {_fmt(stats.get('mean'))}, median "
                f"{_fmt(stats.get('median'))}, SD {_fmt(stats.get('sd'))}, range "
                f"[{_fmt(stats.get('min'))} — {_fmt(stats.get('max'))}] (n = "
                f"{stats.get('count')})."
            )
    elif analysis_type == "frequency":
        sentences.append(
            "Distribution of the selected categories is in the table below."
        )
    else:
        sentences.append(
            f"Analysis '{analysis_type}' completed; see the result table below."
        )

    if warnings:
        sentences.append("Note: " + " ".join(warnings))

    return " ".join(sentences)


def ask(frame: pd.DataFrame, question: str) -> Dict[str, Any]:
    """Full assistant flow: plan -> verify (engine) -> explain.

    The assistant never calculates anything: all numbers come from
    ``stats_engine`` (verified result).
    """
    plan = plan_question(frame, question)
    recommendation = planning.recommend(frame, plan["plan_parameters"])
    result = recommendation.get("result")
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
