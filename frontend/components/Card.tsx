"use client";

import { Icon, IconName } from "./Icon";

type CardPadding = "default" | "compact" | "none";
type CardTone = "default" | "muted" | "warning" | "danger" | "success";

const PADDING_CLASSES: Record<CardPadding, string> = {
  default: "p-4 sm:p-5",
  compact: "p-3",
  none: "p-0",
};

const TONE_CLASSES: Record<CardTone, string> = {
  default: "border-surface-border bg-surface-panel",
  muted: "border-surface-border bg-surface-sunken",
  warning: "border-warning/40 bg-warning-bg",
  danger: "border-danger/40 bg-danger-bg",
  success: "border-success/40 bg-success-bg",
};

interface CardProps {
  title?: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  padding?: CardPadding;
  tone?: CardTone;
  icon?: IconName;
  footer?: React.ReactNode;
}

export function Card({
  title,
  description,
  actions,
  children,
  className = "",
  padding = "default",
  tone = "default",
  icon,
  footer,
}: CardProps) {
  const headerless = !title && !actions && !description;
  return (
    <section
      className={`rounded-md border shadow-card ${TONE_CLASSES[tone]} ${className}`}
    >
      {headerless ? (
        <div className={PADDING_CLASSES[padding]}>{children}</div>
      ) : (
        <>
          <header
            className={`flex flex-wrap items-start justify-between gap-3 ${
              padding === "none" ? "px-4 pt-4 sm:px-5 sm:pt-5" : ""
            }`}
          >
            <div className="flex min-w-0 items-start gap-2.5">
              {icon && (
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-sm bg-primary-50 text-primary-600">
                  <Icon name={icon} size={16} />
                </span>
              )}
              <div className="min-w-0">
                {title && <h2 className="text-h3 text-ink">{title}</h2>}
                {description && (
                  <p className="mt-0.5 text-body text-ink-secondary">{description}</p>
                )}
              </div>
            </div>
            {actions && (
              <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
            )}
          </header>
          <div className={padding === "none" ? "mt-4" : `${padding === "compact" ? "mt-3" : "mt-4"} ${PADDING_CLASSES[padding]}`}>
            {children}
          </div>
        </>
      )}
      {footer && (
        <div className="border-t border-surface-border bg-surface-sunken px-4 py-3 text-caption text-ink-secondary sm:px-5">
          {footer}
        </div>
      )}
    </section>
  );
}

interface StatProps {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: "default" | "accent";
}

export function Stat({ label, value, hint, tone = "default" }: StatProps) {
  return (
    <div className="rounded-sm border border-surface-border bg-surface-sunken px-3.5 py-3">
      <p className="text-overline uppercase tracking-wide text-ink-muted">{label}</p>
      <p
        className={`tabular mt-1 font-mono text-h2 ${
          tone === "accent" ? "text-primary-700" : "text-ink"
        }`}
      >
        {value}
      </p>
      {hint && <p className="mt-0.5 text-caption text-ink-muted">{hint}</p>}
    </div>
  );
}

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: IconName;
}

export function EmptyState({
  title,
  description,
  action,
  icon = "layers",
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center rounded-md border border-dashed border-surface-border-strong bg-surface-sunken px-6 py-10 text-center">
      <span className="flex h-11 w-11 items-center justify-center rounded-sm bg-surface-panel text-ink-muted shadow-card">
        <Icon name={icon} size={20} />
      </span>
      <p className="mt-3 text-body-lg font-medium text-ink">{title}</p>
      {description && (
        <p className="mt-1 max-w-md text-body text-ink-muted">{description}</p>
      )}
      {action && <div className="mt-4 flex justify-center gap-2">{action}</div>}
    </div>
  );
}

export default Card;

