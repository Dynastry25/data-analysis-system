"use client";

import { Badge } from "@/components/Badge";
import { DataTable } from "@/components/DataTable";
import { StandardResult } from "@/lib/api";

/** Format a scalar value for display. */
function fmt(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    if (Math.abs(value) > 0 && Math.abs(value) < 0.0001) return value.toExponential(2);
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  if (typeof value === "boolean") return value ? "ndio" : "hapana";
  return String(value);
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

/**
 * Render any standard result (MVP-19) consistently:
 * estimate, test, confidence interval, effect size, diagnostics, warnings, tables.
 */
export function StandardResultView({ result }: { result: StandardResult }) {
  const pValue = result.test?.p_value;
  const significant = result.test?.significant;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="primary">{result.analysis_type}</Badge>
        <Badge tone={result.status === "success" ? "success" : "warning"}>
          {result.status}
        </Badge>
        {result.sample_size != null && (
          <Badge tone="neutral">n = {result.sample_size}</Badge>
        )}
        {significant != null && (
          <Badge tone={significant ? "success" : "neutral"} withIcon>
            {significant ? "Muhimu (significant)" : "Si muhimu"}
          </Badge>
        )}
      </div>

      {result.warnings.length > 0 && (
        <div className="rounded border border-warning bg-warning/10 p-3 text-caption">
          <p className="mb-1 font-semibold">Tahadhari</p>
          <ul className="list-disc pl-5">
            {result.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

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
          <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-neutral-50 p-3 text-caption">
            {JSON.stringify(result.diagnostics, null, 2)}
          </pre>
        </details>
      )}

      {Object.keys(result.tables).length > 0 && (
        <TablesBlock tables={result.tables} />
      )}
    </div>
  );
}
