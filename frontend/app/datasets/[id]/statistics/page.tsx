"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { CheckboxGroup, SelectInput, TextInput } from "@/components/Field";
import { RecommendationPanel } from "@/components/RecommendationPanel";
import { TableSkeleton } from "@/components/Skeleton";
import { StandardResultView } from "@/components/StandardResultView";
import { useToast } from "@/components/Toast";
import {
  AnalysisRunRecord,
  AnalysisTypeInfo,
  apiErrorMessage,
  PlanningProfileResponse,
  Recommendation,
  StandardResult,
  statflowApi,
} from "@/lib/api";

/** Column-based parameter names used by the v1 engine. */
const COLUMN_PARAMS = new Set([
  "x",
  "y",
  "value_column",
  "group_column",
  "row_column",
  "column_column",
  "target",
]);
const MULTI_COLUMN_PARAMS = new Set(["features", "columns"]);

const PARAM_LABELS: Record<string, string> = {
  x: "X axis (column)",
  y: "Y axis (column)",
  value_column: "Column ya thamani",
  group_column: "Column ya kundi",
  row_column: "Row axis",
  column_column: "Column axis",
  target: "Target (dependent variable)",
  features: "Features",
  columns: "Columns",
};

function humanize(name: string): string {
  return PARAM_LABELS[name] ?? name.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

/** Parse a `requires` entry like "columns (optional)" into name + required flag. */
function parseRequirement(raw: string): { name: string; optional: boolean } {
  const optional = raw.includes("(optional)");
  const name = raw.split(" ")[0];
  return { name: name === "column" ? "columns" : name, optional };
}

function isBlank(value: string | string[] | undefined): boolean {
  if (value === undefined || value === "") return true;
  return Array.isArray(value) && value.length === 0;
}

/** Map a stored run's parameters back into form state so a run can be reproduced. */
function parametersToFormValues(
  parameters: Record<string, unknown>
): Record<string, string | string[]> {
  const values: Record<string, string | string[]> = {};
  for (const [name, raw] of Object.entries(parameters)) {
    if (Array.isArray(raw)) {
      values[name] = raw.map((item) => String(item));
    } else if (raw !== null && raw !== undefined) {
      values[name] = typeof raw === "string" ? raw : String(raw);
    }
  }
  return values;
}

/** Compact chips describing what a stored run actually computed. */
function parameterChips(
  parameters: Record<string, unknown>
): { name: string; value: string }[] {
  return Object.entries(parameters)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([name, value]) => ({
      name: humanize(name),
      value: Array.isArray(value) ? value.map(String).join(", ") : String(value),
    }));
}

/**
 * Which form fields hold the outcome and the predictor, per method.
 *
 * Mirrors the engine's ANALYSIS_PARAMETER_MAP so the live recommendation can be
 * derived from whatever the user has already chosen in the configure form.
 */
const PAIR_PARAMS: Record<string, { outcome: string[]; predictor: string[] }> = {
  welch_t_test: { outcome: ["value_column"], predictor: ["group_column"] },
  mann_whitney: { outcome: ["value_column"], predictor: ["group_column"] },
  one_way_anova: { outcome: ["value_column"], predictor: ["group_column"] },
  kruskal_wallis: { outcome: ["value_column"], predictor: ["group_column"] },
  pearson: { outcome: ["y"], predictor: ["x"] },
  spearman: { outcome: ["y"], predictor: ["x"] },
  linear_regression: { outcome: ["target"], predictor: ["features"] },
  chi_square: { outcome: ["row_column"], predictor: ["column_column"] },
  fisher_exact: { outcome: ["row_column"], predictor: ["column_column"] },
  descriptive: { outcome: ["columns"], predictor: [] },
  frequency: { outcome: ["columns"], predictor: [] },
};

function firstValue(
  values: Record<string, string | string[]>,
  names: string[]
): string | null {
  for (const name of names) {
    const raw = values[name];
    if (Array.isArray(raw)) {
      if (raw.length > 0) return raw[0];
    } else if (raw) {
      return raw;
    }
  }
  return null;
}

/** The variable pair currently described by the form, for live recommendations. */
function resolvePair(
  analysisType: string,
  values: Record<string, string | string[]>
): { outcome: string | null; predictor: string | null } {
  const spec = PAIR_PARAMS[analysisType];
  if (!spec) return { outcome: null, predictor: null };
  return {
    outcome: firstValue(values, spec.outcome),
    predictor: spec.predictor.length > 0 ? firstValue(values, spec.predictor) : null,
  };
}

export default function StatisticsPage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params?.id);
  const { showToast } = useToast();

  const [types, setTypes] = useState<AnalysisTypeInfo[]>([]);
  const [profile, setProfile] = useState<PlanningProfileResponse | null>(null);
  const [runs, setRuns] = useState<AnalysisRunRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [analysisType, setAnalysisType] = useState("");
  const [paramValues, setParamValues] = useState<Record<string, string | string[]>>({});
  const [running, setRunning] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [result, setResult] = useState<StandardResult | null>(null);

  const load = useCallback(async () => {
    if (!Number.isFinite(datasetId)) return;
    setLoading(true);
    setError(null);
    try {
      const [analysisTypes, planningProfile, history] = await Promise.all([
        statflowApi.analysisTypes(),
        statflowApi.planningProfile(datasetId),
        statflowApi.analysisRuns(datasetId),
      ]);
      setTypes(analysisTypes);
      setProfile(planningProfile);
      setRuns(history);
    } catch (caught) {
      const message = apiErrorMessage(caught);
      setError(message);
      showToast(message, "danger");
    } finally {
      setLoading(false);
    }
  }, [datasetId, showToast]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!analysisType && types.length > 0) {
      setAnalysisType(types[0].analysis_type);
    }
  }, [types, analysisType]);

  const currentType = types.find((entry) => entry.analysis_type === analysisType) ?? null;
  const requirements = (currentType?.requires ?? []).map(parseRequirement);
  const numericColumns = (profile?.variables_by_type?.numeric ?? []) as string[];
  const allColumns = (profile?.variables ?? []).map((variable) => variable.name);
  const datasetVersion = profile?.meta.dataset_version ?? null;
  const pair = resolvePair(analysisType, paramValues);

  const missingRequired = requirements.filter(
    (requirement) => !requirement.optional && isBlank(paramValues[requirement.name])
  );
  const canRun = currentType !== null && missingRequired.length === 0 && !running;

  function buildParameters(): Record<string, unknown> {
    const parameters: Record<string, unknown> = {};
    for (const requirement of requirements) {
      const raw = paramValues[requirement.name];
      if (raw === undefined || raw === "") continue;
      if (Array.isArray(raw)) {
        if (raw.length > 0) parameters[requirement.name] = raw;
      } else {
        parameters[requirement.name] = raw;
      }
    }
    return parameters;
  }

  async function runAnalysis() {
    if (!currentType) return;
    setAttempted(true);
    if (!canRun) {
      showToast("Jaza parameters zote zinazohitajika kwanza.", "warning");
      return;
    }
    setRunning(true);
    try {
      const response = await statflowApi.runAnalysis(datasetId, {
        analysis_type: currentType.analysis_type,
        parameters: buildParameters(),
      });
      setResult(response.result);
      setRuns(await statflowApi.analysisRuns(datasetId));
      showToast("Uchambuzi umekamilika", "success");
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setRunning(false);
    }
  }

  /**
   * Adopt the engine's recommendation verbatim, including its parameters, so the
   * form never drifts from the method the diagnostics were computed for.
   */
  function applyRecommendation(recommendation: Recommendation["recommendation"]) {
    setAnalysisType(recommendation.analysis_type);
    setParamValues(parametersToFormValues(recommendation.parameters));
    setAttempted(false);
    setResult(null);
    showToast(`Njia imebadilishwa kuwa ${recommendation.label}.`, "success");
  }

  function downloadResultJson() {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${result.analysis_type}_v${datasetVersion ?? 1}_matokeo.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  /** Re-open a stored run: restore its parameters so it can be re-run or tweaked. */
  function openRun(run: AnalysisRunRecord) {
    setAnalysisType(run.analysis_type);
    setParamValues(parametersToFormValues(run.parameters));
    setAttempted(false);
    setResult(run.result);
    showToast(
      `Umefungua uchambuzi wa ${run.analysis_type} kwenye toleo v${run.dataset_version}.`,
      "info"
    );
  }

  function toggleMulti(name: string, column: string) {
    setParamValues((previous) => {
      const current = Array.isArray(previous[name]) ? (previous[name] as string[]) : [];
      const next = current.includes(column)
        ? current.filter((item) => item !== column)
        : [...current, column];
      return { ...previous, [name]: next };
    });
  }

  function columnOptions(name: string): string[] {
    if (name === "target" || name === "value_column" || name === "x" || name === "y") {
      return numericColumns.length > 0 ? numericColumns : allColumns;
    }
    return allColumns;
  }

  function renderParam(requirement: { name: string; optional: boolean }) {
    const { name } = requirement;
    const value = paramValues[name];
    const error =
      attempted && !requirement.optional && isBlank(value)
        ? "Parameter hii inahitajika kwa uchambuzi huu."
        : undefined;
    const label = humanize(name);

    if (MULTI_COLUMN_PARAMS.has(name)) {
      const selected = Array.isArray(value) ? value : [];
      return (
        <CheckboxGroup
          label={label}
          optionalLabel={requirement.optional ? "hiari" : undefined}
          error={error}
          options={columnOptions(name)}
          selected={selected}
          onToggle={(column) => toggleMulti(name, column)}
          maxHeightClassName="max-h-36"
        />
      );
    }

    if (COLUMN_PARAMS.has(name)) {
      return (
        <SelectInput
          label={label}
          optionalLabel={requirement.optional ? "hiari" : undefined}
          required={!requirement.optional}
          error={error}
          placeholder="— chagua column —"
          value={String(value || "")}
          options={columnOptions(name).map((column) => ({ value: column, label: column }))}
          onChange={(event) =>
            setParamValues((previous) => ({ ...previous, [name]: event.target.value }))
          }
        />
      );
    }

    return (
      <TextInput
        label={label}
        optionalLabel={requirement.optional ? "hiari" : undefined}
        required={!requirement.optional}
        error={error}
        value={String(value ?? "")}
        onChange={(event) =>
          setParamValues((previous) => ({ ...previous, [name]: event.target.value }))
        }
      />
    );
  }

  return (
    <AppShell
      title="Chumba cha takwimu"
      description="Endesha uchambuzi wowote wa engine moja ya takwimu matokeo yote yana muundo mmoja."
      actions={
        <Link href={`/datasets/${datasetId}`}>
          <Button variant="secondary" icon="arrow-right">
            Rudi kwenye dataset
          </Button>
        </Link>
      }
    >
      {loading ? (
        <Card>
          <TableSkeleton rows={6} columns={4} />
        </Card>
      ) : error ? (
        <Card>
          <EmptyState title="Imeshindikana kupakia" description={error} />
        </Card>
      ) : (
        <>
          <Card
            title="Endesha uchambuzi"
            icon="calculator"
            description={
              profile
                ? `Version v${profile.meta.dataset_version ?? 1} · ${profile.sample_size} rows · ${profile.variable_count} columns`
                : undefined
            }
          >
            <div className="grid gap-4 md:grid-cols-2">
              <SelectInput
                label="Aina ya uchambuzi"
                value={analysisType}
                hint={currentType?.description}
                options={types.map((entry) => ({
                  value: entry.analysis_type,
                  label: entry.analysis_type,
                }))}
                onChange={(event) => {
                  setAnalysisType(event.target.value);
                  setParamValues({});
                  setAttempted(false);
                  setResult(null);
                }}
              />
              {requirements.map((requirement) =>
                renderParam(requirement)
              )}
            </div>
            {attempted && missingRequired.length > 0 && (
              <p
                role="alert"
                className="mt-4 flex items-start gap-2 rounded-md border border-danger/30 bg-danger-bg px-3 py-2.5 text-body text-danger-700"
              >
                <span className="font-medium">
                  Jaza parameters zote zinazohitajika:{" "}
                  {missingRequired.map((requirement) => humanize(requirement.name)).join(", ")}.
                </span>
              </p>
            )}
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button size="large" loading={running} onClick={runAnalysis}>
                Endesha uchambuzi
              </Button>
              {currentType && (
                <span className="text-caption text-ink-muted">
                  {requirements.filter((entry) => !entry.optional).length} parameters zinazohitajika
                  · matokeo yatafunguliwa hapa chini
                </span>
              )}
            </div>
          </Card>

          <RecommendationPanel
            datasetId={datasetId}
            datasetVersion={datasetVersion}
            outcome={pair.outcome}
            predictor={pair.predictor}
            selectedAnalysisType={analysisType || null}
            onApply={applyRecommendation}
          />

          <Card
            title="Matokeo"
            description="Muundo wa kawaida wa matokeo: estimate, test, CI, effect size, diagnostics."
            icon="chart"
          >
            {result ? (
              <StandardResultView
                result={result}
                actions={
                  <>
                    <Button
                      variant="secondary"
                      size="small"
                      icon="download"
                      onClick={downloadResultJson}
                    >
                      Pakua matokeo (JSON)
                    </Button>
                    <Button
                      variant="ghost"
                      size="small"
                      icon="calculator"
                      onClick={() => {
                        setResult(null);
                        setAttempted(false);
                      }}
                    >
                      Fanya uchambuzi mwingine
                    </Button>
                  </>
                }
              />
            ) : (
              <EmptyState
                title="Hakuna matokeo bado"
                description="Chagua aina ya uchambuzi kisha bonyeza Endesha uchambuzi. Matokeo yataonyesha hapa pamoja na chanzo cha kila namba."
                icon="calculator"
              />
            )}
          </Card>

          <Card
            title="Historia ya uchambuzi"
            description="Kila run inarekodi aina, parameters, toleo la data na wakati — hivyo matokeo yanaweza kurudiwa."
            icon="history"
          >
            {runs.length === 0 ? (
              <EmptyState
                title="Hakuna uchambuzi uliohifadhiwa"
                description="Uchambuzi wote unaofanywa hapa huhifadhiwa na unaweza kufunguliwa tena baadaye."
                icon="history"
              />
            ) : (
              <ul className="divide-y divide-surface-border">
                {runs.map((run) => {
                  const chips = parameterChips(run.parameters);
                  return (
                    <li key={run.analysis_id} className="py-3 first:pt-0 last:pb-0">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="flex flex-wrap items-center gap-2">
                          <Badge tone="primary">{run.analysis_type}</Badge>
                          <Badge tone={run.status === "success" ? "success" : "warning"}>
                            {run.status}
                          </Badge>
                          <span className="text-caption text-ink-muted">
                            <span className="font-mono font-medium text-ink">
                              v{run.dataset_version}
                            </span>
                            {run.created_at
                              ? ` · ${new Date(run.created_at).toLocaleString()}`
                              : ""}
                          </span>
                        </span>
                        <Button
                          variant="secondary"
                          size="small"
                          icon="table"
                          onClick={() => openRun(run)}
                        >
                          Fungua
                        </Button>
                      </div>
                      {chips.length > 0 && (
                        <ul className="mt-2 flex flex-wrap gap-1.5">
                          {chips.map((chip) => (
                            <li
                              key={chip.name}
                              className="inline-flex items-center gap-1 rounded border border-surface-border bg-surface-sunken px-2 py-0.5 text-caption"
                            >
                              <span className="text-ink-muted">{chip.name}:</span>
                              <span className="truncate font-medium text-ink">
                                {chip.value}
                              </span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </>
      )}
    </AppShell>
  );
}


