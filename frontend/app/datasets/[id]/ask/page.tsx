"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { SelectInput, TextInput } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { StandardResultView, fmt, pFmt } from "@/components/StandardResultView";
import { useToast } from "@/components/Toast";
import {
  apiErrorMessage,
  AssistantAnswer,
  PlanningVariable,
  StandardResult,
  statflowApi,
} from "@/lib/api";

type Turn = {
  question: string;
  outcome?: string;
  predictor?: string;
  answer: AssistantAnswer | null;
  error?: string;
};

export default function AskPage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params?.id);
  const { showToast } = useToast();

  const [examples, setExamples] = useState<string[]>([]);
  const [profileVariables, setProfileVariables] = useState<PlanningVariable[]>([]);
  const [profileVersion, setProfileVersion] = useState<number | undefined>();
  const [profileError, setProfileError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [outcome, setOutcome] = useState("");
  const [predictor, setPredictor] = useState("");
  const [asking, setAsking] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const questionError =
    attempted && question.trim().length < 3
      ? "Andika swali la angalau herufi 3."
      : undefined;
  const predictorError =
    attempted && predictor && !outcome
      ? "Chagua outcome kwanza, au weka predictor kuwa Automatic."
      : undefined;

  const loadExamples = useCallback(async () => {
    try {
      const response = await statflowApi.assistantExamples();
      setExamples(response.examples);
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }, [showToast]);

  const loadProfile = useCallback(async () => {
    if (!Number.isFinite(datasetId)) return;
    setProfileError(null);
    try {
      const response = await statflowApi.planningProfile(datasetId);
      setProfileVariables(response.variables);
      setProfileVersion(response.meta.dataset_version);
    } catch (caught) {
      const message = apiErrorMessage(caught);
      setProfileError(message);
      showToast(message, "danger");
    }
  }, [datasetId, showToast]);

  useEffect(() => {
    loadExamples();
  }, [loadExamples]);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  async function ask(text: string) {
    const trimmed = text.trim();
    setAttempted(true);
    if (trimmed.length < 3 || asking) return;
    if (predictor && !outcome) {
      showToast("Chagua outcome au weka predictor kuwa Automatic.", "warning");
      return;
    }
    if (outcome && predictor && outcome === predictor) {
      showToast("Outcome na predictor lazima viwe tofauti.", "warning");
      return;
    }
    setAsking(true);
    setQuestion("");
    setTurns((previous) => [
      ...previous,
      {
        question: trimmed,
        outcome: outcome || undefined,
        predictor: predictor || undefined,
        answer: null,
      },
    ]);
    try {
      const answer = await statflowApi.ask({
        dataset_id: datasetId,
        dataset_version: profileVersion,
        question: trimmed,
        outcome: outcome || undefined,
        predictor: predictor || undefined,
      });
      setTurns((previous) =>
        previous.map((turn, index) =>
          index === previous.length - 1 ? { ...turn, answer } : turn
        )
      );
    } catch (caught) {
      const message = apiErrorMessage(caught);
      setTurns((previous) =>
        previous.map((turn, index) =>
          index === previous.length - 1 ? { ...turn, error: message } : turn
        )
      );
      showToast(message, "danger");
    } finally {
      setAsking(false);
    }
  }

  return (
    <AppShell
      eyebrow="Msaidizi wa takwimu"
      title="AI Statistical Copilot"
      description="Uliza swali kwa lugha ya kawaida — engine hupanga uchambuzi na kujibu kwa takwimu zilizothibitishwa."
      actions={
        <Link href={`/datasets/${datasetId}`}>
          <Button variant="secondary">Rudi kwenye dataset</Button>
        </Link>
      }
    >
      <Card
        title="Uliza swali"
        icon="message-circle"
        description="Mfano: 'Does income differ between male and female?' au 'Je, kuna uhusiano kati ya umri na mapato?'"
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            ask(question);
          }}
          className="flex flex-col gap-2 sm:flex-row sm:items-start"
        >
          <TextInput
            label="Swali lako"
            value={question}
            error={questionError}
            placeholder="Andika swali lako hapa..."
            inputClassName="flex-1"
            onChange={(event) => setQuestion(event.target.value)}
          />
          <Button type="submit" className="sm:mt-[26px]" loading={asking} icon="message-circle">
            Uliza
          </Button>
        </form>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <SelectInput
            label="Outcome"
            optionalLabel="hiari"
            value={outcome}
            onChange={(event) => {
              const nextOutcome = event.target.value;
              setOutcome(nextOutcome);
              if (nextOutcome && nextOutcome === predictor) setPredictor("");
            }}
            options={[
              { value: "", label: "Automatic — infer from question" },
              ...profileVariables.map((variable) => ({
                value: variable.name,
                label: `${variable.name} (${variable.semantic_type})`,
              })),
            ]}
          />
          <SelectInput
            label="Predictor / grouping variable"
            optionalLabel="hiari"
            value={predictor}
            error={predictorError}
            onChange={(event) => setPredictor(event.target.value)}
            options={[
              { value: "", label: "Automatic — infer from question" },
              ...profileVariables
                .filter((variable) => !outcome || variable.name !== outcome)
                .map((variable) => ({
                  value: variable.name,
                  label: `${variable.name} (${variable.semantic_type})`,
                })),
            ]}
          />
        </div>
        {profileVersion != null && !profileError && (
          <p className="mt-2 text-caption text-ink-muted">
            Orodha ya variables imeambwa kutoka toleo la data{" "}
            <span className="font-mono font-medium text-ink">v{profileVersion}</span>.
          </p>
        )}
        {profileError && (
          <p
            role="alert"
            className="mt-2 flex items-start gap-1.5 rounded-md border border-danger/30 bg-danger-bg px-3 py-2 text-caption text-danger-700"
          >
            <Icon name="alert-circle" size={14} className="mt-0.5 shrink-0" />
            <span>
              Orodha ya variables haijapakiwa. Maswali bado yatatumia toleo la data la
              sasa — pakia ukurasa upya kabla ya kutumia kichaguzi.
            </span>
          </p>
        )}
        {examples.length > 0 && (
          <div className="mt-4">
            <p className="mb-2 text-overline uppercase tracking-wide text-ink-muted">
              Mifano ya maswali
            </p>
            <div className="flex flex-wrap gap-2">
              {examples.map((example) => (
                <button
                  key={example}
                  type="button"
                  className="rounded-pill border border-surface-border bg-surface-sunken px-2.5 py-1 text-caption text-ink-secondary transition-colors duration-150 ease-standard hover:border-primary-300 hover:bg-primary-50 hover:text-primary-700"
                  onClick={() => {
                    setQuestion(example);
                  }}
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}
      </Card>

      {turns.length === 0 ? (
        <section className="flex flex-col items-center px-6 py-10 text-center">
          {/* The prototype's welcome orb and explanation. It sits above the
              question card rather than replacing it, because the variable
              selectors below are the part that makes the answer correct. */}
          <span className="grid h-[52px] w-[52px] place-items-center rounded-[15px] bg-surface-sunken text-[#BBAAFF] shadow-[0_10px_30px_rgba(25,20,36,0.18)]">
            <Icon name="sparkles" size={24} />
          </span>
          <h2 className="mt-3.5 font-display text-h2 font-bold tracking-[-0.02em] text-ink">
            Ungependa kuelewa nini?
          </h2>
          <p className="mt-1.5 max-w-[500px] text-body leading-relaxed text-ink-muted">
            Ninaleta swali lako kwenye variables, kuthibitisha method ya takwimu,
            kuendesha engine, na kueleza matokeo yaliyothibitishwa.
          </p>
        </section>
      ) : (
        turns.map((turn, index) => (
          <Card
            key={`${index}-${turn.question}`}
            title={turn.question}
            icon="message-circle"
            actions={
              <span className="text-caption text-ink-muted">Swali {index + 1}</span>
            }
          >
            {(turn.outcome || turn.predictor) && (
              <p className="mb-3 flex flex-wrap items-center gap-1.5 text-caption text-ink-muted">
                Variables zilizochaguliwa:
                {[turn.outcome, turn.predictor]
                  .filter(Boolean)
                  .map((name) => (
                    <span
                      key={name}
                      className="rounded border border-surface-border bg-surface-sunken px-1.5 py-0.5 font-medium text-ink"
                    >
                      {name}
                    </span>
                  ))}
              </p>
            )}
            {turn.error ? (
              <p
                role="alert"
                className="flex items-start gap-1.5 rounded-md border border-danger/30 bg-danger-bg px-3 py-2 text-body text-danger-700"
              >
                <Icon name="alert-circle" size={15} className="mt-0.5 shrink-0" />
                <span>{turn.error}</span>
              </p>
            ) : turn.answer == null ? (
              <div
                role="status"
                aria-live="polite"
                className="flex items-center gap-2.5 text-body text-ink-secondary"
              >
                <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-primary-600 border-t-transparent" />
                <span>
                  Inachambua — engine ya takwimu inafanya kazi, AI inatafsiri baadaye…
                </span>
              </div>
            ) : (
              <AnswerView answer={turn.answer} />
            )}
          </Card>
        ))
      )}
      <div ref={bottomRef} />
    </AppShell>
  );
}

/** Layer 5 — practical meaning of a run in plain language. */
function interpretation(result: StandardResult): string {
  const sentences: string[] = [];
  const test = result.test;
  const effect = result.effect_size;
  if (test?.significant === true) {
    sentences.push(
      "Tofauti/uhusiano huonekana ni wa kweli katika data hii, si bahati tu."
    );
  } else if (test?.significant === false) {
    sentences.push(
      "Hatuna ushahidi wa kutosha kusema tofauti/uhusiano upo — inawezekana ni bahati au sample ndogo."
    );
  }
  if (effect?.value !== null && effect?.value !== undefined) {
    sentences.push(
      `Ukubwa wa athari (${effect.name ?? "effect size"}) ni ${fmt(effect.value)}${effect.interpretation ? ` — ${effect.interpretation}` : ""}.`
    );
  }
  if (test?.statistic !== null && test?.statistic !== undefined) {
    sentences.push(`Takwimu ya mtihani = ${fmt(test.statistic)} (${test.method ?? "method"}).`);
  }
  if (result.estimate?.r_squared !== undefined) {
    sentences.push(`R² = ${fmt(result.estimate.r_squared)} ya tofauti inaelezewa na model.`);
  }
  if (sentences.length === 0) {
    sentences.push("Hakuna tafsiri rahisi inayoweza kutolewa kwa matokeo haya.");
  }
  return sentences.join(" ");
}

function AnswerView({ answer }: { answer: AssistantAnswer }) {
  const validationTone =
    answer.validation.status === "ok"
      ? "success"
      : answer.validation.status === "warning"
        ? "warning"
        : "danger";

  const variables = Object.values(answer.plan.variables).filter(
    (value): value is string => Boolean(value)
  );

  const result = answer.result;
  const effect = result?.effect_size?.value ?? null;
  const pValue = result?.test?.p_value ?? null;
  const ci = result?.confidence_interval;
  const significant =
    result?.test?.significant === true
      ? "ndio"
      : result?.test?.significant === false
        ? "hapana"
        : "—";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="primary" icon="sparkles">
          ASK STATFLOW
        </Badge>
        {answer.intent.intent && (
          <Badge tone="neutral">intent: {answer.intent.intent}</Badge>
        )}
        <Badge tone="neutral">method: {answer.plan.method_label}</Badge>
        <Badge tone={validationTone as "success" | "warning" | "danger"}>
          validation: {answer.validation.status}
        </Badge>
        {answer.dataset_version != null && (
          <Badge tone="neutral">data v{answer.dataset_version}</Badge>
        )}
      </div>

      {variables.length > 0 && (
        <p className="text-caption text-ink-muted">Variables: {variables.join(", ")}</p>
      )}

      <div className="rounded-lg border border-surface-border border-l-4 border-l-primary-400 bg-surface-panel p-4">
        <p className="text-overline uppercase tracking-wide text-ink-muted">Jibu la copilot</p>
        <p className="mt-1 text-body-lg font-medium text-ink">{answer.explanation}</p>

        {result && (
          <dl className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
            {effect !== null && (
              <div className="rounded-md bg-surface-sunken px-3 py-2.5">
                <dt className="text-overline uppercase tracking-wide text-ink-muted">
                  Effect size
                </dt>
                <dd className="tabular mt-0.5 font-mono text-h3 text-ink">
                  {fmt(effect)}
                </dd>
              </div>
            )}
            {pValue !== null && (
              <div className="rounded-md bg-surface-sunken px-3 py-2.5">
                <dt className="text-overline uppercase tracking-wide text-ink-muted">
                  p-value
                </dt>
                <dd className="tabular mt-0.5 font-mono text-h3 text-ink">
                  {pFmt(pValue)}
                </dd>
              </div>
            )}
            {ci && (ci.lower !== null || ci.upper !== null) && (
              <div className="rounded-md bg-surface-sunken px-3 py-2.5">
                <dt className="text-overline uppercase tracking-wide text-ink-muted">
                  CI {ci.level != null ? `${ci.level}%` : ""}
                </dt>
                <dd className="tabular mt-0.5 font-mono text-h3 text-ink">
                  {fmt(ci.lower)} … {fmt(ci.upper)}
                </dd>
              </div>
            )}
            <div className="rounded-md bg-surface-sunken px-3 py-2.5">
              <dt className="text-overline uppercase tracking-wide text-ink-muted">
                Significant
              </dt>
              <dd className="tabular mt-0.5 font-mono text-h3 text-ink">{significant}</dd>
            </div>
          </dl>
        )}
      </div>

      {result && (
        <section className="rounded-lg border border-surface-border bg-surface-panel p-4">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary-50 text-primary-600">
              <Icon name="calculator" size={16} />
            </span>
            <h3 className="text-h3 text-ink">Maana yake (interpretation)</h3>
          </div>
          <p className="text-body text-ink-secondary">
            {interpretation(result)}
          </p>
        </section>
      )}

      <details className="group rounded-lg border border-surface-border bg-surface-panel">
        <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 px-4 py-3">
          <Icon
            name="chevron-right"
            size={14}
            className="text-ink-muted transition-transform duration-150 group-open:rotate-90"
          />
          <span className="text-body font-medium text-ink">Onyesha hesabu kamili</span>
          <span className="text-caption text-ink-muted">
            Show Calculation — jedwali na assumptions za engine
          </span>
        </summary>
        <div className="details-content px-4 pb-4">
          {result ? (
            <StandardResultView result={result} question={answer.question} />
          ) : (
            <p className="text-body text-ink-muted">
              Engine haikui hesabu kwa swali hili — hakuna takwimu inayoweza kuonyeshwa.
            </p>
          )}
        </div>
      </details>

      {answer.validation.issues.length > 0 && (
        <div className="rounded-md border border-warning/40 bg-warning-bg p-3">
          <p className="mb-1 flex items-center gap-1.5 text-caption font-semibold text-warning-700">
            <Icon name="alert-triangle" size={14} />
            Tahadhari za kuthibitisha
          </p>
          <ul className="list-disc space-y-0.5 pl-5 text-caption text-warning-700">
            {answer.validation.issues.map((issue, index) => (
              <li key={index}>{issue.message}</li>
            ))}
          </ul>
        </div>
      )}

      <section className="rounded-lg border border-danger/30 border-l-4 border-l-danger bg-danger-bg p-4">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-white text-danger shadow-card">
            <Icon name="shield" size={16} />
          </span>
          <h3 className="text-h3 text-ink">LIMITATIONS — mipaka ya copilot</h3>
        </div>
        <ul className="list-disc space-y-1 pl-5 text-caption text-danger-700">
          <li>
            Copilot huchagua na kutafsiri; hajabadilishi takwimu zilizokokotwa na engine.
          </li>
          <li>
            Uchambuzi hufanyika kwenye toleo moja la data (
            {answer.dataset_version != null ? `v${answer.dataset_version}` : "sasa"}); hubadilika
            ukibadilisha toleo.
          </li>
          <li>
            {answer.intent.confidence < 0.6
              ? `Uhakika wa nia ni mdogo (${Math.round(answer.intent.confidence * 100)}%). Eleza outcome na predictor kwa usahihi.`
              : "Hesabu za CI na effect size haziwezi kusema juu ya tafsiri za biashara; thibitisha na mtaalamu."}
          </li>
          {answer.intent.keywords.length > 0 && (
            <li>Maneno yaliyotambuliwa: {answer.intent.keywords.join(", ")}.</li>
          )}
        </ul>
      </section>

      {answer.plan.alternatives.length > 0 && (
        <details className="group">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 text-caption font-semibold text-ink-secondary hover:text-primary-700">
            <Icon
              name="chevron-right"
              size={14}
              className="transition-transform duration-150 group-open:rotate-90"
            />
            Mbinu mbadala ({answer.plan.alternatives.length})
          </summary>
          <ul className="details-content mt-2 list-disc space-y-1 pl-5 text-caption text-ink-secondary">
            {answer.plan.alternatives.map((alternative) => (
              <li key={alternative.analysis_type}>
                <strong>{alternative.label}</strong> — {alternative.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

