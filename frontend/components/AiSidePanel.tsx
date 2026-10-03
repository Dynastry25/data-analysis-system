"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Icon } from "./Icon";
import {
  api,
  apiErrorMessage,
  statflowApi,
  AssistantAnswer,
  DatasetSummary,
} from "@/lib/api";

interface AiSidePanelProps {
  datasets: DatasetSummary[];
  /** The dataset currently in context, if the user is inside one. */
  activeDatasetId?: number | null;
  activeVersion?: number | null;
}

/**
 * The prototype's persistent right-hand assistant panel.
 *
 * Everything it shows comes from the real assistant endpoint. The prototype
 * fabricates its transcript and bar chart from a fixed answer; here the panel
 * reports the plan, the method and the validation issues the engine actually
 * returned, so it is a second route to the same analysis rather than
 * decoration beside it.
 *
 * Hidden below xl: the prototype does the same, and at narrower widths the
 * panel would take space the content needs.
 */
export function AiSidePanel({
  datasets,
  activeDatasetId = null,
  activeVersion = null,
}: AiSidePanelProps) {
  const dataset =
    datasets.find((entry) => entry.id === activeDatasetId) ?? datasets[0] ?? null;

  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState<string[]>([]);
  const [answers, setAnswers] = useState<(AssistantAnswer | null)[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement | null>(null);

  const ask = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || !dataset || busy) return;
      setBusy(true);
      setError(null);
      setAsked((previous) => [...previous, trimmed]);
      setQuestion("");
      try {
        const response = await statflowApi.ask({
          dataset_id: dataset.id,
          question: trimmed,
          dataset_version: activeVersion ?? undefined,
        });
        setAnswers((previous) => [...previous, response]);
      } catch (caught) {
        setError(apiErrorMessage(caught));
        setAnswers((previous) => [...previous, null]);
      } finally {
        setBusy(false);
      }
    },
    [activeVersion, busy, dataset]
  );

  // Keep the newest turn in view as the transcript grows.
  useEffect(() => {
    const node = logRef.current;
    if (node) node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
  }, [asked, answers, busy]);

  if (!dataset) return null;

  return (
    <aside
      aria-label="Msaidizi wa AI"
      className="sticky top-0 hidden h-screen shrink-0 flex-col border-l border-surface-border bg-surface-panel px-4 py-5 xl:flex xl:w-[320px]"
    >
      <div className="grid grid-cols-[36px_1fr_auto] items-center gap-2.5">
        <span className="grid h-9 w-9 place-items-center rounded-[10px] bg-surface-sunken text-[#B9A7FF] shadow-[inset_0_0_0_1px_#373142]">
          <Icon name="sparkles" size={18} />
        </span>
        <div className="min-w-0">
          <h2 className="font-display text-body font-bold tracking-[-0.02em] text-ink">
            Uliza Msaidizi wa AI
          </h2>
          <p className="mt-0.5 text-caption text-ink-muted">
            Majibu yaliyotoka kwenye data yako
          </p>
        </div>
        <span className="flex items-center gap-0.5 rounded bg-success-bg px-1.5 py-1 text-[10px] font-semibold text-success">
          <Icon name="shield" size={12} />
          Verified
        </span>
      </div>

      <ContextBar dataset={dataset} />

      <div ref={logRef} className="flex-1 overflow-y-auto py-5">
        {asked.length === 0 && <AiWelcome />}

        {asked.map((text, index) => (
          <div key={`${text}-${index}`}>
            <p className="ml-auto max-w-[84%] rounded-[11px_11px_3px_11px] bg-primary-50 px-3 py-2.5 text-caption leading-relaxed text-ink-secondary">
              {text}
            </p>
            <div className="mt-5 grid grid-cols-[24px_1fr] gap-2.5">
              <span className="mt-0.5 grid h-6 w-6 place-items-center rounded-[7px] bg-surface-sunken text-[#B9A7FF]">
                <Icon name="sparkles" size={12} />
              </span>
              <div className="min-w-0">
                <span className="text-[10px] font-bold uppercase tracking-[0.09em] text-primary-600">
                  Jibu lililothibitishwa
                </span>
                {index === asked.length - 1 && busy ? (
                  <p className="mt-1.5 text-caption text-ink-muted">
                    Inaanda mpango wa uchambuzi salama…
                  </p>
                ) : (
                  <AnswerBody answer={answers[index] ?? null} />
                )}
              </div>
            </div>
          </div>
        ))}

        {error && (
          <p
            role="alert"
            className="mt-3 flex items-start gap-2 rounded-lg border border-danger/30 bg-danger-bg px-3 py-2 text-caption text-danger-700"
          >
            <Icon name="alert-circle" size={14} className="mt-0.5 shrink-0" />
            {error}
          </p>
        )}
      </div>

      <AskForm
        value={question}
        busy={busy}
        onChange={setQuestion}
        onSubmit={() => void ask(question)}
      />
    </aside>
  );
}

/** Names the dataset the answers are grounded in, with its current version. */
function ContextBar({ dataset }: { dataset: DatasetSummary }) {
  return (
    <div className="mt-5 grid grid-cols-[auto_1fr_auto] items-center gap-2 rounded-lg border border-surface-border bg-surface-sunken px-2.5 py-2 text-caption">
      <span className="text-ink-muted">Inachunguza</span>
      <strong className="truncate font-medium text-ink">
        {dataset.original_filename}
      </strong>
      <span className="rounded bg-primary-50 px-1.5 py-0.5 text-[10px] font-semibold text-primary-700">
        v{dataset.current_version ?? 1}
      </span>
    </div>
  );
}

interface AskFormProps {
  value: string;
  busy: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

function AskForm({ value, busy, onChange, onSubmit }: AskFormProps) {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
      className="flex min-h-[45px] items-center gap-2 rounded-[10px] border border-surface-border bg-surface-panel py-1 pl-3 pr-1 shadow-[0_3px_12px_rgba(28,24,38,0.06)] transition-colors focus-within:border-primary-300"
    >
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Uliza swali..."
        aria-label="Uliza Msaidizi wa AI"
        className="min-w-0 flex-1 border-0 bg-transparent text-caption text-ink outline-none placeholder:text-ink-muted"
      />
      <button
        type="submit"
        disabled={busy || !value.trim()}
        aria-label="Tuma swali"
        className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-lg bg-primary-600 text-white transition-opacity disabled:opacity-50"
      >
        <Icon name="arrow-right" size={16} />
      </button>
    </form>
  );
}

/**
 * The answer, rendered from the engine's own fields. The prototype visualises
 * fixed correlation values in this slot; here it carries the plan the engine
 * proposed, which is the part a reader actually scans for.
 */
function AnswerBody({ answer }: { answer: AssistantAnswer | null }) {
  if (!answer) return null;
  const { plan, validation } = answer;

  return (
    <>
      <p className="mt-1.5 text-caption leading-relaxed text-ink-secondary">
        {answer.explanation}
      </p>

      <dl className="mt-3 rounded-lg border border-surface-border bg-surface-sunken px-3 py-2.5 text-caption">
        {[
          { label: "Method", value: plan.method_label || plan.method },
          { label: "Matokeo", value: plan.variables.outcome ?? "—" },
          { label: "Predictor", value: plan.variables.predictor ?? "—" },
        ].map((row) => (
          <div key={row.label} className="flex items-center justify-between gap-2 py-0.5">
            <dt className="text-ink-muted">{row.label}</dt>
            <dd className="truncate font-semibold text-ink">{row.value}</dd>
          </div>
        ))}
        {plan.why && (
          <p className="mt-2 border-t border-surface-border pt-2 text-caption leading-relaxed text-ink-muted">
            {plan.why}
          </p>
        )}
      </dl>

      {plan.assumptions.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-4 text-caption text-ink-muted">
          {plan.assumptions.slice(0, 4).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}

      {validation.issues.length > 0 && (
        <p className="mt-2 flex items-start gap-1.5 text-caption text-warning-700">
          <Icon name="alert-triangle" size={13} className="mt-0.5 shrink-0" />
          {validation.issues.length} kumbukumbu zinazostahili kukaguliwa kabla ya
          kuendelea.
        </p>
      )}
    </>
  );
}

function AiWelcome() {
  return (
    <div className="px-1 text-center">
      <span className="mx-auto grid h-12 w-12 place-items-center rounded-[15px] bg-surface-sunken text-[#BBAAFF]">
        <Icon name="sparkles" size={22} />
      </span>
      <h3 className="mt-3 font-display text-body font-bold text-ink">
        Una swali kuhusu data?
      </h3>
      <p className="mt-1.5 text-caption leading-relaxed text-ink-muted">
        Niulize kwa lugha ya kawaida. Msaidizi atachagua variables, atapendekeza
        method, na atakuonyesha vigezo.
      </p>
    </div>
  );
}

export default AiSidePanel;