"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState, Stat } from "@/components/Card";
import { DataTable, formatCell } from "@/components/DataTable";
import { SelectInput } from "@/components/Field";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import { api, apiErrorMessage, DatasetDetailResponse, ExploreResponse, OrgProject } from "@/lib/api";
import { DatasetHealth } from "@/components/DatasetHealth";
import { VariableProfiles } from "@/components/VariableProfiles";

/** "Updated 18 min ago" the way the prototype reads it, falling back to a date. */
function relativeTime(value: string | null | undefined): string {
  if (!value) return "—";
  const stamp = new Date(value).getTime();
  if (!Number.isFinite(stamp)) return "—";
  const seconds = Math.round((Date.now() - stamp) / 1000);
  if (seconds < 60) return "sasa hivi";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `kinyuma ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `kinyuma ${hours} saa`;
  const days = Math.round(hours / 24);
  if (days < 30) return `kinyuma ${days} siku`;
  return new Date(value).toLocaleDateString("en-KE");
}

export default function DatasetDetailPage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params?.id);
  const { showToast } = useToast();
  const [detail, setDetail] = useState<DatasetDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<OrgProject[]>([]);
  const [meId, setMeId] = useState<number | null>(null);
  const [explore, setExplore] = useState<ExploreResponse | null>(null);

  useEffect(() => {
    api.auth
      .me()
      .then((profile) => setMeId(profile.id))
      .catch(() => setMeId(null));
  }, []);

  const load = useCallback(async () => {
    if (!Number.isFinite(datasetId)) return;
    setLoading(true);
    setError(null);
    try {
      setDetail(await api.datasets.get(datasetId));
    } catch (caught) {
      const message = apiErrorMessage(caught);
      setError(message);
      showToast(message, "danger");
    } finally {
      setLoading(false);
    }
  }, [datasetId, showToast]);

  useEffect(() => {
    load();
  }, [load]);

  // Explore is what carries the mean, median and distribution for the health
  // panel. It is loaded alongside the detail but never blocks the page: if it
  // fails the panel still shows completeness from the profiles.
  useEffect(() => {
    if (!Number.isFinite(datasetId)) return;
    let cancelled = false;
    api.datasets
      .explore(datasetId)
      .then((response) => {
        if (!cancelled) setExplore(response);
      })
      .catch(() => {
        if (!cancelled) setExplore(null);
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId, load]);

  useEffect(() => {
    api.organizations
      .list()
      .then((orgs) =>
        Promise.all(orgs.map((org) => api.organizations.projects(org.id)))
      )
      .then((lists) => setProjects(lists.flat()))
      .catch(() => setProjects([]));
  }, []);

  async function handleProjectChange(value: string) {
    const projectId = value === "" ? null : Number(value);
    try {
      await api.datasets.setProject(datasetId, projectId);
      showToast(
        projectId === null
          ? "Data imerudi kuwa ya binafsi"
          : "Data imewekwa kwenye mradi",
        "success"
      );
      load();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }

  const columns = useMemo(() => detail?.columns ?? [], [detail]);
  const previewRows = useMemo(() => detail?.preview_rows ?? [], [detail]);
  const previewColumns = useMemo(
    () => (previewRows.length > 0 ? Object.keys(previewRows[0]) : []),
    [previewRows]
  );
  const totalMissing = columns.reduce(
    (sum, column) => sum + (column.missing_count || 0),
    0
  );
  const columnsWithMissing = columns.filter((column) => column.missing_count > 0);
  const numericColumns = columns
    .filter((column) => column.data_type === "numeric")
    .map((column) => column.name);

  // The type row under each preview column name. The stored dtype is what the
  // file actually holds; the explore kind is the richer reading of it, so use
  // that when it is available and fall back to the profile.
  const previewTypes = useMemo(() => {
    const map: Record<string, string> = {};
    for (const column of previewColumns) {
      const kind = explore?.columns.find((entry) => entry.name === column)?.kind;
      const stored = columns.find((entry) => entry.name === column)?.data_type;
      if (kind) {
        map[column] =
          kind === "numeric"
            ? "Numeric"
            : kind === "categorical"
              ? "Categorical"
              : kind === "datetime"
                ? "Date"
                : kind === "boolean"
                  ? "Yes/No"
                  : "Text";
      } else if (stored === "numeric") {
        map[column] = "Numeric";
      } else if (stored === "integer") {
        map[column] = "Numeric";
      } else {
        map[column] = "Categorical";
      }
    }
    return map;
  }, [previewColumns, explore, columns]);

  return (
    <AppShell
      title={detail?.dataset.original_filename ?? "Dataset"}
      description={`Version ${detail?.dataset_version ?? 1} · Updated ${relativeTime(detail?.dataset.uploaded_at)}`}
      actions={
        <>
          <Link href="/datasets">
            <Button variant="ghost" icon="arrow-right">
              Orodha
            </Button>
          </Link>
          <Link href={`/datasets/${datasetId}/studio`}>
            <Button variant="secondary" icon="sliders">
              Data studio
            </Button>
          </Link>
          <Link href={`/datasets/${datasetId}/ask`}>
            <Button variant="secondary" icon="sparkles">
              Msaidizi
            </Button>
          </Link>
          <Link href={`/datasets/${datasetId}/charts`}>
            <Button variant="secondary" icon="chart">
              Chora chati
            </Button>
          </Link>
          <Link href={`/datasets/${datasetId}/statistics`}>
            <Button icon="calculator">Chambua takwimu</Button>
          </Link>
        </>
      }
    >
      {loading ? (
        <Card>
          <TableSkeleton rows={8} columns={5} />
        </Card>
      ) : error ? (
        <Card>
          <EmptyState
            title="Imeshindikana kupata dataset"
            description={error}
            icon="alert-circle"
            action={
              <Link href="/datasets">
                <Button variant="secondary">Rudi kwenye orodha</Button>
              </Link>
            }
          />
        </Card>
      ) : (
        <>
          {detail && (
            <dl className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-md border border-surface-border bg-surface-panel px-4 py-3 text-caption">
              <div className="flex items-center gap-1.5">
                <dt className="text-ink-muted">Toleo</dt>
                <dd className="font-mono font-medium text-ink">
                  v{detail.dataset_version}
                </dd>
              </div>
              <div className="flex items-center gap-1.5">
                <dt className="text-ink-muted">Aina</dt>
                <dd className="font-medium uppercase text-ink">{detail.dataset.file_type}</dd>
              </div>
              <div className="flex items-center gap-1.5">
                <dt className="text-ink-muted">Imepakiwa</dt>
                <dd className="text-ink">
                  {detail.dataset.uploaded_at
                    ? new Date(detail.dataset.uploaded_at).toLocaleString()
                    : "—"}
                </dd>
              </div>
              <div className="flex items-center gap-1.5">
                <dt className="text-ink-muted">Hali</dt>
                <dd>
                  <Badge tone={detail.dataset.status === "ready" ? "success" : "warning"}>
                    {detail.dataset.status}
                  </Badge>
                </dd>
              </div>
              <div className="ml-auto flex items-center gap-1.5">
                <dt className="text-ink-muted">Ufikiaji</dt>
                <dd>
                  {detail.dataset.project_name ? (
                    <Badge tone="info" icon="folder">
                      {detail.dataset.project_name}
                    </Badge>
                  ) : (
                    <Badge tone="neutral">Binafsi</Badge>
                  )}
                </dd>
              </div>
            </dl>
          )}

          <Card
            title="Preview ya data"
            description={`Rows ${previewRows.length} za kwanza kama zilivyo sasa. Aina ya kila column iko chini ya jina lake.`}
            icon="table"
            footer={`${detail?.dataset.row_count.toLocaleString() ?? 0} rows · ${detail?.dataset.column_count ?? 0} columns`}
          >
            {previewRows.length === 0 ? (
              <EmptyState
                title="Hakuna data ya kutosha"
                description="Faili linaonekana halina rows."
                icon="table"
              />
            ) : (
              <DataTable
                caption="Dataset preview"
                columns={previewColumns}
                rows={previewRows}
                numericColumns={numericColumns}
                columnTypes={previewTypes}
                missingDisplay="dot"
                typeRowTone={(column) =>
                  (columns.find((entry) => entry.name === column)?.missing_count ?? 0) > 0
                    ? "warning"
                    : "default"
                }
                maxHeight="28rem"
              />
            )}
          </Card>

          {detail && (
            <DatasetHealth
              rowCount={detail.dataset.row_count}
              columnCount={detail.dataset.column_count}
              columns={columns}
              explore={explore?.columns ?? null}
              isOwnDataset={meId === null || detail.dataset.user_id === meId}
            />
          )}

          {explore && (
            <VariableProfiles
              columns={explore.columns}
              rowCount={explore.row_count}
            />
          )}

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Safu (rows)" value={detail?.dataset.row_count.toLocaleString()} />
            <Stat label="Columns" value={detail?.dataset.column_count} />
            <Stat
              label="Missing values"
              value={totalMissing.toLocaleString()}
              hint={
                columnsWithMissing.length === 0
                  ? "Hakuna missing values"
                  : `Katika columns ${columnsWithMissing.length}`
              }
            />
            <Stat
              label="Columns za namba"
              value={numericColumns.length}
              hint={numericColumns.slice(0, 3).join(", ") || "Hakuna"}
            />
          </div>

          <Card
            title="Ufikiaji wa data"
            description="Data ya binafsi ni yawewe pekee. Ukiiweka kwenye mradi, wanachama wa shirika hilo wataweza kuiona kulingana na kiwango chao."
            icon="folder"
          >
            {meId !== null && detail?.dataset.user_id !== meId ? (
              <div className="flex flex-wrap items-center gap-3">
                <Badge tone="primary" icon="folder">
                  {detail?.dataset.project_name ?? "Mradi"}
                </Badge>
                <p className="text-body text-ink-secondary">
                  Dataset hii ni ya mwanachama mwingine. Unaweza kuiangalia na
                  kuichambua kama kiwango chako kinaruhusu.
                </p>
              </div>
            ) : (
              <div className="flex flex-wrap items-end gap-3">
                <div className="min-w-[220px] flex-1">
                  <SelectInput
                    id="dataset_project"
                    label="Mradi"
                    value={detail?.dataset.project_id ?? ""}
                    onChange={(event) => handleProjectChange(event.target.value)}
                    options={[
                      { value: "", label: "Data ya binafsi" },
                      ...projects.map((project) => ({
                        value: String(project.id),
                        label: project.name,
                      })),
                    ]}
                  />
                </div>
                {detail?.dataset.project_id ? (
                  <Badge tone="info" icon="users">
                    Inashirikishwa na shirika
                  </Badge>
                ) : (
                  <Badge tone="neutral" icon="lock">
                    Binafsi
                  </Badge>
                )}
              </div>
            )}
          </Card>

          {columnsWithMissing.length > 0 && (
            <Card
              title="Tahadhari: missing values"
              icon="alert-triangle"
              tone="warning"
              actions={
                <Link href={`/datasets/${datasetId}/studio`}>
                  <Button variant="secondary" size="small" icon="sliders">
                    Safisha
                  </Button>
                </Link>
              }
            >
              <p className="mb-3 text-body text-ink-secondary">
                Columns zifuata zina thamani zilizo-kosekana. Safisha katika data studio
                kabla ya kuchambua ili matokeo yaweze sahihi.
              </p>
              <div className="flex flex-wrap gap-2">
                {columnsWithMissing.map((column) => (
                  <Badge key={column.name} tone="warning">
                    {column.name}: {column.missing_count}
                  </Badge>
                ))}
              </div>
            </Card>
          )}

          <Card
            title="Muundo wa columns"
            description="Aina ya data, missing values na unique values kwa kila column."
            icon="table"
          >
            <DataTable
              caption="Muundo wa columns"
              columns={["name", "data_type", "missing_count", "unique_count", "min", "max"]}
              columnLabels={{
                name: "Jina",
                data_type: "Aina ya data",
                missing_count: "Zilizokosekana",
                unique_count: "Thamani unique",
                min: "Chini kabisa",
                max: "Juu kabisa",
              }}
              rows={columns as unknown as Record<string, unknown>[]}
              numericColumns={["missing_count", "unique_count", "min", "max"]}
              renderCell={(column, value) => {
                if (column === "data_type") {
                  return (
                    <Badge tone={value === "numeric" ? "primary" : "neutral"}>
                      {String(value ?? "—")}
                    </Badge>
                  );
                }
                if (column === "missing_count" && Number(value) > 0) {
                  return <Badge tone="warning">{String(value)}</Badge>;
                }
                if (column === "name") {
                  return <span className="font-mono text-caption">{String(value)}</span>;
                }
                return formatCell(value);
              }}
            />
          </Card>

          <Card
            title="Safisha na badilisha data"
            description="Data studio huunda version mpya kwa kila hatua hakuna data inayopotea."
            icon="sliders"
            actions={
              <Link href={`/datasets/${datasetId}/studio`}>
                <Button icon="sliders">Fungua data studio</Button>
              </Link>
            }
          >
            <p className="text-body text-ink-secondary">
              Safisha missing values, duplicates na aina za columns, kisha
              badilisha (filter, group, calculate) kabla ya kuchambua.
            </p>
          </Card>
        </>
      )}
    </AppShell>
  );
}
