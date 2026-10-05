"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { Icon } from "@/components/Icon";
import { Skeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import {
  AnalysisRunRecord,
  api,
  apiErrorMessage,
  ChartRecord,
  DashboardRecord,
  http,
  ReportRecord,
  statflowApi,
} from "@/lib/api";

const POLL_DELAY_MS = 1200;
const POLL_ATTEMPTS = 25;

/**
 * Composing a report and handing it over are different acts, so they are
 * different stages on one page rather than one stage that claims to do both.
 */
const EXPORT_SECTIONS = [
  {
    key: "report",
    label: "Ripoti",
    hint: "Chagua takwimu na chati, kisha tengeneza ripoti.",
  },
  {
    key: "export",
    label: "Workspace",
    hint: "Chagua (workspace) ya dataset hii: dashboards, ripoti na kushiriki.",
  },
] as const;

type ExportSection = (typeof EXPORT_SECTIONS)[number]["key"];

function isExportSection(value: string | null): value is ExportSection {
  return EXPORT_SECTIONS.some((entry) => entry.key === value);
}

export default function ExportPage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params?.id);
  const searchParams = useSearchParams();
  const { showToast } = useToast();

  const requested = searchParams.get("stage");
  const [section, setSection] = useState<ExportSection>(
    isExportSection(requested) ? requested : "report"
  );

  useEffect(() => {
    if (isExportSection(requested)) setSection(requested);
  }, [requested]);

  const [analyses, setAnalyses] = useState<AnalysisRunRecord[]>([]);
  const [charts, setCharts] = useState<ChartRecord[]>([]);
  const [reports, setReports] = useState<ReportRecord[]>([]);
  const [dashboards, setDashboards] = useState<DashboardRecord[]>([]);
  const [datasetVersion, setDatasetVersion] = useState<number | null>(null);
  const [selectedAnalyses, setSelectedAnalyses] = useState<number[]>([]);
  const [selectedCharts, setSelectedCharts] = useState<number[]>([]);
  const [format, setFormat] = useState<"pdf" | "xlsx">("pdf");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (!Number.isFinite(datasetId)) return;
    setLoading(true);
    try {
      const [datasetDetail, analysisList, chartList, reportList, dashboardList] =
        await Promise.all([
          api.datasets.get(datasetId),
          statflowApi.analysisRuns(datasetId),
          api.charts.listForDataset(datasetId),
          api.reports.listForDataset(datasetId),
          api.dashboards.listForDataset(datasetId),
        ]);
      const currentVersion = datasetDetail.dataset_version;
      const versionAnalyses = analysisList.filter(
        (item) => item.dataset_version === currentVersion
      );
      const versionCharts = chartList.filter(
        (item) => item.dataset_version === currentVersion
      );
      setDatasetVersion(currentVersion);
      setAnalyses(versionAnalyses);
      setCharts(versionCharts);
      setReports(reportList);
      setDashboards(dashboardList);
      setSelectedAnalyses(versionAnalyses.map((item) => item.analysis_id));
      setSelectedCharts(versionCharts.map((item) => item.chart_id));
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setLoading(false);
    }
  }, [datasetId, showToast]);

  useEffect(() => {
    load();
  }, [load]);

  function toggle(list: number[], id: number): number[] {
    return list.includes(id) ? list.filter((item) => item !== id) : [...list, id];
  }

  const canGenerate =
    !loading && !generating && (selectedAnalyses.length > 0 || selectedCharts.length > 0);

  async function waitForReport(
    reportId: number,
    attempt = 0,
    onProgress?: (percent: number) => void
  ): Promise<string> {
    onProgress?.(Math.min(92, Math.round(((attempt + 1) / POLL_ATTEMPTS) * 100)));
    const status = await api.reports.status(reportId);
    if (status.status !== "processing") {
      onProgress?.(100);
      return status.status;
    }
    if (attempt >= POLL_ATTEMPTS) return "timeout";
    await new Promise((resolve) => setTimeout(resolve, POLL_DELAY_MS));
    return waitForReport(reportId, attempt + 1, onProgress);
  }

  async function generateReport() {
    setGenerating(true);
    setProgress(0);
    try {
      const created = await api.reports.create(datasetId, {
        format,
        dataset_version: datasetVersion ?? undefined,
        include_analysis_ids: selectedAnalyses,
        include_chart_ids: selectedCharts,
      });
      showToast("Ripoti inaandaliwa…", "info");
      const finalStatus = await waitForReport(created.report_id, 0, setProgress);
      await load();
      setProgress(null);
      if (finalStatus === "completed") {
        showToast("Ripoti imekamilika", "success");
        await downloadReport(created.report_id, format);
      } else if (finalStatus === "failed") {
        showToast("Ripoti imeshindikana kuandaliwa", "danger");
      } else {
        showToast("Ripoti bado inaandaliwa. Jaribu kupakua baadaye.", "warning");
      }
    } catch (caught) {
      setProgress(null);
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setGenerating(false);
    }
  }

  async function downloadReport(reportId: number, fileFormat: string) {
    try {
      // The download endpoint needs the JWT, so fetch it as a blob first.
      const response = await http.get(`/reports/${reportId}/download`, {
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = `data_analysis_report_${reportId}.${fileFormat}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }

  return (
    <AppShell
      eyebrow="Ripoti na ushirikishaji"
      title="Reports & Workspace"
      description="Panga ripoti kutoka matokeo uliyochagua, kisha pakua au isambaze."
      actions={
        <>
          <Link href={`/datasets/${datasetId}/analyze`}>
            <Button variant="secondary" icon="calculator">
              Chambua zaidi
            </Button>
          </Link>
          <Link href={`/datasets/${datasetId}/charts`}>
            <Button variant="secondary" icon="chart">
              Chora chati
            </Button>
          </Link>
        </>
      }
    >
      <div className="mb-6">
        <div
          className="inline-flex flex-wrap gap-0.5 rounded-[7px] border border-surface-border bg-surface-sunken p-0.5"
          role="tablist"
          aria-label="Hatua za ripoti"
        >
          {EXPORT_SECTIONS.map((entry) => (
            <Link
              key={entry.key}
              href={`/datasets/${datasetId}/export?stage=${entry.key}`}
              role="tab"
              aria-selected={section === entry.key}
              className={`rounded-[5px] px-3.5 py-1.5 text-body transition-all duration-150 ease-standard focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500 ${
                section === entry.key
                  ? "bg-surface-panel font-semibold text-ink shadow-card"
                  : "font-medium text-ink-muted hover:bg-surface-panel hover:text-ink"
              }`}
            >
              {entry.label}
            </Link>
          ))}
        </div>
        <p className="mt-2 text-caption text-ink-muted">
          {EXPORT_SECTIONS.find((entry) => entry.key === section)?.hint}
        </p>
      </div>

      {section === "report" && (
      <div className="grid gap-4 lg:grid-cols-3">
        <Card
          title="Chagua maudhui ya ripoti"
          description={`Ripoti itatengenezwa kutoka toleo la data v${datasetVersion ?? "—"} ili matokeo yaweze kufuatilia data iliyotumika.`}
          icon="clipboard"
          className="lg:col-span-2"
        >
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-md border border-surface-border p-4">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-h4 font-semibold text-ink">Takwimu (analyses)</h3>
                {analyses.length > 0 && (
                  <Button
                    variant="ghost"
                    size="small"
                    onClick={() =>
                      setSelectedAnalyses(
                        selectedAnalyses.length === analyses.length ? [] : analyses.map((a) => a.analysis_id)
                      )
                    }
                  >
                    {selectedAnalyses.length === analyses.length
                      ? "Ondoa zote"
                      : "Chagua zote"}
                  </Button>
                )}
              </div>
              {analyses.length === 0 ? (
                <p className="mt-2 text-body text-ink-secondary">
                  Hakuna matokeo ya uchambuzi bado.{" "}
                  <Link
                    href={`/datasets/${datasetId}/statistics`}
                    className="font-medium text-primary-700 underline underline-offset-2 hover:text-primary-800"
                  >
                    Endesha uchambuzi
                  </Link>{" "}
                  kwanza.
                </p>
              ) : (
                <ul className="mt-2 space-y-1">
                  {analyses.map((analysis) => (
                    <li key={analysis.analysis_id}>
                      <label className="flex min-h-[44px] cursor-pointer items-center gap-2.5 rounded px-1 text-body text-ink transition-colors duration-150 hover:bg-surface-sunken">
                        <input
                          type="checkbox"
                          className="size-4 shrink-0 rounded border-surface-border-strong text-primary-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500"
                          checked={selectedAnalyses.includes(analysis.analysis_id)}
                          onChange={() =>
                            setSelectedAnalyses((previous) =>
                              toggle(previous, analysis.analysis_id)
                            )
                          }
                        />
                        <span className="font-medium">{analysis.analysis_type}</span>
                        <span className="ml-auto text-caption text-ink-muted">
                          {analysis.created_at
                            ? new Date(analysis.created_at).toLocaleString()
                            : ""}
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="rounded-md border border-surface-border p-4">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-h4 font-semibold text-ink">Chati (charts)</h3>
                {charts.length > 0 && (
                  <Button
                    variant="ghost"
                    size="small"
                    onClick={() =>
                      setSelectedCharts(
                        selectedCharts.length === charts.length ? [] : charts.map((c) => c.chart_id)
                      )
                    }
                  >
                    {selectedCharts.length === charts.length
                      ? "Ondoa zote"
                      : "Chagua zote"}
                  </Button>
                )}
              </div>
              {charts.length === 0 ? (
                <p className="mt-2 text-body text-ink-secondary">
                  Hakuna chati bado.{" "}
                  <Link
                    href={`/datasets/${datasetId}/charts`}
                    className="font-medium text-primary-700 underline underline-offset-2 hover:text-primary-800"
                  >
                    Tengeneza chati
                  </Link>{" "}
                  kwenye ukurasa wa chati.
                </p>
              ) : (
                <ul className="mt-2 space-y-1">
                  {charts.map((chart) => (
                    <li key={chart.chart_id}>
                      <label className="flex min-h-[44px] cursor-pointer items-center gap-2.5 rounded px-1 text-body text-ink transition-colors duration-150 hover:bg-surface-sunken">
                        <input
                          type="checkbox"
                          className="size-4 shrink-0 rounded border-surface-border-strong text-primary-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500"
                          checked={selectedCharts.includes(chart.chart_id)}
                          onChange={() =>
                            setSelectedCharts((previous) => toggle(previous, chart.chart_id))
                          }
                        />
                        <span>
                          <span className="font-medium">{chart.chart_type}</span>{" "}
                          <span className="text-ink-secondary">
                            {chart.config.x}
                            {chart.config.y ? ` vs ${chart.config.y}` : ""}
                          </span>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        <fieldset className="mt-5">
          <legend className="text-body font-medium text-ink">Muundo wa faili</legend>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {(
              [
                {
                  value: "pdf" as const,
                  label: "PDF",
                  hint: "Ripoti ya kusoma na kuprint, yenye muhtasari na chati.",
                },
                {
                  value: "xlsx" as const,
                  label: "Excel (.xlsx)",
                  hint: "Data kamili ya kila jedwali kwa uchambuzi zaidi.",
                },
              ]
            ).map((option) => (
              <label
                key={option.value}
                className={`flex cursor-pointer items-start gap-2.5 rounded-md border p-3 transition-colors duration-150 ${
                  format === option.value
                    ? "border-primary-500 bg-primary-50"
                    : "border-surface-border bg-surface-panel hover:bg-surface-sunken"
                }`}
              >
                <input
                  type="radio"
                  name="format"
                  className="mt-0.5 size-4 shrink-0 border-surface-border-strong text-primary-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500"
                  checked={format === option.value}
                  onChange={() => setFormat(option.value)}
                />
                <span>
                  <span className="block text-body font-medium text-ink">{option.label}</span>
                  <span className="block text-caption text-ink-muted">{option.hint}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-surface-border pt-4">
          <Button
            size="large"
            loading={generating}
            disabled={!canGenerate}
            onClick={generateReport}
          >
            Tengeneza na pakua ripoti
          </Button>
          <p className="text-caption text-ink-muted">
            {selectedAnalyses.length} takwimu · {selectedCharts.length} chati · toleo{" "}
            <span className="font-mono font-medium text-ink">v{datasetVersion ?? "—"}</span>
          </p>
        </div>

        {progress !== null && (
          <div
            role="status"
            aria-live="polite"
            className="mt-4 rounded-md border border-info/30 bg-info-bg p-3"
          >
            <div className="flex items-center gap-2 text-body font-medium text-ink">
              <span className="spinner size-4 shrink-0 rounded-full border-2 border-primary-200 border-t-primary-600" />
              Ripoti inaandaliwa…
            </div>
            <div
              className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-primary-100"
              role="progressbar"
              aria-valuenow={progress}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Maendeleo ya kutengeneza ripoti"
            >
              <div
                className="h-full rounded-full bg-primary-600 transition-[width] duration-300 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="mt-1.5 text-caption text-ink-secondary">
              Hali: inaunganisha takwimu na chati ulizochagua. Unaweza kurudi tena kupakua
              ripoti baadaye.
            </p>
          </div>
        )}
      </Card>

        <div className="flex flex-col gap-4">
          <Card title="Report outline" icon="clipboard">
            <ul className="space-y-1.5 text-body text-ink-secondary">
              <li>Executive Summary — Key finding · Recommendations</li>
              <li>Methodology — Sample &amp; variables · Model specification</li>
              <li>Results — Coefficients · Diagnostics</li>
              <li>Appendix</li>
            </ul>
          </Card>
          <Card title="Workspace" icon="users">
            <ul className="space-y-1.5 text-body text-ink-secondary">
              <li>Notifications — ON</li>
              <li>Comment access — TEAM</li>
              <li>Version locking — ON</li>
            </ul>
          </Card>
        </div>
      </div>
      )}

      <Card
        title="Ripoti zilizotengenezwa"
        description="Ripoti zote za dataset hii unaweza kuzipakua tena."
        icon="file-text"
      >
        {reports.length === 0 ? (
          <EmptyState
            title="Hakuna ripoti bado"
            description="Ripoti zitaonekana hapa baada ya kutengeneza moja kwa juu."
          />
        ) : (
          <ul className="flex flex-col gap-2">
            {reports.map((report) => (
              <li
                key={report.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-surface-border px-3 py-2.5 transition-colors duration-150 ease-standard hover:border-primary-200 hover:bg-primary-50/40"
              >
                <div className="flex min-w-0 items-center gap-3">
                  {/*
                    A format-coloured tile stands in for the prototype's report
                    cover. Reports carry no title in the API, so the tile shows
                    the format -- which is the one thing that reliably
                    distinguishes one from another in this list.
                  */}
                  <span
                    aria-hidden="true"
                    className={`grid h-11 w-9 shrink-0 place-items-center rounded-md text-[10px] font-bold tracking-wide text-white ${
                      report.file_format.toLowerCase() === "xlsx"
                        ? "bg-[#1D7044]"
                        : "bg-[#C0392B]"
                    }`}
                  >
                    {report.file_format.toUpperCase()}
                  </span>
                  <div className="min-w-0">
                    <p className="text-body font-medium text-ink">
                      Ripoti #{report.id}
                    </p>
                    <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-caption text-ink-muted">
                      <span className="tabular">
                        v{report.dataset_version ?? 1}
                      </span>
                      <span aria-hidden="true">·</span>
                      <span>
                        {report.created_at
                          ? new Date(report.created_at).toLocaleString()
                          : "—"}
                      </span>
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Badge
                    tone={
                      report.status === "completed"
                        ? "success"
                        : report.status === "failed"
                          ? "danger"
                          : "warning"
                    }
                  >
                    {report.status}
                  </Badge>
                  <Button
                    variant="secondary"
                    size="small"
                    icon="download"
                    disabled={report.status !== "completed"}
                    onClick={() => downloadReport(report.id, report.file_format)}
                  >
                    Pakua
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {section === "export" && (
        <>
          <Card
            title="Workspace ya dataset hii"
            description="Dashboards na ripoti zote za dataset hii — kila artifact imefungwa kwenye toleo la data lililotumiwa."
            icon="folder"
          >
            {dashboards.length === 0 && reports.length === 0 ? (
              <EmptyState
                title="Workspace bado iko wazi"
                description="Tengeneza dashboard au ripoti kwanza; utazipata zikiorodheshwa hapa kama workspace ya project."
                icon="folder"
              />
            ) : (
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="rounded-md border border-surface-border p-4">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="flex items-center gap-1.5 text-h4 font-semibold text-ink">
                      <Icon name="dashboard" size={16} />
                      Dashboards
                    </h3>
                    <Link href={`/datasets/${datasetId}/dashboard`}>
                      <Button variant="ghost" size="small" icon="plus">
                        Mpya
                      </Button>
                    </Link>
                  </div>
                  {dashboards.length === 0 ? (
                    <p className="mt-2 text-body text-ink-secondary">
                      Hakuna dashboard bado.{" "}
                      <Link
                        href={`/datasets/${datasetId}/dashboard`}
                        className="font-medium text-primary-700 underline underline-offset-2 hover:text-primary-800"
                      >
                        Tengeneza dashboard
                      </Link>
                    </p>
                  ) : (
                    <ul className="mt-2 divide-y divide-surface-border">
                      {dashboards.map((dashboard) => (
                        <li
                          key={dashboard.dashboard_id}
                          className="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-0 last:pb-0"
                        >
                          <span className="flex flex-wrap items-center gap-3">
                            <span className="text-body font-medium text-ink">
                              {dashboard.title || dashboard.name}
                            </span>
                            <Badge tone="primary">
                              <span className="font-mono">
                                v{dashboard.dataset_version}
                              </span>
                            </Badge>
                            <span className="text-caption text-ink-muted">
                              widgets {dashboard.config?.widgets?.length ?? 0}
                            </span>
                          </span>
                          <Link href={`/datasets/${datasetId}/dashboard`}>
                            <Button variant="secondary" size="small" icon="table">
                              Fungua
                            </Button>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="rounded-md border border-surface-border p-4">
                  <h3 className="flex items-center gap-1.5 text-h4 font-semibold text-ink">
                    <Icon name="file-text" size={16} />
                    Ripoti zilizotengenezwa
                  </h3>
                  {reports.length === 0 ? (
                    <p className="mt-2 text-body text-ink-secondary">
                      Hakuna ripoti bado.
                    </p>
                  ) : (
                    <ul className="mt-2 divide-y divide-surface-border">
                      {reports.map((report) => (
                        <li
                          key={report.id}
                          className="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-0 last:pb-0"
                        >
                          <span className="flex flex-wrap items-center gap-3">
                            <Badge
                              tone={
                                report.status === "completed"
                                  ? "success"
                                  : report.status === "failed"
                                    ? "danger"
                                    : "warning"
                              }
                            >
                              {report.status}
                            </Badge>
                            <span className="text-body font-medium text-ink">
                              {report.file_format.toUpperCase()}
                            </span>
                            <span className="text-caption text-ink-muted">
                              {report.created_at
                                ? new Date(report.created_at).toLocaleString()
                                : ""}
                            </span>
                          </span>
                          <Button
                            variant="secondary"
                            size="small"
                            icon="download"
                            disabled={report.status !== "completed"}
                            onClick={() => downloadReport(report.id, report.file_format)}
                          >
                            Pakua
                          </Button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            )}
          </Card>

          <Card
            title="Hamisha kwa mtu mwingine"
            icon="users"
            description="Ripoti inaweza kukopishwa, lakini mtu anayepokea atahitaji akaunti ya StatFlow na ruhusa ya dataset."
          >
          <div className="space-y-4">
            <div>
              <p className="text-body font-medium text-ink">Hatua za kushiriki</p>
              <ol className="mt-2 space-y-2">
                {[
                  "Tengeneza ripoti kwanza ukitaka kuwa na kitu cha kusambaza.",
                  "Msaidie mtumiaji apate ruhusa ya kuona dataset (jumla ya role ya organization).",
                  "Mtu huyo anaweza kupakua ripoti hiyo kutoka akaunti yake mwenyewe.",
                ].map((line, index) => (
                  <li key={line} className="flex items-start gap-2 text-body text-ink-secondary">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-sunken text-caption text-ink-secondary">
                      {index + 1}
                    </span>
                    {line}
                  </li>
                ))}
              </ol>
            </div>

            <div className="rounded-md border border-surface-border bg-surface-sunken px-3.5 py-3">
              <p className="flex items-start gap-2 text-body text-ink-secondary">
                <Icon name="info" size={16} className="mt-0.5 shrink-0 text-ink-muted" />
                <span>
                  Kiungo cha kushiriki kwa moja kwa moja bado haujatengenezwa. Kipendekezo
                  ni link yenye muda wa ukomoja (expiring link) iliyotengenezwa na
                  msimamizi wa dataset, ili isambele bila kupa kila mtu ruhusa ya
                  kuona data nzima.
                </span>
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="secondary"
                icon="copy"
                disabled={reports.length === 0}
                onClick={() => {
                  const origin = window.location.origin;
                  void navigator.clipboard?.writeText(
                    `${origin}/datasets/${datasetId}/export`
                  );
                }}
              >
                Nakili kiungo cha dataset
              </Button>
              <Link href={`/organizations`}>
                <Button variant="ghost" icon="users">
                  Simamia washiriki
                </Button>
              </Link>
            </div>
          </div>
        </Card>
        </>
      )}

      <p className="text-caption text-ink-muted">
        Kila artifact kwenye Workspace imefungwa kwenye toleo la dataset lililotumiwa.
        Hatua ya Ripoti haiandishi rekodi; matokeo ya uchambuzi ndiyo yanayorekodiwa.
      </p>
    </AppShell>
  );
}
