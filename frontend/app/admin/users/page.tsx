"use client";

import { useCallback, useEffect, useState } from "react";

import { AdminShell, hasRole, roleLabel } from "@/components/AdminShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { DataTable } from "@/components/DataTable";
import { SelectInput, TextInput } from "@/components/Field";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import {
  AccountStatus,
  AdminUser,
  PlatformRole,
  adminApi,
  api,
  apiErrorMessage,
} from "@/lib/api";

const PAGE_SIZE = 25;

const ROLE_TONE: Record<PlatformRole, "primary" | "info" | "neutral"> = {
  super_admin: "primary",
  platform_admin: "info",
  admin_viewer: "neutral",
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

export default function AdminUsersPage() {
  const { showToast } = useToast();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<AccountStatus | "">("");
  const [role, setRole] = useState<PlatformRole | "">("");
  const [page, setPage] = useState(1);

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const [canEdit, setCanEdit] = useState(false);
  const [canManageRoles, setCanManageRoles] = useState(false);

  // The role decides which controls are offered. The server still refuses
  // anything a viewer tries, so hiding a button is presentation, not security.
  useEffect(() => {
    api.auth
      .me()
      .then((profile) => {
        const staff = profile?.system_role ?? null;
        setCanEdit(hasRole(staff, "platform_admin"));
        setCanManageRoles(hasRole(staff, "super_admin"));
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search.trim());
      setPage(1);
    }, 350);
    return () => clearTimeout(timer);
  }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await adminApi.users({
        search: query || undefined,
        status: status || undefined,
        system_role: role || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setUsers(data.items);
      setTotal(data.total);
    } catch (caught) {
      setError(apiErrorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [query, status, role, page]);

  useEffect(() => {
    load();
  }, [load]);

  async function suspend(target: AdminUser) {
    const reason = window.prompt(
      `Sababu ya kumsitisha ${target.email}:`,
      ""
    );
    if (reason === null) return;
    setBusyId(target.id);
    try {
      const updated = await adminApi.suspendUser(target.id, reason || undefined);
      setUsers((current) =>
        current.map((item) => (item.id === updated.id ? updated : item))
      );
      showToast(`Akaunti ya ${updated.email} imesitishwa.`, "warning");
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setBusyId(null);
    }
  }

  async function reactivate(target: AdminUser) {
    setBusyId(target.id);
    try {
      const updated = await adminApi.reactivateUser(target.id);
      setUsers((current) =>
        current.map((item) => (item.id === updated.id ? updated : item))
      );
      showToast(`Akaunti ya ${updated.email} imeanza tena.`, "success");
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setBusyId(null);
    }
  }

  async function changeRole(target: AdminUser, next: PlatformRole) {
    setBusyId(target.id);
    try {
      const updated = await adminApi.updateUser(target.id, { system_role: next });
      setUsers((current) =>
        current.map((item) => (item.id === updated.id ? updated : item))
      );
      showToast(`Jukumu la ${updated.email} limebadilishwa.`, "success");
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setBusyId(null);
    }
  }

  async function revokeRole(target: AdminUser) {
    setBusyId(target.id);
    try {
      const updated = await adminApi.updateUser(target.id, { system_role: null });
      setUsers((current) =>
        current.map((item) => (item.id === updated.id ? updated : item))
      );
      showToast(`Ufikiaji wa admin wa ${updated.email} umeondolewa.`, "success");
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setBusyId(null);
    }
  }

  const columns = ["User", "Platform role", "Status", "Organizations", "Datasets", "Analyses", "Last active", "Actions"];
  const rows = users.map((item) => ({ ...item })) as unknown as Record<string, unknown>[];

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <AdminShell
      title="User Management"
      description="Tafuta, kagua na simamisha akaunti. Hatua zote zinarekodiwa kwenye audit log."
      actions={
        <Button variant="secondary" size="small" icon="refresh" onClick={load} loading={loading}>
          Onyesha upya
        </Button>
      }
    >
      <div className="flex flex-col gap-4">
        <Card title="Tafuta" icon="search">
          <div className="grid gap-3 md:grid-cols-3">
            <TextInput
              label="Jina au barua pepe"
              value={search}
              placeholder="mfano: amina@example.com"
              onChange={(event) => setSearch(event.target.value)}
            />
            <SelectInput
              label="Hali"
              value={status}
              options={[
                { value: "", label: "Zote" },
                { value: "active", label: "Active" },
                { value: "suspended", label: "Suspended" },
              ]}
              onChange={(event) => {
                setStatus(event.target.value as AccountStatus | "");
                setPage(1);
              }}
            />
            <SelectInput
              label="Jukumu la platform"
              value={role}
              options={[
                { value: "", label: "Zote" },
                { value: "super_admin", label: "Super Admin" },
                { value: "platform_admin", label: "Platform Admin" },
                { value: "admin_viewer", label: "Support / Viewer" },
              ]}
              onChange={(event) => {
                setRole(event.target.value as PlatformRole | "");
                setPage(1);
              }}
            />
          </div>
        </Card>

        {error ? (
          <Card>
            <EmptyState
              title="Imeshindikana kupakia watumiaji"
              description={error}
              icon="alert-triangle"
              action={
                <Button variant="secondary" onClick={load}>
                  Jaribu tena
                </Button>
              }
            />
          </Card>
        ) : loading ? (
          <Card>
            <TableSkeleton rows={6} columns={6} />
          </Card>
        ) : users.length === 0 ? (
          <Card>
            <EmptyState
              title="Hakuna watumiaji walolingana"
              description="Badilisha vichujio au maneno ya utafutaji."
              icon="search"
            />
          </Card>
        ) : (
          <Card
            title={`Watumiaji (${total})`}
            description="Kimsari, matumizi na hatua za kila akaunti."
            icon="users"
          >
            <DataTable
              columns={columns}
              rows={rows}
              caption="Watumiaji wa platformi"
              numericColumns={["Organizations", "Datasets", "Analyses"]}
              unsortableColumns={["User", "Status", "Platform role", "Actions"]}
              renderCell={(column, value, row) => {
                const item = row as unknown as AdminUser;
                if (column === "User") {
                  return (
                    <div className="min-w-0">
                      <p className="truncate font-medium text-ink">{item.full_name}</p>
                      <p className="truncate text-caption text-ink-muted">{item.email}</p>
                    </div>
                  );
                }
                if (column === "Platform role") {
                  return item.system_role ? (
                    canManageRoles ? (
                      <select
                        aria-label={`Jukumu la ${item.email}`}
                        value={item.system_role}
                        disabled={busyId === item.id}
                        onChange={(event) => {
                          const next = event.target.value as PlatformRole | "";
                          if (next === "") void revokeRole(item);
                          else void changeRole(item, next);
                        }}
                        className="h-9 rounded-md border border-surface-border bg-surface-panel px-2 text-caption text-ink"
                      >
                        <option value="">Hakuna</option>
                        <option value="super_admin">Super Admin</option>
                        <option value="platform_admin">Platform Admin</option>
                        <option value="admin_viewer">Support / Viewer</option>
                      </select>
                    ) : (
                      <Badge tone={ROLE_TONE[item.system_role]} size="sm">
                        {roleLabel(item.system_role)}
                      </Badge>
                    )
                  ) : (
                    <span className="text-caption text-ink-muted">Hakuna</span>
                  );
                }
                if (column === "Status") {
                  return (
                    <div className="flex flex-col items-start gap-1">
                      <Badge
                        tone={item.is_suspended ? "danger" : "success"}
                        size="sm"
                      >
                        {item.is_suspended ? "Suspended" : "Active"}
                      </Badge>
                      {item.suspended_reason && (
                        <span className="max-w-[220px] truncate text-caption text-ink-muted">
                          {item.suspended_reason}
                        </span>
                      )}
                    </div>
                  );
                }
                if (column === "Last active") {
                  return (
                    <span className="text-caption text-ink-secondary">
                      {formatDate(item.last_active_at)}
                    </span>
                  );
                }
                if (column === "Actions") {
                  if (!canEdit) {
                    return (
                      <span className="text-caption text-ink-muted">—</span>
                    );
                  }
                  return item.is_suspended ? (
                    <Button
                      variant="secondary"
                      size="small"
                      loading={busyId === item.id}
                      onClick={() => void reactivate(item)}
                    >
                      Anza
                    </Button>
                  ) : (
                    <Button
                      variant="secondary"
                      size="small"
                      loading={busyId === item.id}
                      onClick={() => void suspend(item)}
                    >
                      Simamisha
                    </Button>
                  );
                }
                return typeof value === "number" ? value : String(value ?? "—");
              }}
            />

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <p className="text-caption text-ink-muted">
                Ukurasa {page} kati ya {pageCount} · {total} matokeo
              </p>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="small"
                  disabled={page <= 1}
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                >
                  Iliyotangulia
                </Button>
                <Button
                  variant="secondary"
                  size="small"
                  disabled={page >= pageCount}
                  onClick={() => setPage((current) => current + 1)}
                >
                  Ifuatayo
                </Button>
              </div>
            </div>
          </Card>
        )}
      </div>
    </AdminShell>
  );
}
