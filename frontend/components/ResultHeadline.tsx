"use client";

import { useMemo } from "react";

import { Badge } from "./Badge";
import { DataTable } from "./DataTable";
import { fmt, pFmt } from "./StandardResultView";
import type { StandardResult } from "@/lib/api";

const COEF_COLUMNS = [
  "variable",
  "estimate",
  "std_error",
  "t_statistic",
  "p_value",
  "ci_lower",
  "ci_upper",
];

const COEF_LABELS: Record<string, string> = {
  variable: "Variable",
  estimate: "Coef",
  std_error: "SE",
  t_statistic: "t",
  p_value: "p",
  ci_lower: "CI chini",
  ci_upper: "CI juu",
};

interface CoefficientTableProps {
  result: StandardResult;
}

/**
 * The per-variable coefficient table.
 *
 * The statistic column is named for the method the engine actually ran, not for
 * the one in the prototype: an ordinary least-squares fit reports a t, a
 * logistic fit would report a z. Labelling it z either way would be a number
 * the engine never computed.
 */
export function CoefficientTable({ result }: CoefficientTableProps) {
  const rows = useMemo(() => {
    const coefficients = result.tables?.coefficients;
    if (!Array.isArray(coefficients) || coefficients.length === 0) return [];
    return coefficients as Record<string, unknown>[];
  }, [result.tables]);

  if (rows.length === 0) return null;

  const columns = COEF_COLUMNS.filter((column) =>
    rows.some((row) => row[column] !== undefined && row[column] !== null)
  );

  return (
    <div>
      <p className="text-overline uppercase tracking-wide text-ink-muted">
        Matokeo ya vibujadi
      </p>
      <div className="mt-1.5">
        <DataTable
          caption="Matokeo ya vibujadi kwa kila variable"
          columns={columns}
          columnLabels={COEF_LABELS}
          rows={rows}
          numericColumns={columns.filter((column) => column !== "variable")}
          renderCell={(column, value) => {
            if (column === "variable") {
              const isIntercept = String(value) === "(intercept)";
              return (
                <span
                  className={`font-mono text-caption ${
                    isIntercept ? "text-ink-muted italic" : "text-ink"
                  }`}
                >
                  {String(value)}
                </span>
              );
            }
            if (column === "p_value") {
              const p = typeof value === "number" ? value : null;
              return (
                <span
                  className={`font-mono ${
                    p !== null && p < 0.05 ? "text-success-700" : "text-ink-muted"
                  }`}
                >
                  {p === null ? "—" : pFmt(p)}
                </span>
              );
            }
            return <span className="font-mono">{fmt(value)}</span>;
          }}
        />
      </div>
      <p className="mt-1.5 text-caption text-ink-muted">
        Mstari wa (intercept) ni thamani ya kivinjari: thamani ya{' '}
        {String(result.estimate.target ?? "target")} wakati features zote ni sifuri.
        Thamani za p chini ya 0.05 zimeandikwa kwa rangi.
      </p>
    </div>
  );
}

interface ResultHeadlineProps {
  result: StandardResult;
  /** The user's own research question, when they wrote one. */
  question?: string | null;
  className?: string;
}

/**
 * The claim, the method, and the three numbers a reader looks for first.
 *
 * The headline is the user's research question when there is one, because that
 * is the claim the result speaks to. Without a question it falls back to what
 * the estimate actually is, stated without a verdict attached.
 */
export function ResultHeadline({
  result,
  question = null,
  className = "",
}: ResultHeadlineProps) {
  const headline = useMemo(() => {
    const trimmed = question?.trim();
    if (trimmed) return trimmed;
    const target = result.estimate.target;
    const features = result.estimate.features;
    if (typeof target === "string" && Array.isArray(features) && features.length > 0) {
      return `${features.join(", ")} → ${target}`;
    }
    if (typeof target === "string") return `${target} imehesabiwa`;
    return null;
  }, [question, result.estimate]);

  const metrics: { label: string; value: string; hint?: string }[] = [];

  const oddsRatio = result.effect_size?.name === "odds_ratio"
    ? result.effect_size.value
    : null;
  if (oddsRatio !== null) {
    metrics.push({
      label: "Odds ratio",
      value: `${fmt(oddsRatio)}×`,
      hint: "mara ngapi",
    });
  } else if (result.effect_size && result.effect_size.value !== null) {
    metrics.push({
      label: result.effect_size.name ?? "Effect size",
      value: fmt(result.effect_size.value),
      hint: result.effect_size.interpretation ?? undefined,
    });
  }

  const ci = result.confidence_interval;
  if (ci && ci.lower !== null && ci.upper !== null) {
    const level = Math.round((ci.level ?? 0.95) * 100);
    metrics.push({
      label: `${level}% confidence interval`,
      value: `${fmt(ci.lower)} – ${fmt(ci.upper)}`,
      hint: "kwa makadirio",
    });
  }

  if (result.test?.p_value !== null && result.test?.p_value !== undefined) {
    metrics.push({
      label: "P-value",
      value: pFmt(result.test.p_value),
      hint: `alpha = ${result.test.alpha ?? 0.05}`,
    });
  }

  if (metrics.length === 0 && result.sample_size !== null) {
    metrics.push({ label: "n", value: String(result.sample_size), hint: "sample size" });
  }

  return (
    <div className={className}>
      {headline && (
        <p className="text-body-lg font-medium text-ink">{headline}</p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {question?.trim() && (
          <Badge tone="neutral">Swali lako</Badge>
        )}
        <Badge tone="primary">{result.test?.method ?? result.analysis_type}</Badge>
        {result.status !== "success" && <Badge tone="warning">{result.status}</Badge>}
        {result.test?.significant !== null && result.test?.significant !== undefined && (
          <Badge tone={result.test.significant ? "success" : "neutral"}>
            Muhimu: {result.test.significant ? "Ndiyo" : "Hapana"}
          </Badge>
        )}
      </div>

      {metrics.length > 0 && (
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {metrics.map((metric) => (
            <div
              key={metric.label}
              className="rounded-md border border-surface-border bg-surface-sunken px-3.5 py-3"
            >
              <p className="truncate text-overline uppercase tracking-wide text-ink-muted">
                {metric.label}
              </p>
              <p className="tabular mt-1 truncate font-mono text-h2 text-ink">
                {metric.value}
              </p>
              {metric.hint && (
                <p className="mt-0.5 truncate text-caption text-ink-muted">
                  {metric.hint}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default ResultHeadline;
