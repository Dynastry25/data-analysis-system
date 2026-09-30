"use client";

import { ReactNode, useMemo, useState } from "react";

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
}: DataTableProps) {
  const [sort, setSort] = useState<SortState | null>(null);
  const numeric = useMemo(() => new Set(numericColumns), [numericColumns]);
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
    if (renderCell) return renderCell(column, value, row);
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
                    className={`border-b border-surface-border px-3 py-0 text-overline uppercase tracking-wide ${
                      isNumeric ? "text-right" : "text-left"
                    } ${active ? "text-primary-700" : "text-ink-muted"}`}
                  >
                    {isSortable ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(column)}
                        className={`flex w-full items-center gap-1 whitespace-nowrap py-2.5 transition-colors duration-150 ease-standard hover:text-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary-600 ${
                          isNumeric ? "justify-end" : "justify-start"
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
                      <span className="block py-2.5">
                        {columnLabels[column] ?? column}
                      </span>
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
                className="odd:bg-surface-panel even:bg-surface-sunken transition-colors duration-150 ease-standard hover:bg-primary-50/60"
              >
                {columns.map((column, columnIndex) => {
                  const value = row[column];
                  const isNumeric =
                    numeric.has(column) ||
                    (typeof value === "number" && !Number.isNaN(value));
                  const isMissing = isMissingValue(value);
                  return (
                    <td
                      key={column}
                      scope={columnIndex === 0 ? "row" : undefined}
                      className={`border-b border-surface-border px-3 py-2 ${
                        isNumeric
                          ? "numeric-table text-right"
                          : "text-left text-ink"
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
