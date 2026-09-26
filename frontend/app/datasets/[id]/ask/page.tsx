"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { SelectInput, TextInput } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { StandardResultView } from "@/components/StandardResultView";
import { useToast } from "@/components/Toast";
import {
  apiErrorMessage,
  AssistantAnswer,
  PlanningVariable,
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
      title="Msaidizi wa takwimu"
      description="Uliza swali kwa lugha ya kawaida — msaidizi hupanga uchambuzi, engine hujibu kwa takwimu zilizothibitishwa."
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
          <Button type="submit" className="sm:mt-[26px]" loading={asking}>
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
            Variable list is from dataset version {profileVersion}.
          </p>
        )}
        {profileError && (
          <p
            role="alert"
            className="mt-2 flex items-start gap-1.5 text-caption text-danger"
          >
            <Icon name="alert-circle" size={14} className="mt-0.5 shrink-0" />
            Variable list could not be loaded. Questions will use the dataset&apos;s current
            version; retry the page before relying on selectors.
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
        <Card>
          <EmptyState
            title="Hakuna maswali bado"
            description="Bonyeza moja ya mifano au andika swali lako la takwimu."
          />
        </Card>
      ) : (
        turns.map((turn, index) => (
          <Card
            key={`${index}-${turn.question}`}
            title={`Swali ${index + 1}: ${turn.question}`}
          >
            {(turn.outcome || turn.predictor) && (
              <p className="mb-3 text-caption text-neutral-500">
                Selected variables: {[turn.outcome, turn.predictor].filter(Boolean).join(", ")}
              </p>
            )}
            {turn.error ? (
              <p className="text-body text-danger">{turn.error}</p>
            ) : turn.answer == null ? (
              <p className="text-body text-neutral-600">Inachambua...</p>
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

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        {answer.intent.intent && (
          <Badge tone="primary">intent: {answer.intent.intent}</Badge>
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

      <section className="rounded-lg border border-surface-border bg-surface-sunken p-4">
        <div className="mb-3 flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-white text-success shadow-card">
            <Icon name="shield" size={16} />
          </span>
          <h3 className="text-h3 text-ink">Computed by Statistical Engine</h3>
        </div>
        {answer.result ? (
          <StandardResultView result={answer.result} />
        ) : (
          <p className="text-body text-ink-muted">
            Engine haikui hesabu kwa swali hili. Hakuna takwimu inayotokana na msaidizi.
          </p>
        )}
      </section>

      <section className="rounded-lg border border-primary-200 bg-primary-50/60 p-4">
        <div className="mb-3 flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-white text-primary-600 shadow-card">
            <Icon name="sparkles" size={16} />
          </span>
          <h3 className="text-h3 text-ink">AI Interpretation</h3>
        </div>
        <div className="space-y-3">
          {answer.plan.why && (
            <div>
              <p className="mb-1 text-overline uppercase tracking-wide text-ink-muted">
                Kwa nini method hii?
              </p>
              <p className="text-body text-ink-secondary">{answer.plan.why}</p>
            </div>
          )}
          <p className="text-body text-ink">{answer.explanation}</p>
          <p className="text-caption text-ink-muted">
            Maelezo haya yametolewa na AI. Thibitisha kwa matokeo ya engine au dataset
            rasmi kabla ya kutumia.
          </p>
        </div>
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

