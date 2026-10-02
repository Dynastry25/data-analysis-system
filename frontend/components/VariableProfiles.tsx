"use client";

import { useMemo } from "react";

import { Badge } from "./Badge";
import { EmptyState } from "./Card";
import { Icon } from "./Icon";
import type { ExploreColumn } from "@/lib/api";
import { useLanguage, type TranslationKey } from "@/lib/i18n";

function formatPercent(ratio: number): string {
  return `${(ratio * 100).toFixed(ratio >= 0.995 || ratio === 0 ? 0 : 1)}%`;
}

/**
 * PASS and WARN are the verdict codes. They are deliberately not translated:
 * they are status tokens that appear in exported output and in the method
 * catalogue, so they stay the same in every language.
 */
const KIND_KEY: Record<ExploreColumn["kind"], TranslationKey> = {
  numeric: "schema.numeric",
  categorical: "schema.categorical",
  datetime: "schema.date",
  text: "schema.text",
  boolean: "schema.boolean",
};

/**
 * A column passes when it is complete and actually varies; otherwise it warns.
 * Both branches describe something the engine found, not a judgement about
 * importance: a full column that never changes cannot be analysed.
 */
function statusFor(column: ExploreColumn, t: (key: TranslationKey, vars?: Record<string, string | number>) => string) {
  if (column.missing_count > 0) {
    return {
      tone: "warning" as const,
      label: "WARN",
      reason: t("profiles.reasonMissing", { count: column.missing_count }),
    };
  }
  if (column.unique_count !== null && column.unique_count <= 1) {
    return {
      tone: "warning" as const,
      label: "WARN",
      reason: t("profiles.reasonConstant"),
    };
  }
  return { tone: "success" as const, label: "PASS", reason: null };
}

interface VariableProfilesProps {
  columns: ExploreColumn[];
  rowCount: number;
  className?: string;
}

/**
 * One row per column: its verdict, its type, and the two numbers that decide
 * most later steps — the centre and the gaps.
 *
 * This renders as a bare list, not a card. The dataset page folds it inside a
 * CollapsibleCard, which already supplies the border, the title and the badge;
 * nesting a card in a card would give two frames around the same content.
 *
 * The list is ordered worst-first so the columns that need attention are at the
 * top rather than wherever the file happened to put them.
 */
export function VariableProfiles({ columns, rowCount, className = "" }: VariableProfilesProps) {
  const { t, formatNumber } = useLanguage();

  const ordered = useMemo(
    () =>
      [...columns].sort((a, b) => {
        const aWarn = statusFor(a, t).tone === "warning" ? 0 : 1;
        const bWarn = statusFor(b, t).tone === "warning" ? 0 : 1;
        if (aWarn !== bWarn) return aWarn - bWarn;
        return b.missing_count - a.missing_count;
      }),
    [columns, t]
  );

  if (ordered.length === 0) {
    return (
      <p className={className}>
        <EmptyState title={t("profiles.empty")} icon="sliders" />
      </p>
    );
  }

  return (
    <div className={className}>
      <ul className="divide-y divide-surface-border">
        {ordered.map((column) => {
          const status = statusFor(column, t);
          const share = rowCount > 0 ? column.missing_ratio : 0;
          return (
            <li
              key={column.name}
              className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-4 py-2.5 sm:px-5"
            >
              <span className="flex min-w-[11rem] flex-1 flex-col gap-0.5">
                <span className="flex items-center gap-2">
                  <span className="truncate font-mono text-caption font-medium text-ink">
                    {column.name}
                  </span>
                  {column.value_labels && (
                    // A badge rather than a column: the codes matter to the
                    // engine, the words are what the researcher needs to read.
                    <Badge tone="primary" size="sm">
                      {t("label.codes")}
                    </Badge>
                  )}
                  {status.reason && status.tone === "warning" && (
                    <span className="sr-only">{status.reason}:</span>
                  )}
                </span>
                {column.variable_label && (
                  <span className="truncate text-caption text-ink-secondary">
                    {column.variable_label}
                  </span>
                )}
              </span>

              <Badge tone={status.tone} size="sm" className="w-16 justify-center">
                {status.label}
              </Badge>

              <span className="w-24 shrink-0 text-caption text-ink-secondary">
                {t(KIND_KEY[column.kind] ?? "schema.text")}
              </span>

              <span className="w-32 shrink-0 text-right font-mono text-caption text-ink">
                {column.kind === "numeric" && column.mean !== null ? (
                  <>
                    <span className="text-ink-muted">{t("common.mean")}</span>{" "}
                    {formatNumber(column.mean)}
                  </>
                ) : column.value_labels ? (
                  // A coded categorical has no mean, but it does have its
                  // codes, and the words they stand for are the useful thing.
                  <CodedValues labels={column.value_labels} />
                ) : (
                  <span className="text-ink-muted">{t("common.notAvailable")}</span>
                )}
              </span>

              <span className="flex w-32 shrink-0 items-center justify-end gap-2">
                <span className="text-caption text-ink-muted">
                  {t("profiles.missingLabel")}
                </span>
                <span
                  className={`font-mono text-caption ${
                    share > 0 ? "text-warning-700" : "text-ink"
                  }`}
                >
                  {formatPercent(share)}
                </span>
              </span>
            </li>
          );
        })}
      </ul>

      <p className="flex items-start gap-2 border-t border-surface-border bg-surface-sunken px-4 py-3 text-caption text-ink-secondary sm:px-5">
        <Icon name="info" size={14} className="mt-0.5 shrink-0" />
        <span>{t("profiles.note")}</span>
      </p>
    </div>
  );
}

/**
 * The first few code/word pairs of a labelled categorical.
 *
 * A label set can hold hundreds of codes, which would swamp a one-line row, so
 * only the first three appear and the rest are counted rather than listed. The
 * full mapping is in the column structure table.
 */
function CodedValues({ labels }: { labels: Record<string, string> }) {
  const { t } = useLanguage();
  const entries = Object.entries(labels);
  const shown = entries.slice(0, 3);
  const hidden = entries.length - shown.length;

  return (
    <span className="flex flex-col items-end gap-0.5">
      <span className="text-ink-secondary">
        {shown.map(([code, word], index) => (
          <span key={code} className="whitespace-nowrap">
            {index > 0 ? ", " : ""}
            {code} = {word}
          </span>
        ))}
      </span>
      {hidden > 0 && (
        <span className="text-caption text-ink-muted">
          +{hidden} {t("label.moreCodes")}
        </span>
      )}
    </span>
  );
}

export default VariableProfiles;
