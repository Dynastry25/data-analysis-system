"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
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

const SELECT_CLASSES =
  "h-10 w-full rounded border border-neutral-200 bg-white px-3 text-body outline-none focus:border-primary-500";

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

/** Parse a `requires` entry like "columns (optional)" into name + required flag. */
function parseRequirement(raw: string): { name: string; optional: boolean } {
  const optional = raw.includes("(optional)");
  const name = raw.split(" ")[0];
  return { name: name === "column" ? "columns" : name, optional };
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
    if (MULTI_COLUMN_PARAMS.has(name)) {
      const selected = Array.isArray(value) ? value : [];
      return (
        <div className="mt-1 flex max-h-32 flex-wrap gap-2 overflow-y-auto rounded border border-neutral-200 p-2">
          {columnOptions(name).map((column) => (
            <label key={column} className="flex items-center gap-1 text-caption">
              <input
                type="checkbox"
                checked={selected.includes(column)}
                onChange={() => toggleMulti(name, column)}
              />
              {column}
            </label>
          ))}
        </div>
      );
    }
    if (COLUMN_PARAMS.has(name)) {
      return (
        <select
          className={`${SELECT_CLASSES} mt-1`}
          value={String(value || "")}
          onChange={(event) =>
            setParamValues((previous) => ({ ...previous, [name]: event.target.value }))
          }
        >
          <option value="">— chagua column —</option>
          {columnOptions(name).map((column) => (
            <option key={column} value={column}>
              {column}
            </option>
          ))}
        </select>
      );
    }
    return (
      <input
        className={`${SELECT_CLASSES} mt-1`}
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
      description="Endesha uchambuzi wowote wa engine moja ya takwimu (MVP-19) — matokeo yote yana muundo mmoja."
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
            description={
              profile
                ? `Version v${profile.meta.dataset_version ?? 1} · ${profile.sample_size} rows · ${profile.variable_count} columns`
                : undefined
            }
          >
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="block text-body text-neutral-600" htmlFor="a-type">
                  Aina ya uchambuzi
                </label>
                <select
                  id="a-type"
                  className={`${SELECT_CLASSES} mt-1`}
                  value={analysisType}
                  onChange={(event) => {
                    setAnalysisType(event.target.value);
                    setParamValues({});
                  }}
                >
                  {types.map((entry) => (
                    <option key={entry.analysis_type} value={entry.analysis_type}>
                      {entry.analysis_type}
                    </option>
                  ))}
                </select>
                {currentType && (
                  <p className="mt-2 text-caption text-neutral-600">
                    {currentType.description}
                  </p>
                )}
              </div>
              {requirements.map((requirement) => (
                <div key={requirement.name}>
                  <label className="block text-body text-neutral-600">
                    {requirement.name}
                    {requirement.optional ? " (hiari)" : ""}
                  </label>
                  {renderParam(requirement)}
                </div>
              ))}
            </div>
            <Button
              className="mt-4"
              size="large"
              loading={running}
              onClick={runAnalysis}
            >
              Endesha uchambuzi
            </Button>
          </Card>

          <Card
            title="Matokeo"
            description="Muundo wa kawaida wa matokeo: estimate, test, CI, effect size, diagnostics."
          >
            {result ? (
              <StandardResultView result={result} />
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


