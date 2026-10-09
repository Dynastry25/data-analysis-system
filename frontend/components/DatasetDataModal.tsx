"use client";

import { useEffect, useState, useCallback } from "react";
import { Icon } from "@/components/Icon";
import { Button } from "@/components/Button";
import { api, DatasetDataResponse, DatasetDataUpdateRequest } from "@/lib/api";
import { useToast } from "@/components/Toast";

interface DatasetDataModalProps {
  isOpen: boolean;
  onClose: () => void;
  datasetId: number;
  datasetName: string;
  mode?: "view" | "edit";
}

export function DatasetDataModal({
  isOpen,
  onClose,
  datasetId,
  datasetName,
  mode = "view",
}: DatasetDataModalProps) {
  const { showToast } = useToast();
  const [data, setData] = useState<DatasetDataResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [editingRow, setEditingRow] = useState<number | null>(null);
  const [editValues, setEditValues] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.datasets.getData(datasetId, { page, page_size: pageSize });
      setData(response);
    } catch (err) {
      showToast("Failed to load dataset data", "danger");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [datasetId, page, pageSize, showToast]);

  useEffect(() => {
    if (isOpen) {
      setPage(1);
      fetchData();
    }
  }, [isOpen, fetchData]);

  const handleEditStart = (rowIndex: number, row: Record<string, unknown>) => {
    if (mode !== "edit") return;
    setEditingRow(rowIndex);
    setEditValues({ ...row });
  };

  const handleEditSave = async (rowIndex: number) => {
    setSaving(true);
    try {
      const payload: DatasetDataUpdateRequest = {
        row_index: (page - 1) * pageSize + rowIndex,
        changes: editValues,
      };
      await api.datasets.updateRow(datasetId, payload);
      showToast("Row updated successfully", "success");
      setEditingRow(null);
      fetchData();
    } catch (err) {
      showToast("Failed to update row", "danger");
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const handleEditCancel = () => {
    setEditingRow(null);
    setEditValues({});
  };

  const handleCellChange = (column: string, value: unknown) => {
    setEditValues((prev) => ({ ...prev, [column]: value }));
  };

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= (data?.total_pages ?? 1)) {
      setPage(newPage);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="fixed inset-0 bg-black/50"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="relative w-full max-w-6xl max-h-[90vh] bg-white rounded-xl shadow-xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-surface-border">
          <div>
            <h2 className="text-lg font-semibold text-ink">
              {mode === "edit" ? "Edit Dataset" : "View Dataset"} - {datasetName}
            </h2>
            <p className="text-sm text-ink-muted">
              {data
                ? `Showing ${((page - 1) * pageSize) + 1}–${Math.min(page * pageSize, data.row_count)} of ${data.row_count.toLocaleString()} rows (Page ${page} of ${data.total_pages})`
                : "Loading..."}
            </p>
          </div>
          <Button variant="ghost" size="small" onClick={onClose}>
            <Icon name="close" size={20} />
          </Button>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary-600 border-t-transparent" />
            </div>
          ) : data && data.rows.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse whitespace-nowrap text-sm">
                <thead>
                  <tr>
                    <th className="sticky top-0 border-b-2 border-surface-border bg-surface-sunken px-3 py-2 text-left text-overline font-semibold uppercase tracking-[0.06em] text-ink-muted">
                      #
                    </th>
                    {data.columns.map((col) => (
                      <th
                        key={col}
                        className="sticky top-0 border-b-2 border-surface-border bg-surface-sunken px-3 py-2 text-left text-overline font-semibold uppercase tracking-[0.06em] text-ink-muted"
                      >
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row, rowIndex) => {
                    const isEditing = editingRow === rowIndex;
                    return (
                      <tr
                        key={rowIndex}
                        className={`transition-colors ${
                          isEditing ? "bg-primary-50" : "hover:bg-primary-50/40"
                        }`}
                      >
                        <td className="border-b border-surface-border px-3 py-2 text-ink-muted font-mono">
                          {(page - 1) * pageSize + rowIndex + 1}
                        </td>
                        {data.columns.map((col) => (
                          <td key={col} className="border-b border-surface-border px-3 py-2">
                            {isEditing ? (
                              <input
                                type="text"
                                value={String(editValues[col] ?? "")}
                                onChange={(e) => handleCellChange(col, e.target.value)}
                                className="w-full px-2 py-1 border border-primary-300 rounded text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                                autoFocus
                              />
                            ) : (
                              <span className="text-ink-secondary">
                                {row[col] === null || row[col] === undefined
                                  ? <span className="text-ink-muted italic">(empty)</span>
                                  : String(row[col])}
                              </span>
                            )}
                          </td>
                        ))}
                        {mode === "edit" && (
                          <td className="border-b border-surface-border px-3 py-2">
                            {isEditing ? (
                              <div className="flex gap-1">
                                <Button
                                  size="small"
                                  variant="primary"
                                  onClick={() => handleEditSave(rowIndex)}
                                  loading={saving}
                                >
                                  Save
                                </Button>
                                <Button
                                  size="small"
                                  variant="ghost"
                                  onClick={handleEditCancel}
                                >
                                  Cancel
                                </Button>
                              </div>
                            ) : (
                              <Button
                                size="small"
                                variant="ghost"
                                onClick={() => handleEditStart(rowIndex, row)}
                              >
                                <Icon name="edit" size={14} />
                              </Button>
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center text-ink-muted py-12">
              No data available
            </div>
          )}
        </div>

        {/* Pagination */}
        {data && data.total_pages > 1 && (
          <div className="px-4 py-3 border-t border-surface-border flex items-center justify-between">
            <span className="text-sm text-ink-muted">
              Page {page} of {data.total_pages}
            </span>
            <div className="flex items-center gap-2">
              <Button
                size="small"
                variant="secondary"
                onClick={() => handlePageChange(page - 1)}
                disabled={page <= 1}
              >
                <Icon name="chevron-left" size={16} />
                Previous
              </Button>
              <Button
                size="small"
                variant="secondary"
                onClick={() => handlePageChange(page + 1)}
                disabled={page >= data.total_pages}
              >
                Next
                <Icon name="chevron-right" size={16} />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default DatasetDataModal;