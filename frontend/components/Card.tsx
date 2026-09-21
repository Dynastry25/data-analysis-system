"use client";

interface CardProps {
  title?: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

/** Neutral surface card: whitespace-first, flat, 8px radius. */
export function Card({
  title,
  description,
  actions,
  children,
  className = "",
}: CardProps) {
  return (
    <section
      className={`rounded border border-neutral-200 bg-white p-4 sm:p-6 ${className}`}
    >
      {(title || actions) && (
        <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-h3 text-neutral-900">{title}</h2>}
            {description && (
              <p className="mt-1 text-body text-neutral-600">{description}</p>
            )}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

interface StatProps {
  label: string;
  value: React.ReactNode;
  hint?: string;
}

/** Single number card (mean, rows, columns ...) shown in monospace. */
export function Stat({ label, value, hint }: StatProps) {
  return (
    <div className="rounded border border-neutral-200 bg-neutral-50 p-4">
      <p className="text-caption uppercase tracking-wide text-neutral-600">{label}</p>
      <p className="mt-1 font-mono text-h2 text-neutral-900">{value}</p>
      {hint && <p className="mt-1 text-caption text-neutral-600">{hint}</p>}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="rounded border border-dashed border-neutral-200 bg-neutral-50 p-6 text-center">
      <p className="text-body-lg text-neutral-900">{title}</p>
      {description && (
        <p className="mt-1 text-body text-neutral-600">{description}</p>
      )}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export default Card;
