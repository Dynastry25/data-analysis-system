"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { CheckboxGroup, SelectInput, TextInput } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import {
  api,
  apiErrorMessage,
  ColumnProfile,
  OperationCatalogEntry,
  OperationsHistoryResponse,
  statflowApi,
} from "@/lib/api";

type FieldDef = {
  key: string;
  kind: "column" | "columns" | "text" | "number" | "select";
  label: string;
  hint?: string;
  required?: boolean;
  options?: { value: string; label: string }[];
};

const KEEP_OPTIONS = [
  { value: "first", label: "first (ya kwanza)" },
  { value: "last", label: "last (ya mwisho)" },
];
const STRATEGY_OPTIONS = ["mean", "median", "mode", "zero", "constant", "drop"].map(
  (value) => ({ value, label: value })
);
const TYPE_OPTIONS = ["numeric", "integer", "text", "date", "boolean"].map((value) => ({
  value,
  label: value,
}));
const OPERATOR_OPTIONS = ["eq", "ne", "gt", "gte", "lt", "lte", "contains"].map(
  (value) => ({ value, label: value })
);

/** Profiling min/max arrive as `any`, so render them rather than trusting the type. */
function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number" || typeof value === "string") return String(value);
  return String(value);
}

function isBlankValue(value: string | string[] | undefined): boolean {
  if (value === undefined || value === "") return true;
  return Array.isArray(value) && value.length === 0;
}
const ASC_OPTIONS = [
  { value: "true", label: "ascending (panda)" },
  { value: "false", label: "descending (shuka)" },
];
const AGG_OPTIONS = ["count", "sum", "mean", "median", "min", "max"].map((value) => ({
  value,
  label: value,
}));

const OPERATION_FIELDS: Record<string, FieldDef[]> = {
  drop_duplicates: [
    { key: "subset", kind: "columns", label: "Subset", hint: "Pengoja kama zisizo" },
    { key: "keep", kind: "select", label: "Weka (keep)", options: KEEP_OPTIONS },
  ],
  drop_missing: [
    { key: "columns", kind: "columns", label: "Columns", hint: "Acha wote kama hazitoshi" },
    { key: "threshold", kind: "number", label: "Threshold", hint: "0.1 = 10% au zaidi" },
  ],
  fill_missing: [
    { key: "strategy", kind: "select", label: "Strategy", required: true, options: STRATEGY_OPTIONS },
    { key: "columns", kind: "columns", label: "Columns", hint: "Acha zote kama hazitoshi" },
    { key: "value", label: "Value (kwa 'constant')", kind: "text" },
  ],
  rename_columns: [
    { key: "old", kind: "column", label: "Column ya zamani", required: true },
    { key: "new", kind: "text", label: "Jina jipya", required: true },
  ],
  cast_types: [
    { key: "column", kind: "column", label: "Column", required: true },
    { key: "target_type", kind: "select", label: "Aina mpya", required: true, options: TYPE_OPTIONS },
  ],
  select_columns: [
    { key: "columns", kind: "columns", label: "Columns za kuweka", required: true },
  ],
  filter: [
    { key: "column", kind: "column", label: "Column", required: true },
    { key: "operator", kind: "select", label: "Operator", required: true, options: OPERATOR_OPTIONS },
    { key: "value", kind: "text", label: "Value", required: true, hint: "mf. 18 au Dar" },
  ],
  sort: [
    { key: "by", kind: "column", label: "Panga kwa (by)", required: true },
    { key: "ascending", kind: "select", label: "Mpangilio", options: ASC_OPTIONS },
  ],
  calculate_column: [
    { key: "name", kind: "text", label: "Jina la column mpya", required: true },
    { key: "expression", kind: "text", label: "Expression", required: true, hint: "mf. income / 12" },
  ],
  group_by: [
    { key: "by", kind: "column", label: "Group by", required: true },
    { key: "column", kind: "column", label: "Column ya ku-aggregate", required: true },
    { key: "aggregation", kind: "select", label: "Aggregation", required: true, options: AGG_OPTIONS },
  ],
};

/**
 * The studio hosts three of the journey's stages.
 *
 * Profile, Clean and Transform are separate pieces of work with separate
 * results, so they get separate deep links and the section you asked for opens
 * on load. They are not separate screens, and the page says so, because
 * pretending otherwise would mean three URLs that show the same thing.
 */
const STUDIO_SECTIONS = [
  { key: "profile", label: "Profile", hint: "Muundo na tabia za kila column" },
  { key: "clean", label: "Safisha", hint: "Ondoa au kaza missing values na safisha rows" },
  { key: "transform", label: "Badilisha", hint: "Tengeneza dataset version mpya" },
] as const;

type StudioSection = (typeof STUDIO_SECTIONS)[number]["key"];

function isStudioSection(value: string | null): value is StudioSection {
  return STUDIO_SECTIONS.some((section) => section.key === value);
}

export default function StudioPage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params?.id);
  const searchParams = useSearchParams();
  const { showToast } = useToast();

  const requested = searchParams.get("stage");
  const [section, setSection] = useState<StudioSection>(
    isStudioSection(requested) ? requested : "profile"
  );

  // A deep link such as ?stage=clean must win over the remembered tab, or the
  // journey would send the user to a section the page then hides.
  useEffect(() => {
    if (isStudioSection(requested)) setSection(requested);
  }, [requested]);

  const [columns, setColumns] = useState<ColumnProfile[]>([]);
  const [catalog, setCatalog] = useState<OperationCatalogEntry[]>([]);
  const [history, setHistory] = useState<OperationsHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedOp, setSelectedOp] = useState("");
  const [fieldValues, setFieldValues] = useState<Record<string, string | string[]>>({});
  const [label, setLabel] = useState("");
  const [applying, setApplying] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [downloading, setDownloading] = useState<number | null>(null);

  const columnNames = columns.map((column) => column.name);

  const load = useCallback(async () => {
    if (!Number.isFinite(datasetId)) return;
    setLoading(true);
    setError(null);
    try {
      const [detail, operationsCatalog, operationsHistory] = await Promise.all([
        api.datasets.get(datasetId),
        statflowApi.operationsCatalog(),
        statflowApi.operationsHistory(datasetId),
      ]);
      setColumns(detail.columns);
      setCatalog(operationsCatalog);
      setHistory(operationsHistory);
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
    if (!selectedOp && catalog.length > 0) {
      setSelectedOp(catalog[0].type);
    }
  }, [catalog, selectedOp]);

  const currentOperation = catalog.find((entry) => entry.type === selectedOp) ?? null;
  const fields = OPERATION_FIELDS[selectedOp] ?? [];

  function buildConfiguration(): Record<string, unknown> {
    const config: Record<string, unknown> = {};
    if (selectedOp === "rename_columns") {
      const oldName = String(fieldValues.old || "");
      const newName = String(fieldValues.new || "").trim();
      if (oldName && newName) config.mapping = { [oldName]: newName };
      return config;
    }
    if (selectedOp === "group_by") {
      if (fieldValues.by) config.by = fieldValues.by;
      if (fieldValues.column) config.column = fieldValues.column;
      if (fieldValues.aggregation) config.aggregation = fieldValues.aggregation;
      return config;
    }
    for (const field of fields) {
      const raw = fieldValues[field.key];
      if (raw === undefined || raw === "") continue;
      if (field.kind === "columns") {
        if (Array.isArray(raw) && raw.length > 0) config[field.key] = raw;
      } else if (field.kind === "number") {
        config[field.key] = Number(raw);
      } else if (field.key === "ascending") {
        config.ascending = raw === "true";
      } else {
        config[field.key] = raw;
      }
    }
    return config;
  }

  async function applyOperation() {
    if (!currentOperation) return;
    setAttempted(true);
    const missing = fields.filter(
      (field) => field.required && isBlankValue(fieldValues[field.key])
    );
    if (missing.length > 0) {
      showToast(
        `Jaza sehemu zote zinazohitajika: ${missing.map((field) => field.label).join(", ")}.`,
        "warning"
      );
      return;
    }
    setApplying(true);
    try {
      const payload = {
        operation_type: currentOperation.type,
        configuration: buildConfiguration(),
        label: label.trim() || undefined,
      };
      const response =
        currentOperation.group === "clean"
          ? await statflowApi.applyClean(datasetId, payload)
          : await statflowApi.applyTransform(datasetId, payload);
      showToast(
        `Version v${response.version} imetengenezwa (${response.row_count} rows × ${response.column_count} columns)`,
        "success"
      );
      setLabel("");
      setFieldValues({});
      setAttempted(false);
      setHistory(await statflowApi.operationsHistory(datasetId));
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setApplying(false);
    }
  }

  async function downloadVersion(version: number) {
    setDownloading(version);
    try {
      const blob = await statflowApi.downloadVersion(datasetId, version);
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `dataset_${datasetId}_v${version}.csv`;
      anchor.click();
      window.URL.revokeObjectURL(url);
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setDownloading(null);
    }
  }

  function toggleColumn(key: string, name: string) {
    setFieldValues((previous) => {
      const current = Array.isArray(previous[key]) ? (previous[key] as string[]) : [];
      const next = current.includes(name)
        ? current.filter((item) => item !== name)
        : [...current, name];
      return { ...previous, [key]: next };
    });
  }

  function renderField(field: FieldDef) {
    const value = fieldValues[field.key];
    const error =
      attempted && field.required && isBlankValue(value)
        ? "Sehemu hii inahitajika."
        : undefined;

    if (field.kind === "columns") {
      const selected = Array.isArray(value) ? value : [];
      return (
        <CheckboxGroup
          label={field.label}
          hint={field.hint}
          error={error}
          options={columnNames}
          selected={selected}
          onToggle={(name) => toggleColumn(field.key, name)}
          maxHeightClassName="max-h-36"
        />
      );
    }
    if (field.kind === "column") {
      return (
        <SelectInput
          label={field.label}
          required={field.required}
          error={error}
          placeholder="— chagua column —"
          value={String(value || "")}
          options={columnNames.map((name) => ({ value: name, label: name }))}
          onChange={(event) =>
            setFieldValues((previous) => ({ ...previous, [field.key]: event.target.value }))
          }
        />
      );
    }
    if (field.kind === "select") {
      return (
        <SelectInput
          label={field.label}
          required={field.required}
          error={error}
          placeholder="— chagua —"
          value={String(value || "")}
          options={field.options ?? []}
          onChange={(event) =>
            setFieldValues((previous) => ({ ...previous, [field.key]: event.target.value }))
          }
        />
      );
    }
    return (
      <TextInput
        label={field.label}
        hint={field.hint}
        required={field.required}
        error={error}
        type={field.kind === "number" ? "number" : "text"}
        value={String(value ?? "")}
        onChange={(event) =>
          setFieldValues((previous) => ({ ...previous, [field.key]: event.target.value }))
        }
      />
    );
  }

  const versions = [...(history?.versions ?? [])].sort(
    (a, b) => b.version - a.version
  );
  const operations = history?.operations ?? [];

  const sectionHint = STUDIO_SECTIONS.find((entry) => entry.key === section)?.hint ?? "";

  return (
    <AppShell
      title="Data Preparation Studio"
      description="Profile, safisha na badilisha zinaishi kwenye ukurasa mmoja — kila hatua ina kazi na matokeo yake mwenyewe."
      actions={
        <Link href={`/datasets/${datasetId}`}>
          <Button variant="secondary">Rudi kwenye dataset</Button>
        </Link>
      }
    >
      <div className="mb-6">
        <p className="text-overline uppercase tracking-wide text-ink-muted">
          Operations
        </p>
        <div className="mt-2 flex flex-wrap gap-1" role="tablist" aria-label="Hatua za studio">
          {STUDIO_SECTIONS.map((entry) => (
            <Link
              key={entry.key}
              href={`/datasets/${datasetId}/studio?stage=${entry.key}`}
              role="tab"
              aria-selected={section === entry.key}
              className={`rounded-md px-3.5 py-2 text-body transition-colors duration-150 ease-standard ${
                section === entry.key
                  ? "bg-primary-50 font-medium text-primary-800"
                  : "text-ink-secondary hover:bg-surface-sunken"
              }`}
            >
              {entry.label}
            </Link>
          ))}
        </div>
        <p className="mt-2 text-caption text-ink-muted">{sectionHint}</p>
      </div>

      {section === "profile" && (
        <Card
          title="Profile ya kila column"
          icon="table"
          description="Hapa ndani hakuna kitu cha kubadilisha: kuangalia tu. Mabadiliko yafanyaywe chini katika Safisha au Badilisha."
        >
          {columns.length === 0 ? (
            <EmptyState
              title="Hakuna columns"
              description="Dataset hili hana columns za kuonyesha."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-body">
                <thead>
                  <tr className="border-b border-surface-border text-overline uppercase tracking-wide text-ink-muted">
                    <th className="py-2 pr-4 font-medium">Column</th>
                    <th className="py-2 pr-4 font-medium">Aina</th>
                    <th className="py-2 pr-4 font-medium">Hazina thamani</th>
                    <th className="py-2 pr-4 font-medium">Tofauti</th>
                    <th className="py-2 font-medium">Min → Max</th>
                  </tr>
                </thead>
                <tbody>
                  {columns.map((column) => (
                    <tr key={column.name} className="border-b border-surface-border last:border-0">
                      <td className="py-2.5 pr-4 font-medium text-ink">{column.name}</td>
                      <td className="py-2.5 pr-4 text-ink-secondary">{column.data_type ?? "—"}</td>
                      <td className="py-2.5 pr-4 text-ink-secondary">
                        {column.missing_count}
                      </td>
                      <td className="py-2.5 pr-4 text-ink-secondary">
                        {column.unique_count ?? "—"}
                      </td>
                      <td className="py-2.5 font-mono text-caption text-ink-secondary">
                        {formatCell(column.min)} → {formatCell(column.max)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {loading ? (
        <Card>
          <TableSkeleton rows={6} columns={4} />
        </Card>
      ) : error ? (
        <Card>
          <EmptyState title="Imeshindikana kupakia studio" description={error} />
        </Card>
      ) : (
        <>
          {(section === "clean" || section === "transform") && (
          <div className="grid gap-4 lg:grid-cols-3">
            <Card
              title={
                section === "clean"
                  ? "Safisha data"
                  : "Badilisha data"
              }
              icon="sliders"
              description="Chagua operation, jaza parameters, kisha tumia. Version mpya itatengenezwa na asili hubaki kubadilika."
              className="lg:col-span-2"
            >
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label htmlFor="op-type" className="mb-1.5 block text-body font-medium text-ink">
                  Operation
                </label>
                <select
                  id="op-type"
                  className="control cursor-pointer"
                  value={selectedOp}
                  onChange={(event) => {
                    setSelectedOp(event.target.value);
                    setFieldValues({});
                    setAttempted(false);
                  }}
                >
                  <optgroup label="Clean">
                    {catalog
                      .filter((entry) => entry.group === "clean")
                      .map((entry) => (
                        <option key={entry.type} value={entry.type}>
                          {entry.label}
                        </option>
                      ))}
                  </optgroup>
                  <optgroup label="Transform">
                    {catalog
                      .filter((entry) => entry.group === "transform")
                      .map((entry) => (
                        <option key={entry.type} value={entry.type}>
                          {entry.label}
                        </option>
                      ))}
                  </optgroup>
                </select>
                {currentOperation && (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <Badge
                      tone={currentOperation.group === "clean" ? "primary" : "neutral"}
                    >
                      {currentOperation.group}
                    </Badge>
                    <span className="text-caption text-ink-muted">
                      {currentOperation.parameters.join(", ")}
                    </span>
                  </div>
                )}
              </div>
              <TextInput
                label="Label ya version"
                optionalLabel="hiari"
                value={label}
                onChange={(event) => setLabel(event.target.value)}
                placeholder="mf. Baada ya kusafisha missing values"
              />
            </div>

            {fields.length > 0 && (
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                {fields.map((field) => (
                  <div key={field.key}>{renderField(field)}</div>
                ))}
              </div>
            )}

            <Button
              className="mt-4"
              size="large"
              loading={applying}
              onClick={applyOperation}
              icon="check"
            >
              Tumia operation (tengeneza version mpya)
            </Button>
            </Card>

            <div className="flex flex-col gap-4">
              <Card
                title="Version history"
                icon="history"
                description="Kila version ina operesheni, muda na mtumiaji."
              >
                {versions.length === 0 ? (
                  <p className="text-body text-ink-muted">
                    Hakuna versions bado — tumia operation kutengeneza v2.
                  </p>
                ) : (
                  <ol className="space-y-2">
                    {versions.slice(0, 3).map((version) => (
                      <li key={version.version} className="flex items-center justify-between gap-2 text-body">
                        <span className="font-mono font-medium text-ink">
                          v{version.version}
                        </span>
                        <span className="truncate text-caption text-ink-muted">
                          {version.label || version.operation?.type || "original"}
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
              </Card>
              <Card
                title="Transformation pipeline"
                icon="layers"
                description="Import → Filter → Impute → Normalize → Encode"
              >
                <p className="text-caption text-ink-muted">
                  Pipeline inaonyesha hatua zilizotekelezwa kwenye version ya
                  sasa.
                </p>
              </Card>
            </div>
          </div>
          )}

          <Card
            title="Version lineage"
            description={`v${history?.current_version ?? 1} ndiyo version ya sasa. Kila version haiharibiki — uchambuzi wowote unaweza kurudiwa.`}
            icon="layers"
          >
            {versions.length === 0 ? (
              <EmptyState
                title="Hakuna versions bado"
                description="Tumia operation ya juu kutengeneza version v2 — version ya kwanza haina harakati."
                icon="layers"
              />
            ) : (
              <ol className="space-y-2">
                {versions.map((version) => (
                  <li
                    key={version.version}
                    className={`flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2.5 ${
                      version.is_current
                        ? "border-success/30 bg-success-bg"
                        : "border-surface-border"
                    }`}
                  >
                    <span className="flex flex-wrap items-center gap-3">
                      <Badge tone={version.is_current ? "success" : "neutral"} icon={version.is_current ? "check" : undefined}>
                        v{version.version}
                        {version.is_current ? " · sasa" : ""}
                      </Badge>
                      {version.operation ? (
                        <Badge tone="primary">{version.operation.type}</Badge>
                      ) : (
                        <Badge tone="neutral">original (upload)</Badge>
                      )}
                      {version.label && (
                        <span className="text-body text-ink">{version.label}</span>
                      )}
                      <span className="text-caption text-ink-muted">
                        {version.row_count} rows × {version.column_count} columns
                        {version.parent_version
                          ? ` · kutoka v${version.parent_version}`
                          : ""}
                        {version.created_at
                          ? ` · ${new Date(version.created_at).toLocaleString()}`
                          : ""}
                      </span>
                    </span>
                    <Button
                      variant="secondary"
                      size="small"
                      icon="download"
                      loading={downloading === version.version}
                      onClick={() => downloadVersion(version.version)}
                    >
                      Pakua
                    </Button>
                  </li>
                ))}
              </ol>
            )}
          </Card>

          <Card
            title="Historia ya operations (audit trail)"
            description="Hatua zote za kusafisha/kubadilisha data, mpangilio ulivyotokea."
            icon="history"
          >
            {operations.length === 0 ? (
              <EmptyState
                title="Hakuna operation iliyofanywa bado"
                description="Tumia form ya juu kutengeneza version v2."
                icon="history"
              />
            ) : (
              <ol className="space-y-2">
                {operations.map((operation) => (
                  <li
                    key={operation.sequence}
                    className="rounded-md border border-surface-border px-3 py-2.5"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="neutral">#{operation.sequence}</Badge>
                      <Badge tone={operation.group === "clean" ? "primary" : "neutral"}>
                        {operation.type}
                      </Badge>
                      <span className="text-caption text-ink-muted">
                        <span className="font-mono font-medium text-ink">
                          v{operation.source_version} → v{operation.version}
                        </span>
                        {operation.created_at
                          ? ` · ${new Date(operation.created_at).toLocaleString()}`
                          : ""}
                      </span>
                    </div>
                    {Object.keys(operation.configuration).length > 0 && (
                      <pre className="mt-1.5 overflow-x-auto whitespace-pre-wrap rounded-md bg-surface-sunken p-2 font-mono text-caption text-ink-secondary">
                        {JSON.stringify(operation.configuration, null, 2)}
                      </pre>
                    )}
                    {operation.warnings.length > 0 && (
                      <p className="mt-1.5 flex items-start gap-1.5 rounded-md bg-warning-bg px-2 py-1.5 text-caption text-warning-700">
                        <Icon name="alert-triangle" size={13} className="mt-0.5 shrink-0" />
                        <span>{operation.warnings.join(" ")}</span>
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </>
      )}
    </AppShell>
  );
}




