"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { CheckboxGroup, SelectInput, TextInput } from "@/components/Field";
import { TableSkeleton } from "@/components/Skeleton";
import { StandardResultView } from "@/components/StandardResultView";
import { useToast } from "@/components/Toast";
import {
  AnalysisRunRecord,
  AnalysisTypeInfo,
  apiErrorMessage,
  PlanningProfileResponse,
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

  function downloadResultJson() {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${result.analysis_type}_matokeo.json`;
    anchor.click();
    URL.revokeObjectURL(url);
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
          <Button variant="secondary">Rudi kwenye dataset</Button>
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

          <Card
            title="Matokeo"
            description="Muundo wa kawaida wa matokeo: estimate, test, CI, effect size, diagnostics."
          >
            {result ? (
              <StandardResultView
                result={result}
                actions={
                  <>
                    <Button variant="secondary" size="small" onClick={downloadResultJson}>
                      Pakua ripoti (JSON)
                    </Button>
                    <Button
                      variant="ghost"
                      size="small"
                      onClick={() => setResult(null)}
                    >
                      Fanya uchambuzi mwingine
                    </Button>
                  </>
                }
              />
            ) : (
              <EmptyState
                title="Hakuna matokeo bado"
                description="Chagua aina ya uchambuzi kisha bonyeza 'Endesha uchambuzi'."
              />
            )}
          </Card>

          <Card
            title="Historia ya uchambuzi"
            description="Matokeo yote yaliyohifadhiwa kwa dataset hii (v1 engine)."
          >
            {runs.length === 0 ? (
              <EmptyState title="Hakuna uchambuzi uliohifadhiwa" />
            ) : (
              <ul className="space-y-2">
                {runs.map((run) => (
                  <li
                    key={run.analysis_id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded border border-neutral-200 px-3 py-2"
                  >
                    <span className="flex flex-wrap items-center gap-3">
                      <Badge tone="primary">{run.analysis_type}</Badge>
                      <Badge tone={run.status === "success" ? "success" : "warning"}>
                        {run.status}
                      </Badge>
                      <span className="text-caption text-neutral-600">
                        v{run.dataset_version}
                        {run.created_at
                          ? ` · ${new Date(run.created_at).toLocaleString()}`
                          : ""}
                      </span>
                    </span>
                    <Button
                      variant="secondary"
                      size="small"
                      onClick={() => {
                        setAnalysisType(run.analysis_type);
                        setResult(run.result);
                      }}
                    >
                      Onyesha matokeo
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </AppShell>
  );
}


