"use client";

import { useEffect, useRef } from "react";

import { Icon, IconName } from "./Icon";

interface ModalProps {
  open: boolean;
  title: string;
  description?: string;
  icon?: IconName;
  onClose: () => void;
  children: React.ReactNode;
  /** Sticky action row at the bottom, e.g. a primary button with its hint. */
  footer?: React.ReactNode;
  /** Width cap, e.g. "sm:max-w-3xl". */
  widthClass?: string;
}

/**
 * A centred dialog for the screens a user opens on purpose.
 *
 * The analysis studio has three things the reader asks for occasionally — the
 * 156-method guide, the stage plan for the chosen method, and the run history —
 * and one thing they rarely want at all: the assumption checks. Inline, those
 * three push the run button and the results below the fold, so the page leads
 * with a list instead of with the task. This component holds them behind a
 * button and gives them the whole viewport when asked for.
 *
 * It follows the same conventions as the app's other overlay (`PanelDrawer`):
 * the sidebar-deep backdrop, Escape to close, focus moved in and restored on
 * close, and `role="dialog"` with `aria-modal` so the state is announced rather
 * than only implied by a backdrop.
 */
export function Modal({
  open,
  title,
  description,
  icon,
  onClose,
  children,
  footer,
  widthClass = "sm:max-w-3xl",
}: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    // A dialog tall enough to scroll has to be locked, or the page behind it
    // scrolls with the wheel over the backdrop.
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      previouslyFocused?.focus?.();
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center p-0 sm:items-center sm:p-4">
      <div aria-hidden="true" onClick={onClose} className="fixed inset-0 bg-sidebar-deep/60" />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={`relative z-50 flex max-h-[92vh] w-full ${widthClass} flex-col overflow-hidden rounded-t-xl border border-surface-border bg-surface-panel shadow-drawer focus:outline-none sm:rounded-xl`}
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

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-5">{children}</div>

        {footer && (
          <div className="border-t border-surface-border bg-surface-sunken px-4 py-3 sm:px-5">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

export default Modal;
