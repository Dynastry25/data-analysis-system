"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import { api, apiErrorMessage, DatasetSummary } from "@/lib/api";

function formatDate(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

export default function DatasetsPage() {
  const { showToast } = useToast();
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDatasets(await api.datasets.list());
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleDelete(dataset: DatasetSummary) {
    if (!window.confirm(`Futa dataset "${dataset.original_filename}"?`)) return;
    try {
      await api.datasets.remove(dataset.id);
      showToast("Dataset imefutwa", "success");
      load();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }

  return (
    <AppShell
      title="Datasets zangu"
      description="Faili ulizopakia, hali yao na hatua zinazofuata."
      actions={
        <Link href="/upload">
          <Button>Pakia data mpya</Button>
        </Link>
      }
    >
      <Card>
        {loading ? (
          <TableSkeleton rows={5} columns={5} />
        ) : datasets.length === 0 ? (
          <EmptyState
            title="Hakuna dataset bado"
            description="Anza kwa kupakia faili la CSV au Excel."
            action={
              <Link href="/upload">
                <Button size="large">Pakia data</Button>
              </Link>
            }
          />
        ) : (
          <div className="space-y-3">
            {datasets.map((dataset) => (
              <article
                key={dataset.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded border border-neutral-200 p-4"
              >
                <div className="min-w-[220px]">
                  <p className="text-body-lg text-neutral-900">
                    {dataset.original_filename}
                  </p>
                  <p className="mt-1 text-caption text-neutral-600">
                    Safu {dataset.row_count.toLocaleString()} · Columns{" "}
                    {dataset.column_count} · {dataset.file_type.toUpperCase()} ·{" "}
                    {formatDate(dataset.uploaded_at)}
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <Badge
                    tone={
                      dataset.status === "analyzed"
                        ? "success"
                        : dataset.status === "cleaned"
                          ? "info"
                          : "neutral"
                    }
                    withIcon
                  >
                    {dataset.status}
                  </Badge>
                  <Link href={`/datasets/${dataset.id}`}>
                    <Button variant="secondary" size="small">
                      Angalia &amp; safisha
                    </Button>
                  </Link>
                  <Link href={`/datasets/${dataset.id}/analyze`}>
                    <Button variant="secondary" size="small">
                      Chambua
                    </Button>
                  </Link>
                  <Link href={`/datasets/${dataset.id}/charts`}>
                    <Button variant="secondary" size="small">
                      Chati
                    </Button>
                  </Link>
                  <Link href={`/datasets/${dataset.id}/export`}>
                    <Button variant="secondary" size="small">
                      Ripoti
                    </Button>
                  </Link>
                  <Button
                    variant="danger"
                    size="small"
                    onClick={() => handleDelete(dataset)}
                  >
                    Futa
                  </Button>
                </div>
              </article>
            ))}
          </div>
        )}
      </Card>
    </AppShell>
  );
}
