"use client";

import { ReactNode } from "react";

export function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === "") return "â€”";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "â€”";
    return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(4);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
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
}: DataTableProps) {
  const numeric = new Set(numericColumns);
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
            {columns.map((column) => (
              <th
                key={column}
                scope="col"
                className="whitespace-nowrap border-b border-surface-border px-3 py-2.5 text-left text-overline uppercase tracking-wide text-ink-muted"
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr
              key={rowIndex}
              className="odd:bg-surface-panel even:bg-surface-sunken hover:bg-primary-50/60"
            >
              {columns.map((column) => {
                const value = row[column];
                const isNumeric =
                  numeric.has(column) ||
                  (typeof value === "number" && !Number.isNaN(value));
                return (
                  <td
                    key={column}
                    className={`whitespace-nowrap border-b border-surface-border px-3 py-2 text-ink ${
                      isNumeric ? "numeric-table text-right" : ""
                    }`}
                  >
                    {renderCell ? renderCell(column, value, row) : formatCell(value)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && (
        <p className="px-4 py-8 text-center text-body text-ink-muted">{emptyMessage}</p>
      )}
    </div>
  );
}

export default DataTable;


