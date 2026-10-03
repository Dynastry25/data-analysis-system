"use client";

import { Icon } from "./Icon";

interface InlineSearchProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  label: string;
}

/**
 * The prototype's bordered search input with a leading magnifier.
 *
 * The native `type="search"` cancel button is suppressed: it renders with the
 * platform's own styling, which ignores the panel background and leaves a
 * stray white box inside a warm-grey field.
 */
export function InlineSearch({
  value,
  onChange,
  placeholder = "Search...",
  label,
}: InlineSearchProps) {
  return (
    <div className="flex h-9 w-full items-center gap-2 rounded-lg border border-surface-border bg-surface-panel px-3 text-ink-faint transition-colors focus-within:border-primary-400 focus-within:ring-2 focus-within:ring-primary-500/15 sm:w-[250px]">
      <Icon name="search" size={15} className="shrink-0" />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={label}
        className="min-w-0 flex-1 border-0 bg-transparent text-body text-ink outline-none placeholder:text-ink-faint [&::-webkit-search-cancel-button]:appearance-none"
      />
    </div>
  );
}

export default InlineSearch;