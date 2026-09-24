"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { Icon } from "@/components/Icon";
import { MetricCard } from "@/components/MetricCard";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import { api, apiErrorMessage, DatasetSummary } from "@/lib/api";
import { completedStageCount } from "@/lib/pipeline";

function formatDate(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

function StageDots({ done, total = 6 }: { done: number; total?: number }) {
  return (
    <span
      className="inline-flex items-center gap-1"
      role="img"
      aria-label={`Hatua ${done} kati ya ${total}`}
    >
      {Array.from({ length: total }).map((_, index) => (
        <span
          key={index}
          className={`h-1.5 w-3.5 rounded-full ${
            index < done ? "bg-primary-600" : "bg-neutral-200"
          }`}
        />
      ))}
    </span>
  );
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

  const totalRows = datasets.reduce((sum, d) => sum + (d.row_count || 0), 0);
  const cleanedCount = datasets.filter((d) => d.status === "cleaned").length;
  const analyzedCount = datasets.filter((d) => d.status === "analyzed").length;

  return (
    <AppShell
      title="Datasets zangu"
      description="Faili ulizopakia, hali yao na hatua zinazofuata."
      actions={
        <>
          <Link href="/dashboard">
            <Button variant="secondary">
              <Icon name="dashboard" size={16} />
              Dashboard
            </Button>
          </Link>
          <Link href="/upload">
            <Button>
              <Icon name="upload" size={16} />
              Pakia data mpya
            </Button>
          </Link>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          icon="database"
          tone="primary"
          label="Datasets"
          value={datasets.length}
          hint="Faili zilizopakiwa"
        />
        <MetricCard
          icon="layers"
          tone="info"
          label="Jumla ya safu"
          value={totalRows.toLocaleString()}
          hint="Rows katika datasets zote"
        />
        <MetricCard
          icon="clipboard"
          tone="success"
          label="Zilizosafishwa"
          value={cleanedCount + analyzedCount}
          hint="Safisha imefanyika"
        />
        <MetricCard
          icon="calculator"
          tone="warning"
          label="Zimechambuliwa"
          value={analyzedCount}
          hint="Uchambuzi umekamilika"
        />
      </div>

      <Card>
        {loading ? (
          <TableSkeleton rows={5} columns={5} />
        ) : datasets.length === 0 ? (
          <EmptyState
            title="Hakuna dataset bado"
            description="Anza kwa kupakia faili la CSV au Excel."
            action={
              <Link href="/upload">
                <Button size="large">
                  <Icon name="upload" size={16} />
                  Pakia data
                </Button>
              </Link>
            }
          />
        ) : (
          <div className="space-y-3">
            {datasets.map((dataset) => {
              const done = completedStageCount({ status: dataset.status });
              return (
                <article
                  key={dataset.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded border border-neutral-200 p-4 transition-colors duration-150 hover:border-neutral-300"
                >
                  <div className="flex min-w-[240px] items-center gap-3">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-600">
                      <Icon name="database" size={20} />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-body-lg text-neutral-900">
                        {dataset.original_filename}
                      </p>
                      <p className="mt-0.5 text-caption text-neutral-600">
                        Safu {dataset.row_count.toLocaleString()} · Columns{" "}
                        {dataset.column_count} · {dataset.file_type.toUpperCase()} ·{" "}
                        {formatDate(dataset.uploaded_at)}
                      </p>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className="hidden flex-col items-end gap-1 sm:flex"
                      title={`Hatua ${done} kati ya 6 zimekamilika`}
                    >
                      <StageDots done={done} />
                    </span>
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
                      <Button size="small">Angalia</Button>
                    </Link>
                    <Link href={`/datasets/${dataset.id}/statistics`}>
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
                      <Icon name="trash" size={14} />
                      Futa
                    </Button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </Card>
    </AppShell>
  );
}