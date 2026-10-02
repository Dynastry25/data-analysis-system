"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { CheckboxGroup, SelectInput, TextInput } from "@/components/Field";
import {
  FilterBuilder,
  buildFilterConfig,
  emptyCondition,
  type FilterCondition,
  type FilterLogic,
} from "@/components/FilterBuilder";
import { Icon } from "@/components/Icon";
import {
  LivePreview,
  OperationRail,
  PreparationPipeline,
  VersionHistory,
} from "@/components/PreparationStudio";
import { PanelCard, PanelDrawer } from "@/components/PanelDrawer";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import {
  api,
  apiErrorMessage,
  ApplyOperationResponse,
  ColumnProfile,
  DatasetSummary,
  OperationCatalogEntry,
  OperationsHistoryResponse,
  statflowApi,
} from "@/lib/api";

type FieldDef = {
  key: string;
  kind: "column" | "columns" | "text" | "number" | "select" | "dataset";
  label: string;
  hint?: string;
  required?: boolean;
  options?: { value: string; label: string }[];
};

/** The secondary panels a summary card can open. */
type OpenPanel = "versions" | "preview" | "pipeline" | "audit" | null;

/** What one cleaning/transform step left behind, for the result panel. */
type LastResult = {
  version: number;
  operation: string;
  rowsBefore: number;
  rowsAfter: number;
  columnsBefore: number;
  columnsAfter: number;
  warnings: string[];
  summary: Record<string, unknown>;
};

/**
 * How a merge is expected to line up. The guide's warning is the reason the
 * choice is surfaced rather than defaulted and forgotten: an inner join that
 * silently drops rows looks like a successful filter.
 */
const JOIN_OPTIONS = [
  { value: "left", label: "left — kila row ya dataset hii (recommended)" },
  { value: "inner", label: "inner — tu rows zinazopatikana kwenye zote mbili" },
  { value: "right", label: "right — kila row ya dataset ya pili" },
  { value: "outer", label: "outer — zote mbili" },
];

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
  drop_columns: [
    {
      key: "columns",
      kind: "columns",
      label: "Ondoa column",
      hint: "Chagua column unazotaka kuondoa",
      required: true,
    },
  ],
  merge: [
    {
      key: "other_dataset_id",
      kind: "dataset",
      label: "Dataset ya pili",
      hint: "Dataset unayotaka kuunganisha na hii",
      required: true,
    },
    { key: "left_on", kind: "column", label: "Key (dataset hii)", required: true },
    {
      key: "right_on",
      kind: "column",
      label: "Key (dataset ya pili)",
      hint: "Weka sawa na key ya kushoto ikiwa jina ni sawa",
    },
    {
      key: "how",
      kind: "select",
      label: "Aina ya kuunganisha",
      hint: "left haipunguzi rows; inner hupunguza",
      options: JOIN_OPTIONS,
    },
  ],
  append: [
    {
      key: "other_dataset_id",
      kind: "dataset",
      label: "Dataset ya pili",
      hint: "Dataset utakaongeza chini ya hii",
      required: true,
    },
  ],
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
  // The filter builds its own conditions through FilterBuilder rather than the
  // generic field list, so it is deliberately absent here.
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
  const [previewRows, setPreviewRows] = useState<Record<string, unknown>[]>([]);
  const [rowCount, setRowCount] = useState(0);
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
  // The datasets this user can merge with. Loaded once alongside everything
  // else, because the merge form cannot be drawn without them.
  const [otherDatasets, setOtherDatasets] = useState<DatasetSummary[]>([]);
  /**
   * The result of the last operation: which version it produced, what it
   * changed, and what the dataset looks like now. This is the "kile kilichobaki
   * baada ya kusafisha" panel -- without it the studio keeps rendering the
   * profile and preview of the data as it was *before* the operation, because
   * only the history was being refetched.
   */
  const [lastResult, setLastResult] = useState<LastResult | null>(null);
  /**
   * Which secondary panel is open, if any. The studio keeps the operation in
   * view and moves the rest behind cards, so this is the only way the preview,
   * the versions, the pipeline or the audit trail are on screen at once.
   */
  const [openPanel, setOpenPanel] = useState<OpenPanel>(null);


  const columnNames = columns.map((column) => column.name);

  const load = useCallback(async () => {
    if (!Number.isFinite(datasetId)) return;
    setLoading(true);
    setError(null);
    try {
      const [detail, operationsCatalog, operationsHistory, datasetList] =
        await Promise.all([
          api.datasets.get(datasetId),
          statflowApi.operationsCatalog(),
          statflowApi.operationsHistory(datasetId),
          api.datasets.list().catch(() => [] as DatasetSummary[]),
        ]);
      setColumns(detail.columns);
      setPreviewRows(detail.preview_rows);
      setRowCount(detail.dataset.row_count);
      setCatalog(operationsCatalog);
      setHistory(operationsHistory);
      // A dataset cannot be merged with itself, so it is filtered out here
      // rather than offering a choice the server will refuse.
      setOtherDatasets(
        (Array.isArray(datasetList) ? datasetList : []).filter(
          (entry: DatasetSummary) => entry.id !== datasetId
        )
      );
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

  /*
   * The filter is the one operation whose parameters are a list rather than a
   * set of named fields, so its conditions live in their own state instead of
   * being flattened into `fieldValues`. `and` is the default because a filter
   * that quietly widens when you add a second condition is the dangerous
   * direction: `or` has to be chosen on purpose.
   */
  const [filterConditions, setFilterConditions] = useState<FilterCondition[]>([]);
  const [filterLogic, setFilterLogic] = useState<FilterLogic>("and");
  const [filterError, setFilterError] = useState<string | null>(null);

  // Re-seed whenever the operation or the dataset changes, so a condition can
  // never reference a column that the new version no longer has.
  useEffect(() => {
    setFilterError(null);
    if (selectedOp === "filter") {
      setFilterConditions(columns.length > 0 ? [emptyCondition(columns)] : []);
    } else {
      setFilterConditions([]);
    }
  }, [selectedOp, columns]);

  function buildConfiguration(): Record<string, unknown> {
    const config: Record<string, unknown> = {};
    if (selectedOp === "filter") {
      // buildFilterConfig has already validated by this point; applyOperation
      // returns early on an error, so an unvalidated path is not reachable.
      const { config: filterConfig } = buildFilterConfig(filterConditions);
      if (filterConfig) {
        return { ...filterConfig, logic: filterLogic };
      }
      return config;
    }
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
    if (selectedOp === "merge") {
      // The endpoint takes the keys as lists, so a single key chosen in the
      // form is wrapped here. Sending a bare string would make pandas treat
      // each character as its own key.
      const left = fieldValues.left_on ? [String(fieldValues.left_on)] : [];
      if (left.length > 0) config.left_on = left;
      // An empty right key means "same name as the left", which is the
      // common case and is left out rather than restated.
      const right = fieldValues.right_on ? [String(fieldValues.right_on)] : [];
      if (right.length > 0) config.right_on = right;
      config.how = String(fieldValues.how || "left");
      return config;
    }
    if (selectedOp === "append") {
      return {};
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

  /**
   * Re-read the dataset after an operation so the studio shows the cleaned
   * data rather than the data as it was.
   *
   * The detail endpoint always serves the *current* version, so one call
   * re-reads the columns, the preview rows and the row count together with the
   * new shape. Refreshing only the history -- which is all this used to do --
   * left the profile and the preview describing the pre-operation data, so the
   * studio appeared to ignore what it had just done.
   *
   * Deliberately does not toggle the page-level `loading` flag: that would
   * blank the whole studio for a change the user just made and is waiting on.
   */
  const refreshAfterOperation = useCallback(
    async (result: ApplyOperationResponse, operation: string, before: { rows: number; columns: number }) => {
      try {
        const [detail, operationsHistory] = await Promise.all([
          api.datasets.get(datasetId),
          statflowApi.operationsHistory(datasetId),
        ]);
        setColumns(detail.columns);
        setPreviewRows(detail.preview_rows);
        setRowCount(detail.dataset.row_count);
        setHistory(operationsHistory);
        setLastResult({
          version: result.version,
          operation,
          rowsBefore: before.rows,
          rowsAfter: detail.dataset.row_count,
          columnsBefore: before.columns,
          columnsAfter: detail.columns.length,
          warnings: result.warnings ?? [],
          summary: result.summary ?? {},
        });
      } catch (caught) {
        // The operation itself succeeded; failing to re-read afterwards should
        // not claim otherwise. Say what happened and leave the history alone.
        showToast(
          `Operation imefanikiwa, lakini hakupatiweka taarifa mpya: ${apiErrorMessage(caught)}`,
          "warning"
        );
      }
    },
    [datasetId, showToast]
  );

  async function applyOperation() {
    if (!currentOperation) return;
    setAttempted(true);

    if (selectedOp === "filter") {
      // Validated here rather than in buildConfiguration so the message can
      // name the row that is wrong instead of reaching the server as a filter
      // that keeps nothing.
      const { config, error } = buildFilterConfig(filterConditions);
      if (error || config === null) {
        setFilterError(error ?? "Add at least one condition.");
        showToast(error ?? "Weka angalia conditions za chujio.", "warning");
        return;
      }
      setFilterError(null);
    }

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
    // Captured before the operation so the result panel can show the change
    // rather than just the end state.
    const before = { rows: rowCount, columns: columns.length };
    try {
      // merge and append read a second dataset, so they go to their own
      // endpoint: the other table is named by id rather than sent in the
      // request body, which keeps it authorisable and out of the payload.
      if (currentOperation.needs_other_dataset) {
        const otherId = Number(fieldValues.other_dataset_id);
        if (!otherId) {
          showToast("Chagua dataset ya pili ya kunganisha.", "warning");
          return;
        }
        const response = await statflowApi.joinDataset(datasetId, {
          operation_type: currentOperation.type as "merge" | "append",
          other_dataset_id: otherId,
          configuration: buildConfiguration(),
          label: label.trim() || undefined,
        });
        await refreshAfterOperation(response, currentOperation.type, before);
        showToast(
          `Version v${response.version} imetengenezwa (${response.row_count} rows · ${response.column_count} columns)`,
          "success"
        );
        setLabel("");
        setFieldValues({});
        setFilterConditions([emptyCondition(columns)]);
        setFilterLogic("and");
        setFilterError(null);
        setAttempted(false);
        return;
      }

      const payload = {
        operation_type: currentOperation.type,
        configuration: buildConfiguration(),
        label: label.trim() || undefined,
      };
      const response =
        currentOperation.group === "clean"
          ? await statflowApi.applyClean(datasetId, payload)
          : await statflowApi.applyTransform(datasetId, payload);
      // Re-read the dataset so the profile, the preview and the row count all
      // describe what is left, not what was there before.
      await refreshAfterOperation(response, currentOperation.type, before);
      showToast(
        `Version v${response.version} imetengenezwa (${response.row_count} rows × ${response.column_count} columns)`,
        "success"
      );
      setLabel("");
      setFieldValues({});
      // The filter is reseeded from the new version's columns, so a condition
      // can never still name a column the operation just removed.
      setFilterConditions([emptyCondition(columns)]);
      setFilterLogic("and");
      setFilterError(null);
      setAttempted(false);
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
    if (field.kind === "dataset") {
      // The picker is fed the user's own datasets with the current one already
      // removed, so the one choice the server would refuse is never offered.
      const options = otherDatasets.map((entry) => ({
        value: String(entry.id),
        label: `${entry.original_filename} (${entry.row_count} rows, ${entry.column_count} columns)`,
      }));
      if (options.length === 0) {
        return (
          <p className="rounded-md border border-surface-border bg-surface-sunken px-3 py-2 text-caption text-ink-muted">
            Hakuna dataset ya pili bado. Ingiza dataset ya pili kwanza ili kuunganisha.
          </p>
        );
      }
      return (
        <SelectInput
          label={field.label}
          required={field.required}
          error={error}
          placeholder="— chagua dataset —"
          value={String(value || "")}
          options={options}
          onChange={(event) =>
            setFieldValues((previous) => ({ ...previous, [field.key]: event.target.value }))
          }
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
      title="Data studio"
      description="Profile, safisha na badilisha zinaishi kwenye ukurasa mmoja — kila hatua ina kazi na matokeo yake mwenyewe."
      actions={
        <Link href={`/datasets/${datasetId}`}>
          <Button variant="secondary">Rudi kwenye dataset</Button>
        </Link>
      }
    >
      <div className="mb-6">
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Hatua za studio">
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
              <div className="grid gap-4 lg:grid-cols-[15rem_1fr]">
                <OperationRail
                  catalog={catalog}
                  selected={selectedOp}
                  onSelect={(type) => {
                    setSelectedOp(type);
                    setFieldValues({});
                    setAttempted(false);
                  }}
                />

                <Card
                  title={currentOperation?.label ?? "Chagua operation"}
                  icon="sliders"
                  description="Jaza parameters, kisha tumia. Version mpya itatengenezwa na asili hubaki kubadilika."
                  actions={
                    currentOperation && (
                      <Badge
                        tone={currentOperation.group === "clean" ? "primary" : "neutral"}
                      >
                        {currentOperation.group === "clean" ? "Safisha" : "Badilisha"}
                      </Badge>
                    )
                  }
                >
                  {currentOperation && (
                    <>
                      <div className="grid gap-4 md:grid-cols-2">
                        <TextInput
                          label="Label ya version"
                          optionalLabel="hiari"
                          value={label}
                          onChange={(event) => setLabel(event.target.value)}
                          placeholder="mf. Baada ya kusafisha missing values"
                        />
                        <div>
                          <p className="text-overline uppercase tracking-wide text-ink-muted">
                            Parameters zinazohitajika
                          </p>
                          <ul className="mt-1.5 space-y-1">
                            {currentOperation.parameters.map((parameter) => (
                              <li
                                key={parameter}
                                className="font-mono text-caption text-ink-secondary"
                              >
                                {parameter}
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>

                      {selectedOp === "filter" ? (
                        <div className="mt-4">
                          <FilterBuilder
                            columns={columns}
                            conditions={filterConditions}
                            logic={filterLogic}
                            onChange={setFilterConditions}
                            onLogicChange={setFilterLogic}
                            attempted={attempted}
                            error={filterError}
                          />
                        </div>
                      ) : fields.length > 0 ? (
                        <div className="mt-4 grid gap-4 md:grid-cols-2">
                          {fields.map((field) => (
                            <div key={field.key}>{renderField(field)}</div>
                          ))}
                        </div>
                      ) : null}

                      <Button
                        className="mt-4"
                        size="large"
                        loading={applying}
                        onClick={applyOperation}
                        icon="check"
                      >
                        Tumia operation (tengeneza version mpya)
                      </Button>
                    </>
                  )}
                </Card>
              </div>
            )}
            {lastResult && (
              <Card
                title="Kimebaki baada ya kusafisha"
                icon="check"
                description={`Version v${lastResult.version} - dataset asili haukubadilika.`}
              >
                <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="rounded-md border border-surface-border bg-surface-sunken px-3 py-2">
                    <dt className="text-caption text-ink-muted">Rows zilizobaki</dt>
                    <dd className="text-ink">
                      <span className="font-medium">{lastResult.rowsAfter}</span>
                      {lastResult.rowsBefore !== lastResult.rowsAfter && (
                        <span className="ml-1.5 text-caption text-ink-muted">
                          (zilikuwa {lastResult.rowsBefore})
                        </span>
                      )}
                    </dd>
                  </div>
                  <div className="rounded-md border border-surface-border bg-surface-sunken px-3 py-2">
                    <dt className="text-caption text-ink-muted">Columns zilizobaki</dt>
                    <dd className="text-ink">
                      <span className="font-medium">{lastResult.columnsAfter}</span>
                      {lastResult.columnsBefore !== lastResult.columnsAfter && (
                        <span className="ml-1.5 text-caption text-ink-muted">
                          (zilikuwa {lastResult.columnsBefore})
                        </span>
                      )}
                    </dd>
                  </div>
                  <div className="rounded-md border border-surface-border bg-surface-sunken px-3 py-2">
                    <dt className="text-caption text-ink-muted">Operation</dt>
                    <dd className="font-mono text-caption text-ink-secondary">
                      {lastResult.operation}
                    </dd>
                  </div>
                  <div className="rounded-md border border-surface-border bg-surface-sunken px-3 py-2">
                    <dt className="text-caption text-ink-muted">Version</dt>
                    <dd className="font-medium text-ink">v{lastResult.version}</dd>
                  </div>
                </dl>

                {lastResult.warnings.length > 0 && (
                  <ul className="mt-3 space-y-1.5">
                    {lastResult.warnings.map((warning) => (
                      <li
                        key={warning}
                        className="flex items-start gap-1.5 text-caption text-ink-secondary"
                      >
                        <Icon name="alert-triangle" size={13} className="mt-0.5 shrink-0" />
                        <span>{warning}</span>
                      </li>
                    ))}
                  </ul>
                )}

                <p className="mt-3 text-caption text-ink-muted">
                  Profile, preview na row count zimewekwa upya kutoka version
                  {` v${lastResult.version}`}. Unaweza kuiendelea na analysis moja kwa moja kwenye
                  dataset hii.
                </p>
              </Card>
            )}

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <PanelCard
                title="Historia ya versions"
                hint="Kila version iliyotengenezwa"
                icon="history"
                onOpen={() => setOpenPanel("versions")}
                value={`v${history?.current_version ?? 1}`}
                meta={`${versions.length} version`}
              />
              <PanelCard
                title="Data preview"
                hint="Rows za version inayo sasa"
                icon="table"
                onOpen={() => setOpenPanel("preview")}
                value={`${rowCount} rows`}
                meta={`${columns.length} columns`}
              />
              <PanelCard
                title="Pipeline"
                hint="Hatua zilizofanywa, mpangilio wake"
                icon="layers"
                onOpen={() => setOpenPanel("pipeline")}
                value={`${operations.length} hatua`}
                meta={operations.length === 0 ? "bado hakuna" : `mwisho: ${operations[operations.length - 1].type}`}
              />
              <PanelCard
                title="Audit trail"
                hint="Mpangilio kamili wa kila operation"
                icon="clipboard"
                onOpen={() => setOpenPanel("audit")}
                value={operations.length === 0 ? "Hakuna" : `${operations.length} rekodi`}
                meta={operations.length === 0 ? "bado hakuna" : "tazama mpangilio kamili"}
              />
            </div>


      {/*
        The secondary panels. Each stays closed until its card is clicked, so
        the operation form keeps the screen and the detail is one click away
        rather than permanently competing with it.
      */}
      <PanelDrawer
        open={openPanel === "versions"}
        onClose={() => setOpenPanel(null)}
        title="Historia ya versions"
        description="Kila version iliyotengenezwa, pamoja na muundo wake."
        icon="history"
      >
        <VersionHistory
          versions={versions}
          onDownload={downloadVersion}
          downloading={downloading}
        />
      </PanelDrawer>

      <PanelDrawer
        open={openPanel === "preview"}
        onClose={() => setOpenPanel(null)}
        title="Data preview"
        description={`Rows za version v${history?.current_version ?? 1} baada ya kusafisha.`}
        icon="table"
      >
        <LivePreview
          rows={previewRows}
          rowCount={rowCount}
          version={history?.current_version ?? 1}
        />
      </PanelDrawer>

      <PanelDrawer
        open={openPanel === "pipeline"}
        onClose={() => setOpenPanel(null)}
        title="Pipeline"
        description="Hatua zilizofanywa na mpangilio wake, toka awali hadi mwisho."
        icon="layers"
      >
        <PreparationPipeline
          history={versions}
          currentVersion={history?.current_version ?? 1}
        />
      </PanelDrawer>

      <PanelDrawer
        open={openPanel === "audit"}
        onClose={() => setOpenPanel(null)}
        title="Audit trail"
        description="Hatua zote za kusafisha/kubadilisha data, mpangilio ulivyotokea."
        icon="clipboard"
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
      </PanelDrawer>
        </>
      )}
    </AppShell>
  );
}




