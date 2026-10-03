"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuthGuard } from "@/lib/useAuth";
import { api, DatasetSummary, UserProfile } from "@/lib/api";
import {
  PIPELINE_PHASES,
  PIPELINE_STAGES,
  PipelinePhaseKey,
  StageProgressInput,
  hrefForPhase,
  phaseFromStep,
  pipelineStageFromPathname,
} from "@/lib/pipeline";
import { useLanguage, type TranslationKey } from "@/lib/i18n";
import { Icon, IconName } from "./Icon";
import { JourneyRail } from "./JourneyRail";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { TopBar } from "./TopBar";
import { WorkflowStrip } from "./WorkflowStrip";

interface SidebarEntry {
  key: string;
  /** Resolved through the translation table, so the nav follows the language. */
  labelKey: TranslationKey;
  descriptionKey: TranslationKey;
  href: string;
  icon: IconName;
}

/**
 * The sidebar, in the order the StatFlow design lays it out: the three
 * destinations that stand on their own, then the five workflow phases.
 */
const FIXED_NAV: SidebarEntry[] = [
  {
    key: "dashboard",
    labelKey: "nav.dashboard",
    descriptionKey: "nav.dashboard.desc",
    href: "/dashboard",
    icon: "dashboard",
  },
  {
    key: "projects",
    labelKey: "nav.projects",
    descriptionKey: "nav.projects.desc",
    href: "/organizations",
    icon: "folder",
  },
  {
    key: "data",
    labelKey: "nav.data",
    descriptionKey: "nav.data.desc",
    href: "/datasets",
    icon: "database",
  },
  {
    key: "templates",
    labelKey: "nav.templates",
    descriptionKey: "nav.templates.desc",
    href: "/templates",
    icon: "clipboard",
  },
  {
    key: "activity",
    labelKey: "nav.activity",
    descriptionKey: "nav.activity.desc",
    href: "/activity",
    icon: "history",
  },
];

/**
 * The workflow phases the sidebar lists after Data. `data` itself is already
 * the Data entry above, so listing it twice would only add noise.
 */
const PHASE_ICON: Record<PipelinePhaseKey, IconName> = {
  data: "database",
  prepare: "sliders",
  analyze: "calculator",
  visualize: "chart",
  explain: "sparkles",
  report: "file-text",
};

/**
 * The bottom group: screens that stand outside the data workflow. They are
 * separate from the phases because none of them is a stage -- they are
 * account, reference and history.
 */
const SECONDARY_NAV: SidebarEntry[] = [
  {
    key: "profile",
    labelKey: "nav.profile",
    descriptionKey: "nav.profile.desc",
    href: "/profile",
    icon: "user",
  },
  {
    key: "settings",
    labelKey: "nav.settings",
    descriptionKey: "nav.settings.desc",
    href: "/settings",
    icon: "sliders",
  },
  {
    key: "help",
    labelKey: "nav.help",
    descriptionKey: "nav.help.desc",
    href: "/help",
    icon: "info",
  },
];

const SIDEBAR_PHASES = PIPELINE_PHASES.filter((phase) => phase.key !== "data");

/**
 * Which sidebar entry is current.
 *
 * The dataset routes have no section of their own, so they map by the phase
 * their URL belongs to — which is what `lib/pipeline.ts` already knows.
 * An unknown route highlights nothing rather than guessing.
 */
function activeNavKey(pathname: string, stage: number | null): string | null {
  if (pathname === "/dashboard") return "dashboard";
  if (pathname === "/organizations" || pathname.startsWith("/organizations/")) {
    return "projects";
  }
  if (pathname === "/datasets" || pathname === "/upload") return "data";
  if (pathname === "/templates") return "templates";
  if (pathname === "/activity") return "activity";
  if (pathname === "/profile") return "profile";
  if (pathname === "/settings") return "settings";
  if (pathname === "/help") return "help";
  return phaseFromStep(stage)?.key ?? null;
}

interface AppShellProps {
  title: string;
  description?: string;
  /** Small caps label above the title, e.g. "WORKSPACE OVERVIEW". */
  eyebrow?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}

function Brand() {
  return (
    <Link href="/dashboard" className="flex items-center gap-2.5">
      <span className="flex h-9 w-9 items-center justify-center rounded-md bg-primary-600 text-white">
        <Icon name="chart-line" size={20} />
      </span>
      <span>
        <span className="block text-h3 leading-tight text-white">StatFlow</span>
        <span className="block text-caption text-neutral-400">Data Analysis</span>
      </span>
    </Link>
  );
}

function Breadcrumbs({ datasetId, pathname }: { datasetId: number; pathname: string }) {
  const section = pathname.split("/")[3] ?? null;
  // Stage links carry a query string, so match on the path and fall back to the
  // section name rather than comparing full hrefs.
  const stage = PIPELINE_STAGES.find((entry) => {
    const href = entry.hrefFor(datasetId);
    return href === pathname || href.split("?")[0] === pathname;
  });
  return (
    <nav aria-label="Njia" className="mb-2">
      <ol className="flex flex-wrap items-center gap-1.5 text-caption text-ink-muted">
        <li>
          <Link href="/datasets" className="transition-colors hover:text-primary-700">
            Data
          </Link>
        </li>
        <li aria-hidden="true" className="text-neutral-300">
          <Icon name="chevron-right" size={12} />
        </li>
        <li>
          <Link
            href={`/datasets/${datasetId}`}
            className="transition-colors hover:text-primary-700"
          >
            Dataset #{datasetId}
          </Link>
        </li>
        {section && (
          <>
            <li aria-hidden="true" className="text-neutral-300">
              <Icon name="chevron-right" size={12} />
            </li>
            <li aria-current="page" className="font-medium text-ink-secondary">
              {stage?.label ?? section}
            </li>
          </>
        )}
      </ol>
    </nav>
  );
}

/**
 * The user-facing shell, arranged the way the StatFlow design lays it out:
 * a dark sidebar, a top bar (search / help / activity / account), the workflow
 * strip (DATA → PREPARE → ANALYZE → VISUALIZE → EXPLAIN → REPORT), then the page.
 *
 * Two rules keep the arrangement honest:
 *
 * - The sidebar and the strip take their targets from `lib/pipeline.ts`, so a
 *   phase can never point at two different screens.
 * - A phase needs a dataset. Inside a dataset the links act on that one;
 *   anywhere else they act on the most recent dataset, and the strip says which
 *   so the links never hide their target. With no datasets at all every phase
 *   resolves to `/upload`, which is the truth.
 */
export function AppShell({
  title,
  description,
  eyebrow,
  actions,
  children,
}: AppShellProps) {
  const ready = useAuthGuard();
  const pathname = usePathname();
  const { t } = useLanguage();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [journeyProgress, setJourneyProgress] = useState<StageProgressInput | null>(
    null
  );

  const pipeline = pipelineStageFromPathname(pathname);
  const latestDataset = datasets[0] ?? null;
  const targetDatasetId = pipeline.datasetId ?? latestDataset?.id ?? null;
  const activeKey = activeNavKey(pathname, pipeline.stage);

  const activeDataset =
    pipeline.datasetId !== null
      ? (datasets.find((entry) => entry.id === pipeline.datasetId) ?? null)
      : latestDataset;
  const contextLabel =
    pipeline.datasetId !== null && activeDataset === null
      ? `Inafanya kazi kwenye: Dataset #${pipeline.datasetId}`
      : activeDataset
        ? `Inafanya kazi kwenye: ${activeDataset.original_filename}`
        : "Hakuna dataset bado · anza kwa kupakia data";

  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  // The journey rail lives in the shell so all 11 stages are visible from every
  // dataset page, not just the one that happens to render a stepper.
  useEffect(() => {
    const datasetId = pipelineStageFromPathname(pathname).datasetId;
    if (datasetId === null || !ready) {
      setJourneyProgress(null);
      return;
    }
    let cancelled = false;
    api.datasets
      .journey(datasetId)
      .then((response) => {
        if (cancelled) return;
        const stage = (key: string) =>
          response.stages.find((entry) => entry.key === key);
        setJourneyProgress({
          status: response.dataset_status,
          profiledColumnCount: stage("profile")?.record_count ?? 0,
          cleanOperationCount: stage("clean")?.record_count ?? 0,
          transformOperationCount: stage("transform")?.record_count ?? 0,
          analysisRunCount: stage("analyze")?.record_count ?? 0,
          chartCount: stage("visualize")?.record_count ?? 0,
          exportCount: stage("export")?.record_count ?? 0,
        });
      })
      .catch(() => {
        // A journey that cannot load must not break the page it decorates.
        if (!cancelled) setJourneyProgress(null);
      });
    return () => {
      cancelled = true;
    };
  }, [pathname, ready]);

  useEffect(() => {
    if (!drawerOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setDrawerOpen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = "";
    };
  }, [drawerOpen]);

  useEffect(() => {
    api.auth
      .me()
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  // The dataset list feeds three things the shell owns: the search box, the
  // activity menu, and where the phase links point when the URL has no dataset.
  // A list that fails to load must degrade to "no datasets known", not break
  // the page it decorates.
  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    api.datasets
      .list()
      .then((response) => {
        if (!cancelled) setDatasets(response);
      })
      .catch(() => {
        if (!cancelled) setDatasets([]);
      });
    return () => {
      cancelled = true;
    };
  }, [ready, pathname]);

  if (!ready) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-surface-canvas">
        <div className="flex flex-col items-center gap-3">
          <span className="h-6 w-6 animate-spin rounded-full border-2 border-primary-600 border-t-transparent" />
          <p className="text-body text-ink-muted">Inapakia…</p>
        </div>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-surface-canvas lg:flex">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:inline-flex focus:h-10 focus:items-center focus:rounded focus:bg-primary-600 focus:px-4 focus:text-body focus:font-medium focus:text-white"
      >
        Nenda kwenye maudhui makuu
      </a>

      {drawerOpen && (
        <div
          aria-hidden="true"
          onClick={() => setDrawerOpen(false)}
          className="fixed inset-0 z-40 bg-sidebar-deep/60 lg:hidden"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-[232px] transform flex-col bg-sidebar transition-transform duration-300 ease-standard lg:static lg:translate-x-0 ${
          drawerOpen ? "translate-x-0 shadow-drawer" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-4 py-6">
          <Brand />
          <button
            type="button"
            aria-label="Funga menyu"
            onClick={() => setDrawerOpen(false)}
            className="flex h-11 w-11 items-center justify-center rounded text-neutral-300 transition-colors hover:bg-white/10 lg:hidden"
          >
            <Icon name="close" size={22} />
          </button>
        </div>

        <nav aria-label="Urambazaji kuu" className="flex-1 overflow-y-auto px-3 pb-4">
          <ul className="space-y-1">
            {FIXED_NAV.map((item) => {
              const active = activeKey === item.key;
              return (
                <li key={item.key} className="relative">
                  {active && (
                    <span aria-hidden="true" className="absolute inset-y-1.5 left-0 w-1 rounded-full bg-primary-400" />
                  )}
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    title={t(item.descriptionKey)}
                    className={`flex min-h-[39px] items-center gap-[11px] rounded-md py-2 pl-[11px] pr-[11px] text-[12.5px] transition-colors duration-150 ease-standard ${
                      active
                        ? "bg-sidebar-active font-medium text-white shadow-[inset_3px_0_0_0_var(--brand)]"
                        : "text-neutral-300 hover:bg-white/[0.06] hover:text-white"
                    }`}
                  >
                    <Icon name={item.icon} size={20} />
                    {t(item.labelKey)}
                  </Link>
                </li>
              );
            })}
          </ul>

          <p className="px-3 pb-2 pt-6 text-overline uppercase tracking-wide text-neutral-400">
            {t("nav.workspace")}
          </p>
          <ul className="space-y-1">
            {SIDEBAR_PHASES.map((phase) => {
              const active = activeKey === phase.key;
              const stageList = PIPELINE_STAGES.filter(
                (stage) => stage.phase === phase.key
              );
              return (
                <li key={phase.key} className="relative">
                  {active && (
                    <span aria-hidden="true" className="absolute inset-y-1.5 left-0 w-1 rounded-full bg-primary-400" />
                  )}
                  <Link
                    href={hrefForPhase(phase.key, targetDatasetId)}
                    aria-current={active ? "page" : undefined}
                    title={stageList.map((stage) => stage.fullLabel).join(" · ")}
                    className={`flex min-h-[39px] items-center gap-[11px] rounded-md py-2 pl-[11px] pr-[11px] text-[12.5px] transition-colors duration-150 ease-standard ${
                      active
                        ? "bg-sidebar-active font-medium text-white shadow-[inset_3px_0_0_0_var(--brand)]"
                        : "text-neutral-300 hover:bg-white/[0.06] hover:text-white"
                    }`}
                  >
                    <Icon name={PHASE_ICON[phase.key]} size={20} />
                    {phase.label}
                  </Link>
                </li>
              );
            })}
          </ul>
          <p className="px-3 pb-2 pt-6 text-overline uppercase tracking-wide text-neutral-400">
            {t("nav.more")}
          </p>
          <ul className="space-y-1">
            {SECONDARY_NAV.map((item) => {
              const active = activeKey === item.key;
              return (
                <li key={item.key} className="relative">
                  {active && (
                    <span aria-hidden="true" className="absolute inset-y-1.5 left-0 w-1 rounded-full bg-primary-400" />
                  )}
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    title={t(item.descriptionKey)}
                    className={`flex min-h-[39px] items-center gap-[11px] rounded-md py-2 pl-[11px] pr-[11px] text-[12.5px] transition-colors duration-150 ease-standard ${
                      active
                        ? "bg-sidebar-active font-medium text-white shadow-[inset_3px_0_0_0_var(--brand)]"
                        : "text-neutral-300 hover:bg-white/[0.06] hover:text-white"
                    }`}
                  >
                    <Icon name={item.icon} size={20} />
                    {t(item.labelKey)}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="border-t border-white/10 p-3">
          <LanguageSwitcher className="mb-2 w-full [&>button]:flex-1" />
          {user?.system_role && (
            <Link
              href="/admin"
              className="flex min-h-[44px] items-center gap-3 rounded-md px-3 text-caption text-neutral-300 transition-colors duration-150 ease-standard hover:bg-white/10 hover:text-white"
            >
              <Icon name="shield" size={18} />
              {t("nav.admin")}
            </Link>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          user={user}
          datasets={datasets}
          onOpenMenu={() => setDrawerOpen(true)}
        />

        <WorkflowStrip
          datasetId={targetDatasetId}
          currentStage={pipeline.stage}
          contextLabel={contextLabel}
        />

        <main id="main-content" className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-content">
            <header className="mb-5">
              {pipeline.datasetId !== null && (
                <Breadcrumbs datasetId={pipeline.datasetId} pathname={pathname} />
              )}
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  {eyebrow && (
                    <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.12em] text-primary-600">
                      {eyebrow}
                    </span>
                  )}
                  <h1 className="font-display text-h1 tracking-[-0.015em] text-ink">
                    {title}
                  </h1>
                  {description && (
                    <p className="mt-1.5 max-w-3xl text-body text-ink-muted">
                      {description}
                    </p>
                  )}
                </div>
                {actions && (
                  <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
                )}
              </div>
            </header>

            {pipeline.datasetId !== null && journeyProgress && (
              <JourneyRail
                datasetId={pipeline.datasetId}
                currentStage={pipeline.stage}
                progress={journeyProgress}
              />
            )}

            <div className="space-y-6">{children}</div>
          </div>
        </main>
      </div>
    </div>
  );
}

export default AppShell;

