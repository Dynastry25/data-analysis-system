"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState, Stat } from "@/components/Card";
import { DataTable } from "@/components/DataTable";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import { api, apiErrorMessage, DatasetDetailResponse, OrgProject } from "@/lib/api";

export default function DatasetDetailPage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params?.id);
  const { showToast } = useToast();
  const [detail, setDetail] = useState<DatasetDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<OrgProject[]>([]);

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
      title={detail?.dataset.original_filename ?? "Dataset"}
      description="Angalia muundo wa data, safisha kasoro, kisha chambua."
      actions={
        <>
          <Link href="/datasets">
            <Button variant="secondary">Rudi kwenye orodha</Button>
          </Link>
          <Link href={`/datasets/${datasetId}/studio`}>
            <Button variant="secondary">Data studio</Button>
          </Link>
          <Link href={`/datasets/${datasetId}/statistics`}>
            <Button>Chambua takwimu</Button>
          </Link>
          <Link href={`/datasets/${datasetId}/ask`}>
            <Button variant="secondary">Msaidizi</Button>
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
            action={
              <Link href="/datasets">
                <Button variant="secondary">Rudi kwenye orodha</Button>
              </Link>
            }
          />
        </Card>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Safu (rows)" value={detail?.dataset.row_count.toLocaleString()} />
            <Stat label="Columns" value={detail?.dataset.column_count} />
            <Stat
              label="Missing values"
              value={totalMissing.toLocaleString()}
              hint={`Katika columns ${columnsWithMissing.length}`}
            />
            <Stat
              label="Columns za namba"
              value={numericColumns.length}
              hint={numericColumns.slice(0, 3).join(", ") || ""}
            />
          </div>

          <Card
            title="Ufikiaji wa data"
            description="Data ya binafsi ni yawewe pekee. Ukiiweka kwenye mradi, wanachama wa shirika hilo wataweza kuiona kulingana na kiwango chao."
          >
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-[220px] flex-1">
                <label htmlFor="dataset_project" className="block text-body text-neutral-900">
                  Mradi
                </label>
                <select
                  id="dataset_project"
                  value={detail?.dataset.project_id ?? ""}
                  onChange={(event) => handleProjectChange(event.target.value)}
                  className="mt-1 h-10 w-full rounded border border-neutral-200 bg-white px-3 text-body outline-none focus:border-primary-500"
                >
                  <option value="">Data ya binafsi</option>
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
                </select>
              </div>
              {detail?.dataset.project_id ? (
                <Badge tone="info">Inashirikishwa na shirika</Badge>
              ) : (
                <Badge tone="neutral">Binafsi</Badge>
              )}
            </div>
          </Card>

          {columnsWithMissing.length > 0 && (
            <Card title="Tahadhari: missing values" className="border-warning">
              <div className="flex flex-wrap gap-2">
                {columnsWithMissing.map((column) => (
                  <Badge key={column.name} tone="warning" withIcon>
                    {column.name}: {column.missing_count}
                  </Badge>
                ))}
              </div>
            </Card>
          )}

          <Card
            title="Muundo wa columns"
            description="Aina ya data, missing values na unique values kwa kila column."
          >
            <DataTable
              caption="Column profile"
              columns={["name", "data_type", "missing_count", "unique_count", "min", "max"]}
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
                  return (
                    <Badge tone="warning" withIcon>
                      {String(value)}
                    </Badge>
                  );
                }
                if (value === null || value === undefined) return "—";
                return String(value);
              }}
            />
          </Card>

          <Card
            title="Preview ya data"
            description={`Rows ${previewRows.length} za kwanza kama zilivyo sasa.`}
          >
            {previewRows.length === 0 ? (
              <EmptyState
                title="Hakuna data ya kutosha"
                description="Faili linaonekana halina rows."
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
            actions={
              <Link href={`/datasets/${datasetId}/studio`}>
                <Button>Fungua data studio</Button>
              </Link>
            }
          >
            <p className="text-body text-neutral-600">
              Safisha missing values, duplicates na aina za columns, kisha
              badilisha (filter, group, calculate) kabla ya kuchambua.
            </p>
          </Card>
        </>
      )}
    </AppShell>
  );
}
