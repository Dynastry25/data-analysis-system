"use client";

import { useCallback, useEffect, useState } from "react";

import { AdminShell } from "@/components/AdminShell";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { DataTable } from "@/components/DataTable";
import { TextInput } from "@/components/Field";
import { TableSkeleton } from "@/components/Skeleton";
import { AdminOrganization, adminApi, apiErrorMessage } from "@/lib/api";

const PAGE_SIZE = 25;

function formatDate(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium" }).format(parsed);
}

export default function AdminOrganizationsPage() {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<AdminOrganization[]>([]);
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
      const data = await adminApi.organizations({
        search: query || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setItems(data.items);
      setTotal(data.total);
    } catch (caught) {
      setError(apiErrorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [query, page]);

  useEffect(() => {
    load();
  }, [load]);

  const columns = ["Organization", "Members", "Projects", "Datasets", "Analyses", "Created"];
  const rows = items.map((item) => ({ ...item })) as unknown as Record<string, unknown>[];
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <AdminShell
      title="Organizations"
      description="Mashirika yote ya platformi na kiwango cha matumizi yake."
      actions={
        <Button variant="secondary" size="small" icon="refresh" onClick={load} loading={loading}>
          Onyesha upya
        </Button>
      }
    >
      <div className="flex flex-col gap-4">
        <Card title="Tafuta" icon="search">
          <TextInput
            label="Jina au slug"
            value={search}
            placeholder="mfano: Acme"
            onChange={(event) => setSearch(event.target.value)}
          />
        </Card>

        {error ? (
          <Card>
            <EmptyState
              title="Imeshindikana kupakia mashirika"
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
            <TableSkeleton rows={6} columns={5} />
          </Card>
        ) : items.length === 0 ? (
          <Card>
            <EmptyState
              title="Hakuna mashirika yaliyolingana"
              description="Badilisha maneno ya utafutaji."
              icon="building"
            />
          </Card>
        ) : (
          <Card
            title={`Mashirika (${total})`}
            description="Hapa tunazingatia metadata ya kiofisi, si data ya wanachama."
            icon="building"
          >
            <DataTable
              columns={columns}
              rows={rows}
              caption="Mashirika ya platformi"
              numericColumns={["Members", "Projects", "Datasets", "Analyses"]}
              unsortableColumns={["Organization", "Created"]}
              renderCell={(column, value, row) => {
                const item = row as unknown as AdminOrganization;
                if (column === "Organization") {
                  return (
                    <div className="min-w-0">
                      <p className="truncate font-medium text-ink">{item.name}</p>
                      <p className="truncate text-caption text-ink-muted">{item.slug}</p>
                    </div>
                  );
                }
                if (column === "Created") {
                  return (
                    <span className="text-caption text-ink-secondary">
                      {formatDate(item.created_at)}
                    </span>
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
