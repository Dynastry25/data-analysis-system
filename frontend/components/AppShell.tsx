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
  { href: "/upload", label: "Pakia data", icon: "upload" },
];

interface AppShellProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}

function isActiveNav(pathname: string, href: string): boolean {
  if (href === "/datasets") {
    return pathname === "/datasets" || pathname.startsWith("/datasets/");
  }
  return pathname === href;
}

function Brand() {
  return (
    <Link href="/dashboard" className="flex items-center gap-2.5">
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-600 text-white">
        <Icon name="chart-line" size={20} />
      </span>
      <span>
        <span className="block text-h3 leading-tight text-neutral-900">StatFlow</span>
        <span className="block text-caption text-neutral-600">Data Analysis</span>
      </span>
    </Link>
  );
}

/**
 * Authenticated layout: brand + grouped sidebar (desktop), off-canvas drawer
 * (mobile), the 6-stage pipeline stepper on dataset pages, and the current
 * user at the bottom. Redirects to /login when there is no token.
 */
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
    api.auth
      .me()
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  if (!ready) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-neutral-50">
        <p className="text-body text-neutral-600">Inapakia…</p>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-neutral-50 lg:flex">
      {/* Mobile top bar */}
      <header className="sticky top-0 z-40 flex items-center justify-between border-b border-neutral-200 bg-white px-4 py-3 lg:hidden">
        <Brand />
        <button
          type="button"
          aria-label="Fungua menyu"
          onClick={() => setDrawerOpen(true)}
          className="flex h-11 w-11 items-center justify-center rounded text-neutral-600 hover:bg-neutral-100"
        >
          <Icon name="menu" size={22} />
        </button>
      </header>

      {/* Overlay behind the mobile drawer */}
      {drawerOpen && (
        <div
          aria-hidden="true"
          onClick={() => setDrawerOpen(false)}
          className="fixed inset-0 z-40 bg-neutral-900/40 lg:hidden"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-64 transform flex-col border-r border-neutral-200 bg-white transition-transform duration-300 ease-in-out lg:static lg:translate-x-0 lg:shadow-none ${
          drawerOpen ? "translate-x-0 shadow-xl" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-4 py-5">
          <Brand />
          <button
            type="button"
            aria-label="Funga menyu"
            onClick={() => setDrawerOpen(false)}
            className="flex h-11 w-11 items-center justify-center rounded text-neutral-600 hover:bg-neutral-100 lg:hidden"
          >
            <Icon name="close" size={22} />
          </button>
        </div>

        <nav aria-label="Urambazaji kuu" className="flex-1 overflow-y-auto px-3 pb-4">
          <p className="px-3 pb-2 pt-1 text-caption uppercase tracking-wide text-neutral-400">
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
                    className={`flex min-h-[44px] items-center gap-3 rounded px-3 text-body transition-colors duration-200 ${
                      active
                        ? "bg-primary-50 font-medium text-primary-900"
                        : "text-neutral-600 hover:bg-neutral-100"
                    }`}
                  >
                    <Icon
                      name={item.icon}
                      size={20}
                      className={active ? "text-primary-600" : "text-neutral-400"}
                    />
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>

          {pipeline.datasetId !== null && pipeline.stage !== null && (
            <>
              <p className="px-3 pb-2 pt-6 text-caption uppercase tracking-wide text-neutral-400">
                Mtiririko
              </p>
              <ul className="space-y-1">
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
                        className={`flex min-h-[40px] items-center gap-3 rounded px-3 text-body transition-colors duration-200 ${
                          active
                            ? "bg-primary-50 font-medium text-primary-900"
                            : "text-neutral-600 hover:bg-neutral-100"
                        }`}
                      >
                        <span
                          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
                            done
                              ? "bg-success-bg text-success"
                              : active
                                ? "bg-primary-600 text-white"
                                : "bg-neutral-100 text-neutral-400"
                          }`}
                        >
                          {done ? (
                            <Icon name="check" size={10} />
                          ) : (
                            <span className="text-[10px] font-medium">{stage.step}</span>
                          )}
                        </span>
                        {stage.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </nav>

        <div className="border-t border-neutral-200 p-3">
          <div className="flex items-center gap-3 px-1 py-2">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-100 text-primary-700">
              <Icon name="user" size={18} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-body text-neutral-900">
                {user?.full_name ?? "Mtumiaji"}
              </p>
              <p className="truncate text-caption text-neutral-600">{user?.email ?? ""}</p>
            </div>
          </div>
          <Button variant="ghost" className="w-full justify-start" onClick={logout}>
            <Icon name="logout" size={18} />
            Toka (logout)
          </Button>
        </div>
      </aside>

      <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-h1 text-neutral-900">{title}</h1>
            {description && (
              <p className="mt-1 text-body-lg text-neutral-600">{description}</p>
            )}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>

        {pipeline.stage !== null && (
          <PipelineStepper
            datasetId={pipeline.datasetId}
            currentStage={pipeline.stage}
          />
        )}

        <div className="space-y-6">{children}</div>
      </main>
    </div>
  );
}

export default AppShell;