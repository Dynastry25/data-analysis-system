"""The assistant's language layer, and its honest label (plan Phase 3b).

Three things live here, and the reasons for each are the point:

**3b.1 — the label.** The assistant is deterministic: keyword tables, a
planner, and the statistics engine. It cannot hallucinate a p-value
because it never writes one; it also cannot answer a question whose
shape its keyword tables miss. Calling that "AI" would promise the
second property while giving up the first, and a demo question it
fumbles would cost more trust than the word ever bought. So the label
is what it is: a bilingual guide that reads your question, picks the
method, and hands the numbers to the engine. ``identity`` below is the
exact sentence the UI and the API both show.

**3b.2 — an optional LLM, behind interfaces, never in the numbers.**
The one thing the rule-based assistant genuinely loses on is coverage:
a reader who phrases a question in words the keyword tables miss gets
"could not understand" from a model that would have understood the
idea. A language model plugged in *behind* ``parse_intent`` closes that
gap, and only that gap -- it rephrases the reader's question into words
the tables know, and it may write one framing sentence. It never sees a
statistic and never writes one; every number in every answer is still
computed by ``stats_engine`` and checked by the assumption gate. With
no provider configured (the default) the assistant is exactly what it
was before: rule-based, offline, and deterministic. Any provider
failure falls back to the rule-based path silently, because a guide
that stops working when a network call fails is worse than no guide.

**3b.3 — published coverage.** A limitation stated as a specification
is a feature: ``coverage`` returns the question shapes the keyword
tables handle, the variable words they map, and the shapes they do
not, so the reader knows what to ask before asking.
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib import error, request

from app.statflow.assistant import INTENT_KEYWORDS, VARIABLE_SYNONYMS

logger = logging.getLogger(__name__)

#: The exact identity sentence, shown in the UI and returned by the API.
IDENTITY = (
    "Msaidizi huyu ni muongozo wa lugha mbili, wa kanuni zilizowekwa "
    "(rule-based): husoma swali lako, huchagua mbinu ya takwimu, na kumpa "
    "engine namba za kujibu. Hakuna AI inayotoa majibu yenyewe -- kila "
    "namba inatoka kwa engine ya takwimu na hupitiwa kwa ukaguzi wa "
    "deterministic. Swali ambalo haeleweki halijibiwi kwa kubuni."
)

#: What the assistant never does, in the answer payload.
NEVER_DOES = [
    "Hakufanyi mahesabu yenyewe -- namba zote hutoka kwa stats_engine.",
    "Hakubuni jibu swali ambalo halielewi -- linasema haielewi.",
    "Haitumii AI (isipokuwa mtoa huduma alisetiwa kwa makusudi), na haina "
    "uwezo wa kubadilisha matokeo ya takwimu.",
]

#: The intents, in the words a reader would use to ask for them.
INTENT_LABELS = {
    "difference": "Tofauti kati ya makundi (difference between groups)",
    "association": "Uhusiano kati ya vigezo viwili (association)",
    "prediction": "Utabiri / regression (prediction)",
    "distribution": "Mgawanyo / muhtasari (distribution / summary)",
}

#: Question shapes the keyword tables cannot handle, stated plainly so
#: the reader knows what to ask before asking.
NOT_COVERED = [
    "Maswali yanayohitaji data ya nje (data outside this dataset).",
    "Maswali yenye pande nyingi za wakati au mfululizo (time series).",
    "Maamuzi ya kibiashara yanayohitaji muktadha (business decisions).",
    "Mistari mirefu ya maelezo badala ya swali moja (long prose).",
]


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def provider_configured() -> bool:
    """True when an LLM provider is configured at all.

    Absent configuration is the default and means the assistant is
    purely rule-based -- the honest default, because the rule-based
    path is the one that cannot be wrong about a number.
    """
    return bool(_env("ASSISTANT_LLM_BASE_URL") and _env("ASSISTANT_LLM_API_KEY"))


class LanguageError(RuntimeError):
    """A language-model call failed or returned something unusable."""


def _post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: float) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        req.add_header(key, value)
    with request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - operator-configured URL
        return json.loads(response.read().decode("utf-8"))


def complete(system: str, user: str, *, timeout: float = 20.0, max_tokens: int = 300) -> str:
    """Call the configured provider and return its text.

    Any failure -- no provider, a network error, a non-200, a shape
    that is not what was asked for -- raises ``LanguageError`` so the
    caller falls back to the rule-based path. The provider is a plain
    OpenAI-compatible chat endpoint configured by environment
    variables, so no SDK dependency is added for a feature that is off
    by default.
    """
    if not provider_configured():
        raise LanguageError("no language provider configured")
    base_url = _env("ASSISTANT_LLM_BASE_URL").rstrip("/")
    model = _env("ASSISTANT_LLM_MODEL") or "gpt-4o-mini"
    try:
        payload = _post_json(
            f"{base_url}/chat/completions",
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
                "max_tokens": max_tokens,
            },
            {"Authorization": f"Bearer {_env('ASSISTANT_LLM_API_KEY')}"},
            timeout,
        )
        text = payload["choices"][0]["message"]["content"]
    except LanguageError:
        raise
    except (error.URLError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise LanguageError(f"language provider returned something unusable: {exc}") from exc
    text = str(text).strip()
    if not text:
        raise LanguageError("language provider returned no text")
    return text


def _timed_call(function, *args, **kwargs):
    """Run a provider call with a wall-clock budget and report why it failed."""
    started = time.perf_counter()
    try:
        return function(*args, **kwargs)
    except LanguageError as exc:
        logger.info("assistant language layer fell back to rules: %s", exc)
        raise
    finally:
        elapsed = time.perf_counter() - started
        if elapsed > 5.0:  # pragma: no cover - operator-side latency
            logger.warning("language provider took %.1fs", elapsed)


def normalise_question(question: str) -> Dict[str, Any]:
    """Rephrase a question into English words the keyword tables know.

    Returns ``{"used": bool, "text": str, "reason": str}``. ``used`` is
    True only when a provider was configured AND answered with
    something usable; everything else returns the original question
    with a reason, and the rule-based parser runs on the original
    regardless. The parser also always sees the original text, so a
    rephrase can add coverage, never remove it -- the LLM's output is
    advisory, and a wrong rephrase is simply a second opinion the
    keyword tables may ignore.
    """
    if not provider_configured():
        return {"used": False, "text": question, "reason": "no provider configured"}
    try:
        text = _timed_call(
            complete,
            "You restate a reader's statistics question in plain English, "
            "keeping the two variables they mention and the kind of "
            "comparison they want. Output one sentence. No preamble, no "
            "statistics, no advice.",
            f"Question: {question}",
            max_tokens=120,
        )
    except LanguageError:
        return {"used": False, "text": question, "reason": "provider failed"}
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) > 600:  # pragma: no cover - defensive
        return {"used": False, "text": question, "reason": "response too long"}
    return {"used": True, "text": cleaned, "reason": "provider rephrased the question"}


def introduce(question: str, plan: Dict[str, Any]) -> Optional[str]:
    """One framing sentence, optional and never a number.

    The deterministic explanation that follows is generated from the
    verified result; this line only says back what the assistant
    understood, in the reader's own words, before the numbers start.
    Any failure returns None and the answer is exactly what it would
    have been without the provider -- a missing greeting is a smaller
    cost than a wrong sentence.
    """
    if not provider_configured():
        return None
    try:
        text = _timed_call(
            complete,
            "Write one short sentence (max 25 words) confirming which "
            "statistical question you understood, in the same language as "
            "the reader. Do not give results, advice, or numbers.",
            "Question: {question}\nUnderstood as: {method} of {variables}".format(
                question=question,
                method=plan.get("method_label", ""),
                variables=", ".join(plan.get("variables") or []),
            ),
            max_tokens=80,
        )
    except LanguageError:
        return None
    sentence = re.sub(r"\s+", " ", text).strip()
    return sentence[:400] or None


def coverage() -> Dict[str, Any]:
    """The assistant's coverage as a specification (plan 3b.3).

    Every entry is derived from the tables the parser actually runs on
    -- the intent keywords and the variable synonyms in ``assistant`` --
    so this list cannot drift from behaviour: change the tables and the
    published coverage changes with them. The `not_covered` block is
    the honest half, and it is why the LLM hook above exists at all.
    """
    return {
        "identity": IDENTITY,
        "never_does": NEVER_DOES,
        "language_provider": "configured" if provider_configured() else "rule-based only",
        "intents": [
            {
                "intent": intent,
                "label": INTENT_LABELS.get(intent, intent),
                "keywords": keywords,
                "examples": _examples_for(intent),
            }
            for intent, keywords in INTENT_KEYWORDS.items()
        ],
        "variable_words": VARIABLE_SYNONYMS,
        "not_covered": NOT_COVERED,
        "how_it_answers": [
            "Swali linapitiwa na parser ya kanuni (rule-based intent parser).",
            "Mipango ya mbinu hutoka kwa planning engine, na variables zinaunganishwa na columns.",
            "Namba zote zinahesabiwa na stats_engine na kupitiwa kwa ukaguzi wa assumptions.",
            "Maelezo yanatengenezwa kutoka kwenye matokeo yaliyothibitishwa.",
        ],
    }


def _examples_for(intent: str) -> List[str]:
    from app.statflow.assistant import EXAMPLE_QUESTIONS

    return [
        example
        for example, example_intent in EXAMPLE_QUESTIONS
        if example_intent == intent
    ]
