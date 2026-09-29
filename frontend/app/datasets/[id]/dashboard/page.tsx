"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/Button";
import { Skeleton } from "@/components/Skeleton";
import DashboardStudio from "@/components/DashboardStudio";
import { useToast } from "@/components/Toast";
import {
  AnalysisRunRecord,
  api,
  apiErrorMessage,
  ChartRecord,
  DashboardRecord,
  ExploreColumn,
  statflowApi,
} from "@/lib/api";

export default function DashboardPage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params?.id);
  const { showToast } = useToast();

  const [loading, setLoading] = useState(true);
  const [columns, setColumns] = useState<ExploreColumn[]>([]);
  const [datasetVersion, setDatasetVersion] = useState(1);
  const [analyses, setAnalyses] = useState<AnalysisRunRecord[]>([]);
  const [charts, setCharts] = useState<ChartRecord[]>([]);
  const [dashboards, setDashboards] = useState<DashboardRecord[]>([]);

  const loadDashboards = useCallback(async () => {
    try {
      setDashboards(await api.dashboards.listForDataset(datasetId));
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    }
  }, [datasetId, showToast]);

  useEffect(() => {
    async function load() {
      if (!Number.isFinite(datasetId)) return;
      setLoading(true);
      try {
        const [detail, explore, runs, savedCharts] = await Promise.all([
          api.datasets.get(datasetId),
          api.datasets.explore(datasetId),
          statflowApi.analysisRuns(datasetId),
          api.charts.listForDataset(datasetId),
        ]);
        setDatasetVersion(detail.dataset_version);
        setColumns(explore.columns);
        setAnalyses(runs.filter((run) => run.status === "completed"));
        setCharts(savedCharts);
        await loadDashboards();
      } catch (caught) {
        showToast(apiErrorMessage(caught), "danger");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [datasetId, loadDashboards, showToast]);

  const title = "Dashboard Builder";
  const description =
    "Tengeneza dashboard zinazofungwa kwenye toleo la dataset na kurejelea uchambuzi na chati halisi.";

  if (loading) {
    return (
      <AppShell title={title} description={description}>
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-96 w-full" />
      </AppShell>
    );
  }

  return (
    <AppShell
      title={title}
      description={description}
      actions={
        <>
          <Link href={`/datasets/${datasetId}/charts`}>
            <Button variant="secondary">
              Visualization Studio
            </Button>
          </Link>
          <Link href={`/datasets/${datasetId}/export`}>
            <Button variant="secondary">Pakua ripoti</Button>
          </Link>
        </>
      }
    >
      <DashboardStudio
        datasetId={datasetId}
        datasetVersion={datasetVersion}
        columns={columns}
        analyses={analyses}
        charts={charts}
        dashboards={dashboards}
        onSaved={() => {
          void loadDashboards();
        }}
      />
    </AppShell>
  );
}