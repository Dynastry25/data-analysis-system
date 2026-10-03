"use client";

import { Icon, IconName } from "./Icon";

type MetricTone = "primary" | "info" | "success" | "warning" | "danger";

const TONE_CLASSES: Record<MetricTone, string> = {
  primary: "bg-primary-50 text-primary-700",
  info: "bg-info-bg text-info-700",
  success: "bg-success-bg text-success-700",
  warning: "bg-warning-bg text-warning-700",
  danger: "bg-danger-bg text-danger-700",
};

interface MetricCardProps {
  icon?: IconName;
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: MetricTone;
  accent?: string;
}

export function MetricCard({
  icon,
  label,
  value,
  hint,
  tone = "primary",
  accent,
}: MetricCardProps) {
  /*
 * The prototype's metric card: a 36px tinted icon in the top-left, the label
 * across the top, the value bottom-aligned on the same grid, and the hint on
 * its own row. It lifts 2px on hover rather than just brightening, because a
 * KPI strip is a row of near-identical cards and hover needs to read as motion
 * to be noticed at all.
 */
return (
    <div className="relative grid min-h-[134px] grid-cols-[36px_1fr] grid-rows-[auto_auto_auto] gap-x-[11px] overflow-hidden rounded-lg border border-surface-border bg-surface-panel p-4 shadow-card transition-all duration-200 ease-standard hover:-translate-y-0.5 hover:border-[#DBD6E3] hover:shadow-hover">
      {accent && (
        <span
          aria-hidden="true"
          className={`absolute inset-x-0 top-0 h-0.5 ${accent}`}
        />
      )}
      {icon && (
        <span
          className={`row-span-2 flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${TONE_CLASSES[tone]}`}
        >
          <Icon name={icon} size={18} />
        </span>
      )}
      <p className="self-center text-overline uppercase tracking-[0.07em] text-ink-muted">
        {label}
      </p>
      <p className="tabular col-span-2 mt-auto font-display text-h1 font-bold tracking-[-0.02em] text-ink">
        {value}
      </p>
      {hint && (
        <p className="col-span-2 mt-1 flex items-center gap-1.5 text-caption text-ink-muted">
          {hint}
        </p>
      )}
    </div>
  );
}

export default MetricCard;
