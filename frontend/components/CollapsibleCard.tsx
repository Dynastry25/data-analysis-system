"use client";

import { useId } from "react";

import { Icon, IconName } from "./Icon";
import { useLanguage } from "@/lib/i18n";

interface CollapsibleCardProps {
  title: string;
  description?: string;
  icon?: IconName;
  /** Shown next to the title: a count, a verdict badge, a status. */
  badge?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  open: boolean;
  onToggle: () => void;
  className?: string;
}

/**
 * A card whose body can be folded away.
 *
 * The dataset page carries a lot of detail — health, preview, profiles, schema,
 * warnings. Showing all of it at once buries the two things that matter, so the
 * page decides what is open rather than each card deciding for itself: the
 * health headline stays open, the rest start folded and open on demand.
 *
 * The button is a real `<button>` with `aria-expanded`/`aria-controls` so the
 * state is announced rather than only implied by a rotating chevron.
 */
export function CollapsibleCard({
  title,
  description,
  icon,
  badge,
  children,
  footer,
  open,
  onToggle,
  className = "",
}: CollapsibleCardProps) {
  const { t } = useLanguage();
  const panelId = useId();

  return (
    <section
      className={`overflow-hidden rounded-md border border-surface-border bg-surface-panel shadow-card ${className}`}
    >
      <h2 className="m-0">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={panelId}
          className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition-colors duration-150 ease-standard hover:bg-surface-sunken sm:px-5"
        >
          {icon && (
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-sm bg-primary-50 text-primary-600">
              <Icon name={icon} size={16} />
            </span>
          )}
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-center gap-2">
              <span className="text-h3 text-ink">{title}</span>
              {badge}
            </span>
            {description && (
              <span className="mt-0.5 block text-caption text-ink-secondary">
                {description}
              </span>
            )}
          </span>
          <Icon
            name={open ? "chevron-up" : "chevron-down"}
            size={16}
            className="shrink-0 text-ink-muted"
          />
        </button>
      </h2>

      {open && (
        <div id={panelId} className="border-t border-surface-border">
          {children}
        </div>
      )}

      {footer && open && (
        <div className="border-t border-surface-border bg-surface-sunken px-4 py-3 text-caption text-ink-secondary sm:px-5">
          {footer}
        </div>
      )}

      {/* Screen readers get the action even while the body is folded. */}
      {!open && <span className="sr-only">{t("common.expand")}</span>}
    </section>
  );
}

export default CollapsibleCard;
