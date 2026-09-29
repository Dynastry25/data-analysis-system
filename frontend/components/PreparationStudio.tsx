"use client";

import { useMemo } from "react";

import { Badge } from "./Badge";
import { Card } from "./Card";
import { Icon, IconName } from "./Icon";
import type { OperationCatalogEntry, VersionLineageEntry } from "@/lib/api";

/**
 * The five operation families the prototype lists, mapped onto the operations
 * the engine actually implements.
 *
 * A family with no implementation is listed as unavailable rather than shown as
 * a button that does nothing. "Join datasets" in particular would need a second
 * dataset, a key and a join type, and none of that exists yet.
 */
const OPERATION_ICONS: Record<string, IconName> = {
  filter: "filter",
  drop_missing: "filter",
  fill_missing: "sparkles",
  cast_types: "sliders",
  calculate_column: "calculator",
  group_by: "layers",
  sort: "chevrons-up-down",
  drop_duplicates: "layers",
  rename_columns: "file-text",
  select_columns: "table",
};

const FAMILY_ORDER: { key: string; label: string; hint: string; ops: string[] }[] = [
  { key: "filter", label: "Chuja rows", hint: "Weke au ondoa rows", ops: ["filter", "drop_missing", "drop_duplicates"] },
  { key: "impute", label: "Jaza missing", hint: "Weka thamani inayofaa", ops: ["fill_missing"] },
  { key: "normalize", label: "Badilisha aina", hint: "Namba, tarehe, boolean", ops: ["cast_types"] },
  { key: "encode", label: "Tengeneza column", hint: "Hesabu, changanya, changanya", ops: ["calculate_column", "group_by"] },
  { key: "join", label: "Unganisha datasets", hint: "Haijaandikwa bado", ops: [] },
];

function stepTone(step: number, currentStep: number) {
  if (step < currentStep) return "done" as const;
  if (step === currentStep) return "current" as const;
  return "pending" as const;
}

/** Import always counts as done: the file is the dataset. */
function pipelineSteps(history: VersionLineageEntry[] | null, currentVersion: number) {
  const applied = (history ?? [])
    .filter((entry) => entry.operation !== null)
    .sort((a, b) => a.version - b.version);

  return [
    { key: "import", label: "Import", tone: "done" as const },
    ...applied.map((entry) => ({
      key: `v${entry.version}`,
      label: entry.operation?.type ?? `v${entry.version}`,
      tone: stepTone(entry.version, currentVersion),
    })),
  ];
}

interface PreparationPipelineProps {
  history: VersionLineageEntry[] | null;
  currentVersion: number;
  className?: string;
}

/**
 * The strip along the bottom of the studio: what has been applied, in order.
 *
 * It is read from the version lineage rather than from a fixed list, so a step
 * only appears when a real operation created a real version.
 */
export function PreparationPipeline({
  history,
  currentVersion,
  className = "",
}: PreparationPipelineProps) {
  const steps = useMemo(
    () => pipelineSteps(history, currentVersion),
    [history, currentVersion]
  );

  return (
    <Card
      title="Mfuatano wa ubadilishaji"
      description="Kila hatua hapa chini ilitengeneza version halisi. Version haziharibiki — unaweza kurudiwa."
      icon="layers"
      className={className}
    >
      {steps.length <= 1 ? (
        <p className="text-body text-ink-secondary">
          Bado hakuna operation imetengenezwa. Tumia operation iliyo kushoto ili juu
          kutengeneza version v2 — hatua zote zitaonekana hapa.
        </p>
      ) : (
        <ol className="flex min-w-max items-center gap-1.5 overflow-x-auto pb-1">
          {steps.map((step, index) => (
            <li key={step.key} className="flex items-center gap-1.5">
              <span
                className={`flex items-center gap-1.5 rounded-pill border px-2.5 py-1 text-caption font-medium ${
                  step.tone === "done"
                    ? "border-success/30 bg-success-bg text-success-700"
                    : step.tone === "current"
                      ? "border-primary-600 bg-primary-50 text-primary-800"
                      : "border-surface-border bg-surface-sunken text-ink-muted"
                }`}
              >
                {step.tone === "done" ? (
                  <Icon name="check" size={12} />
                ) : step.tone === "current" ? (
                  <Icon name="sliders" size={12} />
                ) : (
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-surface-border-strong" />
                )}
                {step.label}
              </span>
              {index < steps.length - 1 && (
                <Icon
                  name="chevron-right"
                  size={13}
                  className="shrink-0 text-surface-border-strong"
                />
              )}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

interface OperationRailProps {
  catalog: OperationCatalogEntry[];
  selected: string;
  onSelect: (type: string) => void;
}

/**
 * The operation rail down the left of the studio.
 *
 * The five families are the mental model; the buttons inside are the operations
 * the engine really has. A family with nothing behind it says so instead of
 * offering a dead click.
 */
export function OperationRail({ catalog, selected, onSelect }: OperationRailProps) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-panel shadow-card">
      <p className="border-b border-surface-border px-3.5 py-2.5 text-overline uppercase tracking-wide text-ink-muted">
        Operations
      </p>
      <ul className="divide-y divide-surface-border">
        {FAMILY_ORDER.map((family) => {
          const entries = family.ops
            .map((type) => catalog.find((entry) => entry.type === type))
            .filter((entry): entry is OperationCatalogEntry => entry !== undefined);

          return (
            <li key={family.key} className="px-3 py-2.5">
              <p className="text-caption font-medium text-ink">{family.label}</p>
              {entries.length === 0 ? (
                <p className="mt-0.5 flex items-center gap-1.5 text-caption text-ink-muted">
                  <Icon name="info" size={12} className="shrink-0" />
                  {family.hint}
                </p>
              ) : (
                <ul className="mt-1.5 space-y-1">
                  {entries.map((entry) => {
                    const active = selected === entry.type;
                    return (
                      <li key={entry.type}>
                        <button
                          type="button"
                          onClick={() => onSelect(entry.type)}
                          aria-pressed={active}
                          className={`flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-caption transition-colors duration-150 ease-standard ${
                            active
                              ? "bg-primary-50 font-medium text-primary-800"
                              : "text-ink-secondary hover:bg-surface-sunken"
                          }`}
                        >
                          <Icon
                            name={OPERATION_ICONS[entry.type] ?? "sliders"}
                            size={13}
                            className="shrink-0"
                          />
                          <span className="truncate">{entry.label}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

interface VersionHistoryProps {
  versions: VersionLineageEntry[];
  onDownload?: (version: number) => void;
  downloading?: number | null;
}

/** Version history, newest first, with the current version marked. */
export function VersionHistory({
  versions,
  onDownload,
  downloading = null,
}: VersionHistoryProps) {
  const ordered = useMemo(
    () => [...versions].sort((a, b) => b.version - a.version),
    [versions]
  );

  return (
    <Card title="Historia ya versions" icon="history" padding="none">
      {ordered.length === 0 ? (
        <p className="px-4 py-8 text-center text-body text-ink-muted">
          Hakuna versions bado.
        </p>
      ) : (
        <ol className="divide-y divide-surface-border">
          {ordered.map((entry) => (
            <li
              key={entry.version}
              className={`flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 ${
                entry.is_current ? "bg-success-bg" : ""
              }`}
            >
              <span className="w-10 shrink-0 font-mono text-caption font-medium text-ink">
                v{entry.version}
              </span>
              <span className="min-w-0 flex-1 truncate text-caption text-ink-secondary">
                {entry.label ??
                  (entry.operation ? entry.operation.type : "original (upload)")}
              </span>
              <span className="shrink-0 text-caption text-ink-muted">
                {entry.created_at
                  ? new Date(entry.created_at).toLocaleString("en-KE", {
                      day: "2-digit",
                      month: "short",
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  : "—"}
              </span>
              {entry.is_current && (
                <Badge tone="success" size="sm">
                  sasa
                </Badge>
              )}
              {onDownload && (
                <button
                  type="button"
                  onClick={() => onDownload(entry.version)}
                  disabled={downloading === entry.version}
                  className="shrink-0 rounded-md border border-surface-border p-1 text-ink-muted transition-colors hover:bg-surface-sunken hover:text-ink disabled:opacity-40"
                  title={`Pakua v${entry.version}`}
                >
                  <Icon name="download" size={13} />
                </button>
              )}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

interface LivePreviewProps {
  rows: Record<string, unknown>[];
  rowCount: number;
  version: number;
  className?: string;
}

/**
 * The rows as they stand in the current version.
 *
 * This is the current version only, not a projection of an operation the user
 * has typed but not applied. A preview that showed unapplied changes would be
 * guessing at the result, and the engine is the thing that knows it.
 */
export function LivePreview({
  rows,
  rowCount,
  version,
  className = "",
}: LivePreviewProps) {
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];

  return (
    <Card
      title="Live preview"
      description={`Rows za kwanza za version v${version} kama zilivyo sasa.`}
      icon="table"
      className={className}
      padding="none"
      footer={`${rowCount.toLocaleString("en-KE")} rows kwenye version hii`}
    >
      {rows.length === 0 || columns.length === 0 ? (
        <p className="px-4 py-8 text-center text-body text-ink-muted">
          Hakuna rows za kuonyesha.
        </p>
      ) : (
        <div className="max-h-72 overflow-auto">
          <table className="min-w-full border-collapse text-caption">
            <thead className="sticky top-0 bg-surface-sunken">
              <tr>
                {columns.map((column) => (
                  <th
                    key={column}
                    scope="col"
                    className="border-b border-surface-border px-3 py-2 text-left text-overline font-normal uppercase tracking-wide text-ink-muted"
                  >
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr
                  key={index}
                  className="odd:bg-surface-panel even:bg-surface-sunken"
                >
                  {columns.map((column) => {
                    const value = row[column];
                    const missing =
                      value === null ||
                      value === undefined ||
                      value === "" ||
                      (typeof value === "number" && Number.isNaN(value));
                    return (
                      <td
                        key={column}
                        className={`border-b border-surface-border px-3 py-1.5 ${
                          missing ? "text-ink-muted" : "text-ink"
                        } ${typeof value === "number" ? "numeric-table text-right" : ""}`}
                      >
                        {missing ? "•" : String(value)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export default PreparationPipeline;
