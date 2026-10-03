"use client";

import { ReactNode, useCallback, useMemo, useState } from "react";

import { Icon } from "./Icon";

/** Formats a number for a data cell: no scientific notation, no noise, no lost precision. */
export function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (value === 0) return "0";
  const magnitude = Math.abs(value);
  if (magnitude >= 1e9) {
    return new Intl.NumberFormat("en-US", {
      notation: "compact",
      maximumFractionDigits: 2,
    }).format(value);
  }
  if (magnitude < 1e-4) {
    return new Intl.NumberFormat("en-US", {
      maximumSignificantDigits: 4,
    }).format(value);
  }
  const decimals = Number.isInteger(value)
    ? 0
    : Math.min(10, Math.max(2, (magnitude < 1 ? 4 : 2) - Math.floor(Math.log10(magnitude))));
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: decimals,
  }).format(value);
}

/** One shared definition of "no value here", used for the badge and for de-emphasis. */
export function isMissingValue(value: unknown): boolean {
  return (
    value === null ||
    value === undefined ||
    value === "" ||
    (typeof value === "number" && Number.isNaN(value))
  );
}

export function formatCell(value: unknown): string {
  if (isMissingValue(value)) return "—";
  if (typeof value === "number") return formatNumber(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

type SortDirection = "asc" | "desc";

interface SortState {
  column: string;
  direction: SortDirection;
}

interface DataTableProps {
  columns: string[];
  rows: Record<string, unknown>[];
  caption?: string;
  numericColumns?: string[];
  renderCell?: (column: string, value: unknown, row: Record<string, unknown>) => ReactNode;
  maxHeight?: string;
  emptyMessage?: string;
  stickyHeader?: boolean;
  /** Columns that should not be sortable, e.g. rendered as rich content. */
  unsortableColumns?: string[];
  /** Display names for structural columns; dataset column names stay untouched. */
  columnLabels?: Record<string, string>;
  /**
   * How a missing cell reads. "badge" (default) spells it out for the tables
   * where the count matters; "dot" is the compact prototype glyph, for a data
   * preview where "Hakuna" repeated 400 times costs more than it explains.
   */
  missingDisplay?: "badge" | "dot";
  /**
   * A second header row carrying the data type of each column, the way a
   * spreadsheet shows it. It is a real `<th>` row with a scope, so a screen
   * reader gets the type attached to the column rather than to a value.
   */
  columnTypes?: Record<string, string>;
  /** Highlight columns whose cells are mostly empty, in the type row. */
  typeRowTone?: (column: string) => "default" | "warning";
  /**
   * Code -> word per column, as the file's author wrote them:
   * `{ gender: { "1": "kiume", "2": "dame" } }`.
   *
   * Only the columns present here get a switch. A column with no lookup has
   * nothing to switch to, so it is left exactly as it was.
   */
  valueLabels?: Record<string, Record<string, string>>;
  /**
   * A short line under the column name, for the variable's own name in the
   * source file ("Sex of respondent"). This is what ties a set of codes to the
   * question they answer, so it belongs next to the codes rather than in a
   * table the reader has to go and find.
   */
  columnNotes?: Record<string, string>;
  /** Tooltip for the per-column switch; `{ action }` is the other action's name. */
  labelToggleTitles?: { showLabel: string; showCode: string };
}

const collator = new Intl.Collator("en", { numeric: true, sensitivity: "base" });

/**
 * A missing value must not be signalled by colour alone (design system §11),
 * so the badge carries an icon and text a screen reader can announce.
 */
export function MissingBadge() {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border border-warning/30 bg-warning-bg px-1.5 py-0.5 text-caption font-medium text-warning-700"
      title="Thamani haipo"
    >
      <Icon name="alert-circle" size={12} className="shrink-0" />
      <span>Hakuna</span>
    </span>
  );
}

/**
 * The compact form: a dot, which is what the prototype uses in a data preview.
 *
 * The dot alone would fail §11 on colour and shape, so the word is kept for
 * assistive technology only and marked aria-hidden on the glyph. The
 * information is still announced; it is just no longer shouting "Hakuna" in
 * every cell of a 5,000-row preview.
 */
export function MissingDot() {
  return (
    <span className="inline-flex items-center text-ink-muted" title="Thamani haipo">
      <span aria-hidden="true" className="text-body leading-none">
        &bull;
      </span>
      <span className="sr-only">Thamani haipo</span>
    </span>
  );
}

function compareValues(a: unknown, b: unknown): number {
  const aMissing = a === null || a === undefined || a === "";
  const bMissing = b === null || b === undefined || b === "";
  if (aMissing && bMissing) return 0;
  if (aMissing) return 1;
  if (bMissing) return -1;
  if (typeof a === "number" && typeof b === "number") {
    if (Number.isNaN(a) && Number.isNaN(b)) return 0;
    if (Number.isNaN(a)) return 1;
    if (Number.isNaN(b)) return -1;
    return a - b;
  }
  if (typeof a === "boolean" && typeof b === "boolean") {
    return Number(a) - Number(b);
  }
  return collator.compare(String(a), String(b));
}

export function DataTable({
  columns,
  rows,
  caption,
  numericColumns = [],
  renderCell,
  maxHeight,
  emptyMessage = "Hakuna data ya kuonyesha.",
  stickyHeader = true,
  unsortableColumns = [],
  columnLabels = {},
  missingDisplay = "badge",
  columnTypes,
  typeRowTone,
  valueLabels,
  columnNotes,
  labelToggleTitles,
}: DataTableProps) {
  const [sort, setSort] = useState<SortState | null>(null);
  const numeric = useMemo(() => new Set(numericColumns), [numericColumns]);

  /*
   * Which columns are currently showing words instead of codes. Default is
   * "show the label", because a reader who opened a labelled survey file
   * wants to read what the codes mean; the codes are one click away. Storing
   * only the columns that were flipped keeps the default live, so a dataset
   * loaded after a toggle does not inherit a stale choice.
   */
  const [codeMode, setCodeMode] = useState<Record<string, boolean>>({});

  const labelsByColumn = useMemo(() => valueLabels ?? {}, [valueLabels]);

  /** True when this column has a lookup to show and is not currently in code mode. */
  const showsLabels = useCallback(
    (column: string) => {
      const lookup = labelsByColumn[column];
      return !!lookup && Object.keys(lookup).length > 0 && !codeMode[column];
    },
    [labelsByColumn, codeMode],
  );

  const toggleColumnMode = useCallback((column: string) => {
    setCodeMode((current) => ({ ...current, [column]: !current[column] }));
  }, []);

  /** Whether this column has a code lookup worth switching between. */
  const hasLabels = useCallback(
    (column: string) => Object.keys(labelsByColumn[column] ?? {}).length > 0,
    [labelsByColumn],
  );
  const locked = useMemo(() => new Set(unsortableColumns), [unsortableColumns]);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const factor = sort.direction === "asc" ? 1 : -1;
    return [...rows].sort(
      (a, b) => factor * compareValues(a[sort.column], b[sort.column]),
    );
  }, [rows, sort]);

  const ariaSortFor = (column: string) => {
    if (!sort || sort.column !== column) return "none" as const;
    return sort.direction === "asc" ? ("ascending" as const) : ("descending" as const);
  };

  const toggleSort = (column: string) => {
    setSort((current) => {
      if (current?.column !== column) return { column, direction: "asc" };
      if (current.direction === "asc") return { column, direction: "desc" };
      return null;
    });
  };

  const renderValue = (
    column: string,
    value: unknown,
    row: Record<string, unknown>,
  ): ReactNode => {
    if (renderCell) {
      const labelled = renderLabelled(column, value);
      return labelled ?? renderCell(column, value, row);
    }
    const labelled = renderLabelled(column, value);
    if (labelled) return labelled;
    if (isMissingValue(value)) {
      return missingDisplay === "dot" ? <MissingDot /> : <MissingBadge />;
    }
    if (typeof value === "boolean") {
      return (
        <span
          className={`inline-flex items-center rounded-full border px-1.5 py-0.5 text-caption font-medium ${
            value
              ? "border-success/30 bg-success-bg text-success-700"
              : "border-surface-border bg-surface-sunken text-ink-muted"
          }`}
        >
          {value ? "true" : "false"}
        </span>
      );
    }
    return formatCell(value);
  };

  /**
   * The cell as it reads once a column's labels are applied. Kept separate from
   * renderValue so the preview page can keep its own first-column styling while
   * still honouring the switch: that page passes a renderCell, which would
   * otherwise bypass the label lookup entirely.
   */
  const renderLabelled = (column: string, value: unknown): ReactNode => {
    if (!showsLabels(column) || isMissingValue(value)) return null;
    const code = formatCell(value);
    const word = labelsByColumn[column][code] ?? code;
    if (word === code) return null;
    return (
      <span title={`${word} (${code})`}>
        {word}
        <span className="ml-1 font-mono text-caption text-ink-muted">{code}</span>
      </span>
    );
  };

  if (rows.length === 0) {
    return (
      <div className="overflow-hidden rounded-md border border-surface-border bg-surface-panel">
        <p className="px-4 py-10 text-center text-body text-ink-muted">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <>
      {/* Mobile: one card per row, so a wide table never needs a long sideways scroll (design system §7). */}
      <div className="space-y-2 sm:hidden">
        {sorted.map((row, rowIndex) => (
          <div
            key={rowIndex}
            className="rounded-md border border-surface-border bg-surface-panel p-3"
          >
            <p className="mb-2 break-words text-body font-medium text-ink">
              {renderValue(columns[0], row[columns[0]], row)}
            </p>
            <dl className="space-y-1.5">
              {columns.slice(1).map((column) => (
                <div
                  key={column}
                  className="flex items-start justify-between gap-3"
                >
                  <dt className="shrink-0 text-caption text-ink-muted">
                    {columnLabels[column] ?? column}
                  </dt>
                  <dd
                    className={`min-w-0 break-words text-body ${
                      numeric.has(column) ? "numeric-table text-right" : ""
                    }`}
                  >
                    {renderValue(column, row[column], row)}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>

      <div
        className="hidden overflow-auto rounded-md border border-surface-border bg-surface-panel sm:block"
        style={{ maxHeight }}
      >
        <table className="min-w-full border-collapse text-body">
          {caption && <caption className="sr-only">{caption}</caption>}
          <thead
            className={`bg-surface-sunken ${
              stickyHeader ? "sticky top-0 z-10" : ""
            }`}
          >
            <tr>
              {columns.map((column, columnIndex) => {
                const isNumeric =
                  numeric.has(column) ||
                  typeof rows[0]?.[column] === "number";
                const isSortable = !locked.has(column);
                const active = sort?.column === column;
                return (
                  <th
                    key={column}
                    scope="col"
                    aria-sort={isSortable ? ariaSortFor(column) : undefined}
                    className={`border-b border-surface-border bg-surface-sunken px-3 py-2.5 text-overline uppercase tracking-[0.07em] ${
                      isNumeric && !showsLabels(column) ? "text-right" : "text-left"
                    } ${active ? "text-primary-700" : "text-ink-muted"}`}
                  >
                    <div
                      className={`flex items-center gap-1 py-2.5 ${
                        isNumeric && !showsLabels(column) ? "justify-end" : "justify-start"
                      }`}
                    >
                      {isSortable ? (
                        <button
                          type="button"
                          onClick={() => toggleSort(column)}
                          className={`flex min-w-0 items-center gap-1 whitespace-nowrap transition-colors duration-150 ease-standard hover:text-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary-600 ${
                            isNumeric && !showsLabels(column)
                              ? "justify-end"
                              : "justify-start"
                          }`}
                        >
                          <span className="truncate">
                            {columnLabels[column] ?? column}
                          </span>
                          <Icon
                            name={
                              !active
                                ? "chevrons-up-down"
                                : sort.direction === "asc"
                                  ? "chevron-up"
                                  : "chevron-down"
                            }
                            size={13}
                            className={active ? "shrink-0" : "shrink-0 opacity-40"}
                          />
                        </button>
                      ) : (
                        <span className="min-w-0 truncate">
                          {columnLabels[column] ?? column}
                        </span>
                      )}
                      {hasLabels(column) && (
                        <button
                          type="button"
                          onClick={() => toggleColumnMode(column)}
                          title={
                            showsLabels(column)
                              ? labelToggleTitles?.showCode
                              : labelToggleTitles?.showLabel
                          }
                          aria-pressed={showsLabels(column)}
                          className="shrink-0 rounded-pill border border-surface-border bg-surface-panel px-1.5 py-0.5 text-[10px] font-medium normal-case tracking-normal text-ink-muted transition-colors duration-150 ease-standard hover:border-primary-300 hover:text-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
                        >
                          {showsLabels(column) ? "123" : "Aa"}
                        </button>
                      )}
                    </div>
                    {columnNotes?.[column] && (
                      /*
                       * The variable's own name in the source file, lowercase and
                       * unstyled, so it reads as an annotation on the column
                       * rather than as a second column name competing with it.
                       */
                      <p className="-mt-1.5 truncate pb-2 text-[11px] font-normal normal-case tracking-normal text-ink-muted/80">
                        {columnNotes[column]}
                      </p>
                    )}
                  </th>
                );
              })}
            </tr>
            {columnTypes && (
              <tr className="bg-surface-sunken">
                {columns.map((column) => {
                  const type = columnTypes[column];
                  const warning = typeRowTone?.(column) === "warning";
                  return (
                    <th
                      key={`type-${column}`}
                      scope="col"
                      className={`border-b border-surface-border px-3 py-1 text-overline font-normal normal-case tracking-normal ${
                        numeric.has(column) || typeof rows[0]?.[column] === "number"
                          ? "text-right"
                          : "text-left"
                      } ${warning ? "text-warning-700" : "text-ink-muted"}`}
                    >
                      {type ? (
                        <span
                          className={`inline-flex items-center gap-1 rounded-pill px-1.5 py-0.5 ${
                            warning
                              ? "bg-warning-bg text-warning-700"
                              : "bg-surface-panel text-ink-muted"
                          }`}
                        >
                          {type}
                        </span>
                      ) : (
                        <span>&nbsp;</span>
                      )}
                    </th>
                  );
                })}
              </tr>
            )}
          </thead>
          <tbody>
            {sorted.map((row, rowIndex) => (
              <tr
                key={rowIndex}
                className="odd:bg-surface-panel/60 even:bg-white hover:bg-primary-50/50"
              >
                {columns.map((column, columnIndex) => {
                  const value = row[column];
                  const isNumeric =
                    numeric.has(column) ||
                    (typeof value === "number" && !Number.isNaN(value));
                  const isMissing = isMissingValue(value);
                  /*
                   * A cell showing a word is text even when the code it came
                   * from was a number, so it is aligned as text. Keeping the
                   * right alignment would put "kiume" against the edge of the
                   * column, which reads as a number that happens to be spelled
                   * out rather than as a category.
                   */
                  const alignRight =
                    isNumeric && (!showsLabels(column) || isMissing);
                  return (
                    <td
                      key={column}
                      scope={columnIndex === 0 ? "row" : undefined}
                      className={`border-b border-surface-border px-3 py-2 ${
                        alignRight ? "numeric-table text-right" : "text-left text-ink"
                      } ${columnIndex === 0 ? "font-medium text-ink" : ""} ${
                        isMissing ? "text-ink-muted" : ""
                      }`}
                    >
                      {renderValue(column, value, row)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export default DataTable;
