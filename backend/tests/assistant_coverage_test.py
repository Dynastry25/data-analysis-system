"""The assistant, honestly: identity, coverage, and the LLM fallback (3b).

Three promises are pinned here:

  * **Every published example parses.** ``EXAMPLE_QUESTIONS`` pairs each
    example with the intent the parser actually resolves, and this file
    asserts every pair still holds, so the published coverage can never
    drift from the parser that has to honour it. A question the tables
    miss belongs in ``NOT_COVERED``, not in the examples.
  * **The label is honest.** The answer carries an identity block that
    says what the assistant is -- a rule-based bilingual guide -- and
    what it never does, and with no provider configured the response
    says "rule-based only".
  * **The language provider is optional and cannot break the answer.**
    With no provider it is not used at all; with a provider that fails
    the answer is identical to the rule-based one; with a provider that
    works it only rephrases a question the tables already failed on,
    and the numbers in the answer are still the engine's.

Run it with:  python tests/assistant_coverage_test.py
"""

import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

TEST_ROOT = Path(tempfile.mkdtemp(prefix="assistant_coverage_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["STORAGE_DIR"] = str(TEST_ROOT / "storage")
os.environ["SECRET_KEY"] = "assistant-coverage-secret"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.statflow import assistant, assistant_language  # noqa: E402
from app.statflow.assistant import EXAMPLE_QUESTIONS, parse_intent  # noqa: E402

PASSED = 0


def check(condition: bool, message: str) -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"FAILED: {message}")
    PASSED += 1
    print(f"  [ok] {message}")


def frame() -> pd.DataFrame:
    rng = pd.Series(range(40))
    return pd.DataFrame(
        {
            "income": rng * 3 + 10,
            "age": rng + 18,
            "gender": (["f", "m"] * 20),
            "region": (["Nairobi"] * 10 + ["Mombasa"] * 10 + ["Kisumu"] * 20),
        }
    )


# ------------------------------------------------------------------- tests


def test_every_published_example_parses() -> None:
    print("\n1) Every published example resolves to its stated intent")
    check(bool(EXAMPLE_QUESTIONS), "the example registry is not empty")
    for question, intent in EXAMPLE_QUESTIONS:
        parsed = parse_intent(question)
        check(
            parsed["intent"] == intent,
            f"'{question}' parses as {intent} (got {parsed['intent']})",
        )


def test_the_matcher_handles_conjugations_without_overreaching() -> None:
    print("\n2) Conjugations parse; short roots keep their boundaries")
    # Swahili carries the subject in the prefix and tense in the suffix,
    # so one root covers many forms.
    check(
        parse_intent("Je, mauzo yanatofautiana kati ya mikoa?")["intent"] == "difference",
        "'yanatofautiana' is recognised as a difference question",
    )
    check(
        parse_intent("Are income and age correlated?")["intent"] == "association",
        "'correlated' is recognised as an association question",
    )
    # And a short root must not reach into an unrelated word: "age"
    # inside "manage"/"usage", "price" inside "appraise"d.
    for text in ("manage the sales process", "usage hours are high", "the appraised parcel"):
        check(
            parse_intent(text)["intent"] is None,
            f"'{text}' matches no intent (no short-root false positive)",
        )


def test_coverage_is_published_from_the_tables() -> None:
    print("\n3) Coverage is a specification, derived from the parser")
    coverage = assistant_language.coverage()
    intents = {entry["intent"] for entry in coverage["intents"]}
    check(
        intents == set(assistant.INTENT_KEYWORDS),
        "the coverage lists exactly the intents the parser knows",
    )
    check(
        all(entry["keywords"] for entry in coverage["intents"]),
        "each intent publishes the keywords that trigger it",
    )
    check(
        coverage["variable_words"] == dict(assistant.VARIABLE_SYNONYMS),
        "the variable words are the parser's own table",
    )
    check(
        bool(coverage["not_covered"]),
        "and it says plainly what it does not handle",
    )


def test_the_identity_block_is_honest() -> None:
    print("\n4) The answer says what it is and what it never does")
    answer = assistant.ask(frame(), "Does income differ between male and female?")
    identity = answer["identity"]
    check("rule-based" in identity["label"] or "kanuni" in identity["label"],
          "the label says rule-based, not AI")
    check(bool(identity["never_does"]), "and it lists what it never does")
    check(
        identity["language_provider"] == "rule-based only",
        "with no provider configured, the answer says so",
    )
    check(
        answer["language"]["used"] is False,
        "and no rephrasing was used",
    )
    # The numbers still come from the engine, with the plan visible.
    check(
        answer["result"]["test"]["p_value"] is not None,
        "the result is the engine's, not a guess",
    )
    check(
        answer["plan"]["method"] == "welch_t_test",
        f"the plan chose Welch's t-test (got {answer['plan']['method']})",
    )


def test_a_failing_provider_cannot_break_the_answer() -> None:
    print("\n5) A provider that fails leaves the rule-based answer intact")
    # A question the keyword tables do not know at all -- a scheduling
    # request, not a statistics question.
    unknown = "Unaweza kusaidia kuandaa ratiba ya wiki ijayo?"
    os.environ["ASSISTANT_LLM_BASE_URL"] = "http://127.0.0.1:1/v1"
    os.environ["ASSISTANT_LLM_API_KEY"] = "test-key"
    try:
        check(assistant_language.provider_configured(), "a configured provider is detected")
        normalised = assistant_language.normalise_question(unknown)
        check(
            normalised["used"] is False and normalised["text"] == unknown,
            "a failed rephrase returns the original question, not an error",
        )
        check(
            assistant_language.introduce(unknown, {"method_label": "t-test", "variables": []}) is None,
            "and a failed framing sentence is simply absent",
        )

        # The answer to a question the tables miss is the same honest
        # failure it would have been with no provider at all.
        try:
            assistant.ask(frame(), unknown)
            answered = True
        except Exception:
            answered = False
        check(not answered, "an unparseable question is still refused, not invented")
    finally:
        del os.environ["ASSISTANT_LLM_BASE_URL"]
        del os.environ["ASSISTANT_LLM_API_KEY"]


def test_a_working_provider_only_rephrases_when_needed() -> None:
    print("\n6) A working provider rephrases only a question the tables missed")
    os.environ["ASSISTANT_LLM_BASE_URL"] = "http://provider.test/v1"
    os.environ["ASSISTANT_LLM_API_KEY"] = "test-key"
    os.environ["ASSISTANT_LLM_MODEL"] = "test-model"
    original_complete = assistant_language.complete

    def fake_complete(system: str, user: str, **kwargs) -> str:
        # A rephrase into words the keyword tables know.
        if "restate" in system.lower() or "restates" in system.lower():
            return "Does income differ between male and female?"
        return "I understood this as a difference question."

    assistant_language.complete = fake_complete
    try:
        # A question the tables do not know, phrased in a way the
        # provider can rescue into a known one.
        unknown = "Kagua uwiano wa mapato kulingana na jinsia kwa mujibu"
        normalised = assistant_language.normalise_question(unknown)
        check(normalised["used"], "the rephrase is used for an unknown question")
        check(
            parse_intent(normalised["text"])["intent"] == "difference",
            "and it turns a miss into a difference question",
        )

        # With the rules confident, the provider is not consulted at all:
        # a rephrase must never override an answer the tables gave.
        answer = assistant.ask(frame(), "Does income differ between male and female?")
        check(
            answer["language"]["used"] is False,
            "a question the tables match is never sent to the provider",
        )
        check(
            isinstance(answer["introduction"], str) or answer["introduction"] is None,
            "the framing sentence is its own field, separate from the answer",
        )
        without_provider = assistant.ask(frame(), "Does income differ between male and female?")
        check(
            answer["explanation"] == without_provider["explanation"],
            "the engine's explanation is identical with and without a provider",
        )

        # And when the provider IS used, the numbers are still the
        # engine's: same result as the same question in English.
        answered = assistant.ask(frame(), unknown)
        check(
            answered["plan"]["method"] == "welch_t_test",
            "the rescued plan is the same method the English question gives",
        )
        check(
            answered["result"]["test"]["p_value"]
            == answer["result"]["test"]["p_value"],
            "and the p-value is the engine's, not the provider's",
        )
        check(
            answered["language"]["used"] is True,
            "the answer records that a rephrase was used",
        )
    finally:
        assistant_language.complete = original_complete
        for name in ("ASSISTANT_LLM_BASE_URL", "ASSISTANT_LLM_API_KEY", "ASSISTANT_LLM_MODEL"):
            os.environ.pop(name, None)


def main() -> int:
    print("ASSISTANT COVERAGE AND IDENTITY TESTS")
    test_every_published_example_parses()
    test_the_matcher_handles_conjugations_without_overreaching()
    test_coverage_is_published_from_the_tables()
    test_the_identity_block_is_honest()
    test_a_failing_provider_cannot_break_the_answer()
    test_a_working_provider_only_rephrases_when_needed()
    print(f"\nALL ASSISTANT COVERAGE TESTS PASSED ({PASSED} checks)")
    return 0


def test_assistant_coverage() -> None:
    """pytest entry point: same run as ``python tests/assistant_coverage_test.py``."""
    main()


if __name__ == "__main__":
    raise SystemExit(main())
