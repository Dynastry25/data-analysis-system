"use client";

import { Icon, IconName } from "./Icon";

type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger" | "primary";

const TONES: Record<BadgeTone, string> = {
  neutral: "border-surface-border bg-surface-sunken text-ink-secondary",
  primary: "bg-primary-50 text-primary-800 border-primary-200",
  info: "bg-info-bg text-info-700 border-info/30",
  success: "bg-success-bg text-success-700 border-success/30",
  warning: "bg-warning-bg text-warning-700 border-warning/30",
  danger: "bg-danger-bg text-danger-700 border-danger/30",
};

const STATUS_ICONS: Partial<Record<BadgeTone, IconName>> = {
  warning: "alert-triangle",
  danger: "alert-circle",
  success: "check",
  info: "info",
};

interface BadgeProps {
  tone?: BadgeTone;
  children: React.ReactNode;
  className?: string;
  icon?: IconName | null;
  size?: "sm" | "md";
}

export function Badge({
  tone = "neutral",
  children,
  className = "",
  icon,
  size = "md",
}: BadgeProps) {
  const statusIcon = icon === null ? undefined : (icon ?? STATUS_ICONS[tone]);
  return (
    <span
      className={`inline-flex max-w-full items-center gap-1 rounded-pill border font-medium ${
        size === "sm" ? "px-1.5 py-0 text-caption" : "px-2 py-0.5 text-caption"
      } ${TONES[tone]} ${className}`}
    >
      {statusIcon && <Icon name={statusIcon} size={12} className="shrink-0" />}
      <span className="truncate">{children}</span>
    </span>
  );
}

export default Badge;

