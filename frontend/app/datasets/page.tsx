"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { EmptyState } from "@/components/Card";
import { Icon } from "@/components/Icon";
import { InlineSearch } from "@/components/InlineSearch";
import { SummaryStrip } from "@/components/SummaryStrip";
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

  const [query, setQuery] = useState("");
  const projectNames = useMemo(() => {
    const names = new Map<string, number>();
    for (const dataset of datasets) {
      const key = dataset.project_name?.trim() || "Binafsi";
      names.set(key, (names.get(key) ?? 0) + 1);
    }
    return [...names.entries()].sort((a, b) => b[1] - a[1]);
  }, [datasets]);
  const [activeProject, setActiveProject] = useState<string>("all");
  const filteredDatasets = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return datasets.filter((dataset) => {
      if (
        activeProject !== "all" &&
        (dataset.project_name?.trim() || "Binafsi") !== activeProject
      ) {
        return false;
      }
      if (!needle) return true;
      // Match the filename and the project, since users often recall one and
      // search for the other.
      return (
        dataset.original_filename.toLowerCase().includes(needle) ||
        (dataset.project_name?.toLowerCase().includes(needle) ?? false) ||
        dataset.file_type.toLowerCase().includes(needle)
      );
    });
  }, [datasets, activeProject, query]);

  const totalRows = datasets.reduce((sum, d) => sum + (d.row_count || 0), 0);
  const totalColumns = datasets.reduce((sum, d) => sum + (d.column_count || 0), 0);

  // The strip reports what we can actually count. The prototype shows a storage
  // figure and an average quality score; neither is available from this API, so
  // variables and projects stand in rather than inventing either.
  const projectCount = new Set(
    datasets.map((dataset) => dataset.project_name?.trim() || "Binafsi")
  ).size;

  return (
    <AppShell
      title="Projects & Datasets"
      description={`${projectCount} ${
        projectCount === 1 ? "mradi" : "miradi"
      } · ${datasets.length} ${datasets.length === 1 ? "dataset" : "datasets"}`}
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
      <SummaryStrip
        items={[
          {
            icon: "database",
            value: datasets.length.toLocaleString(),
            label: "Datasets zote",
          },
          { value: totalRows.toLocaleString(), label: "Jumla ya safu" },
          { value: totalColumns.toLocaleString(), label: "Jumla ya vigezo" },
          {
            icon: "folder",
            value: projectCount.toLocaleString(),
            label: "Miradi",
          },
        ]}
      />

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

      {/* Prototype library toolbar: search on the left, count on the right. */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <InlineSearch
          value={query}
          onChange={setQuery}
          placeholder="Tafuta datasets..."
          label="Tafuta datasets"
        />
        <p className="text-caption text-ink-muted" aria-live="polite">
          {loading
            ? "Inapakia..."
            : `Inaonyesha ${filteredDatasets.length} kati ya ${datasets.length}`}
        </p>
      </div>

      <div className="overflow-hidden rounded-xl border border-surface-border bg-surface-panel shadow-card">
        {loading ? (
          <div className="p-4">
            <TableSkeleton rows={5} columns={5} />
          </div>
        ) : datasets.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="Hakuna dataset bado"
              description="Anza kwa kupakia faili la CSV, Excel, JSON, Stata, SPSS au R."
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
          </div>
        ) : filteredDatasets.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="Hakuna matokeo"
              description="Hakuna dataset inayolingana na kichujio hiki."
              icon="search"
              action={
                <Button
                  variant="secondary"
                  onClick={() => {
                    setQuery("");
                    setActiveProject("all");
                  }}
                >
                  Onyesha zote
                </Button>
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse whitespace-nowrap">
              <thead>
                <tr>
                  {[
                    "Dataset",
                    "Format",
                    "Safu",
                    "Vigezo",
                    "Hali",
                    "Toleo",
                    "Imebadilishwa",
                    "Hatua",
                    "",
                  ].map((heading, index) => (
                    <th
                      key={heading || index}
                      scope="col"
                      className="border-b border-surface-border bg-surface-sunken px-3 py-2.5 text-left text-overline font-semibold uppercase tracking-[0.06em] text-ink-muted"
                    >
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
            {filteredDatasets.map((dataset) => {
              const done = completedStageCount({ status: dataset.status });
              const confirming = pendingDelete === dataset.id;
              const canDelete = meId === null || dataset.user_id === meId;
              return (
                <tr
                  key={dataset.id}
                  className="transition-colors duration-150 ease-standard hover:bg-primary-50/40"
                >
                  <td className="border-b border-surface-border px-3 py-2.5">
                    <div className="flex items-center gap-2.5">
                      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary-50 text-primary-600">
                        <Icon name="database" size={16} />
                      </span>
                      <div className="min-w-0">
                        <Link
                          href={`/datasets/${dataset.id}`}
                          className="block max-w-[240px] truncate font-medium text-ink hover:text-primary-700 hover:underline"
                        >
                          {dataset.original_filename}
                        </Link>
                        {dataset.project_name && (
                          <span className="block max-w-[240px] truncate text-caption text-ink-muted">
                            {dataset.project_name}
                          </span>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="border-b border-surface-border px-3 py-2.5">
                    <span className="rounded bg-surface-sunken px-1.5 py-0.5 text-caption font-semibold uppercase text-ink-secondary">
                      {dataset.file_type}
                    </span>
                  </td>
                  <td className="tabular border-b border-surface-border px-3 py-2.5 text-body text-ink-secondary">
                    {dataset.row_count.toLocaleString()}
                  </td>
                  <td className="tabular border-b border-surface-border px-3 py-2.5 text-body text-ink-secondary">
                    {dataset.column_count}
                  </td>
                  <td className="border-b border-surface-border px-3 py-2.5">
                    <Badge
                      size="sm"
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
                  </td>
                  <td className="tabular border-b border-surface-border px-3 py-2.5 text-body text-ink-secondary">
                    v{dataset.current_version ?? 1}
                  </td>
                  <td className="border-b border-surface-border px-3 py-2.5 text-caption text-ink-muted">
                    {formatDate(dataset.uploaded_at)}
                  </td>

                  {/* Pipeline progress stays as a title-only tooltip: the table
                      has no room for six dots per row, and the status badge
                      already carries the same information visibly. */}
                  <td className="border-b border-surface-border px-3 py-2.5">
                    <span
                      className="hidden sm:inline-flex"
                      title={`Hatua ${done} kati ya 6 zimekamilika`}
                    >
                      <StageDots done={done} />
                    </span>
                  </td>
                  <td className="border-b border-surface-border px-3 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Link href={`/datasets/${dataset.id}`}>
                        <Button size="small">
                          <Icon name="eye" size={14} />
                          Fungua
                        </Button>
                      </Link>
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
                      {canDelete &&
                        (confirming ? (
                          <span className="flex items-center gap-1 rounded-md border border-danger/30 bg-danger-bg px-1.5 py-0.5">
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
                  </td>
                </tr>
              );
            })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppShell>
  );
}
