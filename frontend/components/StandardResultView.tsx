"use client";

import { Badge } from "@/components/Badge";
import { DataTable } from "@/components/DataTable";
import { StandardResult } from "@/lib/api";
import { colorForIndex } from "@/lib/constants";

/** Format a scalar value for display. */
export function fmt(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    if (Math.abs(value) > 0 && Math.abs(value) < 0.0001) return value.toExponential(2);
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  if (typeof value === "boolean") return value ? "ndio" : "hapana";
  return String(value);
}

/** Format a p-value the way statisticians expect. */
export function pFmt(p: number | null | undefined): string {
  if (p === null || p === undefined) return "—";
  if (p < 0.0001) return "< 0.0001";
  return p.toFixed(4);
}

/** Layer 1 — plain-language headline (design system §10). */
function buildHeadline(result: StandardResult): string {
  if (result.status !== "success") {
    return "Uchambuzi haujakamilika — hakikisha data inatosha na parameters ni sahihi.";
  }
  const test = result.test;
  const method = test?.method ?? result.analysis_type;
  if (!test || test.significant === null || test.significant === undefined) {
    return `Muhtasari wa takwimu (${result.analysis_type}) kwa n = ${result.sample_size ?? "—"} rekodi.`;
  }
  const pText = `p = ${pFmt(test.p_value)}`;
  if (test.significant) {
    return `Matokeo ni muhimu kiotakwimu (${method}, ${pText}) — kuna ushahidi wa kutosha kuwa tofauti/uhusiano ni wa kweli.`;
  }
  return `Matokeo si muhimu kiotakwimu (${method}, ${pText}) — hakuna ushahidi wa kutosha wa tofauti/uhusiano.`;
}

/** Layer 5 — practical (not just statistical) meaning in plain language. */
function buildInterpretation(result: StandardResult): string {
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
  if (effect && effect.value !== null && effect.value !== undefined) {
    const sizeText = effect.interpretation ? ` (${effect.interpretation})` : "";
    sentences.push(
      `Ukubwa wa athari: ${effect.name ?? "effect size"} = ${fmt(effect.value)}${sizeText} — huu ndio uzito wa vitendo wa matokeo.`
    );
  }
  if (result.sample_size !== null && result.sample_size < 30) {
    sentences.push("Sample ni ndogo (n < 30): chukulia matokeo haya kwa tahadhari.");
  }
  if (sentences.length === 0) {
    sentences.push(
      "Angalia jedwali la makadirio ndani ya 'Angalia zaidi' — lina muhtasari kamili wa data yako."
    );
  }
  return sentences.join(" ");
}

/** First flat {label: number} record inside the estimate (group means, counts, ...). */
function findGroupValues(
  estimate: Record<string, unknown>
): { label: string; value: number }[] | null {
  for (const value of Object.values(estimate)) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const entries = Object.entries(value as Record<string, unknown>);
      if (
        entries.length >= 2 &&
        entries.length <= 10 &&
        entries.every(([, v]) => typeof v === "number")
      ) {
        return entries.map(([label, v]) => ({ label, value: v as number }));
      }
    }
  }
  return null;
}

/** Best-guess point estimate for the CI chart. */
function pointEstimate(result: StandardResult): number | null {
  for (const key of [
    "estimate",
    "difference",
    "mean_difference",
    "mean",
    "correlation",
    "coefficient",
  ]) {
    const value = result.estimate[key];
    if (typeof value === "number") return value;
  }
  return null;
}

/** Render a flat record as a small key/value table. */
function EstimateTable({ record }: { record: Record<string, unknown> }) {
  const entries = Object.entries(record);
  if (entries.length === 0) return null;
  return (
    <table className="w-full text-left text-body">
      <tbody>
        {entries.map(([key, value]) => (
          <tr key={key} className="border-b border-neutral-100 last:border-0">
            <th className="py-1.5 pr-4 font-medium text-neutral-600">{key}</th>
            <td className="py-1.5">
              {value !== null && typeof value === "object" ? (
                <pre className="whitespace-pre-wrap text-caption">
                  {JSON.stringify(value, null, 2)}
                </pre>
              ) : (
                fmt(value)
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Render the generic tables block (frequency tables, contingency tables, ...). */
function TablesBlock({ tables }: { tables: Record<string, unknown> }) {
  const rendered: JSX.Element[] = [];
  for (const [key, value] of Object.entries(tables)) {
    if (Array.isArray(value) && value.length > 0 && typeof value[0] === "object") {
      const rows = value as Record<string, unknown>[];
      rendered.push(
        <div key={key}>
          <p className="mb-1 text-caption font-semibold text-neutral-600">{key}</p>
          <DataTable
            caption={key}
            columns={Object.keys(rows[0])}
            rows={rows}
            numericColumns={Object.keys(rows[0]).filter(
              (k) => typeof rows[0][k] === "number"
            )}
          />
        </div>
      );
    } else {
      rendered.push(
        <div key={key}>
          <p className="mb-1 text-caption font-semibold text-neutral-600">{key}</p>
          <pre className="whitespace-pre-wrap rounded bg-neutral-50 p-2 text-caption">
            {JSON.stringify(value, null, 2)}
          </pre>
        </div>
      );
    }
  }
  return <div className="space-y-3">{rendered}</div>;
}

/** Single key-number card (mono font per design system §3) — reused by result views. */
export function MetricCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded border border-neutral-200 bg-neutral-50 p-4">
      <p className="truncate text-caption uppercase tracking-wide text-neutral-600">
        {label}
      </p>
      <p className="mt-1 truncate font-mono text-h2 text-neutral-900">{value}</p>
      {hint && (
        <p className="mt-1 truncate text-caption text-neutral-600">{hint}</p>
      )}
    </div>
  );
}

/** Layer 4 wrapper — full statistical details behind a collapsible (design system §10). */
export function CollapsibleDetails({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <details className="rounded border border-neutral-200">
      <summary className="cursor-pointer px-4 py-3 text-body font-medium text-neutral-600 transition-colors duration-150 ease-out hover:bg-neutral-50">
        {label}
      </summary>
      <div className="details-content space-y-4 border-t border-neutral-200 p-4">
        {children}
      </div>
    </details>
  );
}

/** Layer 5 — practical meaning in plain language, in an info box. */
export function InterpretationBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded border border-info bg-info-bg p-4">
      <p className="text-caption font-semibold text-info">
        Tafsiri kwa lugha rahisi
      </p>
      <p className="mt-1 text-body text-neutral-900">{children}</p>
    </div>
  );
}

/** Layer 2 — key numbers as short metric cards (mono font per design system §3). */
function MetricCards({ result }: { result: StandardResult }) {
  const metrics: { label: string; value: string; hint?: string }[] = [];
  if (result.test && result.test.statistic !== null && result.test.statistic !== undefined) {
    metrics.push({
      label: result.test.method ?? "Test statistic",
      value: fmt(result.test.statistic),
      hint: "test statistic",
    });
  }
  if (result.test && result.test.p_value !== null && result.test.p_value !== undefined) {
    metrics.push({
      label: "p-value",
      value: pFmt(result.test.p_value),
      hint: `alpha = ${result.test.alpha ?? 0.05}`,
    });
  }
  if (result.sample_size !== null) {
    metrics.push({ label: "n", value: String(result.sample_size), hint: "sample size" });
  }
  if (result.effect_size && result.effect_size.value !== null) {
    metrics.push({
      label: result.effect_size.name ?? "Effect size",
      value: fmt(result.effect_size.value),
      hint: result.effect_size.interpretation ?? undefined,
    });
  }
  if (metrics.length === 0) return null;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {metrics.map((metric) => (
        <MetricCard key={metric.label} {...metric} />
      ))}
    </div>
  );
}

/** Layer 3a — confidence interval whisker (pure CSS, screen-reader friendly). */
function CiChart({ result }: { result: StandardResult }) {
  const ci = result.confidence_interval;
  if (!ci || ci.lower === null || ci.upper === null || ci.upper <= ci.lower) {
    return null;
  }
  const point = pointEstimate(result);
  const span = ci.upper - ci.lower;
  const pad = span * 0.75;
  const min = ci.lower - pad;
  const max = ci.upper + pad;
  const pct = (v: number) => Math.min(100, Math.max(0, ((v - min) / (max - min)) * 100));
  const levelPct =
    ci.level !== undefined && ci.level !== null ? Math.round(ci.level * 100) : 95;
  const zeroInside = min < 0 && max > 0;
  const ariaLabel =
    `Confidence interval ya ${levelPct}%: ${fmt(ci.lower)} hadi ${fmt(ci.upper)}` +
    (point !== null ? `, makadirio ${fmt(point)}` : "") +
    (zeroInside ? `. Mstari wa sifuri umeonyeshwa.` : "");

  return (
    <div role="img" aria-label={ariaLabel}>
      <p className="mb-2 text-caption font-semibold text-neutral-600">
        Confidence interval ({levelPct}%)
      </p>
      <div className="relative h-8" aria-hidden="true">
        <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-neutral-200" />
        {zeroInside && (
          <div
            className="absolute top-0 h-full w-px bg-neutral-400"
            style={{ left: `${pct(0)}%` }}
          />
        )}
        <div
          className="bar-grow absolute top-1/2 h-2 -translate-y-1/2 rounded bg-primary-300"
          style={{
            left: `${pct(ci.lower)}%`,
            width: `${pct(ci.upper) - pct(ci.lower)}%`,
          }}
        />
        {point !== null && (
          <div
            className="absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-primary-600"
            style={{ left: `${pct(point)}%` }}
          />
        )}
      </div>
      <div className="mt-1 flex justify-between font-mono text-caption text-neutral-600">
        <span>{fmt(ci.lower)}</span>
        {point !== null && <span className="text-primary-700">{fmt(point)}</span>}
        <span>{fmt(ci.upper)}</span>
      </div>
    </div>
  );
}

/** Layer 3b — horizontal bars comparing values (Okabe-Ito colors). */
export function GroupBars({
  values,
  title = "Kulinganisha makundi",
}: {
  values: { label: string; value: number }[];
  title?: string;
}) {
  const maxAbs = Math.max(...values.map((v) => Math.abs(v.value)), 1e-9);
  const ariaLabel = `Chati ya makundi: ${values
    .map((v) => `${v.label} = ${fmt(v.value)}`)
    .join(", ")}`;
  return (
    <div role="img" aria-label={ariaLabel}>
      <p className="mb-2 text-caption font-semibold text-neutral-600">
        {title}
      </p>
      <div className="space-y-2" aria-hidden="true">
        {values.map((entry, index) => (
          <div key={entry.label} className="flex items-center gap-2">
            <span
              className="w-28 truncate text-caption text-neutral-600"
              title={entry.label}
            >
              {entry.label}
            </span>
            <div className="h-4 flex-1 rounded bg-neutral-100">
              <div
                className="bar-grow h-full rounded"
                style={{
                  width: `${(Math.abs(entry.value) / maxAbs) * 100}%`,
                  backgroundColor: colorForIndex(index),
                }}
              />
            </div>
            <span className="w-20 text-right font-mono text-caption text-neutral-900">
              {fmt(entry.value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

interface StandardResultViewProps {
  result: StandardResult;
  /** Optional next-step buttons (design system §10 layer 6). */
  actions?: React.ReactNode;
}

/**
 * Progressive-disclosure result view (design system §10 — inverted pyramid):
 * 1. headline (plain language) + significance badge
 * 2. metric cards (statistic, p-value, n, effect size)
 * 3. visuals (CI whisker, group bars)
 * 4. "Angalia zaidi" — full details behind a collapsible
 * 5. plain-language interpretation
 * 6. next-step actions
 */
export function StandardResultView({ result, actions }: StandardResultViewProps) {
  const pValue = result.test?.p_value;
  const significant = result.test?.significant ?? null;
  const groupValues = findGroupValues(result.estimate);
  const hasVisual =
    (result.confidence_interval !== null &&
      result.confidence_interval.lower !== null &&
      result.confidence_interval.upper !== null) ||
    groupValues !== null;

  return (
    <div className="space-y-6">
      {/* Layer 1 — Kichwa cha habari */}
      <div>
        <p className="text-body-lg text-neutral-900">{buildHeadline(result)}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Badge tone="primary">{result.analysis_type}</Badge>
          {significant !== null && (
            <Badge tone={significant ? "success" : "neutral"} withIcon>
              Umuhimu wa kitakwimu: {significant ? "Ndiyo" : "Hapana"}
            </Badge>
          )}
          {result.status !== "success" && (
            <Badge tone="warning" withIcon>
              {result.status}
            </Badge>
          )}
        </div>
      </div>

      {result.warnings.length > 0 && (
        <div
          role="alert"
          className="rounded border border-warning bg-warning-bg p-3 text-caption text-warning"
        >
          <p className="mb-1 font-semibold">⚠ Tahadhari</p>
          <ul className="list-disc pl-5">
            {result.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Layer 2 — Namba muhimu */}
      <MetricCards result={result} />

      {/* Layer 3 — Taswira */}
      {hasVisual && (
        <div className="space-y-4 rounded border border-neutral-200 bg-neutral-50 p-4">
          <CiChart result={result} />
          {groupValues && <GroupBars values={groupValues} />}
        </div>
      )}

      {/* Layer 4 — Angalia zaidi (undani wa kitakwimu) */}
      <CollapsibleDetails label="Angalia zaidi — undani wa kitakwimu (estimate, CI, df, diagnostics)">
          <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-1 text-caption font-semibold text-neutral-600">
            Makadirio (estimate)
          </p>
          <EstimateTable record={result.estimate} />
        </div>
        <div className="space-y-3">
          {result.test && (
            <div>
              <p className="mb-1 text-caption font-semibold text-neutral-600">
                Jaribio (test)
              </p>
              <div className="rounded border border-neutral-200 p-3">
                <EstimateTable
                  record={{
                    test: result.test.method,
                    statistic: result.test.statistic,
                    df: result.test.df ?? result.test.df1,
                    p_value: pValue,
                    alpha: result.test.alpha,
                    significant: significant,
                  }}
                />
              </div>
            </div>
          )}
          {result.confidence_interval && (
            <div>
              <p className="mb-1 text-caption font-semibold text-neutral-600">
                Confidence interval
              </p>
              <div className="rounded border border-neutral-200 p-3">
                <EstimateTable
                  record={{
                    level: result.confidence_interval.level,
                    lower: result.confidence_interval.lower,
                    upper: result.confidence_interval.upper,
                  }}
                />
              </div>
            </div>
          )}
          {result.effect_size && (
            <div>
              <p className="mb-1 text-caption font-semibold text-neutral-600">
                Effect size
              </p>
              <div className="rounded border border-neutral-200 p-3">
                <EstimateTable
                  record={{
                    name: result.effect_size.name,
                    value: result.effect_size.value,
                    interpretation: result.effect_size.interpretation,
                  }}
                />
              </div>
            </div>
          )}
        </div>
      </div>

          {Object.keys(result.diagnostics).length > 0 && (
            <details>
              <summary className="cursor-pointer text-caption font-semibold text-neutral-600">
                Diagnostics
              </summary>
              <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-neutral-50 p-3 font-mono text-caption">
                {JSON.stringify(result.diagnostics, null, 2)}
              </pre>
            </details>
          )}

          {Object.keys(result.tables).length > 0 && (
            <TablesBlock tables={result.tables} />
          )}
      </CollapsibleDetails>

      {/* Layer 5 — Tafsiri kwa lugha rahisi */}
      <InterpretationBox>{buildInterpretation(result)}</InterpretationBox>

      {/* Layer 6 — Hatua zinazofuata */}
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
