"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuthGuard, useLogout } from "@/lib/useAuth";
import { api, UserProfile } from "@/lib/api";
import { pipelineStageFromPathname, PIPELINE_STAGES } from "@/lib/pipeline";
import { Button } from "./Button";
import { Icon, IconName } from "./Icon";
import { PipelineStepper } from "./PipelineStepper";

const PRIMARY_NAV: { href: string; label: string; icon: IconName }[] = [
  { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { href: "/datasets", label: "Datasets zangu", icon: "database" },
  { href: "/organizations", label: "Mashirika", icon: "building" },
  { href: "/upload", label: "Pakia data", icon: "upload" },
];

interface AppShellProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}

function isActiveNav(pathname: string, href: string): boolean {
  if (href === "/datasets" || href === "/organizations") {
    return pathname === href || pathname.startsWith(`${href}/`);
  }
  return pathname === href;
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
  const stage = PIPELINE_STAGES.find((entry) => entry.hrefFor(datasetId) === pathname);
  return (
    <nav aria-label="Njia" className="mb-2">
      <ol className="flex flex-wrap items-center gap-1.5 text-caption text-ink-muted">
        <li>
          <Link href="/datasets" className="transition-colors hover:text-primary-700">
            Datasets
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

export function AppShell({ title, description, actions, children }: AppShellProps) {
  const ready = useAuthGuard();
  const logout = useLogout();
  const pathname = usePathname();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [user, setUser] = useState<UserProfile | null>(null);

  const pipeline = pipelineStageFromPathname(pathname);

  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

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

      <header className="sticky top-0 z-40 flex items-center justify-between border-b border-surface-border bg-neutral-900 px-4 py-3 lg:hidden">
        <Brand />
        <button
          type="button"
          aria-label="Fungua menyu"
          aria-expanded={drawerOpen}
          onClick={() => setDrawerOpen(true)}
          className="flex h-11 w-11 items-center justify-center rounded text-neutral-300 transition-colors hover:bg-neutral-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400"
        >
          <Icon name="menu" size={22} />
        </button>
      </header>

      {drawerOpen && (
        <div
          aria-hidden="true"
          onClick={() => setDrawerOpen(false)}
          className="fixed inset-0 z-40 bg-neutral-900/50 lg:hidden"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-64 transform flex-col bg-neutral-900 transition-transform duration-300 ease-standard lg:static lg:translate-x-0 ${
          drawerOpen ? "translate-x-0 shadow-drawer" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-4 py-5">
          <Brand />
          <button
            type="button"
            aria-label="Funga menyu"
            onClick={() => setDrawerOpen(false)}
            className="flex h-11 w-11 items-center justify-center rounded text-neutral-300 transition-colors hover:bg-neutral-800 lg:hidden"
          >
            <Icon name="close" size={22} />
          </button>
        </div>

        <nav aria-label="Urambazaji kuu" className="flex-1 overflow-y-auto px-3 pb-4">
          <p className="px-3 pb-2 pt-1 text-overline uppercase tracking-wide text-neutral-500">
            Kuu
          </p>
          <ul className="space-y-1">
            {PRIMARY_NAV.map((item) => {
              const active = isActiveNav(pathname, item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`flex min-h-[44px] items-center gap-3 rounded-md px-3 text-body transition-colors duration-150 ease-standard ${
                      active
                        ? "bg-primary-600 font-medium text-white"
                        : "text-neutral-300 hover:bg-neutral-800 hover:text-white"
                    }`}
                  >
                    <Icon name={item.icon} size={20} />
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>

          {pipeline.datasetId !== null && pipeline.stage !== null && (
            <>
              <p className="px-3 pb-2 pt-6 text-overline uppercase tracking-wide text-neutral-500">
                Mtiririko wa dataset
              </p>
              <ul className="space-y-0.5">
                {PIPELINE_STAGES.map((stage) => {
                  const active = pipeline.stage === stage.step;
                  const done = (pipeline.stage ?? 0) > stage.step;
                  const href =
                    pipeline.datasetId !== null
                      ? stage.hrefFor(pipeline.datasetId)
                      : "/upload";
                  return (
                    <li key={stage.key}>
                      <Link
                        href={href}
                        aria-current={active ? "step" : undefined}
                        className={`flex min-h-[40px] items-center gap-3 rounded-md px-3 text-body transition-colors duration-150 ease-standard ${
                          active
                            ? "bg-neutral-800 font-medium text-white"
                            : "text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100"
                        }`}
                      >
                        <span
                          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] ${
                            done
                              ? "bg-success/20 text-success"
                              : active
                                ? "bg-primary-600 text-white"
                                : "bg-neutral-800 text-neutral-500"
                          }`}
                        >
                          {done ? <Icon name="check" size={12} /> : stage.step}
                        </span>
                        {stage.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
              {pipeline.datasetId !== null && (
                <Link
                  href={`/datasets/${pipeline.datasetId}/ask`}
                  className="mt-2 flex min-h-[40px] items-center gap-3 rounded-md px-3 text-body text-neutral-400 transition-colors duration-150 ease-standard hover:bg-neutral-800 hover:text-neutral-100"
                >
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-neutral-800 text-neutral-500">
                    <Icon name="sparkles" size={12} />
                  </span>
                  Eleza (AI)
                </Link>
              )}
            </>
          )}
        </nav>

        <div className="border-t border-neutral-800 p-3">
          {user?.system_role && (
            <Link
              href="/admin"
              className="mb-1 flex min-h-[40px] items-center gap-3 rounded-md px-2 text-caption text-neutral-300 transition-colors duration-150 ease-standard hover:bg-neutral-800 hover:text-white"
            >
              <Icon name="shield" size={18} />
              Admin portal
            </Link>
          )}
          <div className="flex items-center gap-3 px-1 py-2">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-600 text-white">
              <Icon name="user" size={18} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-body text-white">
                {user?.full_name ?? "Mtumiaji"}
              </p>
              <p className="truncate text-caption text-neutral-400">{user?.email ?? ""}</p>
            </div>
          </div>
          <Button
            variant="ghost"
            className="w-full justify-start text-neutral-300 hover:bg-neutral-800 hover:text-white"
            onClick={logout}
          >
            <Icon name="logout" size={18} />
            Toka (logout)
          </Button>
        </div>
      </aside>

      <main id="main-content" className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-content">
          <header className="mb-5">
            {pipeline.datasetId !== null && (
              <Breadcrumbs datasetId={pipeline.datasetId} pathname={pathname} />
            )}
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <h1 className="text-h1 text-ink">{title}</h1>
                {description && (
                  <p className="mt-1 max-w-3xl text-body-lg text-ink-secondary">
                    {description}
                  </p>
                )}
              </div>
              {actions && (
                <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
              )}
            </div>
          </header>

          {pipeline.stage !== null && (
            <PipelineStepper
              datasetId={pipeline.datasetId}
              currentStage={pipeline.stage}
            />
          )}

          <div className="space-y-6">{children}</div>
        </div>
      </main>
    </div>
  );
}

export default AppShell;
