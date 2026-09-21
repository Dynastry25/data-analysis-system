"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuthGuard, useLogout } from "@/lib/useAuth";
import { Button } from "./Button";

const NAV_ITEMS = [
  { href: "/datasets", label: "Datasets" },
  { href: "/upload", label: "Pakia data" },
];

interface AppShellProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}

/**
 * Authenticated layout: sidebar navigation on desktop, stacked header on mobile.
 * Redirects to /login when there is no token.
 */
export function AppShell({ title, description, actions, children }: AppShellProps) {
  const ready = useAuthGuard();
  const logout = useLogout();
  const pathname = usePathname();

  if (!ready) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-neutral-50">
        <p className="text-body text-neutral-600">Inapakia…</p>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-neutral-50 lg:flex">
      <aside className="border-b border-neutral-200 bg-white px-4 py-4 lg:w-60 lg:border-b-0 lg:border-r lg:py-6">
        <p className="text-h3 text-primary-900">Data Analysis</p>
        <p className="text-caption text-neutral-600">Platform MVP</p>
        <nav aria-label="Main navigation" className="mt-4 flex gap-2 lg:flex-col">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex min-h-[44px] items-center rounded px-3 text-body transition-colors duration-200 ${
                  active
                    ? "bg-primary-50 text-primary-900"
                    : "text-neutral-600 hover:bg-neutral-100"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
          <Button
            variant="ghost"
            className="min-h-[44px] justify-start"
            onClick={logout}
          >
            Toka (logout)
          </Button>
        </nav>
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
        <div className="space-y-6">{children}</div>
      </main>
    </div>
  );
}

export default AppShell;
