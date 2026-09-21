"use client";

import { ReactNode } from "react";

export function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") {
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
}

/**
 * Scrollable data table. Numbers use the monospace font so digits line up.
 * On mobile the table scrolls horizontally instead of squashing columns.
 */
export function DataTable({
  columns,
  rows,
  caption,
  numericColumns = [],
  renderCell,
  maxHeight,
}: DataTableProps) {
  const numeric = new Set(numericColumns);
  return (
    <div className="overflow-x-auto rounded border border-neutral-200" style={{ maxHeight }}>
      <table className="min-w-full border-collapse text-body">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="bg-neutral-100">
          <tr>
            {columns.map((column) => (
              <th
                key={column}
                scope="col"
                className="whitespace-nowrap border-b border-neutral-200 px-3 py-2 text-left text-caption font-medium uppercase tracking-wide text-neutral-600"
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="odd:bg-white even:bg-neutral-50">
              {columns.map((column) => {
                const value = row[column];
                const isNumeric =
                  numeric.has(column) ||
                  (typeof value === "number" && !Number.isNaN(value));
                return (
                  <td
                    key={column}
                    className={`whitespace-nowrap border-b border-neutral-200 px-3 py-2 text-neutral-900 ${
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
        <p className="p-4 text-body text-neutral-600">No rows to display.</p>
      )}
    </div>
  );
}

export default DataTable;
