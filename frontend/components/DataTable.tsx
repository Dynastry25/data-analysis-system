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

export function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
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
}

const collator = new Intl.Collator("en", { numeric: true, sensitivity: "base" });

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

  if (rows.length === 0) {
    return (
      <div className="overflow-hidden rounded-lg border border-surface-border bg-surface-panel">
        <p className="px-4 py-10 text-center text-body text-ink-muted">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div
      className="overflow-auto rounded-lg border border-surface-border bg-surface-panel"
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
                const isMissing =
                  value === null || value === undefined || value === "";
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
                    {renderCell ? (
                      renderCell(column, value, row)
                    ) : typeof value === "boolean" && !renderCell ? (
                      <span
                        className={`inline-flex items-center rounded-pill border px-1.5 py-0.5 text-caption font-medium ${
                          value
                            ? "border-success/30 bg-success-bg text-success-700"
                            : "border-surface-border bg-surface-sunken text-ink-muted"
                        }`}
                      >
                        {value ? "true" : "false"}
                      </span>
                    ) : (
                      formatCell(value)
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default DataTable;
