"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { dictionaries, en, type TranslationKey } from "./dictionaries";

export type Language = "en" | "sw";

/**
 * English is the product default. Swahili is offered because the team and its
 * users work in it, not because it is a nicety layered on afterwards.
 */
export const DEFAULT_LANGUAGE: Language = "en";

const STORAGE_KEY = "statflow.language";

const LOCALE: Record<Language, string> = {
  en: "en-GB",
  sw: "en-KE",
};

interface LanguageContextValue {
  language: Language;
  setLanguage: (language: Language) => void;
  /** BCP-47 tag for `Intl` formatting, so numbers and dates follow the choice. */
  locale: string;
  /**
   * Look up a key. Unknown keys return the key itself rather than an empty
   * string, so a missing translation is visible during review instead of
   * silently rendering a blank label.
   */
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string;
  /** Nullish renders as the em dash, not as "0" or "NaN". */
  formatNumber: (value: number | null | undefined, options?: Intl.NumberFormatOptions) => string;
  formatDate: (value: string | Date | null | undefined, options?: Intl.DateTimeFormatOptions) => string;
  /** "3 hours ago", in the chosen language. Falls back to an absolute date. */
  formatRelative: (value: string | null | undefined) => string;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

function isLanguage(value: unknown): value is Language {
  return value === "en" || value === "sw";
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>(DEFAULT_LANGUAGE);

  // Read the stored choice after mount, never during render: the server has no
  // localStorage, so reading it there would make the first client paint
  // disagree with the server HTML.
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (isLanguage(stored)) setLanguageState(stored);
    } catch {
      // Private browsing or a blocked storage partition. The default stands.
    }
  }, []);

  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // The choice still applies for this session; it just will not persist.
    }
  }, []);

  // Keep the document language honest for screen readers and hyphenation.
  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const t = useCallback(
    (key: TranslationKey, vars?: Record<string, string | number>) => {
      const table = dictionaries[language];
      const template = (table[key] ?? en[key] ?? key) as string;
      if (!vars) return template;
      return template.replace(/\{(\w+)\}/g, (match, name: string) =>
        name in vars ? String(vars[name]) : match,
      );
    },
    [language],
  );

  const formatNumber = useCallback(
    (value: number | null | undefined, options?: Intl.NumberFormatOptions) => {
      if (value === null || value === undefined || !Number.isFinite(value)) return "\u2014";
      return new Intl.NumberFormat(LOCALE[language], options).format(value);
    },
    [language],
  );

  const formatDate = useCallback(
    (
      value: string | Date | null | undefined,
      options?: Intl.DateTimeFormatOptions,
    ) => {
      if (!value) return "—";
      const date = value instanceof Date ? value : new Date(value);
      if (Number.isNaN(date.getTime())) return "—";
      return new Intl.DateTimeFormat(
        LOCALE[language],
        options ?? { dateStyle: "medium", timeStyle: "short" },
      ).format(date);
    },
    [language],
  );

  const formatRelative = useCallback(
    (value: string | null | undefined) => {
      if (!value) return "—";
      const stamp = new Date(value).getTime();
      if (!Number.isFinite(stamp)) return "—";
      const seconds = Math.round((Date.now() - stamp) / 1000);
      const future = seconds < 0;
      const abs = Math.abs(seconds);
      if (abs < 60) return t("time.now");
      const minutes = Math.round(abs / 60);
      if (minutes < 60) return t(future ? "time.inMinutes" : "time.minutesAgo", { count: minutes });
      const hours = Math.round(minutes / 60);
      if (hours < 24) return t(future ? "time.inHours" : "time.hoursAgo", { count: hours });
      const days = Math.round(hours / 24);
      if (days < 30) return t(future ? "time.inDays" : "time.daysAgo", { count: days });
      return formatDate(value, { dateStyle: "medium" });
    },
    [t, formatDate],
  );

  const value = useMemo<LanguageContextValue>(
    () => ({
      language,
      setLanguage,
      locale: LOCALE[language],
      t,
      formatNumber,
      formatDate,
      formatRelative,
    }),
    [language, setLanguage, t, formatNumber, formatDate, formatRelative],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useLanguage must be used inside <LanguageProvider>");
  }
  return context;
}

export type { TranslationKey };
