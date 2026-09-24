"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { ResultsView } from "@/components/ResultsView";
import { Skeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import {
  AnalysisRecord,
  AnalysisType,
  api,
  apiErrorMessage,
  ColumnProfile,
} from "@/lib/api";

const ANALYSIS_OPTIONS: { value: AnalysisType; label: string; hint: string }[] = [
  {
    value: "descriptive_stats",
    label: "Descriptive statistics",
    hint: "Mean, median, mode, std dev, min/max na quartiles",
  },
  {
    value: "correlation",
    label: "Correlation",
    hint: "Uhusiano kati ya variables (Pearson au Spearman)",
  },
  {
    value: "regression",
    label: "Regression",
    hint: "Kutabiri target kutoka features (linear regression)",
  },
  {
    value: "hypothesis_test",
    label: "Hypothesis test",
    hint: "t-test: linganisha wastani wa makundi mawili",
  },
];

const SELECT_CLASSES =
  "h-10 w-full rounded border border-neutral-200 bg-white px-3 text-body outline-none focus:border-primary-500";

export default function AnalyzePage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params?.id);
  const { showToast } = useToast();

  const [columns, setColumns] = useState<ColumnProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [analysisType, setAnalysisType] = useState<AnalysisType>("descriptive_stats");
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [method, setMethod] = useState<"pearson" | "spearman">("pearson");
  const [targetColumn, setTargetColumn] = useState("");
  const [featureColumns, setFeatureColumns] = useState<string[]>([]);
  const [valueColumn, setValueColumn] = useState("");
  const [groupColumn, setGroupColumn] = useState("");
  const [alpha, setAlpha] = useState("0.05");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<AnalysisRecord | null>(null);
  const [history, setHistory] = useState<AnalysisRecord[]>([]);

  const numericColumns = columns
    .filter((column) => column.data_type === "numeric")
    .map((column) => column.name);

  const loadHistory = useCallback(async () => {
    try {
      setHistory(await api.analysis.listForDataset(datasetId));
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }, [datasetId, showToast]);

  useEffect(() => {
    async function load() {
      if (!Number.isFinite(datasetId)) return;
      setLoading(true);
      try {
        const detail = await api.datasets.get(datasetId);
        setColumns(detail.columns);
        const numeric = detail.columns
          .filter((column) => column.data_type === "numeric")
          .map((column) => column.name);
        setSelectedColumns(numeric);
        setFeatureColumns(numeric.slice(1));
        setTargetColumn(numeric[1] ?? numeric[0] ?? "");
        setValueColumn(numeric[0] ?? "");
        setGroupColumn(
          detail.columns.find((column) => column.unique_count === 2)?.name ?? ""
        );
        await loadHistory();
      } catch (caught) {
        showToast(apiErrorMessage(caught), "danger");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [datasetId, loadHistory, showToast]);

  function toggle(list: string[], value: string, setter: (next: string[]) => void) {
    setter(list.includes(value) ? list.filter((item) => item !== value) : [...list, value]);
  }

  function buildParameters(): Record<string, unknown> {
    switch (analysisType) {
      case "descriptive_stats":
        return selectedColumns.length > 0 ? { columns: selectedColumns } : {};
      case "correlation":
        return {
          ...(selectedColumns.length >= 2 ? { columns: selectedColumns } : {}),
          method,
        };
      case "regression":
        return { target: targetColumn, features: featureColumns };
      case "hypothesis_test":
        return {
          value_column: valueColumn,
          ...(groupColumn ? { group_column: groupColumn } : {}),
          alpha: Number(alpha) || 0.05,
        };
      default:
        return {};
    }
  }

  async function runAnalysis() {
    setRunning(true);
    try {
      const record = await api.analysis.run(datasetId, {
        analysis_type: analysisType,
        parameters: buildParameters(),
      });
      setResult(record);
      showToast("Uchambuzi umekamilika", "success");
      await loadHistory();
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setRunning(false);
    }
  }

  function downloadResultJson() {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result.result_data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${result.analysis_type}_matokeo.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const columnPicker = (
    list: string[],
    setter: (next: string[]) => void,
    options: string[],
    emptyHint: string
  ) => (
    <div className="mt-2 flex max-h-40 flex-wrap gap-2 overflow-y-auto rounded border border-neutral-200 p-2">
      {options.length === 0 ? (
        <p className="text-caption text-neutral-600">{emptyHint}</p>
      ) : (
        options.map((option) => (
          <label
            key={option}
            className="inline-flex min-h-[32px] items-center gap-2 rounded border border-neutral-200 px-2 text-body"
          >
            <input
              type="checkbox"
              checked={list.includes(option)}
              onChange={() => toggle(list, option, setter)}
            />
            {option}
          </label>
        ))
      )}
    </div>
  );

  return (
    <AppShell
      title="Chambua takwimu"
      description="Chagua aina ya uchambuzi, weka parameters na uone matokeo papo hapo."
      actions={
        <>
          <Link href={`/datasets/${datasetId}`}>
            <Button variant="secondary">Angalia data</Button>
          </Link>
          <Link href={`/datasets/${datasetId}/charts`}>
            <Button variant="secondary">Chora chati</Button>
          </Link>
        </>
      }
    >
      <Card title="Aina ya uchambuzi">
        <label className="block text-body text-neutral-600" htmlFor="analysis-type">
          Chagua
        </label>
        <select
          id="analysis-type"
          className={`${SELECT_CLASSES} mt-1`}
          value={analysisType}
          onChange={(event) => setAnalysisType(event.target.value as AnalysisType)}
        >
          {ANALYSIS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label} — {option.hint}
            </option>
          ))}
        </select>

        <div className="mt-4 space-y-3">
          {(analysisType === "descriptive_stats" || analysisType === "correlation") && (
            <div>
              <p className="text-body text-neutral-900">
                Columns{" "}
                {analysisType === "correlation" ? "(numeric, angalau 2)" : "(si lazima)"}
              </p>
              {columnPicker(
                selectedColumns,
                setSelectedColumns,
                numericColumns,
                "Hakuna column ya namba. Badilisha aina ya column kwanza."
              )}
            </div>
          )}

          {analysisType === "correlation" && (
            <div>
              <label className="block text-body text-neutral-600" htmlFor="method">
                Method
              </label>
              <select
                id="method"
                className={`${SELECT_CLASSES} mt-1`}
                value={method}
                onChange={(event) =>
                  setMethod(event.target.value as "pearson" | "spearman")
                }
              >
                <option value="pearson">pearson</option>
                <option value="spearman">spearman</option>
              </select>
            </div>
          )}

          {analysisType === "regression" && (
            <div className="space-y-3">
              <div>
                <label className="block text-body text-neutral-600" htmlFor="target">
                  Target (column ya kutabiri)
                </label>
                <select
                  id="target"
                  className={`${SELECT_CLASSES} mt-1`}
                  value={targetColumn}
                  onChange={(event) => setTargetColumn(event.target.value)}
                >
                  {numericColumns.map((column) => (
                    <option key={column} value={column}>
                      {column}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <p className="text-body text-neutral-900">Features (X)</p>
                {columnPicker(
                  featureColumns,
                  setFeatureColumns,
                  numericColumns.filter((column) => column !== targetColumn),
                  "Hakuna column nyingine ya namba."
                )}
              </div>
            </div>
          )}

          {analysisType === "hypothesis_test" && (
            <div className="space-y-3">
              <div>
                <label
                  className="block text-body text-neutral-600"
                  htmlFor="value-column"
                >
                  Value column (numeric)
                </label>
                <select
                  id="value-column"
                  className={`${SELECT_CLASSES} mt-1`}
                  value={valueColumn}
                  onChange={(event) => setValueColumn(event.target.value)}
                >
                  {numericColumns.map((column) => (
                    <option key={column} value={column}>
                      {column}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label
                  className="block text-body text-neutral-600"
                  htmlFor="group-column"
                >
                  Group column (makundi 2, si lazima)
                </label>
                <select
                  id="group-column"
                  className={`${SELECT_CLASSES} mt-1`}
                  value={groupColumn}
                  onChange={(event) => setGroupColumn(event.target.value)}
                >
                  <option value="">— Hakuna (one-sample t-test) —</option>
                  {columns.map((column) => (
                    <option key={column.name} value={column.name}>
                      {column.name} (unique: {column.unique_count ?? "?"})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-body text-neutral-600" htmlFor="alpha">
                  Alpha (kawaida 0.05)
                </label>
                <input
                  id="alpha"
                  className={`${SELECT_CLASSES} mt-1`}
                  value={alpha}
                  onChange={(event) => setAlpha(event.target.value)}
                />
              </div>
            </div>
          )}
        </div>

        <Button className="mt-4" size="large" loading={running} onClick={runAnalysis}>
          Endesha uchambuzi
        </Button>
      </Card>

      <Card
        title="Matokeo"
        description="Yanahesabiwa kutoka data yako iliyosafishwa."
      >
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : result ? (
          <div className="space-y-4">
            <ResultsView
              analysisType={result.analysis_type}
              result={result.result_data}
            />
            {/* Layer 6 — Hatua zinazofuata (design system §10) */}
            <div className="flex flex-wrap gap-2">
              <Link href={`/datasets/${datasetId}/charts`}>
                <Button variant="secondary" size="small">
                  Chora chati ya matokeo
                </Button>
              </Link>
              <Button variant="ghost" size="small" onClick={downloadResultJson}>
                Pakua matokeo (JSON)
              </Button>
            </div>
          </div>
        ) : (
          <EmptyState
            title="Hakuna matokeo bado"
            description="Chagua aina ya uchambuzi kisha bonyeza 'Endesha uchambuzi'."
          />
        )}
      </Card>

      <Card
        title="Uchambuzi uliofanyika"
        description="Matokeo yote yaliyohifadhiwa kwa dataset hii."
      >
        {history.length === 0 ? (
          <EmptyState title="Hakuna uchambuzi uliohifadhiwa" />
        ) : (
          <ul className="space-y-2">
            {history.map((record) => (
              <li
                key={record.analysis_id}
                className="flex flex-wrap items-center justify-between gap-2 rounded border border-neutral-200 px-3 py-2"
              >
                <span className="flex flex-wrap items-center gap-3">
                  <Badge tone="primary">{record.analysis_type}</Badge>
                  <span className="text-caption text-neutral-600">
                    {record.created_at
                      ? new Date(record.created_at).toLocaleString()
                      : ""}
                  </span>
                </span>
                <Button
                  variant="secondary"
                  size="small"
                  onClick={() => {
                    setAnalysisType(record.analysis_type);
                    setResult(record);
                  }}
                >
                  Onyesha matokeo
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

    </AppShell>
  );
}
