"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { StandardResultView } from "@/components/StandardResultView";
import { useToast } from "@/components/Toast";
import { apiErrorMessage, AssistantAnswer, statflowApi } from "@/lib/api";

const INPUT_CLASSES =
  "w-full rounded border border-neutral-200 bg-white px-3 py-2 text-body outline-none focus:border-primary-500";

type Turn = { question: string; answer: AssistantAnswer | null; error?: string };

export default function AskPage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params?.id);
  const { showToast } = useToast();

  const [examples, setExamples] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const loadExamples = useCallback(async () => {
    try {
      const response = await statflowApi.assistantExamples();
      setExamples(response.examples);
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }, [showToast]);

  useEffect(() => {
    loadExamples();
  }, [loadExamples]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  async function ask(text: string) {
    const trimmed = text.trim();
    if (trimmed.length < 3 || asking) return;
    setAsking(true);
    setQuestion("");
    setTurns((previous) => [...previous, { question: trimmed, answer: null }]);
    try {
      const answer = await statflowApi.ask({ dataset_id: datasetId, question: trimmed });
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
        description="Mfano: 'Does income differ between male and female?' au 'Je, kuna uhusiano kati ya umri na mapato?'"
      >
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            className={`${INPUT_CLASSES} flex-1`}
            value={question}
            placeholder="Andika swali lako hapa..."
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") ask(question);
            }}
          />
          <Button loading={asking} onClick={() => ask(question)}>
            Uliza
          </Button>
        </div>
        {examples.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {examples.map((example) => (
              <button
                key={example}
                type="button"
                className="rounded border border-neutral-200 px-2 py-1 text-caption text-neutral-600 hover:border-primary-500 hover:text-primary-600"
                onClick={() => {
                  setQuestion(example);
                }}
              >
                {example}
              </button>
            ))}
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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {answer.intent.intent && (
          <Badge tone="primary">intent: {answer.intent.intent}</Badge>
        )}
        <Badge tone="neutral">method: {answer.plan.method_label}</Badge>
        <Badge tone={validationTone as "success" | "warning" | "danger"} withIcon>
          validation: {answer.validation.status}
        </Badge>
        {answer.dataset_version != null && (
          <Badge tone="neutral">data v{answer.dataset_version}</Badge>
        )}
      </div>

      {answer.plan.variables.length > 0 && (
        <p className="text-caption text-neutral-600">
          Variables: {answer.plan.variables.join(", ")}
        </p>
      )}

      {answer.plan.why && (
        <div className="rounded border border-neutral-200 bg-neutral-50 p-3">
          <p className="mb-1 text-caption font-semibold text-neutral-600">
            Kwa nini method hii?
          </p>
          <p className="text-body">{answer.plan.why}</p>
        </div>
      )}

      {answer.validation.issues.length > 0 && (
        <div className="rounded border border-warning bg-warning/10 p-3 text-caption">
          <p className="mb-1 font-semibold">Tahadhari za kuthibitisha</p>
          <ul className="list-disc pl-5">
            {answer.validation.issues.map((issue, index) => (
              <li key={index}>{issue.message}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="rounded border border-primary-200 bg-primary-50 p-3">
        <p className="mb-1 text-caption font-semibold text-primary-700">Jawabu</p>
        <p className="text-body">{answer.explanation}</p>
      </div>

      {answer.result && <StandardResultView result={answer.result} />}

      {answer.plan.alternatives.length > 0 && (
        <details>
          <summary className="cursor-pointer text-caption font-semibold text-neutral-600">
            Mbinu mbadala ({answer.plan.alternatives.length})
          </summary>
          <ul className="mt-2 list-disc pl-5 text-caption text-neutral-600">
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

