"use client";

import { useCallback, useEffect, useState } from "react";

import { AdminShell } from "@/components/AdminShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { DataTable } from "@/components/DataTable";
import { SelectInput, TextInput } from "@/components/Field";
import { TableSkeleton } from "@/components/Skeleton";
import { AdminAuditEntry, adminApi, apiErrorMessage } from "@/lib/api";

const PAGE_SIZE = 25;

const RESULT_TONE: Record<AdminAuditEntry["result"], "success" | "warning" | "danger"> =
  {
    success: "success",
    failure: "warning",
    denied: "danger",
  };

const RESULT_LABEL: Record<AdminAuditEntry["result"], string> = {
  success: "Success",
  failure: "Failure",
  denied: "Denied",
};

/** The actions the platform records, so the filter is not a free-text guess. */
const KNOWN_ACTIONS = [
  { value: "", label: "Zote" },
  { value: "auth.login", label: "auth.login" },
  { value: "auth.login.failed", label: "auth.login.failed" },
  { value: "auth.login.blocked", label: "auth.login.blocked" },
  { value: "admin.user.update", label: "admin.user.update" },
  { value: "admin.user.suspend", label: "admin.user.suspend" },
  { value: "admin.user.reactivate", label: "admin.user.reactivate" },
];

function formatDate(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(parsed);
}

function describeMetadata(entry: AdminAuditEntry): string {
  const meta = entry.metadata ?? {};
  const parts: string[] = [];
  const target = meta.target_email;
  if (typeof target === "string") parts.push(`target: ${target}`);
  if (typeof meta.reason === "string") parts.push(`reason: ${meta.reason}`);
  const changes = meta.changes;
  if (Array.isArray(changes)) parts.push(`changed: ${changes.join(", ")}`);
  if (meta.previous_role !== undefined || meta.new_role !== undefined) {
    parts.push(`${String(meta.previous_role)} → ${String(meta.new_role)}`);
  }
  if (typeof meta.detail === "string") parts.push(meta.detail);
  return parts.length > 0 ? parts.join(" · ") : "—";
}

export default function AdminAuditPage() {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [action, setAction] = useState("");
  const [result, setResult] = useState<AdminAuditEntry["result"] | "">("");
  const [page, setPage] = useState(1);

  const [entries, setEntries] = useState<AdminAuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
      const data = await adminApi.audit({
        search: query || undefined,
        action: action || undefined,
        result: result || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setEntries(data.items);
      setTotal(data.total);
    } catch (caught) {
      setError(apiErrorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [query, action, result, page]);

  useEffect(() => {
    load();
  }, [load]);

  const columns = [
    "Timestamp",
    "Actor",
    "Action",
    "Resource",
    "Result",
    "IP",
    "Details",
  ];
  const rows = entries.map((entry) => ({ ...entry })) as unknown as Record<
    string,
    unknown
  >[];
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <AdminShell
      title="Audit Logs"
      description="Kumbukumbu ya matendo ya usalama. Hakuna njia ya kufuta au kuhariri shentries hizi."
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
              label="Actor, action au resource"
              value={search}
              placeholder="mfano: admin.user.suspend"
              onChange={(event) => setSearch(event.target.value)}
            />
            <SelectInput
              label="Action"
              value={action}
              options={KNOWN_ACTIONS}
              onChange={(event) => {
                setAction(event.target.value);
                setPage(1);
              }}
            />
            <SelectInput
              label="Result"
              value={result}
              options={[
                { value: "", label: "Zote" },
                { value: "success", label: "Success" },
                { value: "failure", label: "Failure" },
                { value: "denied", label: "Denied" },
              ]}
              onChange={(event) => {
                setResult(event.target.value as AdminAuditEntry["result"] | "");
                setPage(1);
              }}
            />
          </div>
        </Card>

        {error ? (
          <Card>
            <EmptyState
              title="Imeshindikana kupakia audit log"
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
            <TableSkeleton rows={8} columns={6} />
          </Card>
        ) : entries.length === 0 ? (
          <Card>
            <EmptyState
              title="Hakuna shentries zilizolingana"
              description="Badilisha vichujio au maneno ya utafutaji."
              icon="shield"
            />
          </Card>
        ) : (
          <Card
            title={`Matukio (${total})`}
            description="Kila mwisho wa mistari unaonyesha metadata iliyohifadhiwa."
            icon="shield"
          >
            <DataTable
              columns={columns}
              rows={rows}
              caption="Shentries za audit log"
              unsortableColumns={["Actor", "Action", "Resource", "Result", "Details"]}
              renderCell={(column, _value, row) => {
                const entry = row as unknown as AdminAuditEntry;
                if (column === "Timestamp") {
                  return (
                    <span className="whitespace-nowrap text-caption text-ink-secondary">
                      {formatDate(entry.created_at)}
                    </span>
                  );
                }
                if (column === "Actor") {
                  return (
                    <div className="min-w-0">
                      <p className="truncate text-caption text-ink">
                        {entry.actor_email ?? "—"}
                      </p>
                      {entry.user_id === null && (
                        <p className="text-caption text-ink-muted">hakuna akaunti</p>
                      )}
                    </div>
                  );
                }
                if (column === "Action") {
                  return (
                    <code className="text-caption text-ink">{entry.action}</code>
                  );
                }
                if (column === "Resource") {
                  return entry.resource ? (
                    <span className="text-caption text-ink-secondary">
                      {entry.resource}
                      {entry.resource_id ? ` #${entry.resource_id}` : ""}
                    </span>
                  ) : (
                    <span className="text-caption text-ink-muted">—</span>
                  );
                }
                if (column === "Result") {
                  return (
                    <Badge tone={RESULT_TONE[entry.result]} size="sm">
                      {RESULT_LABEL[entry.result]}
                    </Badge>
                  );
                }
                if (column === "IP") {
                  return (
                    <span className="text-caption text-ink-muted">
                      {entry.ip_address ?? "—"}
                    </span>
                  );
                }
                if (column === "Details") {
                  return (
                    <span className="text-caption text-ink-secondary">
                      {describeMetadata(entry)}
                    </span>
                  );
                }
                return null;
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
