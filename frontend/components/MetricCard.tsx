"use client";

import { Icon, IconName } from "./Icon";

type MetricTone = "primary" | "info" | "success" | "warning";

const TONE_CLASSES: Record<MetricTone, string> = {
  primary: "bg-primary-50 text-primary-600",
  info: "bg-info-bg text-info",
  success: "bg-success-bg text-success",
  warning: "bg-warning-bg text-warning",
};

interface MetricCardProps {
  icon?: IconName;
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: MetricTone;
}

/** Overview metric: icon badge + label + monospace value + optional hint. */
export function MetricCard({
  icon,
  label,
  value,
  hint,
  tone = "primary",
}: MetricCardProps) {
  return (
    <div className="flex items-start gap-3 rounded border border-neutral-200 bg-white p-4">
      {icon && (
        <span
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded ${TONE_CLASSES[tone]}`}
        >
          <Icon name={icon} size={20} />
        </span>
      )}
      <div className="min-w-0">
        <p className="text-caption uppercase tracking-wide text-neutral-600">{label}</p>
        <p className="mt-0.5 font-mono text-h2 text-neutral-900">{value}</p>
        {hint && <p className="mt-0.5 truncate text-caption text-neutral-600">{hint}</p>}
      </div>
    </div>
  );
}

export default MetricCard;