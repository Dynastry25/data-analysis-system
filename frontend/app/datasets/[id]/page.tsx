"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { CollapsibleCard } from "@/components/CollapsibleCard";
import { DataTable, formatCell } from "@/components/DataTable";
import { SelectInput } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import { api, apiErrorMessage, DatasetDetailResponse, ExploreResponse, OrgProject } from "@/lib/api";
import { DatasetHealth } from "@/components/DatasetHealth";
import { VariableProfiles } from "@/components/VariableProfiles";
import { useLanguage } from "@/lib/i18n";

/** The four reference sections that fold away, and whether each is open. */
interface OpenSections {
  preview: boolean;
  profiles: boolean;
  schema: boolean;
  studio: boolean;
}

export default function DatasetDetailPage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params?.id);
  const { showToast } = useToast();
  const { t, formatNumber, formatDate, formatRelative } = useLanguage();
  const [detail, setDetail] = useState<DatasetDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<OrgProject[]>([]);
  const [meId, setMeId] = useState<number | null>(null);
  const [explore, setExplore] = useState<ExploreResponse | null>(null);

  /*
   * The preview is the one section that opens by default: a dataset page whose
   * preview is folded looks empty, and people arrive here to see their rows.
   * The other three are reference material, so they start folded.
   */
  const [open, setOpen] = useState<OpenSections>({
    preview: true,
    profiles: false,
    schema: false,
    studio: false,
  });

  const toggle = useCallback((key: keyof OpenSections) => {
    setOpen((current) => ({ ...current, [key]: !current[key] }));
  }, []);

  const allOpen = open.preview && open.profiles && open.schema && open.studio;
  const toggleAll = useCallback(() => {
    setOpen((current) => {
      const next = !current.preview && !current.profiles && !current.schema && !current.studio;
      return { preview: next, profiles: next, schema: next, studio: next };
    });
  }, []);

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
          ? t("project.personal")
          : t("project.assigned"),
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
  const exploreColumns = useMemo(() => explore?.columns ?? [], [explore]);

  const columnsWithMissing = useMemo(
    () => columns.filter((column) => column.missing_count > 0),
    [columns]
  );

  // The same rule the profiles card uses, counted here so its header badge can
  // say how many columns need review before anyone opens it.
  const warnCount = useMemo(
    () =>
      exploreColumns.filter(
        (column) =>
          column.missing_count > 0 ||
          (column.unique_count !== null && column.unique_count <= 1)
      ).length,
    [exploreColumns]
  );

  const isOwnDataset = meId === null || detail?.dataset.user_id === meId;

  // The type row under each preview column name, already translated. The stored
  // dtype is what the file actually holds; the explore kind is the richer
  // reading of it, so prefer that when it is loaded.
  const previewTypes = useMemo(() => {
    const map: Record<string, string> = {};
    for (const name of previewColumns) {
      const kind = exploreColumns.find((entry) => entry.name === name)?.kind;
      const stored = columns.find((entry) => entry.name === name)?.data_type;
      if (kind === "numeric") map[name] = t("schema.numeric");
      else if (kind === "categorical") map[name] = t("schema.categorical");
      else if (kind === "datetime") map[name] = t("schema.date");
      else if (kind === "boolean") map[name] = t("schema.boolean");
      else if (kind === "text") map[name] = t("schema.text");
      else if (stored === "numeric" || stored === "integer") map[name] = t("schema.numeric");
      else map[name] = t("schema.categorical");
    }
    return map;
  }, [previewColumns, exploreColumns, columns, t]);
  return (
    <AppShell
      title={detail?.dataset.original_filename ?? t("common.noResults")}
      description={t("dataset.subtitle", {
        version: `${t("common.version")} ${detail?.dataset_version ?? 1}`,
        relative: formatRelative(detail?.dataset.uploaded_at),
      })}
      actions={
        <>
          <Link href="/datasets">
            <Button variant="ghost" icon="arrow-right">
              {t("dataset.backToList")}
            </Button>
          </Link>
          <Link href={`/datasets/${datasetId}/studio`}>
            <Button variant="secondary" icon="sliders">
              {t("dataset.dataStudio")}
            </Button>
          </Link>
          <Link href={`/datasets/${datasetId}/ask`}>
            <Button variant="secondary" icon="sparkles">
              {t("dataset.assistant")}
            </Button>
          </Link>
          <Link href={`/datasets/${datasetId}/charts`}>
            <Button variant="secondary" icon="chart">
              {t("dataset.drawChart")}
            </Button>
          </Link>
        </>
      }
    >
      {loading ? (
        <div className="space-y-6">
          <TableSkeleton rows={4} columns={4} />
          <TableSkeleton rows={6} columns={5} />
        </div>
      ) : error ? (
        <EmptyState
          title={t("dataset.error.title")}
          description={error}
          action={
            <Button icon="refresh" onClick={load}>
              {t("common.retry")}
            </Button>
          }
          icon="alert-triangle"
        />
      ) : !detail ? null : (
        <>
          {/*
            A compact identity strip. These facts answer "which file, which
            version, whose is it" without scrolling. They are facts rather than
            controls, so they stay clear of the health verdict below.
          */}
          <Card
            title={t("overview.title")}
            icon="info"
            description={formatDate(detail.dataset.uploaded_at)}
            actions={
              <Badge tone="neutral" icon={detail.dataset.project_id ? "folder" : "lock"}>
                {detail.dataset.project_id ? t("project.assigned") : t("common.private")}
              </Badge>
            }
          >
            <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { label: t("overview.version"), value: `v${detail.dataset_version ?? 1}` },
                { label: t("overview.type"), value: (detail.dataset.file_type ?? "—").toUpperCase() },
                {
                  label: t("common.rows"),
                  value: formatNumber(detail.dataset.row_count ?? 0, { maximumFractionDigits: 0 }),
                },
                { label: t("overview.status"), value: detail.dataset.status ?? "—" },
              ].map((item) => (
                <div
                  key={item.label}
                  className="rounded-sm border border-surface-border bg-surface-sunken px-3.5 py-3"
                >
                  <dt className="text-overline uppercase tracking-wide text-ink-muted">
                    {item.label}
                  </dt>
                  <dd className="tabular mt-1 font-mono text-body font-medium text-ink">
                    {item.value}
                  </dd>
                </div>
              ))}
            </dl>

            {/*
              The project picker is offered only to the owner. A member of
              someone else's organisation can see that a dataset is shared, but
              must not be able to move it between projects.
            */}
            {isOwnDataset && (
              <div className="mt-4 border-t border-surface-border pt-4">
                <div className="mt-1.5 max-w-sm">
                  <SelectInput
                    label={t("project.label")}
                    value={detail.dataset.project_id ? String(detail.dataset.project_id) : ""}
                    onChange={(event) => handleProjectChange(event.target.value)}
                    options={[
                      { value: "", label: t("project.personal") },
                      ...projects.map((project) => ({
                        value: String(project.id),
                        label: project.name,
                      })),
                    ]}
                  />
                </div>
                <p className="mt-2 text-caption text-ink-muted">
                  {detail.dataset.project_id
                    ? t("project.sharedBody")
                    : t("project.personalBody")}
                </p>
              </div>
            )}
          </Card>

          {/*
            The health verdict is the first analysis card on the page and it is
            never folded. Every other decision here — clean it, read the rows,
            look at one column — depends on whether the data is sound, so the
            verdict is read first and the detail sits underneath it.
          */}
          <DatasetHealth
            rowCount={detail.dataset.row_count ?? 0}
            columnCount={detail.dataset.column_count ?? 0}
            columns={columns}
            explore={exploreColumns}
            isOwnDataset={isOwnDataset}
          />

          {columnsWithMissing.length > 0 && (
            <Card
              title={t("warning.title")}
              icon="alert-triangle"
              tone="warning"
              actions={
                <Link href={`/datasets/${datasetId}/studio`}>
                  <Button variant="secondary" size="small" icon="sliders">
                    {t("warning.clean")}
                  </Button>
                </Link>
              }
            >
              <p className="text-body text-ink-secondary">
                {t("warning.description")}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {columnsWithMissing.map((column) => (
                  <Badge key={column.name} tone="warning">
                    {column.name}:{" "}
                    {formatNumber(column.missing_count, { maximumFractionDigits: 0 })}
                  </Badge>
                ))}
              </div>
            </Card>
          )}

          {/*
            Everything below is on demand. A 16-column preview and a schema
            table are reference material: useful when wanted, noise the rest of
            the time. Each header carries its own counts and verdicts, so a
            folded card still says whether opening it is worth it.
          */}
          <section className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-h3 text-ink">{t("overview.title")}</h2>
              <Button
                variant="ghost"
                size="small"
                icon={allOpen ? "chevron-up" : "chevron-down"}
                onClick={toggleAll}
              >
                {allOpen ? t("common.collapseAll") : t("common.expandAll")}
              </Button>
            </div>

            <CollapsibleCard
              title={t("preview.title")}
              description={t("preview.description", { count: previewRows.length })}
              icon="table"
              badge={
                <Badge tone="neutral">
                  {formatNumber(detail.dataset.row_count ?? 0, { maximumFractionDigits: 0 })}{" "}
                  {t("common.rows")}
                </Badge>
              }
              open={open.preview}
              onToggle={() => toggle("preview")}
              footer={t("preview.footer", {
                rows: formatNumber(detail.dataset.row_count ?? 0, { maximumFractionDigits: 0 }),
                columns: detail.dataset.column_count ?? 0,
              })}
            >
              {previewRows.length === 0 ? (
                <div className="px-4 py-4 sm:px-5">
                  <EmptyState
                    title={t("preview.empty.title")}
                    description={t("preview.empty.description")}
                    icon="table"
                  />
                </div>
              ) : (
                <div className="px-4 pb-4 sm:px-5">
                  <DataTable
                    caption={t("preview.title")}
                    columns={previewColumns}
                    columnLabels={Object.fromEntries(
                      previewColumns.map((column) => [column, column]),
                    )}
                    rows={previewRows as unknown as Record<string, unknown>[]}
                    columnTypes={previewTypes}
                    typeRowTone={(column) =>
                      columnsWithMissing.some((entry) => entry.name === column)
                        ? "warning"
                        : "default"
                    }
                    renderCell={(column, value) =>
                      column === previewColumns[0] ? (
                        <span className="font-mono text-caption">
                          {String(value ?? "—")}
                        </span>
                      ) : value === null || value === undefined || value === "" ? (
                        <span className="text-caption text-ink-muted">
                          <span aria-hidden="true">•</span> {t("common.valueMissing")}
                        </span>
                      ) : (
                        formatCell(value)
                      )
                    }
                  />
                  <p className="mt-3 flex items-start gap-2 text-caption text-ink-muted">
                    <Icon name="info" size={14} className="mt-0.5 shrink-0" />
                    <span>{t("preview.moreHint")}</span>
                  </p>
                </div>
              )}
            </CollapsibleCard>

            <CollapsibleCard
              title={t("profiles.title")}
              description={t("profiles.description")}
              icon="sliders"
              badge={
                warnCount > 0 ? (
                  <Badge tone="warning" icon="alert-triangle">
                    {t("profiles.needReview", { count: warnCount })}
                  </Badge>
                ) : (
                  <Badge tone="success" icon="check">
                    {t("profiles.allClean")}
                  </Badge>
                )
              }
              open={open.profiles}
              onToggle={() => toggle("profiles")}
            >
              {exploreColumns.length === 0 ? (
                <div className="px-4 py-4 sm:px-5">
                  <EmptyState title={t("profiles.empty")} icon="sliders" />
                </div>
              ) : (
                <VariableProfiles
                  columns={exploreColumns}
                  rowCount={detail.dataset.row_count ?? 0}
                />
              )}
            </CollapsibleCard>

            <CollapsibleCard
              title={t("schema.title")}
              description={t("schema.description")}
              icon="table"
              badge={
                <Badge tone="neutral">
                  {columns.length} {t("common.columns")}
                </Badge>
              }
              open={open.schema}
              onToggle={() => toggle("schema")}
              footer={t("schema.expandHint")}
            >
              <DataTable
                caption={t("schema.title")}
                columns={[
                  "name",
                  "variable_label",
                  "data_type",
                  "missing_count",
                  "unique_count",
                  "min",
                  "max",
                ]}
                columnLabels={{
                  name: t("common.name"),
                  variable_label: t("label.column"),
                  data_type: t("common.type"),
                  missing_count: t("common.missing"),
                  unique_count: t("common.uniqueValues"),
                  min: t("common.min"),
                  max: t("common.max"),
                }}
                rows={columns as unknown as Record<string, unknown>[]}
                numericColumns={["missing_count", "unique_count", "min", "max"]}
                renderCell={(column, value) => {
                  if (column === "variable_label") {
                    // Only a labelled column has something to say here. An
                    // empty cell is the honest answer for every other file.
                    if (value === null || value === undefined || value === "") {
                      return (
                        <span className="text-caption text-ink-muted">
                          {t("label.none")}
                        </span>
                      );
                    }
                    return (
                      <span className="text-caption text-ink-secondary">
                        {String(value)}
                      </span>
                    );
                  }
                  if (column === "data_type") {
                    return (
                      <Badge tone={value === "numeric" ? "primary" : "neutral"}>
                        {String(value ?? "—")}
                      </Badge>
                    );
                  }
                  if (column === "missing_count" && Number(value) > 0) {
                    return (
                      <Badge tone="warning">
                        {formatNumber(Number(value), { maximumFractionDigits: 0 })}
                      </Badge>
                    );
                  }
                  if (column === "name") {
                    return <span className="font-mono text-caption">{String(value)}</span>;
                  }
                  return formatCell(value);
                }}
              />
            </CollapsibleCard>

            <CollapsibleCard
              title={t("studio.title")}
              description={t("studio.description")}
              icon="sliders"
              open={open.studio}
              onToggle={() => toggle("studio")}
            >
              <div className="px-4 pb-4 pt-4 sm:px-5">
                <p className="text-body text-ink-secondary">{t("studio.body")}</p>
                <div className="mt-3">
                  <Link href={`/datasets/${datasetId}/studio`}>
                    <Button icon="sliders">{t("studio.open")}</Button>
                  </Link>
                </div>
              </div>
            </CollapsibleCard>
          </section>
        </>
      )}
    </AppShell>
  );
}
