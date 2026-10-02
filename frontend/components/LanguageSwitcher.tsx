"use client";

import { Icon } from "./Icon";
import { useLanguage, type Language } from "@/lib/i18n";

const OPTIONS: { value: Language; labelKey: "language.en" | "language.sw" }[] = [
  { value: "en", labelKey: "language.en" },
  { value: "sw", labelKey: "language.sw" },
];

/**
 * A two-option segmented control rather than a dropdown: there are only two
 * languages, and a switch is faster to hit and easier to read than a menu.
 *
 * `aria-pressed` carries the state so it is announced, and each button names
 * the language in that language — a user who cannot read the current UI still
 * recognises their own.
 */
export function LanguageSwitcher({ className = "" }: { className?: string }) {
  const { language, setLanguage, t } = useLanguage();

  return (
    <div
      role="group"
      aria-label={t("language.switch")}
      className={`inline-flex items-center gap-0.5 rounded-sm border border-surface-border bg-surface-sunken p-0.5 ${className}`}
    >
      {OPTIONS.map((option) => {
        const active = language === option.value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => setLanguage(option.value)}
            aria-pressed={active}
            lang={option.value}
            title={t(option.labelKey)}
            className={`inline-flex min-h-[28px] items-center gap-1.5 rounded-[3px] px-2 text-caption font-medium transition-colors duration-150 ease-standard ${
              active
                ? "bg-surface-panel text-ink shadow-card"
                : "text-ink-muted hover:text-ink"
            }`}
          >
            {option.value === "en" ? (
              <span className="font-mono text-[11px] tracking-wide">EN</span>
            ) : (
              <span className="font-mono text-[11px] tracking-wide">SW</span>
            )}
            <span className="hidden sm:inline">{t(option.labelKey)}</span>
          </button>
        );
      })}
    </div>
  );
}

/**
 * The same control, sized for the sidebar footer. The sidebar is dark, so the
 * neutral tokens would be unreadable there; it needs its own colour set.
 */
export function SidebarLanguageSwitcher() {
  const { language, setLanguage, t } = useLanguage();

  return (
    <div
      role="group"
      aria-label={t("language.switch")}
      className="rounded-md border border-white/10 bg-white/5 p-0.5"
    >
      <div className="flex items-center gap-0.5">
        {OPTIONS.map((option) => {
          const active = language === option.value;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => setLanguage(option.value)}
              aria-pressed={active}
              lang={option.value}
              className={`flex min-h-[32px] flex-1 items-center justify-center gap-1.5 rounded-[4px] px-2 text-caption font-medium transition-colors duration-150 ease-standard ${
                active
                  ? "bg-white/15 text-white"
                  : "text-neutral-400 hover:bg-white/10 hover:text-white"
              }`}
            >
              {active && <Icon name="check" size={12} />}
              <span>{t(option.labelKey)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default LanguageSwitcher;
