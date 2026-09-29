"use client";

import { useMemo } from "react";

import { Badge } from "./Badge";
import { Card } from "./Card";
import { Icon } from "./Icon";
import type { ExploreColumn } from "@/lib/api";

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("en-KE", { maximumFractionDigits: 2 });
}

const KIND_LABEL: Record<ExploreColumn["kind"], string> = {
  numeric: "Numeric",
  categorical: "Categorical",
  datetime: "Date",
  text: "Text",
  boolean: "Yes/No",
};

/** A column passes when it is complete and actually varies; otherwise it warns. */
function statusFor(column: ExploreColumn) {
  if (column.missing_count > 0) {
    return {
      tone: "warning" as const,
      label: "WARN",
      reason: `${column.missing_count} cell zilizokosekana`,
    };
  }
  if (column.unique_count !== null && column.unique_count <= 1) {
    return {
      tone: "warning" as const,
      label: "WARN",
      reason: "thamani moja tu, haibadilishi",
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
 * PASS and WARN are read off the counts the engine already computed. A column
 * is never marked PASS because nothing was found to complain about; it is
 * marked PASS because it is complete and it varies.
 */
export function VariableProfiles({ columns, rowCount, className = "" }: VariableProfilesProps) {
  const ordered = useMemo(
    () =>
      [...columns].sort((a, b) => {
        const aWarn = statusFor(a).tone === "warning" ? 0 : 1;
        const bWarn = statusFor(b).tone === "warning" ? 0 : 1;
        if (aWarn !== bWarn) return aWarn - bWarn;
        return b.missing_count - a.missing_count;
      }),
    [columns]
  );

  const warningCount = ordered.filter((column) => statusFor(column).tone === "warning").length;

  return (
    <Card
      title="Profiles za variables"
      description="Aina, wastani na mapengo kwa kila column. Pass inamaanisha kamba ina thamani zote na inabadilika; warn inamaanisha kuna kitu cha kuangalia."
      icon="sliders"
      className={className}
      padding="none"
      actions={
        warningCount > 0 ? (
          <Badge tone="warning" icon="alert-triangle">
            {warningCount} zinahitaji kuangalia
          </Badge>
        ) : (
          <Badge tone="success" icon="check">
            Zote ziko safi
          </Badge>
        )
      }
    >
      {ordered.length === 0 ? (
        <p className="px-4 py-8 text-center text-body text-ink-muted sm:px-5">
          Hakuna columns bado.
        </p>
      ) : (
        <ul className="divide-y divide-surface-border">
          {ordered.map((column) => {
            const status = statusFor(column);
            const share =
              rowCount > 0 ? column.missing_ratio : 0;
            return (
              <li
                key={column.name}
                className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-4 py-2.5 sm:px-5"
              >
                <span className="flex min-w-[9rem] flex-1 items-center gap-2">
                  <span className="truncate font-mono text-caption font-medium text-ink">
                    {column.name}
                  </span>
                  {status.reason && status.tone === "warning" && (
                    <span className="sr-only">{status.reason}:</span>
                  )}
                </span>

                <Badge tone={status.tone} size="sm" className="w-16 justify-center">
                  {status.label}
                </Badge>

                <span className="w-24 shrink-0 text-caption text-ink-secondary">
                  {KIND_LABEL[column.kind] ?? column.kind}
                </span>

                <span className="w-24 shrink-0 text-right font-mono text-caption text-ink">
                  {column.kind === "numeric" ? (
                    <>
                      <span className="text-ink-muted">mean</span>{" "}
                      {formatNumber(column.mean)}
                    </>
                  ) : (
                    <span className="text-ink-muted">—</span>
                  )}
                </span>

                <span className="flex w-32 shrink-0 items-center justify-end gap-2">
                  <span className="text-caption text-ink-muted">missing</span>
                  <span
                    className={`font-mono text-caption ${
                      share > 0 ? "text-warning-700" : "text-ink"
                    }`}
                  >
                    {(share * 100).toFixed(1)}%
                  </span>
                </span>
              </li>
            );
          })}
        </ul>
      )}

      <p className="flex items-start gap-2 border-t border-surface-border bg-surface-sunken px-4 py-3 text-caption text-ink-secondary sm:px-5">
        <Icon name="info" size={14} className="mt-0.5 shrink-0" />
        <span>
          Wastani linaonyeshwa kwa columns za nambari pekee. Kategoria hazina
          wastani — zinaonyeshwa kwa idadi ya kila kundi kwenye hatua ya kuchunguza.
        </span>
      </p>
    </Card>
  );
}

export default VariableProfiles;
