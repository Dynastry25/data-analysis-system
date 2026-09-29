"use client";

import { Badge } from "./Badge";
import { Card } from "./Card";
import { Icon, IconName } from "./Icon";
import type {
  AssumptionCheck,
  AssumptionStatus,
  PlanningVariable,
  Recommendation,
} from "@/lib/api";

const STATUS_META: Record<
  AssumptionStatus,
  { label: string; tone: "neutral" | "success" | "warning" | "danger"; icon: IconName }
> = {
  pass: { label: "Pass", tone: "success", icon: "check" },
  warn: { label: "Warn", tone: "warning", icon: "alert-triangle" },
  fail: { label: "Fail", tone: "danger", icon: "alert-circle" },
  not_applicable: { label: "Not needed", tone: "neutral", icon: "info" },
};

function variableKind(variable: PlanningVariable | null): string {
  if (!variable) return "—";
  const type = String(variable.semantic_type ?? "");
  if (type === "numeric") return "Numeric";
  if (type === "categorical") return "Categorical";
  if (type === "datetime") return "Date";
  if (type === "boolean") return "Yes/No";
  return type || "—";
}

interface AssumptionStripProps {
  checks: AssumptionCheck[];
  className?: string;
}

/** The three assumption checks, side by side, as the prototype reads them. */
export function AssumptionStrip({ checks, className = "" }: AssumptionStripProps) {
  if (checks.length === 0) return null;

  return (
    <div className={className}>
      <p className="text-overline uppercase tracking-wide text-ink-muted">
        Ukaguzi wa vigezo
      </p>
      <ul className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {checks.map((check) => {
          const meta = STATUS_META[check.status] ?? STATUS_META.not_applicable;
          return (
            <li
              key={check.name}
              className="rounded-md border border-surface-border bg-surface-panel px-3 py-2.5"
            >
              <div className="flex items-center gap-2">
                <Badge tone={meta.tone} size="sm" icon={meta.icon}>
                  {meta.label}
                </Badge>
                <span className="truncate text-caption font-medium text-ink">
                  {check.name}
                </span>
              </div>
              <p className="mt-1.5 text-caption text-ink-secondary">{check.detail}</p>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

interface ResearchBriefProps {
  question: string;
  onQuestionChange: (value: string) => void;
  outcome: PlanningVariable | null;
  predictor: PlanningVariable | null;
  confidenceLevel: string;
  onConfidenceChange: (value: string) => void;
  recommendation: Recommendation | null;
  canRun: boolean;
  running: boolean;
  onRun: () => void;
  className?: string;
}

const CONFIDENCE_LEVELS = ["0.90", "0.95", "0.99"];

/**
 * The research question and the variables, laid out the way the studio does.
 *
 * The question is the user's own sentence. The variables are named by the
 * engine's variable detector, not typed by a user, and the recommendation is the
 * engine's — this panel only arranges them.
 */
export function ResearchBrief({
  question,
  onQuestionChange,
  outcome,
  predictor,
  confidenceLevel,
  onConfidenceChange,
  recommendation,
  canRun,
  running,
  onRun,
  className = "",
}: ResearchBriefProps) {
  return (
    <Card
      title="Statistical Analysis Studio"
      icon="calculator"
      className={className}
      description="Tunga swali la utafiti, chagua variables, kisha endesha. Engine ndiye anayopendekeza njia na kuangalia vigezo."
    >
      <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
        <div>
          <p className="text-overline uppercase tracking-wide text-ink-muted">
            Swali la utafiti
          </p>
          <textarea
            value={question}
            onChange={(event) => onQuestionChange(event.target.value)}
            rows={3}
            className="control mt-1.5 resize-y"
            placeholder="mf. Je, kukamilisha onboarding inaathiri retention ya siku 90?"
          />
          <p className="mt-1.5 text-caption text-ink-muted">
            Swali hili linaeleza kile unachotaka kujua. Linawa kuchagua variables,
            si kubadilisha matokeo.
          </p>

          <div className="mt-4">
            <p className="text-overline uppercase tracking-wide text-ink-muted">
              Variables
            </p>
            <dl className="mt-2 space-y-2">
              <div className="rounded-md border border-surface-border px-3 py-2.5">
                <dt className="text-caption text-ink-muted">Variable inayo tegosiwa</dt>
                <dd className="mt-0.5 flex flex-wrap items-center gap-2">
                  <span className="font-mono text-body font-medium text-ink">
                    {outcome?.name ?? "— chagua kwenye fomu —"}
                  </span>
                  <span className="text-caption text-ink-muted">
                    · {variableKind(outcome)}
                  </span>
                </dd>
              </div>
              <div className="rounded-md border border-surface-border px-3 py-2.5">
                <dt className="text-caption text-ink-muted">Variable ya kujibu</dt>
                <dd className="mt-0.5 flex flex-wrap items-center gap-2">
                  <span className="font-mono text-body font-medium text-ink">
                    {predictor?.name ?? "— chagua kwenye fomu —"}
                  </span>
                  <span className="text-caption text-ink-muted">
                    · {variableKind(predictor)}
                  </span>
                </dd>
              </div>
            </dl>
          </div>
        </div>

        <div className="min-w-0">
          <p className="text-overline uppercase tracking-wide text-ink-muted">
            Pendekezo la smart
          </p>
          {recommendation ? (
            <div className="mt-2 rounded-md border border-primary-200 bg-primary-50 px-3 py-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <Icon name="sparkles" size={15} className="text-primary-600" />
                <span className="text-body font-medium text-primary-800">
                  {recommendation.recommendation.label}
                </span>
                <Badge tone="primary" size="sm">
                  {recommendation.recommendation.family}
                </Badge>
              </div>
              <p className="mt-1.5 text-caption text-ink-secondary">
                {recommendation.recommendation.why}
              </p>
            </div>
          ) : (
            <p className="mt-2 rounded-md border border-dashed border-surface-border-strong bg-surface-sunken px-3 py-3 text-caption text-ink-muted">
              Chagua variable inayo tegosiwa na ya kujibu ili kupendekezwa njia.
            </p>
          )}

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div>
              <label
                htmlFor="confidence-level"
                className="text-overline uppercase tracking-wide text-ink-muted"
              >
                Kiwango cha uhakika
              </label>
              <select
                id="confidence-level"
                value={confidenceLevel}
                onChange={(event) => onConfidenceChange(event.target.value)}
                className="control mt-1.5 cursor-pointer"
              >
                {CONFIDENCE_LEVELS.map((level) => (
                  <option key={level} value={level}>
                    {Math.round(Number(level) * 100)}%
                  </option>
                ))}
              </select>
            </div>
            <div>
              <p className="text-overline uppercase tracking-wide text-ink-muted">
                Bootstrap estimates
              </p>
              <p className="mt-1.5 flex items-center gap-1.5 rounded-md border border-surface-border bg-surface-sunken px-3 py-2.5 text-caption text-ink-secondary">
                <Icon name="info" size={13} className="shrink-0" />
                Zinapatikana kwa regression, si kwa kila njia.
              </p>
            </div>
          </div>

          <div className="mt-4">
            <button
              type="button"
              onClick={onRun}
              disabled={!canRun}
              className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-primary-600 px-4 text-body font-medium text-white transition-colors hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {running ? "Inaendelea…" : "Endesha uchambuzi"}
            </button>
            {!canRun && !running && (
              <p className="mt-1.5 text-center text-caption text-ink-muted">
                Jaza parameters zote zinazohitajika kwanza.
              </p>
            )}
          </div>
        </div>
      </div>

      {recommendation && (
        <div className="mt-5 border-t border-surface-border pt-4">
          <AssumptionStrip checks={recommendation.recommendation.assumption_checks ?? []} />
        </div>
      )}
    </Card>
  );
}

export default ResearchBrief;
