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
  return (
    <div className="relative flex items-start gap-3 overflow-hidden rounded-md border border-surface-border bg-surface-panel p-4 shadow-card transition-shadow duration-150 ease-standard hover:shadow-raised">
      {accent && (
        <span
          aria-hidden="true"
          className={`absolute inset-x-0 top-0 h-0.5 ${accent}`}
        />
      )}
      {icon && (
        <span
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-sm ${TONE_CLASSES[tone]}`}
        >
          <Icon name={icon} size={20} />
        </span>
      )}
      <div className="min-w-0">
        <p className="text-overline uppercase tracking-wide text-ink-muted">{label}</p>
        <p className="tabular mt-0.5 font-mono text-h2 text-ink">{value}</p>
        {hint && <p className="mt-0.5 text-caption text-ink-muted">{hint}</p>}
      </div>
    </div>
  );
}

export default MetricCard;
