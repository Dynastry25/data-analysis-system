"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { useToast } from "@/components/Toast";
import {
  api,
  apiErrorMessage,
  CleaningHistoryItem,
  ColumnProfile,
} from "@/lib/api";

interface CleaningPanelProps {
  datasetId: number;
  columns: ColumnProfile[];
  onApplied: () => void;
}

const METHODS = ["mean", "median", "mode", "value"] as const;
const TARGET_TYPES = ["numeric", "integer", "text", "date", "boolean"] as const;

const SELECT_CLASSES =
  "h-10 w-full rounded border border-neutral-200 bg-white px-3 text-body outline-none focus:border-primary-500";

function describeAction(action: CleaningHistoryItem): string {
  const applied = (action.parameters?.applied ?? {}) as Record<string, unknown>;
  switch (action.action_type) {
    case "drop_duplicates":
      return `Ondoa duplicates — zilizoondolewa: ${applied.duplicate_rows_removed ?? 0}`;
    case "fill_missing":
      return `Jaza missing (${applied.method ?? "—"}) kwenye "${applied.column ?? "—"}" — zilizojazwa: ${applied.missing_filled ?? 0}`;
    case "drop_column":
      return `Ondoa column "${applied.column ?? "—"}"`;
    case "convert_type":
      return `Badilisha aina ya "${applied.column ?? "—"}" kuwa ${applied.target_type ?? "—"}`;
    default:
      return action.action_type;
  }
}

export function CleaningPanel({ datasetId, columns, onApplied }: CleaningPanelProps) {
  const { showToast } = useToast();
  const [history, setHistory] = useState<CleaningHistoryItem[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [column, setColumn] = useState(columns[0]?.name ?? "");
  const [method, setMethod] = useState<(typeof METHODS)[number]>("mean");
  const [fillValue, setFillValue] = useState("");
  const [targetType, setTargetType] =
    useState<(typeof TARGET_TYPES)[number]>("numeric");

  const loadHistory = useCallback(async () => {
    try {
      setHistory(await api.cleaning.history(datasetId));
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }, [datasetId, showToast]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    if (column && !columns.some((item) => item.name === column)) {
      setColumn(columns[0]?.name ?? "");
    }
  }, [columns, column]);

  async function apply(
    actionType: "drop_duplicates" | "fill_missing" | "drop_column" | "convert_type",
    parameters: Record<string, unknown>
  ) {
    setBusy(actionType);
    try {
      const result = await api.cleaning.apply(datasetId, {
        action_type: actionType,
        parameters,
      });
      showToast(
        `Imefanikiwa. Safu zilizobaki: ${result.row_count.toLocaleString()}`,
        "success"
      );
      await loadHistory();
      onApplied();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card
      title="Safisha data"
      description="Kila kitendo kinarekodiwa (audit trail) — unaweza kufuatilia kilichofanyika."
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-3 rounded border border-neutral-200 p-4">
          <p className="text-h3 text-neutral-900">Ondoa safu zinazorudiwa</p>
          <p className="text-body text-neutral-600">
            Huondoa rows zinazorudia kabisa na kuacha ya kwanza.
          </p>
          <Button
            variant="secondary"
            loading={busy === "drop_duplicates"}
            onClick={() => apply("drop_duplicates", {})}
          >
            Ondoa duplicates
          </Button>
        </div>

        <div className="space-y-3 rounded border border-neutral-200 p-4">
          <p className="text-h3 text-neutral-900">Jaza missing values</p>
          <label className="block text-body text-neutral-600" htmlFor="fill-column">
            Column
          </label>
          <select
            id="fill-column"
            className={SELECT_CLASSES}
            value={column}
            onChange={(event) => setColumn(event.target.value)}
          >
            {columns.map((item) => (
              <option key={item.name} value={item.name}>
                {item.name} ({item.data_type})
              </option>
            ))}
          </select>

          <label className="block text-body text-neutral-600" htmlFor="fill-method">
            Njia
          </label>
          <select
            id="fill-method"
            className={SELECT_CLASSES}
            value={method}
            onChange={(event) =>
              setMethod(event.target.value as (typeof METHODS)[number])
            }
          >
            {METHODS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>

          {method === "value" && (
            <>
              <label className="block text-body text-neutral-600" htmlFor="fill-value">
                Thamani
              </label>
              <input
                id="fill-value"
                className={SELECT_CLASSES}
                value={fillValue}
                onChange={(event) => setFillValue(event.target.value)}
                placeholder="mfano: Unknown"
              />
            </>
          )}

          <Button
            variant="secondary"
            loading={busy === "fill_missing"}
            onClick={() =>
              apply("fill_missing", {
                column,
                method,
                ...(method === "value" ? { value: fillValue } : {}),
              })
            }
          >
            Jaza missing
          </Button>
        </div>

        <div className="space-y-3 rounded border border-neutral-200 p-4">
          <p className="text-h3 text-neutral-900">Ondoa column</p>
          <label className="block text-body text-neutral-600" htmlFor="drop-column">
            Column
          </label>
          <select
            id="drop-column"
            className={SELECT_CLASSES}
            value={column}
            onChange={(event) => setColumn(event.target.value)}
          >
            {columns.map((item) => (
              <option key={item.name} value={item.name}>
                {item.name}
              </option>
            ))}
          </select>
          <Button
            variant="danger"
            loading={busy === "drop_column"}
            onClick={() => apply("drop_column", { column })}
          >
            Ondoa column
          </Button>
        </div>

        <div className="space-y-3 rounded border border-neutral-200 p-4">
          <p className="text-h3 text-neutral-900">Badilisha aina ya data</p>
          <label className="block text-body text-neutral-600" htmlFor="convert-column">
            Column
          </label>
          <select
            id="convert-column"
            className={SELECT_CLASSES}
            value={column}
            onChange={(event) => setColumn(event.target.value)}
          >
            {columns.map((item) => (
              <option key={item.name} value={item.name}>
                {item.name} ({item.data_type})
              </option>
            ))}
          </select>

          <label className="block text-body text-neutral-600" htmlFor="convert-type">
            Aina mpya
          </label>
          <select
            id="convert-type"
            className={SELECT_CLASSES}
            value={targetType}
            onChange={(event) =>
              setTargetType(event.target.value as (typeof TARGET_TYPES)[number])
            }
          >
            {TARGET_TYPES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>

          <Button
            variant="secondary"
            loading={busy === "convert_type"}
            onClick={() => apply("convert_type", { column, target_type: targetType })}
          >
            Badilisha aina
          </Button>
        </div>
      </div>

      <div className="mt-6">
        <p className="text-h3 text-neutral-900">Historia ya usafishaji</p>
        {history.length === 0 ? (
          <div className="mt-2">
            <EmptyState title="Hakuna kitendo cha usafishaji bado" />
          </div>
        ) : (
          <ol className="mt-2 space-y-2">
            {history.map((action) => (
              <li
                key={action.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded border border-neutral-200 px-3 py-2"
              >
                <span className="text-body text-neutral-900">
                  {describeAction(action)}
                </span>
                <span className="text-caption text-neutral-600">
                  {action.created_at
                    ? new Date(action.created_at).toLocaleString()
                    : ""}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </Card>
  );
}

export default CleaningPanel;
