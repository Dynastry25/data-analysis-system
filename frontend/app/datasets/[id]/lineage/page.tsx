"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Card, EmptyState, Stat } from "@/components/Card";
import { Icon } from "@/components/Icon";
import { TableSkeleton } from "@/components/Skeleton";
import {
  apiErrorMessage,
  LineageResponse,
  LineageVersion,
  statflowApi,
} from "@/lib/api";

/** What one operation left behind, in one line a reader can check. */
function describeSummary(version: LineageVersion): string {
  const operation = version.produced_by as
    | { type?: string; summary?: Record<string, unknown> }
    | null;
  const summary = operation?.summary ?? {};

  if (Array.isArray(summary.applied)) {
    const applied = summary.applied as { label?: string }[];
    return applied.map((item) => item.label).filter(Boolean).join(" · ");
  }
  if (typeof summary.duplicate_rows_removed === "number") {
    return `${summary.duplicate_rows_removed} rows zinazojirudia ziliondolewa`;
  }
  if (Array.isArray(summary.dropped_columns)) {
    return `Columns ziliondolewa: ${(summary.dropped_columns as string[]).join(", ")}`;
  }
  if (Array.isArray(summary.renamed)) {
    const renames = summary.renamed as { from: string; to: string }[];
    return `Majina mapya: ${renames
      .map((item) => `${item.from} → ${item.to}`)
      .join(", ")}`;
  }
  if (summary.renamed && typeof summary.renamed === "object") {
    const pairs = Object.entries(summary.renamed as Record<string, string>);
    return `Majina mapya: ${pairs
      .map(([from, to]) => `${from} → ${to}`)
      .join(", ")}`;
  }
  if (typeof summary.missing_cells_filled === "number") {
    return `${summary.missing_cells_filled} seli za tupu zilijazwa (${summary.strategy})`;
  }
  if (typeof summary.values_became_missing === "number") {
    return `${summary.values_became_missing} thamani zilizokuwa hazikuweza kusomwa`;
  }
  const type = operation?.type ?? "operation";
  return type.charAt(0).toUpperCase() + type.slice(1).replace(/_/g, " ");
}

/** The human wording of an operation type, for the version header. */
const OPERATION_LABELS: Record<string, string> = {
  remediate: "Usafishaji kiotomatiki",
  clean: "Kusafisha",
  transform: "Kubadilisha",
};

function deltaText(delta: number | null, unit: string): string | null {
  if (delta === null || delta === 0) return null;
  return `${delta > 0 ? "+" : ""}${delta.toLocaleString("en-KE")} ${unit}`;
}

function formatMoment(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleString("sw-TZ", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

const ANALYSIS_PATHS: Record<string, string> = {
  welch_t_test: "statistics",
  mann_whitney: "statistics",
  one_way_anova: "statistics",
  correlation_matrix: "statistics",
  linear_regression: "statistics",
};

/** The page: one chain, read top-down from the file that started it. */
export default function LineagePage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params.id);

  const [lineage, setLineage] = useState<LineageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    statflowApi.lineage(datasetId)
      .then((response) => {
        if (!cancelled) {
          setLineage(response);
          setError(null);
        }
      })
      .catch((cause) => {
        if (!cancelled) setError(apiErrorMessage(cause));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  return (
    <AppShell
      title="Asili ya Matokeo"
      description="Kila namba iliyotoka kwenye data hii: faili lililopakiwa, version zilizotengenezwa, na uchambuzi kiliofanywa kwenye kila version."
    >
      {loading && <TableSkeleton rows={6} />}

      {!loading && error && (
        <Card title="Imeshindikana kupata mti wa data">
          <p className="text-body text-danger">{error}</p>
        </Card>
      )}

      {!loading && !error && lineage && (
        <>
          <Card>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary-50 text-primary-700">
                  <Icon name="file-text" size={20} />
                </span>
                <div>
                  <p className="text-h3 text-ink">{lineage.dataset.name}</p>
                  <p className="mt-0.5 text-caption text-ink-secondary">
                    {lineage.dataset.file_type.toUpperCase()} · kupakiwa{" "}
                    {formatMoment(lineage.dataset.uploaded_at)} ·{" "}
                    {lineage.dataset.row_count.toLocaleString("en-KE")} rows ×{" "}
                    {lineage.dataset.column_count} columns
                  </p>
                </div>
              </div>
              <Link
                href={`/datasets/${datasetId}/studio`}
                className="flex min-h-[36px] items-center gap-2 rounded-md border border-surface-border px-3.5 text-caption text-ink-secondary transition-colors duration-150 ease-standard hover:bg-surface-sunken"
              >
                Safisha au badilisha data
              </Link>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-4">
              <Stat
                label="Versions"
                value={String(lineage.totals.versions)}
                hint={`sasa v${lineage.dataset.current_version ?? 1}`}
              />
              <Stat
                label="Operations"
                value={String(lineage.totals.operations)}
                hint={lineage.totals.operations === 0 ? "hakuna" : "hatua za kusafisha"}
              />
              <Stat label="Uchambuzi" value={String(lineage.totals.analyses)} />
              <Stat
                label="Charts/Rapoti"
                value={`${lineage.totals.charts}/${lineage.totals.reports}`}
              />
            </div>
          </Card>

          {lineage.versions.length === 0 ? (
            <EmptyState
              icon="file-text"
              title="Hakuna version bado"
              description="Data hii haijapakiwa kikamilifu."
            />
          ) : (
            <ol className="space-y-4">
              {lineage.versions.map((entry) => {
                const operation = entry.produced_by as
                  | { type?: string; group?: string; warnings?: string[]; created_at?: string }
                  | null;
                const rowDelta = deltaText(entry.row_delta, "rows");
                const columnDelta = deltaText(entry.column_delta, "columns");
                return (
                  <li key={entry.version} className="relative">
                    {/* The connector: the chain reads top-down, so each
                        version hangs off the one before it. */}
                    {entry.parent_version !== null && (
                      <span
                        aria-hidden="true"
                        className="absolute -top-4 left-5 h-4 w-px bg-surface-border"
                      />
                    )}
                    <Card>
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge
                          tone={entry.is_current ? "primary" : "neutral"}
                          size="md"
                        >
                          v{entry.version}
                        </Badge>
                        {entry.is_current && (
                          <Badge tone="success" size="sm" icon="check">
                            toleo la sasa
                          </Badge>
                        )}
                        {entry.label && (
                          <span className="text-caption text-ink-muted">
                            {entry.label}
                          </span>
                        )}
                        <span className="ml-auto text-caption text-ink-muted">
                          {formatMoment(entry.created_at)}
                        </span>
                      </div>

                      <p className="mt-2 text-body text-ink">
                        {entry.produced_by ? (
                          <>
                            <span className="font-medium">
                              {OPERATION_LABELS[
                                operation?.group ?? "operation"
                              ] ?? describeSummary(entry)}
                            </span>{" "}
                            — {describeSummary(entry)}
                          </>
                        ) : (
                          <span className="font-medium">
                            Faili lililopakiwa
                          </span>
                        )}
                      </p>

                      <div className="mt-1 flex flex-wrap items-center gap-2 text-caption text-ink-muted">
                        <span>
                          {entry.row_count.toLocaleString("en-KE")} rows ×{" "}
                          {entry.column_count} columns
                        </span>
                        {rowDelta && <span className="text-warning-700">{rowDelta}</span>}
                        {columnDelta && (
                          <span className="text-warning-700">{columnDelta}</span>
                        )}
                        {operation?.created_at && (
                          <span>· {formatMoment(operation.created_at)}</span>
                        )}
                      </div>

                      {Array.isArray(operation?.warnings) &&
                        operation.warnings.length > 0 && (
                          <ul className="mt-2 space-y-1">
                            {(operation.warnings as string[]).map((warning) => (
                              <li
                                key={warning}
                                className="flex items-start gap-1.5 rounded-md bg-warning-bg px-2.5 py-1.5 text-caption text-warning-700"
                              >
                                <Icon name="alert-triangle" size={13} className="mt-0.5" />
                                {warning}
                              </li>
                            ))}
                          </ul>
                        )}

                      {entry.result_count === 0 ? (
                        <p className="mt-3 text-caption text-ink-muted">
                          Hakuna uchambuzi uliofanywa kwenye toleo hili.
                        </p>
                      ) : (
                        <div className="mt-3 space-y-1.5">
                          {entry.analyses.map((run) => (
                            <Link
                              key={`analysis-${run.id}`}
                              href={`/datasets/${datasetId}/${
                                ANALYSIS_PATHS[run.analysis_type] ?? "statistics"
                              }`}
                              className="flex items-center gap-2 rounded-md border border-surface-border px-3 py-2 text-caption text-ink transition-colors duration-150 ease-standard hover:bg-surface-sunken"
                            >
                              <Icon name="chart" size={14} className="text-primary-700" />
                              <span className="font-medium">
                                {run.analysis_type.replace(/_/g, " ")}
                              </span>
                              <span className="text-ink-muted">
                                #{run.id}
                              </span>
                              {run.status !== "success" && (
                                <Badge tone="warning" size="sm">
                                  {run.status}
                                </Badge>
                              )}
                            </Link>
                          ))}
                          {entry.charts.map((chart) => (
                            <Link
                              key={`chart-${chart.id}`}
                              href={`/datasets/${datasetId}/charts`}
                              className="flex items-center gap-2 rounded-md border border-surface-border px-3 py-2 text-caption text-ink transition-colors duration-150 ease-standard hover:bg-surface-sunken"
                            >
                              <Icon name="chart" size={14} className="text-primary-700" />
                              <span className="font-medium">
                                {chart.title || chart.chart_type}
                              </span>
                              <span className="text-ink-muted">chart</span>
                            </Link>
                          ))}
                          {entry.reports.map((report) => (
                            <Link
                              key={`report-${report.id}`}
                              href={`/datasets/${datasetId}/export`}
                              className="flex items-center gap-2 rounded-md border border-surface-border px-3 py-2 text-caption text-ink transition-colors duration-150 ease-standard hover:bg-surface-sunken"
                            >
                              <Icon name="download" size={14} className="text-primary-700" />
                              <span className="font-medium">
                                Ripoti {report.file_format.toUpperCase()}
                              </span>
                              <span className="text-ink-muted">#{report.id}</span>
                            </Link>
                          ))}
                        </div>
                      )}
                    </Card>
                  </li>
                );
              })}
            </ol>
          )}

          <p className="text-caption text-ink-muted">
            Mti huu unasomwa kwenye rekodi zilizopo; hakuna kitu kinachopatikana
            upya. Kwa hiyo, matokeo yanayofanya kazi kwenye versions tofauti
            yanaonekana tofauti — na unaweza kuona ni kwanini.
          </p>
        </>
      )}
    </AppShell>
  );
}
