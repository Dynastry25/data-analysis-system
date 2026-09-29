"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

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
            index < done ? "bg-primary-600" : "bg-surface-sunken"
          }`}
        />
      ))}
    </span>
  );
}

export default function DatasetsPage() {
  const { showToast } = useToast();
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [meId, setMeId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [pendingDelete, setPendingDelete] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);

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

  useEffect(() => {
    api.auth
      .me()
      .then((profile) => setMeId(profile.id))
      .catch(() => setMeId(null));
  }, []);

  async function handleDelete(dataset: DatasetSummary) {
    setDeleting(true);
    try {
      await api.datasets.remove(dataset.id);
      showToast("Dataset imefutwa", "success");
      setPendingDelete(null);
      load();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setDeleting(false);
    }
  }

  const projectNames = useMemo(() => {
    const names = new Map<string, number>();
    for (const dataset of datasets) {
      const key = dataset.project_name?.trim() || "Binafsi";
      names.set(key, (names.get(key) ?? 0) + 1);
    }
    return [...names.entries()].sort((a, b) => b[1] - a[1]);
  }, [datasets]);
  const [activeProject, setActiveProject] = useState<string>("all");
  const filteredDatasets =
    activeProject === "all"
      ? datasets
      : datasets.filter(
          (dataset) => (dataset.project_name?.trim() || "Binafsi") === activeProject
        );

  const totalRows = datasets.reduce((sum, d) => sum + (d.row_count || 0), 0);
  const cleanedCount = datasets.filter((d) => d.status === "cleaned").length;
  const analyzedCount = datasets.filter((d) => d.status === "analyzed").length;

  return (
    <AppShell
      title="Projects & Datasets"
      description={`${datasets.length} projects · ${datasets.length} datasets`}
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
              <Icon name="upload" size={16} />+ Add Dataset
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
          hint="Faili zilizopakiwa na zilizoshirikishwa"
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

      {/* Project filter chips — prototype page-03 groups datasets under projects */}
      {projectNames.length > 1 && (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Chuja kwa mradi">
          <button
            type="button"
            onClick={() => setActiveProject("all")}
            aria-pressed={activeProject === "all"}
            className={`rounded-full border px-2.5 py-1 text-caption transition-colors duration-150 ease-standard ${
              activeProject === "all"
                ? "border-primary-200 bg-primary-50 font-medium text-primary-800"
                : "border-surface-border bg-surface-sunken text-ink-secondary hover:border-primary-300"
            }`}
          >
            All ({datasets.length})
          </button>
          {projectNames.map(([name, count]) => (
            <button
              key={name}
              type="button"
              onClick={() => setActiveProject(name)}
              aria-pressed={activeProject === name}
              className={`rounded-full border px-2.5 py-1 text-caption transition-colors duration-150 ease-standard ${
                activeProject === name
                  ? "border-primary-200 bg-primary-50 font-medium text-primary-800"
                  : "border-surface-border bg-surface-sunken text-ink-secondary hover:border-primary-300"
              }`}
            >
              {name} ({count})
            </button>
          ))}
        </div>
      )}

      <Card
        title={activeProject === "all" ? "Datasets zako" : activeProject}
        icon="database"
        description={
          datasets.length > 0
            ? `${datasets.length} datasets · jumla ya ${totalRows.toLocaleString()} safu`
            : "Faili ulizopakia na data iliyoshirikishwa na wanachama wa mashirika yako."
        }
      >
        {loading ? (
          <TableSkeleton rows={5} columns={5} />
        ) : datasets.length === 0 ? (
          <EmptyState
            title="Hakuna dataset bado"
            description="Anza kwa kupakia faili la CSV au Excel."
            icon="database"
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
          <ul className="space-y-3">
            {filteredDatasets.map((dataset) => {
              const done = completedStageCount({ status: dataset.status });
              const confirming = pendingDelete === dataset.id;
              const canDelete = meId === null || dataset.user_id === meId;
              return (
                <li
                  key={dataset.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-surface-border bg-surface-panel p-4 shadow-card transition-shadow duration-150 ease-standard hover:shadow-raised"
                >
                  <div className="flex min-w-[240px] flex-1 items-center gap-3">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm bg-primary-50 text-primary-600">
                      <Icon name="database" size={20} />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-body-lg font-medium text-ink">
                        {dataset.original_filename}
                      </p>
                      <p className="mt-1 flex flex-wrap items-center gap-x-2 text-caption text-ink-muted">
                        <span className="font-mono tabular">DATASET SIZE</span>
                        <span aria-hidden="true">·</span>
                        <span>
                          Safu {dataset.row_count.toLocaleString()} · Columns{" "}
                          {dataset.column_count}
                        </span>
                      </p>
                      <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-caption text-ink-muted">
                        <span className="font-mono tabular">UPDATED</span>
                        <span aria-hidden="true">·</span>
                        <span>{formatDate(dataset.uploaded_at)}</span>
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
                    >
                      {dataset.status}
                    </Badge>
                    {dataset.project_id ? (
                      <Badge tone="primary" icon="folder">
                        {dataset.project_name ?? "Mradi"}
                      </Badge>
                    ) : (
                      <Badge tone="neutral" icon="lock">
                        Binafsi
                      </Badge>
                    )}
                    <Link href={`/datasets/${dataset.id}`}>
                      <Button size="small">
                        <Icon name="eye" size={14} />
                        Fungua
                      </Button>
                    </Link>
                    <div className="flex items-center gap-1">
                      <Link href={`/datasets/${dataset.id}/statistics`}>
                        <Button
                          variant="ghost"
                          size="small"
                          aria-label={`Chambua ${dataset.original_filename}`}
                        >
                          <Icon name="calculator" size={16} />
                        </Button>
                      </Link>
                      <Link href={`/datasets/${dataset.id}/charts`}>
                        <Button
                          variant="ghost"
                          size="small"
                          aria-label={`Chati za ${dataset.original_filename}`}
                        >
                          <Icon name="chart" size={16} />
                        </Button>
                      </Link>
                      <Link href={`/datasets/${dataset.id}/ask`}>
                        <Button
                          variant="ghost"
                          size="small"
                          aria-label={`Msaidizi wa AI kwa ${dataset.original_filename}`}
                        >
                          <Icon name="sparkles" size={16} />
                        </Button>
                      </Link>
                      <Link href={`/datasets/${dataset.id}/export`}>
                        <Button
                          variant="ghost"
                          size="small"
                          aria-label={`Ripoti za ${dataset.original_filename}`}
                        >
                          <Icon name="file-text" size={16} />
                        </Button>
                      </Link>
                    </div>
                    {canDelete &&
                      (confirming ? (
                        <span className="flex items-center gap-2 rounded-md border border-danger/30 bg-danger-bg px-2 py-1">
                          <span className="text-caption text-danger-700">Futa?</span>
                          <Button
                            variant="danger"
                            size="small"
                            loading={deleting}
                            onClick={() => handleDelete(dataset)}
                          >
                            Ndiyo
                          </Button>
                          <Button
                            variant="ghost"
                            size="small"
                            onClick={() => setPendingDelete(null)}
                          >
                            Ghairi
                          </Button>
                        </span>
                      ) : (
                        <Button
                          variant="ghost"
                          size="small"
                          aria-label={`Futa ${dataset.original_filename}`}
                          onClick={() => setPendingDelete(dataset.id)}
                        >
                          <Icon name="trash" size={16} />
                        </Button>
                      ))}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </AppShell>
  );
}
