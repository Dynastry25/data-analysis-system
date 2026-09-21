"use client";

type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger" | "primary";

const TONES: Record<BadgeTone, string> = {
  neutral: "bg-neutral-100 text-neutral-600 border-neutral-200",
  primary: "bg-primary-100 text-primary-900 border-primary-300",
  info: "bg-info-bg text-info border-info",
  success: "bg-success-bg text-success border-success",
  warning: "bg-warning-bg text-warning border-warning",
  danger: "bg-danger-bg text-danger border-danger",
};

const ICONS: Partial<Record<BadgeTone, string>> = {
  warning: "⚠",
  danger: "✕",
  success: "✓",
  info: "i",
};

interface BadgeProps {
  tone?: BadgeTone;
  children: React.ReactNode;
  className?: string;
  withIcon?: boolean;
}

/**
 * Status badge. Meaning is never conveyed by colour alone: warning/danger/info
 * badges always show a small icon as well (accessibility requirement).
 */
export function Badge({
  tone = "neutral",
  children,
  className = "",
  withIcon = false,
}: BadgeProps) {
  const icon = withIcon ? ICONS[tone] : undefined;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-caption ${TONES[tone]} ${className}`}
    >
      {icon && <span aria-hidden="true">{icon}</span>}
      {children}
    </span>
  );
}

export default Badge;
