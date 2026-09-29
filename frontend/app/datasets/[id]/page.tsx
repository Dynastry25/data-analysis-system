"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState, Stat } from "@/components/Card";
import { DataTable, formatCell } from "@/components/DataTable";
import { SelectInput } from "@/components/Field";
import { MetricCard } from "@/components/MetricCard";
import { ProfileSummary } from "@/components/ProfileSummary";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import { api, apiErrorMessage, DatasetDetailResponse, OrgProject } from "@/lib/api";

function formatDate(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
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

  const columns = detail?.columns ?? [];
  const previewRows = detail?.preview_rows ?? [];
  const previewColumns = previewRows.length > 0 ? Object.keys(previewRows[0]) : [];
  const totalMissing = columns.reduce(
    (sum, column) => sum + (column.missing_count || 0),
    0
  );
  const columnsWithMissing = columns.filter((column) => column.missing_count > 0);
  const numericColumns = columns
    .filter((column) => column.data_type === "numeric")
    .map((column) => column.name);

  return (
    <AppShell
      title={`${detail?.dataset.original_filename ?? "Dataset"} · v${detail?.dataset_version ?? 1}`}
      description={`Updated ${formatDate(detail?.dataset.uploaded_at ?? null)}`}
            actions={
              <>
                <Link href="/datasets">
                  <Button variant="ghost" icon="arrow-right">
                    Orodha
                  </Button>
                </Link>
                <Link href={`/datasets/${datasetId}/validate`}>
                  <Button variant="secondary" icon="check">
                    Validate
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
                <dd className="text-ink">{formatDate(detail.dataset.uploaded_at)}</dd>
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

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              icon="layers"
              tone="primary"
              label="Safu (rows)"
              value={(detail?.dataset.row_count ?? 0).toLocaleString()}
              hint="Rows zilizopo kwenye toleo la sasa"
            />
            <MetricCard
              icon="grid"
              tone="info"
              label="Columns"
              value={detail?.dataset.column_count ?? 0}
              hint={`${numericColumns.length} za namba · ${
                columns.length - numericColumns.length
              } nyingine`}
            />
            <MetricCard
              icon={totalMissing === 0 ? "check" : "alert-triangle"}
              tone={totalMissing === 0 ? "success" : "warning"}
              label="Missing values"
              value={totalMissing.toLocaleString()}
              hint={
                columnsWithMissing.length === 0
                  ? "Hakuna missing values"
                  : `Katika columns ${columnsWithMissing.length}`
              }
            />
            <MetricCard
              icon="calculator"
              tone="primary"
              label="Columns za namba"
              value={numericColumns.length}
              hint={
                numericColumns.length === 0
                  ? "Hakuna column ya namba"
                  : `${numericColumns.slice(0, 3).join(", ")}${
                      numericColumns.length > 3
                        ? ` +${numericColumns.length - 3}`
                        : ""
                    }`
              }
            />
          </div>

          <Card
            title="Dataset Health"
            icon="chart"
            description="Ukamilifu, missing cells na wastani — kutoka kwenye profile halisi."
          >
            <div className="grid gap-3 sm:grid-cols-4">
              <Stat
                label="Completeness"
                value={`${detail && detail.dataset.row_count > 0 ? Math.max(0, Math.round((1 - totalMissing / (detail.dataset.row_count * Math.max(columns.length, 1))) * 100)) : 100}%`}
              />
              <Stat label="Missing cells" value={totalMissing.toLocaleString()} />
              <Stat
                label="Rows"
                value={(detail?.dataset.row_count ?? 0).toLocaleString()}
              />
              <Stat label="Columns" value={detail?.dataset.column_count ?? 0} />
            </div>
          </Card>

          <Card
            title="Muhtasari wa data"
            description="Ukamilifu, aina za columns na thamani unique — zote zikitoka kwenye profile halisi ya dataset hii."
            icon="chart"
            actions={
              <>
                {totalMissing > 0 && (
                  <Link href={`/datasets/${datasetId}/studio`}>
                    <Button variant="secondary" size="small" icon="sliders">
                      Safisha missing
                    </Button>
                  </Link>
                )}
                <Link href={`/datasets/${datasetId}/explore`}>
                  <Button variant="secondary" size="small" icon="chart-line">
                    Chunguza zaidi
                  </Button>
                </Link>
              </>
            }
          >
            <ProfileSummary
              columns={columns}
              rowCount={detail?.dataset.row_count ?? 0}
            />
          </Card>

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
            title="Preview ya data"
            description={`Rows ${previewRows.length} za kwanza kama zilivyo sasa.`}
            icon="table"
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
                maxHeight="28rem"
              />
            )}
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
