"use client";

import { useCallback, useEffect, useState } from "react";

import { AdminShell } from "@/components/AdminShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { DataTable } from "@/components/DataTable";
import { SelectInput, TextInput } from "@/components/Field";
import { TableSkeleton } from "@/components/Skeleton";
import { AdminDataset, adminApi, apiErrorMessage } from "@/lib/api";

const PAGE_SIZE = 25;

const STATUS_TONE: Record<string, "neutral" | "info" | "success" | "warning"> = {
  uploaded: "neutral",
  cleaned: "info",
  analyzed: "success",
  failed: "warning",
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium" }).format(parsed);
}

export default function AdminDatasetsPage() {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<AdminDataset[]>([]);
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
      const data = await adminApi.datasets({
        search: query || undefined,
        status: status || undefined,
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
  }, [query, status, page]);

  useEffect(() => {
    load();
  }, [load]);

  const columns = [
    "Dataset",
    "Owner",
    "Organization",
    "Rows",
    "Columns",
    "Version",
    "Status",
    "Created",
  ];
  const rows = items.map((item) => ({ ...item })) as unknown as Record<string, unknown>[];
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <AdminShell
      title="Datasets"
      description="Metadata ya kiofisi tu. Data halisi haipatikani kupitia ukurasa huu."
      actions={
        <Button variant="secondary" size="small" icon="refresh" onClick={load} loading={loading}>
          Onyesha upya
        </Button>
      }
    >
      <div className="flex flex-col gap-4">
        <Card title="Tafuta" icon="search">
          <div className="grid gap-3 md:grid-cols-2">
            <TextInput
              label="Jina la faili"
              value={search}
              placeholder="mfano: survey.csv"
              onChange={(event) => setSearch(event.target.value)}
            />
            <SelectInput
              label="Hali"
              value={status}
              options={[
                { value: "", label: "Zote" },
                { value: "uploaded", label: "Uploaded" },
                { value: "cleaned", label: "Cleaned" },
                { value: "analyzed", label: "Analyzed" },
              ]}
              onChange={(event) => {
                setStatus(event.target.value);
                setPage(1);
              }}
            />
          </div>
        </Card>

        {error ? (
          <Card>
            <EmptyState
              title="Imeshindikana kupakia datasets"
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
        ) : items.length === 0 ? (
          <Card>
            <EmptyState
              title="Hakuna datasets zilizolingana"
              description="Badilisha vichujio au maneno ya utafutaji."
              icon="database"
            />
          </Card>
        ) : (
          <Card
            title={`Datasets (${total})`}
            description="Kumbukumbu ya uendelevu: mmiliki, ukubwa na toleo la mwisho."
            icon="database"
          >
            <DataTable
              columns={columns}
              rows={rows}
              caption="Datasets za platformi"
              numericColumns={["Rows", "Columns", "Version"]}
              unsortableColumns={["Dataset", "Owner", "Organization", "Status", "Created"]}
              renderCell={(column, value, row) => {
                const item = row as unknown as AdminDataset;
                if (column === "Dataset") {
                  return (
                    <div className="min-w-0">
                      <p className="truncate font-medium text-ink">
                        {item.original_filename}
                      </p>
                      <p className="text-caption text-ink-muted uppercase">
                        {item.file_type}
                      </p>
                    </div>
                  );
                }
                if (column === "Owner") {
                  return (
                    <span className="text-caption text-ink-secondary">
                      {item.owner_email ?? "—"}
                    </span>
                  );
                }
                if (column === "Organization") {
                  return (
                    <span className="text-caption text-ink-secondary">
                      {item.organization_name ?? "Personal"}
                    </span>
                  );
                }
                if (column === "Version") {
                  return (
                    <span className="text-caption text-ink-secondary">
                      {item.latest_version ? `v${item.latest_version}` : "—"}
                    </span>
                  );
                }
                if (column === "Status") {
                  return (
                    <Badge tone={STATUS_TONE[item.status] ?? "neutral"} size="sm">
                      {item.status}
                    </Badge>
                  );
                }
                if (column === "Created") {
                  return (
                    <span className="whitespace-nowrap text-caption text-ink-secondary">
                      {formatDate(item.created_at)}
                    </span>
                  );
                }
                return typeof value === "number"
                  ? new Intl.NumberFormat("en-US").format(value)
                  : String(value ?? "—");
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
