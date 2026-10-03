"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";

import { Button } from "./Button";
import { Icon } from "./Icon";
import { DatasetSummary, UserProfile } from "@/lib/api";
import { PIPELINE_PHASES, PIPELINE_STAGES } from "@/lib/pipeline";
import { useLogout } from "@/lib/useAuth";

type MenuKey = "help" | "activity" | "user";

interface TopBarProps {
  user: UserProfile | null;
  /** The signed-in user's datasets, newest first — powers search + activity. */
  datasets: DatasetSummary[];
  onOpenMenu: () => void;
}

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

/**
 * The bar above every screen: search, help, activity and the user menu.
 *
 * Every panel is fed by data the product already has, because a menu that
 * looks like a feature and does nothing is worse than no menu:
 *
 * - Search filters the user's own datasets (the API returns them newest first)
 *   and links straight to the dataset page. It cannot search projects or
 *   analyses because no endpoint returns those by text, so the placeholder
 *   says exactly what it searches instead of promising more.
 * - "Shughuli" is a recent-activity view built from `uploaded_at` on the user's
 *   own datasets — not a notification feed with no producer behind it.
 * - "Msaada" is generated from `lib/pipeline.ts`, so it can never describe a
 *   workflow different from the one the app runs.
 */
export function TopBar({ user, datasets, onOpenMenu }: TopBarProps) {
  const router = useRouter();
  const logout = useLogout();
  const headerRef = useRef<HTMLElement | null>(null);
  const [openMenu, setOpenMenu] = useState<MenuKey | null>(null);
  const [query, setQuery] = useState("");
  const [searchActive, setSearchActive] = useState(false);
  const searchRef = useRef<HTMLInputElement | null>(null);

  const trimmedQuery = query.trim().toLowerCase();
  const matches = trimmedQuery
    ? datasets
        .filter((dataset) =>
          dataset.original_filename.toLowerCase().includes(trimmedQuery)
        )
        .slice(0, 6)
    : [];
  const showResults = searchActive && trimmedQuery.length > 0;

  useEffect(() => {
    function closeOnOutsideClick(event: MouseEvent) {
      if (headerRef.current?.contains(event.target as Node)) return;
      setOpenMenu(null);
      setSearchActive(false);
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setOpenMenu(null);
      setSearchActive(false);
      setQuery("");
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    // Ctrl/Cmd+K focuses search, matching the hint rendered beside the field.
    function focusSearch(event: KeyboardEvent) {
      if (event.key.toLowerCase() !== "k") return;
      if (!(event.ctrlKey || event.metaKey)) return;
      event.preventDefault();
      searchRef.current?.focus();
      setSearchActive(true);
    }
    document.addEventListener("keydown", focusSearch);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
      document.removeEventListener("keydown", focusSearch);
    };
  }, []);

  function toggleMenu(key: MenuKey) {
    setSearchActive(false);
    setOpenMenu((current) => (current === key ? null : key));
  }

  function handleSearchSubmit(event: FormEvent) {
    event.preventDefault();
    setSearchActive(false);
    router.push("/datasets");
  }

  const phasesWithStages = PIPELINE_PHASES.map((phase) => ({
    ...phase,
    stages: PIPELINE_STAGES.filter((stage) => stage.phase === phase.key),
  }));

  const menuButton =
    "flex h-9 items-center gap-1.5 rounded px-2 text-body text-ink-secondary transition-colors duration-150 ease-standard hover:bg-surface-sunken";

  return (
    <header
      ref={headerRef}
      className="sticky top-0 z-30 flex h-[70px] items-center gap-2 border-b border-surface-border bg-surface-panel/90 px-4 backdrop-blur-[14px] sm:gap-3 sm:px-6 lg:px-[27px]"
    >
      <button
        type="button"
        aria-label="Fungua menyu"
        onClick={onOpenMenu}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded text-ink-secondary transition-colors hover:bg-surface-sunken lg:hidden"
      >
        <Icon name="menu" size={22} />
      </button>

      <Link
        href="/dashboard"
        aria-label="StatFlow nyumbani"
        className="flex shrink-0 items-center lg:hidden"
      >
        <span className="flex h-8 w-8 items-center justify-center rounded bg-primary-600 text-white">
          <Icon name="chart-line" size={18} />
        </span>
      </Link>

      <form
        role="search"
        onSubmit={handleSearchSubmit}
        className="relative min-w-0 max-w-md flex-1"
      >
        <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-muted">
          <Icon name="search" size={16} />
        </span>
        <input
          ref={searchRef}
          type="search"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setSearchActive(true);
          }}
          onFocus={() => setSearchActive(true)}
          placeholder="Search projects, datasets, analyses…"
          aria-label="Search projects, datasets, analyses"
          className="h-[37px] w-full rounded-md border border-transparent bg-surface-sunken pl-8 pr-14 text-body text-ink transition-colors duration-200 ease-standard placeholder:text-ink-muted focus:border-[#CFC7F8] focus:bg-surface-panel focus:outline-none focus:ring-0 [&::-webkit-search-cancel-button]:appearance-none"
        />
        {/*
          Keyboard hint. Wired to the real shortcut rather than left as
          decoration: a badge that lies about a binding is worse than none.
        */}
        <kbd className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 items-center gap-0.5 rounded border border-surface-border bg-surface-panel px-1.5 py-0.5 font-mono text-[10px] text-ink-muted sm:inline-flex">
          Ctrl K
        </kbd>

        {showResults && (
          <div className="absolute left-0 right-0 top-full z-40 mt-2 overflow-hidden rounded-md border border-surface-border bg-surface-panel shadow-overlay">
            {matches.length === 0 ? (
              <div className="px-3 py-3">
                <p className="text-body text-ink-secondary">
                  Hakuna dataset inayolingana na “{query.trim()}”.
                </p>
                <Link
                  href="/upload"
                  onClick={() => {
                    setQuery("");
                    setSearchActive(false);
                  }}
                  className="mt-1 inline-block text-caption font-medium text-primary-700 hover:underline"
                >
                  Pakia faili jipya
                </Link>
              </div>
            ) : (
              <ul>
                {matches.map((dataset) => (
                  <li
                    key={dataset.id}
                    className="border-b border-surface-border last:border-0"
                  >
                    <Link
                      href={`/datasets/${dataset.id}`}
                      onClick={() => {
                        setQuery("");
                        setSearchActive(false);
                      }}
                      className="flex items-start justify-between gap-3 px-3 py-2 transition-colors hover:bg-surface-sunken"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-body font-medium text-ink">
                          {dataset.original_filename}
                        </span>
                        <span className="block text-caption text-ink-muted">
                          Safu {dataset.row_count.toLocaleString()} · Columns{" "}
                          {dataset.column_count} · {dataset.status}
                        </span>
                      </span>
                      <Icon
                        name="arrow-right"
                        size={14}
                        className="mt-1 shrink-0 text-ink-muted"
                      />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            <Link
              href="/datasets"
              onClick={() => {
                setQuery("");
                setSearchActive(false);
              }}
              className="block border-t border-surface-border px-3 py-2 text-caption font-medium text-primary-700 hover:bg-surface-sunken"
            >
              Datasets zote ({datasets.length})
            </Link>
          </div>
        )}
      </form>

      <div className="ml-auto flex shrink-0 items-center gap-1">
        <Link href="/upload" aria-label="Pakia data">
          <Button size="small" icon="upload" className="hidden sm:inline-flex">
            <span className="hidden md:inline">Pakia data</span>
          </Button>
        </Link>
        <Link
          href="/upload"
          aria-label="Pakia data"
          className="flex h-11 w-11 items-center justify-center rounded text-ink-secondary hover:bg-surface-sunken sm:hidden"
        >
          <Icon name="upload" size={20} />
        </Link>

        <div className="relative hidden sm:block">
          <button
            type="button"
            aria-haspopup="true"
            aria-expanded={openMenu === "help"}
            onClick={() => toggleMenu("help")}
            className={menuButton}
          >
            <Icon name="info" size={18} />
            <span className="hidden xl:inline">Msaada</span>
          </button>
          {openMenu === "help" && (
            <div className="absolute right-0 top-full z-40 mt-2 w-80 rounded-md border border-surface-border bg-surface-panel p-3 shadow-overlay">
              <p className="text-overline uppercase tracking-wide text-ink-muted">
                Mwongozo wa mtiririko
              </p>
              <p className="mt-1 text-caption text-ink-secondary">
                Hatua 6, na kazi zake ndani ya kila moja.
              </p>
              <ul className="mt-2 space-y-2">
                {phasesWithStages.map((phase) => (
                  <li key={phase.key}>
                    <p className="text-body font-medium text-ink">{phase.label}</p>
                    <p className="text-caption text-ink-muted">
                      {phase.stages.map((stage) => stage.fullLabel).join(" · ")}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="relative">
          <button
            type="button"
            aria-haspopup="true"
            aria-expanded={openMenu === "activity"}
            onClick={() => toggleMenu("activity")}
            aria-label="Shughuli za hivi karibuni"
            className={menuButton}
          >
            <Icon name="history" size={18} />
            <span className="hidden xl:inline">Shughuli</span>
          </button>
          {openMenu === "activity" && (
            <div className="absolute right-0 top-full z-40 mt-2 w-80 rounded-md border border-surface-border bg-surface-panel p-3 shadow-overlay">
              <p className="text-overline uppercase tracking-wide text-ink-muted">
                Shughuli za hivi karibuni
              </p>
              <p className="mt-1 text-caption text-ink-secondary">
                Datasets zako, mpya kwanza.
              </p>
              {datasets.length === 0 ? (
                <p className="mt-3 text-body text-ink-muted">
                  Hakuna dataset bado. Pakia faili lako la kwanza.
                </p>
              ) : (
                <ul className="mt-2 divide-y divide-surface-border">
                  {datasets.slice(0, 5).map((dataset) => (
                    <li key={dataset.id}>
                      <Link
                        href={`/datasets/${dataset.id}`}
                        onClick={() => setOpenMenu(null)}
                        className="flex items-center justify-between gap-3 py-2 transition-colors hover:text-primary-700"
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-body text-ink">
                            {dataset.original_filename}
                          </span>
                          <span className="block text-caption text-ink-muted">
                            {dataset.status} · {formatTimestamp(dataset.uploaded_at)}
                          </span>
                        </span>
                        <Icon
                          name="arrow-right"
                          size={14}
                          className="shrink-0 text-ink-muted"
                        />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              <Link
                href="/datasets"
                onClick={() => setOpenMenu(null)}
                className="mt-2 block border-t border-surface-border pt-2 text-caption font-medium text-primary-700 hover:underline"
              >
                Datasets zote
              </Link>
            </div>
          )}
        </div>

        <div className="relative">
          <button
            type="button"
            aria-haspopup="true"
            aria-expanded={openMenu === "user"}
            onClick={() => toggleMenu("user")}
            className={`${menuButton} max-w-[12rem]`}
          >
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-600 text-white">
              <Icon name="user" size={16} />
            </span>
            <span className="hidden truncate sm:inline">
              {user?.full_name ?? "Mtumiaji"}
            </span>
            <Icon name="chevron-down" size={14} className="shrink-0" />
          </button>
          {openMenu === "user" && (
            <div className="absolute right-0 top-full z-40 mt-2 w-64 rounded-md border border-surface-border bg-surface-panel p-2 shadow-overlay">
              <div className="px-2 py-1.5">
                <p className="truncate text-body font-medium text-ink">
                  {user?.full_name ?? "Mtumiaji"}
                </p>
                <p className="truncate text-caption text-ink-muted">{user?.email ?? ""}</p>
              </div>
              <div className="my-1 border-t border-surface-border" />
              {user?.system_role && (
                <Link
                  href="/admin"
                  onClick={() => setOpenMenu(null)}
                  className="flex items-center gap-2 rounded px-2 py-2 text-body text-ink-secondary transition-colors hover:bg-surface-sunken"
                >
                  <Icon name="shield" size={16} />
                  Admin portal
                </Link>
              )}
              <Button
                variant="ghost"
                size="small"
                onClick={logout}
                className="w-full justify-start text-danger hover:bg-danger-bg"
              >
                <Icon name="logout" size={16} />
                Toka (logout)
              </Button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

export default TopBar;
