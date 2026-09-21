"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { Skeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import {
  AnalysisRecord,
  api,
  apiErrorMessage,
  ChartRecord,
  http,
  ReportRecord,
} from "@/lib/api";

const POLL_DELAY_MS = 1200;
const POLL_ATTEMPTS = 25;

export default function ExportPage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params?.id);
  const { showToast } = useToast();

  const [analyses, setAnalyses] = useState<AnalysisRecord[]>([]);
  const [charts, setCharts] = useState<ChartRecord[]>([]);
  const [reports, setReports] = useState<ReportRecord[]>([]);
  const [selectedAnalyses, setSelectedAnalyses] = useState<number[]>([]);
  const [selectedCharts, setSelectedCharts] = useState<number[]>([]);
  const [format, setFormat] = useState<"pdf" | "xlsx">("pdf");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  const load = useCallback(async () => {
    if (!Number.isFinite(datasetId)) return;
    setLoading(true);
    try {
      const [analysisList, chartList, reportList] = await Promise.all([
        api.analysis.listForDataset(datasetId),
        api.charts.listForDataset(datasetId),
        api.reports.listForDataset(datasetId),
      ]);
      setAnalyses(analysisList);
      setCharts(chartList);
      setReports(reportList);
      // Everything is selected by default — the common case is "give me it all".
      setSelectedAnalyses(analysisList.map((item) => item.analysis_id));
      setSelectedCharts(chartList.map((item) => item.chart_id));
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

  async function waitForReport(reportId: number, attempt = 0): Promise<string> {
    const status = await api.reports.status(reportId);
    if (status.status !== "processing") return status.status;
    if (attempt >= POLL_ATTEMPTS) return "timeout";
    await new Promise((resolve) => setTimeout(resolve, POLL_DELAY_MS));
    return waitForReport(reportId, attempt + 1);
  }

  async function generateReport() {
    setGenerating(true);
    try {
      const created = await api.reports.create(datasetId, {
        format,
        include_analysis_ids: selectedAnalyses,
        include_chart_ids: selectedCharts,
      });
      showToast("Ripoti inaandaliwa…", "info");
      const finalStatus = await waitForReport(created.report_id);
      await load();
      if (finalStatus === "completed") {
        showToast("Ripoti imekamilika", "success");
        await downloadReport(created.report_id, format);
      } else if (finalStatus === "failed") {
        showToast("Ripoti imeshindikana kuandaliwa", "danger");
      } else {
        showToast("Ripoti bado inaandaliwa. Jaribu kupakua baadaye.", "warning");
      }
    } catch (caught) {
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
      title="Pakua ripoti"
      description="Chagua takwimu na chati za kujumuisha, kisha pakua PDF au Excel."
      actions={
        <>
          <Link href={`/datasets/${datasetId}/analyze`}>
            <Button variant="secondary">Chambua zaidi</Button>
          </Link>
          <Link href={`/datasets/${datasetId}/charts`}>
            <Button variant="secondary">Chora chati</Button>
          </Link>
        </>
      }
    >
      <Card
        title="Chagua maudhui ya ripoti"
        description="Cheki takwimu na chati unazotaka ziwe ndani ya ripoti."
      >
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded border border-neutral-200 p-4">
              <p className="text-h3 text-neutral-900">Takwimu (analyses)</p>
              {analyses.length === 0 ? (
                <p className="mt-2 text-body text-neutral-600">
                  Hakuna matokeo ya uchambuzi bado. Endesha uchambuzi kwanza.
                </p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {analyses.map((analysis) => (
                    <li key={analysis.analysis_id}>
                      <label className="flex min-h-[44px] items-center gap-2 text-body">
                        <input
                          type="checkbox"
                          checked={selectedAnalyses.includes(analysis.analysis_id)}
                          onChange={() =>
                            setSelectedAnalyses((previous) =>
                              toggle(previous, analysis.analysis_id)
                            )
                          }
                        />
                        <span>{analysis.analysis_type}</span>
                        <span className="text-caption text-neutral-600">
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

            <div className="rounded border border-neutral-200 p-4">
              <p className="text-h3 text-neutral-900">Chati (charts)</p>
              {charts.length === 0 ? (
                <p className="mt-2 text-body text-neutral-600">
                  Hakuna chati bado. Tengeneza chati kwenye ukurasa wa chati.
                </p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {charts.map((chart) => (
                    <li key={chart.chart_id}>
                      <label className="flex min-h-[44px] items-center gap-2 text-body">
                        <input
                          type="checkbox"
                          checked={selectedCharts.includes(chart.chart_id)}
                          onChange={() =>
                            setSelectedCharts((previous) =>
                              toggle(previous, chart.chart_id)
                            )
                          }
                        />
                        <span>
                          {chart.chart_type} — {chart.config.x}
                          {chart.config.y ? ` vs ${chart.config.y}` : ""}
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        <fieldset className="mt-4">
          <legend className="text-body text-neutral-900">Muundo wa faili</legend>
          <div className="mt-2 flex flex-wrap gap-4">
            <label className="flex min-h-[44px] items-center gap-2 text-body">
              <input
                type="radio"
                name="format"
                checked={format === "pdf"}
                onChange={() => setFormat("pdf")}
              />
              PDF (ripoti ya kusoma/kuprint)
            </label>
            <label className="flex min-h-[44px] items-center gap-2 text-body">
              <input
                type="radio"
                name="format"
                checked={format === "xlsx"}
                onChange={() => setFormat("xlsx")}
              />
              Excel (data kamili ya kila jedwali)
            </label>
          </div>
        </fieldset>

        <Button
          className="mt-4"
          size="large"
          loading={generating}
          onClick={generateReport}
        >
          Tengeneza na pakua ripoti
        </Button>
      </Card>

      <Card
        title="Ripoti zilizotengenezwa"
        description="Ripoti zote za dataset hii — unaweza kuzipakua tena."
      >
        {reports.length === 0 ? (
          <EmptyState title="Hakuna ripoti bado" />
        ) : (
          <ul className="space-y-2">
            {reports.map((report) => (
              <li
                key={report.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded border border-neutral-200 px-3 py-2"
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
                    withIcon
                  >
                    {report.status}
                  </Badge>
                  <span className="text-body text-neutral-900">
                    {report.file_format.toUpperCase()}
                  </span>
                  <span className="text-caption text-neutral-600">
                    {report.created_at
                      ? new Date(report.created_at).toLocaleString()
                      : ""}
                  </span>
                </span>
                <Button
                  variant="secondary"
                  size="small"
                  disabled={report.status !== "completed"}
                  onClick={() => downloadReport(report.id, report.file_format)}
                >
                  Pakua
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

    </AppShell>
  );
}
