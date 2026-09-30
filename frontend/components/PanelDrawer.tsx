"use client";

/**
 * A slide-over panel used to hold secondary detail out of the way.
 *
 * The preparation studio has more information than fits comfortably in one
 * screen: the operation form, the data preview, the version history, the
 * pipeline and the audit trail. Showing all of it at once leaves the operation
 * -- the thing the user came to do -- competing with everything around it.
 * So the secondary panels sit behind summary cards and open here instead.
 *
 * Built from the existing design tokens rather than new ones: the same
 * overlay treatment as the app drawer (`bg-sidebar-deep/60` over `z-40`), the
 * `shadow-drawer` elevation from the spec's "floating menus" rule, and the same
 * Escape / backdrop-click dismissal the rest of the app already uses.
 */

import { useEffect, useRef } from "react";

import { Icon, IconName } from "./Icon";

interface PanelDrawerProps {
  open: boolean;
  title: string;
  description?: string;
  icon?: IconName;
  onClose: () => void;
  children: React.ReactNode;
  /** Tailwind width class for the panel, e.g. "sm:max-w-xl". */
  widthClass?: string;
}

export function PanelDrawer({
  open,
  title,
  description,
  icon,
  onClose,
  children,
  widthClass = "sm:max-w-2xl",
}: PanelDrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  // Escape closes, matching every other overlay in the app.
  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  // Move focus into the panel when it opens so the keyboard follows the eye,
  // and restore it to the card that opened it on close.
  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    return () => previouslyFocused?.focus?.();
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40" role="presentation">
      <div
        aria-hidden="true"
        onClick={onClose}
        className="fixed inset-0 bg-sidebar-deep/60"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={`fixed inset-y-0 right-0 z-50 flex w-full ${widthClass} flex-col bg-surface-panel shadow-drawer focus:outline-none`}
      >
        <header className="flex items-start justify-between gap-3 border-b border-surface-border px-4 py-3 sm:px-5">
          <div className="flex min-w-0 items-start gap-2.5">
            {icon && (
              <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-sm bg-primary-50 text-primary-600">
                <Icon name={icon} size={16} />
              </span>
            )}
            <div className="min-w-0">
              <h2 className="text-h3 text-ink">{title}</h2>
              {description && (
                <p className="mt-0.5 text-body text-ink-secondary">{description}</p>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Funga"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-ink-muted transition-colors duration-150 ease-standard hover:bg-surface-sunken hover:text-ink"
          >
            <Icon name="close" size={18} />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-5">
          {children}
        </div>
      </div>
    </div>
  );
}

interface PanelCardProps {
  title: string;
  hint: string;
  icon: IconName;
  onOpen: () => void;
  /** The one number worth seeing without opening anything. */
  value?: string;
  meta?: string;
}

/**
 * The summary card that stands in for a panel until it is asked for.
 *
 * It carries enough to decide whether opening is worth it -- what the panel
 * holds, and the headline number -- so hiding the detail does not also hide
 * the information.
 */
export function PanelCard({ title, hint, icon, onOpen, value, meta }: PanelCardProps) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group flex w-full items-start gap-3 rounded-md border border-surface-border bg-surface-panel p-4 text-left shadow-card transition-colors duration-150 ease-standard hover:border-primary-200 hover:bg-primary-50/40"
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm bg-primary-50 text-primary-600">
        <Icon name={icon} size={17} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span className="text-h3 text-ink">{title}</span>
          <Icon
            name="arrow-right"
            size={13}
            className="text-ink-muted transition-transform duration-150 ease-standard group-hover:translate-x-0.5"
          />
        </span>
        <span className="mt-0.5 block text-caption text-ink-muted">{hint}</span>
        {value && (
          <span className="mt-1.5 block text-body font-medium text-ink">{value}</span>
        )}
        {meta && <span className="mt-0.5 block text-caption text-ink-muted">{meta}</span>}
      </span>
    </button>
  );
}
