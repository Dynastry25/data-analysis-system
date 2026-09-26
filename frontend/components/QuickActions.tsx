"use client";

import Link from "next/link";

import { Icon, IconName } from "./Icon";

export interface QuickAction {
  icon: IconName;
  label: string;
  description: string;
  href: string;
}

/** Grid of shortcut cards to the platform's main features. */
export function QuickActions({ actions }: { actions: QuickAction[] }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {actions.map((action) => (
        <Link
          key={action.label}
          href={action.href}
          className="group flex h-full flex-col rounded-lg border border-surface-border bg-surface-panel p-4 shadow-card transition-all duration-150 ease-standard hover:border-primary-300 hover:shadow-raised"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-md bg-primary-50 text-primary-600 transition-colors duration-150 ease-standard group-hover:bg-primary-100">
            <Icon name={action.icon} size={18} />
          </span>
          <p className="mt-3 text-body-lg font-medium text-ink">{action.label}</p>
          <p className="mt-0.5 flex-1 text-caption text-ink-secondary">
            {action.description}
          </p>
          <span className="mt-3 inline-flex items-center gap-1 text-caption font-medium text-primary-600 transition-all duration-150 ease-standard group-hover:gap-2">
            Fungua
            <Icon name="arrow-right" size={14} />
          </span>
        </Link>
      ))}
    </div>
  );
}

export default QuickActions;