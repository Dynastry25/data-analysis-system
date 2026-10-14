"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Card, EmptyState } from "@/components/Card";
import { Icon } from "@/components/Icon";
import { StandardResultView } from "@/components/StandardResultView";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import {
  apiErrorMessage,
  AnalysisTemplate,
  PlanningVariable,
  statflowApi,
  TemplateRunResponse,
  TemplateVariable,
} from "@/lib/api";

/**
 * Phase 3.3 — the questions organisations actually ask, pre-translated
 * into the variables and methods that answer them.
 *
 * The page's whole job is the translation a first-time reader stalls
 * on: pick the question, confirm the columns (proposed by type, never
 * assumed by name), run. The engine is the ordinary one — every step
 * below is a standard result with its assumption checks and its
 * interpretation — so nothing here is a shortcut the reader has to
 * trust, and the parameters each step ran with are shown.
 */
export default function TemplatesPage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params?.id);
  const { showToast } = useToast();

  const [templates, setTemplates] = useState<AnalysisTemplate[]>([]);
  const [note, setNote] = useState("");
  const [variables, setVariables] = useState<PlanningVariable[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [choices, setChoices] = useState<Record<string, Record<string, Record<string, string>>>>({});
  const [running, setRunning] = useState<string | null>(null);
  const [run, setRun] = useState<TemplateRunResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    statflowApi
      .templates()
      .then((response) => {
        if (cancelled) return;
        setTemplates(response.templates);
        setNote(response.note);
      })
      .catch((cause) => showToast(apiErrorMessage(cause), "danger"))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [showToast]);

  // The reader's own columns, so a picker offers the dataset rather
  // than a type. If the profile cannot be read the template still
  // runs: the engine resolves the variables from the data itself.
  useEffect(() => {
    let cancelled = false;
    statflowApi
      .planningProfile(datasetId)
      .then((profile) => {
        if (!cancelled) setVariables(profile.variables);
      })
      .catch(() => {
        // A missing profile must not disable the run: the template
        // resolves the reader's dataset itself from its own types.
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  const columnsFor = useCallback(
    (expectedType: string) => {
      const wantsCategorical = expectedType === "categorical";
      const matching = variables.filter((variable) =>
        wantsCategorical
          ? variable.semantic_type === "categorical" || variable.semantic_type === "boolean"
          : variable.semantic_type === "numeric"
      );
      return matching.length > 0
        ? matching.map((variable) => variable.name)
        : variables.map((variable) => variable.name);
    },
    [variables]
  );

  const runTemplate = useCallback(
    async (key: string) => {
      setRunning(key);
      try {
        const response = await statflowApi.runTemplate(datasetId, key, choices[key]);
        setRun(response);
      } catch (cause) {
        showToast(apiErrorMessage(cause), "danger");
      } finally {
        setRunning(null);
      }
    },
    [choices, datasetId, showToast]
  );

  const byCategory = templates.reduce<Record<string, AnalysisTemplate[]>>(
    (groups, template) => {
      groups[template.category] = [...(groups[template.category] ?? []), template];
      return groups;
    },
    {}
  );

  return (
    <AppShell
      eyebrow="Template za uchambuzi"
      title="Maswali ya kawaida ya shirika"
      description="Chagua swali unalojibu mara nyingi: donor reporting, tathmini ya programu, mazao, au kukaa kwa wateja. Template inapanga variables na mbinu — engine ya takwimu inakokotoa kila namba, kama kawaida."
      actions={
        <Link href={`/datasets/${datasetId}`}>
          <button
            type="button"
            className="flex min-h-[36px] items-center gap-2 rounded-md border border-surface-border px-3.5 text-caption text-ink-secondary transition-colors duration-150 ease-standard hover:bg-surface-sunken"
          >
            Rudi kwenye dataset
          </button>
        </Link>
      }
    >
      {loading && <TableSkeleton rows={4} />}

      {!loading && templates.length === 0 && (
        <EmptyState
          icon="clipboard"
          title="Hakuna template bado"
          description="Template za maswali ya kawaida hazijapakiwa."
        />
      )}

      {!loading &&
        Object.entries(byCategory).map(([category, entries]) => (
          <section key={category} className="mb-6">
            <h2 className="mb-2.5 text-overline uppercase tracking-wide text-ink-muted">
              {category}
            </h2>
            <div className="grid gap-4 md:grid-cols-2">
              {entries.map((template) => {
                const open = selected === template.key;
                return (
                  <Card key={template.key}>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-body font-medium text-ink">{template.label}</p>
                        <p className="mt-0.5 text-caption text-ink-muted">
                          {template.label_swahili}
                        </p>
                      </div>
                      <Badge tone="neutral" size="sm">
                        {template.steps.length} hatua
                      </Badge>
                    </div>

                    <p className="mt-2 text-body text-ink-secondary">{template.question}</p>
                    <p className="mt-1 text-caption text-ink-muted">
                      {template.when_to_use}
                    </p>

                    <button
                      type="button"
                      onClick={() => {
                        setSelected(open ? null : template.key);
                        setRun(null);
                      }}
                      className="mt-3 flex min-h-[36px] items-center gap-2 rounded-md border border-surface-border px-3.5 text-caption text-ink-secondary transition-colors duration-150 ease-standard hover:bg-surface-sunken"
                    >
                      <Icon name={open ? "chevron-up" : "chevron-down"} size={13} />
                      {open ? "Funga" : "Chagua variables"}
                    </button>

                    {open && (
                      <div className="mt-3 space-y-3 rounded-md border border-surface-border bg-surface-sunken p-3">
                        <p className="text-caption text-ink-muted">{note}</p>
                        {template.steps.map((step) => (
                          <div key={step.key}>
                            <p className="text-caption font-medium text-ink">
                              {step.label}
                            </p>
                            <p className="text-caption text-ink-muted">{step.description}</p>
                            <div className="mt-2 space-y-2">
                              {step.variables.map((variable) => (
                                <VariablePicker
                                  key={`${step.key}-${variable.key}`}
                                  variable={variable}
                                  columns={columnsFor(variable.expected_type)}
                                  value={choices[template.key]?.[step.key]?.[variable.key] ?? ""}
                                  onChange={(value) =>
                                    setChoices((previous) => {
                                      const templateChoices = {
                                        ...(previous[template.key] ?? {}),
                                      };
                                      templateChoices[step.key] = {
                                        ...(templateChoices[step.key] ?? {}),
                                        [variable.key]: value,
                                      };
                                      return { ...previous, [template.key]: templateChoices };
                                    })
                                  }
                                />
                              ))}
                            </div>
                          </div>
                        ))}
                        <button
                          type="button"
                          onClick={() => runTemplate(template.key)}
                          disabled={running === template.key}
                          className="flex min-h-[40px] w-full items-center justify-center gap-2 rounded-md bg-primary-600 px-4 text-body font-medium text-white transition-colors duration-150 ease-standard hover:bg-primary-700 disabled:opacity-60"
                        >
                          {running === template.key
                            ? "Inachambua…"
                            : `Endelea na ${template.steps.length} hatua`}
                        </button>
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
          </section>
        ))}

      {run && (
        <section className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="success" size="md" icon="check">
              {run.template.label}
            </Badge>
            <span className="text-caption text-ink-muted">
              data v{run.dataset_version} · {run.meta.rows.toLocaleString("en-KE")} rows
            </span>
          </div>
          {run.steps.map((step, index) => (
            <div key={step.key}>
              <p className="mb-1.5 flex items-center gap-2 text-body font-medium text-ink">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary-50 text-caption font-semibold text-primary-700">
                  {index + 1}
                </span>
                {step.label}
                <span className="text-caption font-normal text-ink-muted">{step.reads}</span>
              </p>
              <StandardResultView result={step.result} />
            </div>
          ))}
        </section>
      )}
    </AppShell>
  );
}

/**
 * One variable to confirm before a template runs. The default is
 * "automatic" because a template proposes by type — it never assumes
 * a column the reader has not chosen. The picker only narrows what
 * the reader sees; leaving it on automatic hands the choice to the
 * engine, which resolves it from the data's own types.
 */
function VariablePicker({
  variable,
  columns,
  value,
  onChange,
}: {
  variable: TemplateVariable;
  columns: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="mb-1 block text-caption text-ink-secondary">
        {variable.label}
        <span className="ml-1.5 text-ink-muted">({variable.role})</span>
      </label>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-[36px] w-full rounded-md border border-surface-border bg-surface-panel px-2.5 text-caption text-ink"
      >
        <option value="">Automatic — engine huchagua kutoka aina ya data</option>
        {columns.map((column) => (
          <option key={column} value={column}>
            {column}
          </option>
        ))}
      </select>
    </div>
  );
}
