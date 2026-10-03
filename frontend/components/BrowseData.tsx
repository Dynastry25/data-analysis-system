"use client";

import { useCallback, useMemo, useState } from "react";

import { Button } from "@/components/Button";
import { DataTable, formatCell } from "@/components/DataTable";
import { Icon } from "@/components/Icon";
import { useToast } from "@/components/Toast";
import { apiErrorMessage, statflowApi, type ColumnProfile } from "@/lib/api";

/**
 * Browse the data itself, with a view/edit switch.
 *
 * The profile table elsewhere on this page answers "what is this column". This
 * answers "what does this row actually say", which is a different question and
 * the one people come to a dataset to ask.
 *
 * Edit mode is deliberately not a spreadsheet. Edited cells are collected and
 * applied as one `set_values` operation, which creates a new version -- the
 * same rule every other change in this studio follows. Editing in place would
 * leave the version history claiming the file was never touched, which is the
 * kind of quiet lie that makes a result impossible to reproduce later.
 */
export interface BrowseDataProps {
  datasetId: number;
  rows: Record<string, unknown>[];
  columns: ColumnProfile[];
  /** Total rows in the dataset; the table shows the first N of them. */
  totalRows: number;
  version: number;
  onSaved: () => void | Promise<void>;
}

type Mode = "view" | "edit";

interface PendingEdit {
  row: number;
  column: string;
  /** The value the cell held before it was touched, for the changed marker. */
  before: string;
  draft: string;
}

const editKey = (row: number, column: string) => `${row}::${column}`;

/**
 * A typed draft becomes a number when it looks like one and stays a string
 * otherwise, so correcting an income cell keeps it numeric instead of turning
 * the whole column into text.
 */
function coerceDraft(draft: string): string | number {
  const trimmed = draft.trim();
  if (trimmed === "") return "";
  if (/^-?\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed);
  return draft;
}

export function BrowseData({
  datasetId,
  rows,
  columns,
  totalRows,
  version,
  onSaved,
}: BrowseDataProps) {
  const { showToast } = useToast();
  const [mode, setMode] = useState<Mode>("view");
  const [pending, setPending] = useState<Record<string, PendingEdit>>({});
  const [saving, setSaving] = useState(false);

  const columnNames = useMemo(
    () => (rows.length > 0 ? Object.keys(rows[0]) : columns.map((c) => c.name)),
    [rows, columns]
  );

  /*
   * The same code -> word lookups the dataset page uses, so a labelled Stata or
   * SPSS file reads in the researcher's own words here too. DataTable looks the
   * key up on the formatted cell, because values arrive as floats while the
   * backend's label keys are strings ("1", not 1.0).
   */
  const valueLabels = useMemo(() => {
    const map: Record<string, Record<string, string>> = {};
    for (const column of columns) {
      const lookup = column.value_labels;
      if (lookup && Object.keys(lookup).length > 0) map[column.name] = lookup;
    }
    return map;
  }, [columns]);

  const notes = useMemo(() => {
    const map: Record<string, string> = {};
    for (const column of columns) {
      if (column.variable_label) map[column.name] = column.variable_label;
    }
    return map;
  }, [columns]);

  const pendingList = Object.values(pending);
  const changedCount = pendingList.length;

  const setDraft = useCallback(
    (row: number, column: string, draft: string, before: string) => {
      setPending((current) => {
        const next = { ...current };
        // Reverting a cell to what it was drops the edit rather than recording
        // a no-op, so "3 changes" always means three real changes.
        if (draft === before) {
          delete next[editKey(row, column)];
        } else {
          next[editKey(row, column)] = { row, column, before, draft };
        }
        return next;
      });
    },
    []
  );

  function discardAll() {
    setPending({});
    showToast("Mabadiliko yamefutwa", "info");
  }

  async function save() {
    if (changedCount === 0) return;
    setSaving(true);
    try {
      const edits = pendingList.map((edit) => ({
        row: edit.row,
        column: edit.column,
        // An emptied cell clears it; the backend reads "" as "no value".
        value: edit.draft === "" ? "" : coerceDraft(edit.draft),
      }));
      const result = await statflowApi.applyClean(datasetId, {
        operation_type: "set_values",
        configuration: { edits },
        dataset_version: version,
        label: `Hand-edited ${changedCount} cell${changedCount === 1 ? "" : "s"}`,
      });
      setPending({});
      setMode("view");
      showToast(
        `Cell ${changedCount} zimehifadhiwa. Version ${result.version} iko sasa.`,
        "success"
      );
      await onSaved();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setSaving(false);
    }
  }

  const editing = mode === "edit";

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ModeSwitch mode={mode} onChange={setMode} />
        <p className="text-caption text-ink-muted">
          {rows.length < totalRows
            ? `Zinaonyesha rows ${rows.length} za ${totalRows}`
            : `Zinaonyesha rows zote ${totalRows}`}
        </p>
      </div>

      {editing && (
        <p className="flex items-start gap-2 rounded-md border border-primary-200 bg-primary-50 px-3 py-2.5 text-caption text-primary-800">
          <Icon name="info" size={14} className="mt-0.5 shrink-0" />
          <span>
            Badilisha thamani kwa kubofya cell, kisha bonyeza{" "}
            <kbd className="rounded border border-primary-300 bg-surface-panel px-1 font-mono">
              Enter
            </kbd>{" "}
            kuthibitisha au{" "}
            <kbd className="rounded border border-primary-300 bg-surface-panel px-1 font-mono">
              Esc
            </kbd>{" "}
            kughairi. Kila uhifadhi hujenga version mpya; data ya asili hubadiliki.
          </span>
        </p>
      )}

      <DataTable
        columns={columnNames}
        rows={rows}
        valueLabels={valueLabels}
        columnNotes={notes}
        numericColumns={columnNames.filter((name) => {
          // Right-aligned codes read as data; a text input must be left-aligned
          // or the caret sits nowhere near where the value is typed.
          if (editing) return false;
          const kind = columns.find((entry) => entry.name === name)?.data_type;
          return kind === "numeric" || kind === "integer";
        })}
        missingDisplay="dot"
        renderCell={(column, value, row) => {
          const rowIndex = rows.indexOf(row);
          const edit = pending[editKey(rowIndex, column)];
          if (!editing) return null;
          const before = formatCell(value);
          return (
            <input
              type="text"
              aria-label={`${column}, row ${rowIndex + 1}`}
              value={edit ? edit.draft : before}
              onChange={(event) =>
                setDraft(rowIndex, column, event.target.value, before)
              }
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.preventDefault();
                  setDraft(rowIndex, column, before, before);
                }
              }}
              className={`w-full min-w-[5rem] rounded border bg-surface-panel px-1.5 py-1 text-left text-body text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary-600 ${
                edit
                  ? "border-warning bg-warning-bg/50 font-medium"
                  : "border-transparent hover:border-surface-border"
              }`}
            />
          );
        }}
      />

      {editing && changedCount > 0 && (
        <div className="sticky bottom-2 flex flex-wrap items-center justify-between gap-3 rounded-md border border-surface-border bg-surface-panel px-3.5 py-3 shadow-card">
          <p className="text-body text-ink">
            Cell <span className="font-medium">{changedCount}</span>{" "}
            zimebadilishwa lakini bado hazijahifadhiwi.
          </p>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="small"
              onClick={discardAll}
              disabled={saving}
            >
              Ghairi
            </Button>
            <Button size="small" onClick={save} loading={saving}>
              Hifadhi na tengeneza version
            </Button>
          </div>
        </div>
      )}

      {editing && changedCount === 0 && (
        <p className="text-caption text-ink-muted">
          Bado hujabadilisha kitu. Thibitisha cell yoyote ili kuanza.
        </p>
      )}
    </div>
  );
}

/**
 * Two named modes rather than an "edit" checkbox: a tick labelled "edit" is
 * ambiguous about whether it enables editing or performs it.
 */
function ModeSwitch({
  mode,
  onChange,
}: {
  mode: Mode;
  onChange: (next: Mode) => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div
        role="radiogroup"
        aria-label="Hali ya kuona data"
        className="inline-flex rounded-md border border-surface-border bg-surface-sunken p-0.5"
      >
        {(
          [
            { key: "view", label: "Tazama", icon: "eye" },
            { key: "edit", label: "Badilisha", icon: "sliders" },
          ] as const
        ).map((option) => (
          <button
            key={option.key}
            type="button"
            role="radio"
            aria-checked={mode === option.key}
            onClick={() => onChange(option.key)}
            className={`inline-flex items-center gap-1.5 rounded-[5px] px-3 py-1.5 text-body transition-colors duration-150 ease-standard focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 ${
              mode === option.key
                ? "bg-surface-panel font-medium text-ink shadow-card"
                : "text-ink-secondary hover:text-ink"
            }`}
          >
            <Icon name={option.icon} size={14} />
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export default BrowseData;
