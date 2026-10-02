"use client";

import { useMemo } from "react";

import { Badge } from "./Badge";
import { Card } from "./Card";
import { Icon } from "./Icon";
import type { ColumnProfile } from "@/lib/api";
import type { ExploreColumn } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";

function formatPercent(ratio: number): string {
  return `${(ratio * 100).toFixed(ratio >= 0.995 || ratio === 0 ? 0 : 1)}%`;
}

/** A completeness ring, so the headline number is a reading, not a claim. */
function ScoreRing({ score }: { score: number }) {
  const { t } = useLanguage();
  const percent = Math.max(0, Math.min(100, score * 100));
  const radius = 34;
  const circumference = 2 * Math.PI * radius;
  const stroke =
    percent >= 95 ? "#16A34A" : percent >= 80 ? "#D97706" : "#DC2626";

  return (
    <div className="relative h-24 w-24 shrink-0">
      <svg
        viewBox="0 0 80 80"
        className="h-24 w-24 -rotate-90"
        role="img"
        aria-label={`${t("health.completeness")} ${percent.toFixed(0)}%`}
      >
        <circle
          cx="40"
          cy="40"
          r={radius}
          fill="none"
          stroke="#F1F5F9"
          strokeWidth="8"
        />
        <circle
          cx="40"
          cy="40"
          r={radius}
          fill="none"
          stroke={stroke}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - percent / 100)}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="tabular font-mono text-h2 font-medium text-ink">
          {percent.toFixed(0)}%
        </span>
      </div>
    </div>
  );
}

/** Per-column completeness bars, sorted worst first so the gap is visible. */
function CompletenessChart({ columns }: { columns: ExploreColumn[] }) {
  const { t, formatNumber } = useLanguage();
  const rows = useMemo(
    () =>
      [...columns]
        .filter((column) => column.missing_count > 0)
        .sort((a, b) => b.missing_ratio - a.missing_ratio)
        .slice(0, 8),
    [columns]
  );

  if (rows.length === 0) {
    return (
      <p className="flex items-center gap-2 text-body text-success-700">
        <Icon name="check" size={16} />
        {t("health.allComplete")}
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {rows.map((column) => {
        const share = column.missing_ratio;
        return (
          <li key={column.name} className="flex items-center gap-3">
            <span className="w-28 shrink-0 truncate font-mono text-caption text-ink-secondary">
              {column.name}
            </span>
            <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-sunken">
              <span
                className={`block h-full ${
                  share >= 0.5 ? "bg-danger-500" : share >= 0.2 ? "bg-warning-500" : "bg-info-500"
                }`}
                style={{ width: `${Math.max(share * 100, 1.5)}%` }}
              />
            </span>
            <span className="w-20 shrink-0 text-right font-mono text-caption text-ink-muted">
              {formatPercent(share)}
            </span>
            <span className="w-24 shrink-0 text-right font-mono text-caption text-ink-muted">
              {formatNumber(column.missing_count, { maximumFractionDigits: 0 })}{" "}
              {t("common.missing")}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** A distribution strip, the same div-drawn histogram used on Explore. */
function DistributionStrip({ column }: { column: ExploreColumn }) {
  const { t, formatNumber } = useLanguage();
  const bins = column.histogram ?? [];
  if (bins.length === 0) return null;
  const tallest = Math.max(...bins.map((bin) => bin.count), 1);

  return (
    <div
      className="mt-2 flex h-10 items-end gap-px"
      role="img"
      aria-label={t("health.distributionAlt", { name: column.name })}
    >
      {bins.map((bin) => (
        <div
          key={`${bin.start}-${bin.end}`}
          className="min-w-[2px] flex-1 rounded-t-sm bg-primary-200"
          style={{ height: `${Math.max((bin.count / tallest) * 100, 2)}%` }}
          title={`${formatNumber(bin.start)} – ${formatNumber(bin.end)}: ${formatNumber(bin.count, { maximumFractionDigits: 0 })}`}
        />
      ))}
    </div>
  );
}

interface DatasetHealthProps {
  rowCount: number;
  columnCount: number;
  /** Profiles carry the per-column missing counts the score is built from. */
  columns: ColumnProfile[];
  /**
   * Explore output, when it is loaded. Mean, median and the distribution strip
   * only exist there; without it the panel shows completeness and missingness
   * alone rather than inventing a summary.
   */
  explore: ExploreColumn[] | null;
  isOwnDataset: boolean;
}

/**
 * Dataset health, the way the prototype reads it: one score, the missing cells
 * behind it, and the summary of the numeric columns.
 *
 * Every number here comes from the backend profile or the explore engine. The
 * score is completeness (present cells over total cells), which is the one
 * definition that can be recomputed from the file by hand.
 */
export function DatasetHealth({
  rowCount,
  columnCount,
  columns,
  explore,
  isOwnDataset,
}: DatasetHealthProps) {
  const { t, formatNumber } = useLanguage();
  const totalCells = rowCount * columnCount;
  const missingCells = columns.reduce(
    (sum, column) => sum + (column.missing_count || 0),
    0
  );
  const completeness =
    totalCells > 0 ? Math.max(0, 1 - missingCells / totalCells) : 1;
  const columnsWithGaps = columns.filter((column) => (column.missing_count || 0) > 0);

  const numeric = useMemo(
    () => (explore ?? []).filter((column) => column.kind === "numeric"),
    [explore]
  );

  // The headline mean and median are the first two numeric columns, so the panel
  // answers "what is this data" without waiting for a column choice.
  const lead = numeric.slice(0, 2);

  const verdict =
    missingCells === 0
      ? { tone: "success" as const, label: t("verdict.noGaps"), icon: "check" as const }
      : completeness >= 0.9
        ? { tone: "success" as const, label: t("verdict.usable"), icon: "check" as const }
        : completeness >= 0.7
          ? { tone: "warning" as const, label: t("verdict.needsCleaning"), icon: "alert-triangle" as const }
          : { tone: "danger" as const, label: t("verdict.unusable"), icon: "alert-circle" as const };

  return (
    <Card
      title={t("health.title")}
      description={t("health.description")}
      icon="shield"
      padding="none"
      actions={
        <Badge tone={verdict.tone} icon={verdict.icon}>
          {verdict.label}
        </Badge>
      }
    >
      <div className="grid gap-5 px-4 py-4 sm:px-5 lg:grid-cols-[auto_1fr]">
        <div className="flex items-center gap-4">
          <ScoreRing score={completeness} />
          <dl className="space-y-1.5 text-caption">
            <div className="flex gap-2">
              <dt className="text-ink-muted">{t("health.completeness")}</dt>
              <dd className="tabular font-mono font-medium text-ink">
                {formatPercent(completeness)}
              </dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-ink-muted">{t("health.missingCells")}</dt>
              <dd className="tabular font-mono font-medium text-ink">
                {formatNumber(missingCells, { maximumFractionDigits: 0 })}
              </dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-ink-muted">{t("health.totalCells")}</dt>
              <dd className="tabular font-mono font-medium text-ink">
                {formatNumber(totalCells, { maximumFractionDigits: 0 })}
              </dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-ink-muted">{t("health.columnsWithGaps")}</dt>
              <dd className="tabular font-mono font-medium text-ink">
                {t("health.columnsWithGapsOf", {
                  with: columnsWithGaps.length,
                  total: columnCount,
                })}
              </dd>
            </div>
          </dl>
        </div>

        <div className="min-w-0">
          <p className="text-overline uppercase tracking-wide text-ink-muted">
            {t("health.gapsByColumn")}
          </p>
          <div className="mt-2">
            {explore ? (
              <CompletenessChart columns={explore} />
            ) : (
              <ul className="space-y-2">
                {columnsWithGaps.slice(0, 8).map((column) => {
                  const share = rowCount > 0 ? (column.missing_count || 0) / rowCount : 0;
                  return (
                    <li key={column.name} className="flex items-center gap-3">
                      <span className="w-28 shrink-0 truncate font-mono text-caption text-ink-secondary">
                        {column.name}
                      </span>
                      <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-sunken">
                        <span
                          className={`block h-full ${
                            share >= 0.5
                              ? "bg-danger-500"
                              : share >= 0.2
                                ? "bg-warning-500"
                                : "bg-info-500"
                          }`}
                          style={{ width: `${Math.max(share * 100, 1.5)}%` }}
                        />
                      </span>
                      <span className="w-20 shrink-0 text-right font-mono text-caption text-ink-muted">
                        {formatPercent(share)}
                      </span>
                    </li>
                  );
                })}
                {columnsWithGaps.length === 0 && (
                  <p className="flex items-center gap-2 text-body text-success-700">
                    <Icon name="check" size={16} />
                    Kila column imejaa kabisa. Hakuna cell iliyokosekana.
                  </p>
                )}
              </ul>
            )}
          </div>
        </div>
      </div>

      {lead.length > 0 && (
        <div className="border-t border-surface-border px-4 py-4 sm:px-5">
          <p className="text-overline uppercase tracking-wide text-ink-muted">
            {t("health.numericSummary")}
          </p>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {lead.map((column) => (
              <div
                key={column.name}
                className="rounded-md border border-surface-border px-3 py-2.5"
              >
                <div className="flex items-center gap-2">
                  <span className="truncate font-mono text-caption font-medium text-ink">
                    {column.name}
                  </span>
                  {column.missing_count > 0 && (
                    <Badge tone="warning" size="sm">
                      {t("health.countWithZilizo", { count: column.missing_count })}
                    </Badge>
                  )}
                </div>
                <dl className="mt-2 grid grid-cols-2 gap-2">
                  <div>
                    <dt className="text-overline uppercase tracking-wide text-ink-muted">
                      {t("common.mean")}
                    </dt>
                    <dd className="tabular font-mono text-body text-ink">
                      {formatNumber(column.mean)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-overline uppercase tracking-wide text-ink-muted">
                      {t("common.median")}
                    </dt>
                    <dd className="tabular font-mono text-body text-ink">
                      {formatNumber(column.median)}
                    </dd>
                  </div>
                </dl>
                <DistributionStrip column={column} />
                <p className="mt-1 flex justify-between text-caption text-ink-muted">
                  <span>{formatNumber(column.min)}</span>
                  <span>{formatNumber(column.max)}</span>
                </p>
              </div>
            ))}
          </div>
          {numeric.length > lead.length && (
            <p className="mt-2 text-caption text-ink-muted">
              {t("health.moreNumeric", { count: numeric.length - lead.length })}
            </p>
          )}
        </div>
      )}

      <p className="border-t border-surface-border bg-surface-sunken px-4 py-3 text-caption text-ink-secondary sm:px-5">
        {t(
          isOwnDataset ? "health.definitionOwn" : "health.definitionShared",
          {
            total: `${formatNumber(rowCount, { maximumFractionDigits: 0 })} × ${formatNumber(columnCount, { maximumFractionDigits: 0 })}`,
          },
        )}
      </p>
    </Card>
  );
}

export default DatasetHealth;
