"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Card, EmptyState, Stat } from "@/components/Card";
import { Icon } from "@/components/Icon";
import { TableSkeleton } from "@/components/Skeleton";
import {
  ExploreColumn,
  ExploreResponse,
  api,
  apiErrorMessage,
} from "@/lib/api";

const KIND_LABEL: Record<ExploreColumn["kind"], string> = {
  numeric: "Nambari",
  categorical: "Makundi",
  datetime: "Tarehe",
  text: "Maandishi",
  boolean: "Ndio/Hapana",
};

const KIND_TONE: Record<ExploreColumn["kind"], "primary" | "info" | "neutral"> = {
  numeric: "primary",
  categorical: "info",
  datetime: "info",
  text: "neutral",
  boolean: "neutral",
};

const STRENGTH_TONE: Record<string, "success" | "warning" | "neutral"> = {
  strong: "success",
  moderate: "warning",
  weak: "neutral",
};

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("en-KE", { maximumFractionDigits: 3 });
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "(tupu)";
  if (typeof value === "number") return formatNumber(value);
  return String(value);
}

/**
 * A text bar chart of a histogram, drawn with divs.
 *
 * The numbers are printed next to every bar, so the chart is a reading aid and
 * not the only way to get the value. A chart you cannot read a number off is
 * decoration.
 */
function Histogram({ column }: { column: ExploreColumn }) {
  const bins = column.histogram ?? [];
  if (bins.length === 0) return null;
  const tallest = Math.max(...bins.map((bin) => bin.count), 1);

  return (
    <div className="mt-3">
      <div className="flex h-28 items-end gap-px" role="img" aria-label={`Distribution of ${column.name}`}>
        {bins.map((bin) => (
          <div
            key={`${bin.start}-${bin.end}`}
            className="min-w-[2px] flex-1 rounded-t-sm bg-primary-200"
            style={{ height: `${Math.max((bin.count / tallest) * 100, 2)}%` }}
            title={`${formatNumber(bin.start)} – ${formatNumber(bin.end)}: ${bin.count}`}
          />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-caption text-ink-muted">
        <span>{formatNumber(bins[0]?.start)}</span>
        <span>
          {bins.length} bins · juu yake {formatNumber(tallest)}
        </span>
        <span>{formatNumber(bins[bins.length - 1]?.end)}</span>
      </div>
    </div>
  );
}

export default function ExploreDatasetPage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params.id);

  const [report, setReport] = useState<ExploreResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState<ExploreColumn["kind"] | "all">("all");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.datasets
      .explore(datasetId)
      .then((response) => {
        if (!cancelled) {
          setReport(response);
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

  const shownColumns = useMemo(() => {
    if (!report) return [];
    return kindFilter === "all"
      ? report.columns
      : report.columns.filter((column) => column.kind === kindFilter);
  }, [report, kindFilter]);

  const kinds = useMemo(() => {
    const counts = new Map<ExploreColumn["kind"], number>();
    for (const column of report?.columns ?? []) {
      counts.set(column.kind, (counts.get(column.kind) ?? 0) + 1);
    }
    return [...counts.entries()];
  }, [report]);

  return (
    <AppShell
      title="Chunguza data"
      description="Muundo, distributions na uhusiano wa columns kabla ya kuchagua mbinu ya uchambuzi. Kila kitu hapa kimehesabiwa na engine, si miongozo."
    >
      {loading && <TableSkeleton rows={6} />}

      {!loading && error && (
        <Card title="Imeshindikana kuchunguza data">
          <p className="text-body text-danger">{error}</p>
        </Card>
      )}

      {!loading && !error && report && (
        <>
          <Card>
            <div className="grid gap-3 sm:grid-cols-4">
              <Stat
                label="Rows"
                value={formatNumber(report.row_count)}
                hint={`version ${report.dataset_version}`}
              />
              <Stat label="Columns" value={String(report.column_count)} />
              <Stat
                label="Mahusiano"
                value={String(report.correlations.length)}
                hint="jozi za columns"
              />
              <Stat
                label="Tahadhari"
                value={String(report.warnings.length)}
                tone={report.warnings.length > 0 ? "accent" : "default"}
              />
            </div>

            {report.warnings.length > 0 && (
              <ul className="mt-4 space-y-2">
                {report.warnings.map((warning) => (
                  <li
                    key={warning}
                    className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning-bg px-3 py-2"
                  >
                    <Icon name="alert-triangle" size={16} className="mt-0.5 shrink-0 text-warning" />
                    <p className="text-body text-ink-secondary">{warning}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title="Mahusiano kati ya columns"
            icon="trending-up"
            actions={
              <Link
                href={`/datasets/${datasetId}/statistics`}
                className="flex min-h-[36px] items-center gap-1.5 rounded-md border border-surface-border px-3 text-caption font-medium text-ink-secondary transition-colors duration-150 hover:bg-surface-sunken"
              >
                Endelea kwenye uchambuzi
                <Icon name="arrow-right" size={14} />
              </Link>
            }
          >
            {report.correlations.length === 0 ? (
              <EmptyState
                icon="trending-up"
                title="Hakuna mahusiano ya kutoa"
                description={
                  report.columns.filter((column) => column.kind === "numeric").length < 2
                    ? "Uchunguzi unahitaji angalau columns mbili za nambari. Badilisha aina ya data au safisha ili zionekane kama nambari."
                    : "Haijapatikana mahusiano ya maana kati ya columns za nambari kwenye data hii."
                }
              />
            ) : (
              <ul className="divide-y divide-surface-border">
                {report.correlations.map((pair) => (
                  <li key={`${pair.x}-${pair.y}`} className="py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <code className="rounded bg-surface-sunken px-1.5 py-0.5 font-mono text-caption text-ink-secondary">
                        {pair.x}
                      </code>
                      <span className="text-ink-muted">×</span>
                      <code className="rounded bg-surface-sunken px-1.5 py-0.5 font-mono text-caption text-ink-secondary">
                        {pair.y}
                      </code>
                      <Badge tone={STRENGTH_TONE[pair.strength]} size="sm">
                        {pair.strength}
                      </Badge>
                      <Badge tone="neutral" size="sm">
                        {pair.method}
                      </Badge>
                      <span className="ml-auto font-mono text-body text-ink">
                        r = {formatNumber(pair.coefficient)}
                      </span>
                    </div>
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-sunken">
                      <div
                        className="h-full bg-primary-500"
                        style={{ width: `${Math.abs(pair.coefficient) * 100}%` }}
                      />
                    </div>
                    <p className="mt-2 text-body text-ink-secondary">{pair.interpretation}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card
            title={`Muundo wa kila column (${shownColumns.length})`}
            icon="table"
            actions={
              <div className="flex flex-wrap items-center gap-1">
                <button
                  type="button"
                  onClick={() => setKindFilter("all")}
                  className={`rounded-md px-2.5 py-1 text-caption transition-colors duration-150 ${
                    kindFilter === "all"
                      ? "bg-primary-50 font-medium text-primary-800"
                      : "text-ink-muted hover:bg-surface-sunken"
                  }`}
                >
                  Zote
                </button>
                {kinds.map(([kind, count]) => (
                  <button
                    key={kind}
                    type="button"
                    onClick={() => setKindFilter(kind)}
                    className={`rounded-md px-2.5 py-1 text-caption transition-colors duration-150 ${
                      kindFilter === kind
                        ? "bg-primary-50 font-medium text-primary-800"
                        : "text-ink-muted hover:bg-surface-sunken"
                    }`}
                  >
                    {KIND_LABEL[kind]}
                    <span className="ml-1">{count}</span>
                  </button>
                ))}
              </div>
            }
          >
            {shownColumns.length === 0 ? (
              <p className="text-body text-ink-muted">Hakuna column katika kategoria hiyo.</p>
            ) : (
              <ul className="space-y-4">
                {shownColumns.map((column) => (
                  <li
                    key={column.name}
                    className="rounded-md border border-surface-border p-3.5"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-body font-medium text-ink">{column.name}</span>
                      <Badge tone={KIND_TONE[column.kind]} size="sm">
                        {KIND_LABEL[column.kind]}
                      </Badge>
                      {column.missing_count > 0 && (
                        <Badge tone="warning" size="sm">
                          {(column.missing_ratio * 100).toFixed(0)}% hazina thamani
                        </Badge>
                      )}
                      {column.unique_count !== null && (
                        <span className="ml-auto text-caption text-ink-muted">
                          {column.unique_count.toLocaleString("en-KE")} thamani tofauti
                        </span>
                      )}
                    </div>

                    {column.kind === "numeric" && (
                      <>
                        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
                          {(
                            [
                              ["Min", column.min],
                              ["Max", column.max],
                              ["Wastani", column.mean],
                              ["Median", column.median],
                            ] as const
                          ).map(([label, value]) => (
                            <div key={label}>
                              <dt className="text-overline uppercase tracking-wide text-ink-muted">
                                {label}
                              </dt>
                              <dd className="text-body text-ink">{formatNumber(value)}</dd>
                            </div>
                          ))}
                        </dl>
                        {column.quantiles && Object.keys(column.quantiles).length > 0 && (
                          <p className="mt-2 text-caption text-ink-muted">
                            Quartiles:{" "}
                            {Object.entries(column.quantiles)
                              .map(([key, value]) => `${key} = ${formatNumber(value)}`)
                              .join(" · ")}
                            {column.std !== null && column.std !== undefined
                              ? ` · SD = ${formatNumber(column.std)}`
                              : ""}
                          </p>
                        )}
                        <Histogram column={column} />
                      </>
                    )}

                    {(column.kind === "categorical" || column.kind === "boolean") &&
                      (column.top_values?.length ?? 0) > 0 && (
                        <ul className="mt-3 space-y-1.5">
                          {column.top_values!.map((entry) => {
                            const share =
                              report.row_count > 0
                                ? (entry.count / report.row_count) * 100
                                : 0;
                            return (
                              <li key={String(entry.value)} className="flex items-center gap-3">
                                <span className="w-32 shrink-0 truncate text-caption text-ink-secondary">
                                  {formatValue(entry.value)}
                                </span>
                                <span className="h-2 flex-1 overflow-hidden rounded-full bg-surface-sunken">
                                  <span
                                    className="block h-full bg-info-500"
                                    style={{ width: `${share}%` }}
                                  />
                                </span>
                                <span className="w-24 shrink-0 text-right font-mono text-caption text-ink-muted">
                                  {entry.count} ({share.toFixed(0)}%)
                                </span>
                              </li>
                            );
                          })}
                        </ul>
                      )}

                    {(column.kind === "text" || column.kind === "datetime") && (
                      <p className="mt-2 text-caption text-ink-muted">
                        {column.kind === "text"
                          ? "Maandishi mengi: kila thamani ni tofauti, kwa hiyo hazihitaji kuhesabiwa."
                          : "Tarehe: zinaweza kutumika kwa mwenendo wa wakati."}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <p className="text-caption text-ink-muted">
            Kuchunguza hakiiandishi rekodi, kwa hiyo hatua hii inabaki kuwa &ldquo;Soma&rdquo;.
            Mahusiano yaliyotolewa ni ya uhusiano, si ushahidi wa kisababu.
          </p>
        </>
      )}
    </AppShell>
  );
}
