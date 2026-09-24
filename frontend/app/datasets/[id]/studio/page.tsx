"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
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

const SELECT_CLASSES =
  "h-10 w-full rounded border border-neutral-200 bg-white px-3 text-body outline-none focus:border-primary-500";

type FieldDef = {
  key: string;
  kind: "column" | "columns" | "text" | "number" | "select";
  label: string;
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
    { key: "subset", kind: "columns", label: "Subset (hiari)" },
    { key: "keep", kind: "select", label: "Weka (keep)", options: KEEP_OPTIONS },
  ],
  drop_missing: [
    { key: "columns", kind: "columns", label: "Columns (hiari)" },
    { key: "threshold", kind: "number", label: "Threshold (hiari)" },
  ],
  fill_missing: [
    { key: "strategy", kind: "select", label: "Strategy", options: STRATEGY_OPTIONS },
    { key: "columns", kind: "columns", label: "Columns (hiari: zote)" },
    { key: "value", label: "Value (kwa 'constant')", kind: "text" },
  ],
  rename_columns: [
    { key: "old", kind: "column", label: "Column ya zamani" },
    { key: "new", kind: "text", label: "Jina jipya" },
  ],
  cast_types: [
    { key: "column", kind: "column", label: "Column" },
    { key: "target_type", kind: "select", label: "Aina mpya", options: TYPE_OPTIONS },
  ],
  select_columns: [{ key: "columns", kind: "columns", label: "Columns za kuweka" }],
  filter: [
    { key: "column", kind: "column", label: "Column" },
    { key: "operator", kind: "select", label: "Operator", options: OPERATOR_OPTIONS },
    { key: "value", kind: "text", label: "Value (mf. 18 au Dar)" },
  ],
  sort: [
    { key: "by", kind: "column", label: "Panga kwa (by)" },
    { key: "ascending", kind: "select", label: "Mpangilio", options: ASC_OPTIONS },
  ],
  calculate_column: [
    { key: "name", kind: "text", label: "Jina la column mpya" },
    { key: "expression", kind: "text", label: "Expression (mf. income / 12)" },
  ],
  group_by: [
    { key: "by", kind: "column", label: "Group by" },
    { key: "column", kind: "column", label: "Column ya ku-aggregate" },
    { key: "aggregation", kind: "select", label: "Aggregation", options: AGG_OPTIONS },
  ],
};

export default function StudioPage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params?.id);
  const { showToast } = useToast();

  const [columns, setColumns] = useState<ColumnProfile[]>([]);
  const [catalog, setCatalog] = useState<OperationCatalogEntry[]>([]);
  const [history, setHistory] = useState<OperationsHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedOp, setSelectedOp] = useState("");
  const [fieldValues, setFieldValues] = useState<Record<string, string | string[]>>({});
  const [label, setLabel] = useState("");
  const [applying, setApplying] = useState(false);
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
    if (field.kind === "column") {
      return (
        <select
          className={`${SELECT_CLASSES} mt-1`}
          value={String(value || "")}
          onChange={(event) =>
            setFieldValues((previous) => ({ ...previous, [field.key]: event.target.value }))
          }
        >
          <option value="">— chagua column —</option>
          {columnNames.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      );
    }
    if (field.kind === "columns") {
      const selected = Array.isArray(value) ? value : [];
      return (
        <div className="mt-1 flex max-h-32 flex-wrap gap-2 overflow-y-auto rounded border border-neutral-200 p-2">
          {columnNames.map((name) => (
            <label key={name} className="flex items-center gap-1 text-caption">
              <input
                type="checkbox"
                checked={selected.includes(name)}
                onChange={() => toggleColumn(field.key, name)}
              />
              {name}
            </label>
          ))}
        </div>
      );
    }
    if (field.kind === "select") {
      return (
        <select
          className={`${SELECT_CLASSES} mt-1`}
          value={String(value || "")}
          onChange={(event) =>
            setFieldValues((previous) => ({ ...previous, [field.key]: event.target.value }))
          }
        >
          <option value="">— chagua —</option>
          {(field.options ?? []).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      );
    }
    return (
      <input
        type={field.kind === "number" ? "number" : "text"}
        className={`${SELECT_CLASSES} mt-1`}
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

  return (
    <AppShell
      title="Data studio"
      description="Tumia operations (clean/transform) — kila operation hutengeneza version mpya isiyobadilishwa."
      actions={
        <Link href={`/datasets/${datasetId}`}>
          <Button variant="secondary">Rudi kwenye dataset</Button>
        </Link>
      }
    >
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
          <Card
            title="Tumia operation mpya"
            description="Chagua operation, jaza parameters, kisha tumia. Version mpya itatengenezwa."
          >
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="block text-body text-neutral-600" htmlFor="op-type">
                  Operation
                </label>
                <select
                  id="op-type"
                  className={`${SELECT_CLASSES} mt-1`}
                  value={selectedOp}
                  onChange={(event) => {
                    setSelectedOp(event.target.value);
                    setFieldValues({});
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
                    <span className="text-caption text-neutral-600">
                      {currentOperation.parameters.join(", ")}
                    </span>
                  </div>
                )}
              </div>
              <div>
                <label className="block text-body text-neutral-600" htmlFor="op-label">
                  Label ya version (hiari)
                </label>
                <input
                  id="op-label"
                  className={`${SELECT_CLASSES} mt-1`}
                  value={label}
                  onChange={(event) => setLabel(event.target.value)}
                  placeholder="mf. Baada ya kusafisha missing values"
                />
              </div>
            </div>

            {fields.length > 0 && (
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                {fields.map((field) => (
                  <div key={field.key}>
                    <label className="block text-body text-neutral-600">
                      {field.label}
                    </label>
                    {renderField(field)}
                  </div>
                ))}
              </div>
            )}

            <Button
              className="mt-4"
              size="large"
              loading={applying}
              onClick={applyOperation}
            >
              Tumia operation (tengeneza version mpya)
            </Button>
          </Card>

          <Card
            title="Version lineage"
            description={`v${history?.current_version ?? 1} ndiyo version ya sasa. Kila version haiharibiki — uchambuzi wowote unaweza kurudiwa.`}
          >
            {versions.length === 0 ? (
              <EmptyState title="Hakuna versions bado" />
            ) : (
              <ol className="space-y-2">
                {versions.map((version) => (
                  <li
                    key={version.version}
                    className="flex flex-wrap items-center justify-between gap-2 rounded border border-neutral-200 px-3 py-2"
                  >
                    <span className="flex flex-wrap items-center gap-3">
                      <Badge tone={version.is_current ? "success" : "neutral"}>
                        v{version.version}
                        {version.is_current ? " · sasa" : ""}
                      </Badge>
                      {version.operation ? (
                        <Badge tone="primary">{version.operation.type}</Badge>
                      ) : (
                        <Badge tone="neutral">original (upload)</Badge>
                      )}
                      {version.label && (
                        <span className="text-body">{version.label}</span>
                      )}
                      <span className="text-caption text-neutral-600">
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
          >
            {operations.length === 0 ? (
              <EmptyState
                title="Hakuna operation iliyofanywa bado"
                description="Tumia form ya juu kutengeneza version v2."
              />
            ) : (
              <ol className="space-y-2">
                {operations.map((operation) => (
                  <li
                    key={operation.sequence}
                    className="rounded border border-neutral-200 px-3 py-2"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="neutral">#{operation.sequence}</Badge>
                      <Badge
                        tone={operation.group === "clean" ? "primary" : "neutral"}
                      >
                        {operation.type}
                      </Badge>
                      <span className="text-caption text-neutral-600">
                        v{operation.source_version} → v{operation.version}
                        {operation.created_at
                          ? ` · ${new Date(operation.created_at).toLocaleString()}`
                          : ""}
                      </span>
                    </div>
                    {Object.keys(operation.configuration).length > 0 && (
                      <pre className="mt-1 whitespace-pre-wrap text-caption text-neutral-600">
                        {JSON.stringify(operation.configuration)}
                      </pre>
                    )}
                    {operation.warnings.length > 0 && (
                      <p className="mt-1 text-caption text-warning">
                        {operation.warnings.join(" ")}
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




