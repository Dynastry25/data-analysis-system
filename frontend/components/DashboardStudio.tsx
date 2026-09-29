"use client";

import { useState } from "react";

import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { ChartView } from "@/components/ChartView";
import { SelectInput, TextArea, TextInput } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { useToast } from "@/components/Toast";
import {
  AnalysisRunRecord,
  api,
  apiErrorMessage,
  ChartRecord,
  DashboardRecord,
  DashboardWidget,
  DashboardWidgetType,
  ExploreColumn,
} from "@/lib/api";

// ------------------------------------------------------------- KPI resolving

const ANALYSIS_METRICS: Record<string, { label: string; sample: (r: AnalysisRunRecord) => boolean }> = {
  effect_size: {
    label: "Effect size",
    sample: (r) => r.result.effect_size?.value !== null && r.result.effect_size?.value !== undefined,
  },
  p_value: {
    label: "p-value",
    sample: (r) => r.result.test?.p_value !== null && r.result.test?.p_value !== undefined,
  },
  r_squared: {
    label: "R squared",
    sample: (r) => r.result.estimate?.r_squared !== undefined,
  },
  sample_size: {
    label: "Sample size",
    sample: (r) => r.result.sample_size !== null,
  },
};

function metricValue(analysis: AnalysisRunRecord, metric?: string): number | null {
  if (!analysis?.result) return null;
  switch (metric) {
    case "effect_size":
      return analysis.result.effect_size?.value ?? null;
    case "p_value":
      return analysis.result.test?.p_value ?? null;
    case "r_squared": {
      const value = analysis.result.estimate?.r_squared;
      return typeof value === "number" ? value : null;
    }
    case "sample_size":
      return analysis.result.sample_size ?? null;
    default:
      return null;
  }
}

function formatKpi(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (Math.abs(value) >= 1e4) return `${(value / 1e3).toFixed(1)}k`;
  if (Math.abs(value) >= 1 && Math.abs(value) < 100) return value.toFixed(2);
  if (Math.abs(value) < 1) return value.toFixed(3);
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function kpiForWidget(
  widget: DashboardWidget,
  analyses: AnalysisRunRecord[],
  columns: ExploreColumn[],
): { value: number | null; label: string; note?: string } {
  if (widget.type === "kpi" && widget.source) {
    const source = widget.source;
    if (source.kind === "analysis") {
      const analysis = analyses.find((item) => item.analysis_id === source.analysis_id);
      if (analysis) {
        return {
          value: metricValue(analysis, source.metric),
          label: source.label || (source.metric ? ANALYSIS_METRICS[source.metric]?.label ?? source.metric : "Metric"),
          note: `${analysis.analysis_type} · v${analysis.dataset_version}`,
        };
      }
    }
    if (source.kind === "column" && source.column) {
      const column = columns.find((item) => item.name === source.column);
      if (column) {
        return {
          value: column.mean ?? column.median ?? null,
          label: source.label || `Maan ya ${source.column}`,
          note: `wasiani wa ${source.column}`,
        };
      }
    }
  }
  return { value: null, label: "KPI bila chanzo", note: "Chagua chanzo katika mipangilio" };
}

function insightText(
  widget: DashboardWidget,
  analyses: AnalysisRunRecord[],
): string | null {
  if (widget.type === "insight" && widget.analysis_id) {
    const analysis = analyses.find((item) => item.analysis_id === widget.analysis_id);
    if (!analysis) return "Uchambuzi haupatikani tena.";
    const result = analysis.result;
    const parts: string[] = [];
    if (result.effect_size?.value !== null && result.effect_size?.value !== undefined) {
      parts.push(`Effect size = ${formatKpi(result.effect_size.value)}`);
    }
    if (result.test?.p_value !== null && result.test?.p_value !== undefined) {
      const p = result.test.p_value as number;
      parts.push(`p ${p < 0.001 ? "< .001" : `= ${p.toFixed(3)}`}`);
    }
    if (result.estimate?.r_squared !== undefined) {
      parts.push(`R² = ${formatKpi(result.estimate.r_squared as number)}`);
    }
    if (parts.length === 0) parts.push(`Uchambuzi: ${analysis.analysis_type}`);
    return `Nadharia ya ${analysis.analysis_type}: ${parts.join(" · ")}.`;
  }
  return null;
}

function analysisMetricOptions(analysis?: AnalysisRunRecord): { value: string; label: string }[] {
  if (!analysis) return [];
  return Object.entries(ANALYSIS_METRICS)
    .filter(([, check]) => check.sample(analysis))
    .map(([key, meta]) => ({ value: key, label: meta.label }));
}

// ------------------------------------------------------------------- Editor

interface DashboardStudioProps {
  datasetId: number;
  datasetVersion: number;
  columns: ExploreColumn[];
  analyses: AnalysisRunRecord[];
  charts: ChartRecord[];
  dashboards: DashboardRecord[];
  onSaved: (dashboard: DashboardRecord) => void;
}

const WIDGET_LIBRARY: { type: DashboardWidgetType; label: string; description: string }[] = [
  {
    type: "kpi",
    label: "KPI",
    description: "Thamani moja kutoka uchambuzi au column",
  },
  {
    type: "chart",
    label: "Chati",
    description: "Chati iliyohifadhiwa kutoka Visual Studio",
  },
  {
    type: "filter",
    label: "Filter",
    description: "Rekodi ya kichujio cha muhtasari huu",
  },
  {
    type: "insight",
    label: "Insight",
    description: "Muhtasari wa uchambuzi uliohifadhiwa",
  },
  {
    type: "text",
    label: "Maelezo",
    description: "Note halisi kwa washiriki",
  },
];

function freshWidget(type: DashboardWidgetType): DashboardWidget {
  const id = `${type}-${Date.now().toString(36)}`;
  if (type === "kpi") return { id, type, title: "KPI mpya", source: { kind: "analysis" } };
  if (type === "chart") return { id, type, title: "Chati" };
  if (type === "filter") return { id, type, title: "Filter", operator: ">" };
  if (type === "insight") return { id, type, title: "Insight" };
  return { id, type, title: "Maelezo", content: "" };
}

export function DashboardStudio({
  datasetId,
  datasetVersion,
  columns,
  analyses,
  charts,
  dashboards,
  onSaved,
}: DashboardStudioProps) {
  const { showToast } = useToast();

  const [widgets, setWidgets] = useState<DashboardWidget[]>([]);
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [configWidget, setConfigWidget] = useState<string | null>(null);

  const columnOptions = columns.map((column) => ({ value: column.name, label: column.name }));
  const analysisOptions = analyses.map((analysis) => ({
    value: String(analysis.analysis_id),
    label: `${analysis.analysis_type} · v${analysis.dataset_version} · #${analysis.analysis_id}`,
  }));
  const chartOptions = charts.map((record) => ({
    value: String(record.chart_id),
    label: `${record.chart_type} · x:${record.config.x}${record.config.y ? ` / ${record.config.y}` : ""}`,
  }));

  function patchWidget(id: string, patch: Partial<DashboardWidget>) {
    setWidgets((previous) =>
      previous.map((widget) => (widget.id === id ? { ...widget, ...patch } : widget)),
    );
  }

  function addWidget(type: DashboardWidgetType) {
    const widget = freshWidget(type);
    setWidgets((previous) => [...previous, widget]);
    setConfigWidget(widget.id);
    setTitle((previous) => previous || "Dashboard ya uchambuzi");
  }

  function moveWidget(id: string, direction: -1 | 1) {
    setWidgets((previous) => {
      const index = previous.findIndex((widget) => widget.id === id);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= previous.length) return previous;
      const next = [...previous];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  async function saveDashboard() {
    if (widgets.length === 0) {
      showToast("Ongeza angalau widget moja kwenye dashboard", "danger");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        name: name || (title ? "dashboard-untitled" : "dashboard"),
        title: title || undefined,
        widgets,
      };
      let saved: DashboardRecord;
      if (editing === null) {
        saved = await api.dashboards.create(datasetId, payload);
        showToast("Dashboard imehifadhiwa kwenye toleo mpya", "success");
      } else {
        saved = await api.dashboards.update(editing, payload);
        showToast("Dashboard imesasishwa", "success");
      }
      onSaved(saved);
      setEditing(saved.dashboard_id);
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setSaving(false);
    }
  }

  function loadDashboard(record: DashboardRecord) {
    setEditing(record.dashboard_id);
    setWidgets(record.config?.widgets ?? []);
    setName(record.name);
    setTitle(record.title ?? "");
    setConfigWidget(null);
  }

  function clearDraft() {
    setEditing(null);
    setWidgets([]);
    setName("");
    setTitle("");
    setConfigWidget(null);
  }

  function WidgetEditor({ widget }: { widget: DashboardWidget }) {
    return (
      <div className="rounded-md border border-primary-200 bg-primary-50/40 p-3">
        <p className="mb-2 flex items-center gap-1.5 text-overline uppercase tracking-wide text-primary-800">
          <Icon name="sliders" size={12} />
          Mipangilio ya widget
        </p>
        <div className="grid gap-3">
          <TextInput
            label="Kichwa"
            value={widget.title ?? ""}
            onChange={(event) => patchWidget(widget.id, { title: event.target.value })}
          />
          {widget.type === "kpi" && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <SelectInput
                  label="Chanzo"
                  value={widget.source?.kind ?? "analysis"}
                  options={[
                    { value: "analysis", label: "Uchambuzi uliohifadhiwa" },
                    { value: "column", label: "Column (wastani)" },
                  ]}
                  onChange={(event) =>
                    patchWidget(widget.id, {
                      source: {
                        ...(widget.source ?? { kind: "analysis" as const }),
                        kind: event.target.value as "analysis" | "column",
                      },
                    })
                  }
                />
                {widget.source?.kind === "column" && (
                  <SelectInput
                    label="Column"
                    value={widget.source.column ?? ""}
                    options={columnOptions}
                    onChange={(event) =>
                      patchWidget(widget.id, {
                        source: {
                          ...(widget.source ?? { kind: "column" as const }),
                          column: event.target.value,
                        },
                      })
                    }
                  />
                )}
              </div>
              {widget.source?.kind === "analysis" && (
                <div className="grid grid-cols-2 gap-3">
                  <SelectInput
                    label="Uchambuzi"
                    value={widget.source.analysis_id ? String(widget.source.analysis_id) : ""}
                    options={analysisOptions}
                    onChange={(event) =>
                      patchWidget(widget.id, {
                        source: {
                          ...(widget.source ?? { kind: "analysis" as const }),
                          analysis_id: Number(event.target.value),
                        },
                      })
                    }
                  />
                  <SelectInput
                    label="Metric"
                    value={widget.source.metric ?? ""}
                    options={analysisMetricOptions(
                      analyses.find(
                        (item) =>
                          item.analysis_id === (widget.source ?? { kind: "analysis" }).analysis_id
                      ),
                    )}
                    onChange={(event) =>
                      patchWidget(widget.id, {
                        source: {
                          ...(widget.source ?? { kind: "analysis" as const }),
                          metric: event.target.value,
                        },
                      })
                    }
                  />
                </div>
              )}
            </>
          )}
          {widget.type === "chart" && (
            <SelectInput
              label="Chati iliyohifadhiwa"
              value={widget.chart_id ? String(widget.chart_id) : ""}
              options={chartOptions}
              onChange={(event) =>
                patchWidget(widget.id, { chart_id: Number(event.target.value) })
              }
            />
          )}
          {widget.type === "filter" && (
            <div className="grid grid-cols-3 gap-3">
              <SelectInput
                label="Column"
                value={widget.column ?? ""}
                options={columnOptions}
                onChange={(event) => patchWidget(widget.id, { column: event.target.value })}
              />
              <SelectInput
                label="Operator"
                value={widget.operator ?? ">"}
                options={[
                  { value: "=", label: "=" },
                  { value: ">", label: ">" },
                  { value: "<", label: "<" },
                ]}
                onChange={(event) =>
                  patchWidget(widget.id, { operator: event.target.value as "=" | ">" | "<" })
                }
              />
              <TextInput
                label="Thamani"
                value={widget.value ?? ""}
                onChange={(event) => patchWidget(widget.id, { value: event.target.value })}
              />
            </div>
          )}
          {widget.type === "insight" && (
            <SelectInput
              label="Uchambuzi"
              value={widget.analysis_id ? String(widget.analysis_id) : ""}
              options={analysisOptions}
              onChange={(event) =>
                patchWidget(widget.id, { analysis_id: Number(event.target.value) })
              }
            />
          )}
          {widget.type === "text" && (
            <TextArea
              label="Maelezo"
              rows={2}
              value={widget.content ?? ""}
              onChange={(event) => patchWidget(widget.id, { content: event.target.value })}
            />
          )}
        </div>
      </div>
    );
  }

  function WidgetPreview({ widget }: { widget: DashboardWidget }) {
    const kpi = widget.type === "kpi" ? kpiForWidget(widget, analyses, columns) : null;
    const insight = widget.type === "insight" ? insightText(widget, analyses) : null;
    const chartRecord =
      widget.type === "chart"
        ? charts.find((record) => record.chart_id === widget.chart_id)
        : undefined;

    return (
      <div className="flex h-full flex-col gap-2">
        <p className="text-overline uppercase tracking-wide text-ink-muted">
          {widget.title || widget.type}
        </p>
        {widget.type === "kpi" && kpi && (
          <p className="tabular font-mono text-h2 text-ink">{formatKpi(kpi.value)}</p>
        )}
        {kpi?.label && (
          <p className="text-caption font-medium text-primary-800">{kpi.label}</p>
        )}
        {kpi?.note && <p className="text-caption text-ink-muted">{kpi.note}</p>}

        {widget.type === "chart" &&
          (chartRecord ? (
            <div className="mt-auto">
              <ChartView data={chartRecord.chart_data} height={180} format={chartRecord.config.format ?? null} />
            </div>
          ) : (
            <p className="text-caption text-warning-700">Hakuna chati iliyochaguliwa.</p>
          ))}

        {widget.type === "filter" && (
          <div className="mt-auto">
            <Badge tone="info" icon="filter">
              {widget.column ?? "column"} {widget.operator} {widget.value ?? "…"}
            </Badge>
            <p className="mt-2 text-caption text-ink-muted">
              Filter inaandikwa kwenye dashboard hii; haikokotoi takwimu mpya hapa.
            </p>
          </div>
        )}

        {widget.type === "insight" &&
          (insight ? (
            <p className="mt-auto rounded-md bg-surface-sunken px-3 py-2 text-body text-ink-secondary">
              {insight}
            </p>
          ) : (
            <p className="mt-auto text-caption text-warning-700">Chagua uchambuzi.</p>
          ))}

        {widget.type === "text" && (
          <p className="mt-auto text-body text-ink-secondary">{widget.content || "—"}</p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card
        title="Maktaba ya widgets"
        description="Chagua kipengele ili kuiongeza kwenye dashboard. Thamani zote zinatoka kwenye uchambuzi, chati na columns halisi."
        icon="layers"
      >
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {WIDGET_LIBRARY.map((item) => (
            <li key={item.type}>
              <button
                type="button"
                onClick={() => addWidget(item.type)}
                className="flex h-full w-full flex-col items-start gap-1 rounded-md border border-dashed border-surface-border-strong bg-surface-sunken px-3 py-3 text-left transition-colors hover:border-primary-300 hover:bg-primary-50/40"
              >
                <span className="flex h-7 w-7 items-center justify-center rounded-md bg-surface-panel text-primary-600 shadow-card">
                  <Icon name="plus" size={14} />
                </span>
                <span className="mt-1 text-body font-medium text-ink">{item.label}</span>
                <span className="text-caption text-ink-muted">{item.description}</span>
              </button>
            </li>
          ))}
        </ul>
      </Card>

      <Card
        title="Dashboard Builder"
        icon="dashboard"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" size="small" onClick={clearDraft} disabled={widgets.length === 0}>
              Wazi
            </Button>
          </div>
        }
        footer={
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <TextInput
                label="Jina la dashboard"
                placeholder="sales-overview"
                value={name}
                onChange={(event) => setName(event.target.value)}
                inputClassName="w-52"
              />
              <TextInput
                label="Kichwa"
                placeholder="Mauzo kwa mkoa"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                inputClassName="w-64"
              />
            </div>
            <Button
              icon="check"
              loading={saving}
              disabled={widgets.length === 0}
              onClick={saveDashboard}
            >
              {editing === null ? "Hifadhi dashboard" : "Sasisha dashboard"}
            </Button>
          </div>
        }
      >
        {widgets.length === 0 ? (
          <EmptyState
            title="Dashboard bado iko wazi"
            description="Kila dashboard inafungwa kwenye toleo la dataset (v{datasetVersion}) na hurejelea analyses na charts ulizohifadhi tayari."
            icon="dashboard"
          />
        ) : (
          <ul className="grid gap-4 md:grid-cols-2">
            {widgets.map((widget) => (
              <li
                key={widget.id}
                className="rounded-md border border-surface-border bg-surface-panel p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Badge tone="primary" icon={widget.type === "kpi" ? "target" : widget.type === "chart" ? "chart" : widget.type === "insight" ? "lightbulb" : widget.type === "filter" ? "filter" : "clipboard"}>
                    {widget.type}
                  </Badge>
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="small" icon="chevron-left" onClick={() => moveWidget(widget.id, -1)} aria-label="Sogeza juu" />
                    <Button variant="ghost" size="small" icon="chevron-right" onClick={() => moveWidget(widget.id, 1)} aria-label="Sogeza chini" />
                    <Button
                      variant="ghost"
                      size="small"
                      icon="sliders"
                      aria-pressed={configWidget === widget.id}
                      onClick={() => setConfigWidget(configWidget === widget.id ? null : widget.id)}
                    />
                    <Button
                      variant="ghost"
                      size="small"
                      icon="close"
                      aria-label="Futa widget"
                      onClick={() => setWidgets((previous) => previous.filter((item) => item.id !== widget.id))}
                    />
                  </div>
                </div>
                <div className="mt-3 min-h-[140px]">
                  <WidgetPreview widget={widget} />
                </div>
                {configWidget === widget.id && (
                  <div className="mt-3">
                    <WidgetEditor widget={widget} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Dashboards zilizohifadhiwa" description="Chagua dashboard ili kuihariri au kuangalia toleo lake." icon="history">
        {dashboards.length === 0 ? (
          <EmptyState
            title="Hakuna dashboard bado"
            description="Tengeneza dashboard yako ya kwanza na itaonekana hapa, imefungwa kwenye toleo la dataset."
            icon="dashboard"
          />
        ) : (
          <ul className="grid gap-3 lg:grid-cols-2">
            {dashboards.map((record) => (
              <li key={record.dashboard_id} className="flex items-center justify-between gap-3 rounded-md border border-surface-border p-3">
                <div className="min-w-0">
                  <p className="truncate text-body font-medium text-ink">{record.title || record.name}</p>
                  <p className="text-caption text-ink-muted">
                    <Badge tone="primary" icon="layers">
                      v{record.dataset_version}
                    </Badge>{" "}
                    · widgets {record.config?.widgets?.length ?? 0}
                  </p>
                </div>
                <Button variant="secondary" size="small" icon="table" onClick={() => loadDashboard(record)}>
                  Hariri
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

export default DashboardStudio;