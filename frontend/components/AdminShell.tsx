"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "./Badge";
import { Icon, IconName } from "./Icon";
import { useAuthGuard, useLogout } from "@/lib/useAuth";
import { PlatformRole, api } from "@/lib/api";

interface NavItem {
  href: string;
  label: string;
  icon: IconName;
  /** Minimum platform role. Absent means any staff role may open it. */
  minimumRole?: PlatformRole;
}

/**
 * Admin navigation, grouped the way an operator thinks about the platform
 * (spec 25) rather than mirroring the user dashboard.
 *
 * Only screens that have real endpoints are listed. A navigation entry that
 * leads to a 404 is worse than a missing entry, so the roadmap pages are not
 * here yet: they appear when their API does.
 */
const ADMIN_NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Overview",
    items: [{ href: "/admin", label: "Admin Dashboard", icon: "dashboard" }],
  },
  {
    group: "Platform",
    items: [
      { href: "/admin/users", label: "Users", icon: "users" },
      { href: "/admin/organizations", label: "Organizations", icon: "building" },
      { href: "/admin/datasets", label: "Datasets", icon: "database" },
    ],
  },
  {
    group: "Security",
    items: [{ href: "/admin/audit", label: "Audit Logs", icon: "shield" }],
  },
];

const ROLE_RANK: Record<PlatformRole, number> = {
  admin_viewer: 1,
  platform_admin: 3,
  super_admin: 4,
};

const ROLE_LABELS: Record<PlatformRole, string> = {
  super_admin: "Super Admin",
  platform_admin: "Platform Admin",
  admin_viewer: "Support / Viewer",
};

export function roleLabel(role: PlatformRole | null | undefined): string {
  return role ? ROLE_LABELS[role] : "Hakuna";
}

export function hasRole(
  current: PlatformRole | null,
  minimum: PlatformRole | undefined
): boolean {
  if (!minimum) return true;
  if (!current) return false;
  return ROLE_RANK[current] >= ROLE_RANK[minimum];
}

interface AdminShellProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}

/**
 * Layout for the admin portal.
 *
 * Visually a sibling of AppShell rather than a copy of it, but deliberately
 * denser: an operator scans tables of accounts and events, so the row height is
 * tighter and the sidebar is narrower.
 *
 * Access is decided by the server. This component only hides navigation a role
 * cannot use; every screen still fails closed on its own.
 */
export function AdminShell({ title, description, actions, children }: AdminShellProps) {
  const ready = useAuthGuard();
  const logout = useLogout();
  const pathname = usePathname();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [role, setRole] = useState<PlatformRole | null>(null);
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  useEffect(() => {
    // The profile already carries the platform role, so the shell can shape
    // itself without a probe that would 403 for non-staff on every load.
    // A 403 here means the server disagrees, so the portal stays closed.
    api.auth
      .me()
      .then((profile) => {
        if (profile?.system_role) {
          setRole(profile.system_role);
        } else {
          setDenied(true);
        }
      })
      .catch(() => setDenied(true));
  }, []);

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

  if (denied) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-surface-canvas px-4">
        <div className="max-w-md rounded-md border border-danger/30 bg-danger-bg px-6 py-8 text-center">
          <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-danger/10 text-danger-700">
            <Icon name="lock" size={20} />
          </span>
          <h1 className="mt-3 text-h3 text-ink">Ufikiaji wa admin haupatikani</h1>
          <p className="mt-2 text-body text-danger-700">
            Akaunti yako hana jukumu la kusimamia platform. Hii hali inathibitishwa
            kwenye server, hivyo kuficha menyu peke yake si usalama.
          </p>
          <Link
            href="/dashboard"
            className="mt-4 inline-flex h-10 items-center rounded-md bg-primary-600 px-4 text-body font-medium text-white hover:bg-primary-700"
          >
            Rudi kwenye dashboard
          </Link>
        </div>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-surface-canvas lg:flex">
      <a
        href="#admin-main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:inline-flex focus:h-10 focus:items-center focus:rounded focus:bg-primary-600 focus:px-4 focus:text-body focus:font-medium focus:text-white"
      >
        Nenda kwenye maudhui makuu
      </a>

      <header className="sticky top-0 z-40 flex items-center justify-between border-b border-surface-border bg-sidebar px-4 py-3 lg:hidden">
        <Brand />
        <button
          type="button"
          aria-label="Fungua menyu"
          aria-expanded={drawerOpen}
          onClick={() => setDrawerOpen(true)}
          className="flex h-11 w-11 items-center justify-center rounded text-neutral-300 transition-colors hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-400"
        >
          <Icon name="menu" size={22} />
        </button>
      </header>

      {drawerOpen && (
        <div
          aria-hidden="true"
          onClick={() => setDrawerOpen(false)}
          className="fixed inset-0 z-40 bg-sidebar-deep/60 lg:hidden"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-60 transform flex-col bg-sidebar transition-transform duration-300 ease-standard lg:static lg:translate-x-0 ${
          drawerOpen ? "translate-x-0 shadow-drawer" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-4 py-4">
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

        <Badge tone="warning" size="sm" className="mx-4 mb-1 self-start">
          Admin portal
        </Badge>

        <nav aria-label="Urambazaji wa admin" className="flex-1 overflow-y-auto px-3 pb-4">
          {ADMIN_NAV.map((section) => {
            const visible = section.items.filter((item) => hasRole(role, item.minimumRole));
            if (visible.length === 0) return null;
            return (
              <div key={section.group} className="mt-4 first:mt-1">
                <p className="px-3 pb-1 text-overline uppercase tracking-wide text-neutral-500">
                  {section.group}
                </p>
                <ul className="space-y-0.5">
                  {visible.map((item) => {
                    const active =
                      item.href === "/admin"
                        ? pathname === "/admin"
                        : pathname.startsWith(item.href);
                    return (
                      <li key={item.href}>
                        <Link
                          href={item.href}
                          aria-current={active ? "page" : undefined}
                          className={`flex min-h-[38px] items-center gap-2.5 rounded-md px-3 text-caption transition-colors duration-150 ease-standard ${
                            active
                              ? "bg-sidebar-active font-medium text-white"
                              : "text-neutral-300 hover:bg-white/10 hover:text-white"
                          }`}
                        >
                          <Icon name={item.icon} size={18} />
                          {item.label}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </nav>

        <div className="border-t border-white/10 px-4 py-3">
          <Link
            href="/dashboard"
            className="flex min-h-[38px] items-center gap-2 rounded-md text-caption text-neutral-400 transition-colors hover:bg-white/10 hover:text-white"
          >
            <Icon name="arrow-right" size={16} />
            Rudi kwenye programu
          </Link>
          <button
            type="button"
            onClick={logout}
            className="mt-1 flex min-h-[38px] w-full items-center gap-2 rounded-md px-1 text-caption text-neutral-400 transition-colors hover:bg-white/10 hover:text-white"
          >
            <Icon name="logout" size={16} />
            Toka
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-surface-border bg-surface-panel px-4 py-4 sm:px-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 className="text-h2 text-ink">{title}</h1>
              {description && <p className="mt-0.5 text-body text-ink-secondary">{description}</p>}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {role && <Badge tone="primary">{roleLabel(role)}</Badge>}
              {actions}
            </div>
          </div>
        </header>
        <main id="admin-main" className="flex-1 px-4 py-5 sm:px-6">
          {children}
        </main>
      </div>
    </div>
  );
}

function Brand() {
  return (
    <Link href="/admin" className="flex items-center gap-2.5">
      <Icon name="shield" size={20} />
      <span className="text-body-lg font-semibold text-white">StatFlow Admin</span>
    </Link>
  );
}

export default AdminShell;
