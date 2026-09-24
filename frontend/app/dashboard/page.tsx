"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { Icon } from "@/components/Icon";
import { MetricCard } from "@/components/MetricCard";
import { QuickActions, QuickAction } from "@/components/QuickActions";
import { Skeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import {
  api,
  apiErrorMessage,
  DatasetSummary,
  statflowApi,
  UserProfile,
} from "@/lib/api";
import { completedStageCount, PIPELINE_STAGES } from "@/lib/pipeline";

function formatDate(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

interface DatasetActivity {
  analyses: number;
  charts: number;
  reports: number;
}

function StageDots({ done, total = 6 }: { done: number; total?: number }) {
  return (
    <span
      className="inline-flex items-center gap-1"
      role="img"
      aria-label={`Hatua ${done} kati ya ${total}`}
    >
      {Array.from({ length: total }).map((_, index) => (
        <span
          key={index}
          className={`h-1.5 w-3.5 rounded-full ${
            index < done ? "bg-primary-600" : "bg-neutral-200"
          }`}
        />
      ))}
    </span>
  );
}

export default function DashboardPage() {
  const { showToast } = useToast();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [activity, setActivity] = useState<Map<number, DatasetActivity>>(new Map());
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [me, list] = await Promise.all([api.auth.me(), api.datasets.list()]);
      setUser(me);
      setDatasets(list);

      const results = await Promise.allSettled(
        list.map(async (dataset) => {
          const [analyses, charts, reports] = await Promise.all([
            statflowApi.analysisRuns(dataset.id).then((runs) => runs.length),
            api.charts.listForDataset(dataset.id).then((chartsList) => chartsList.length),
            api.reports.listForDataset(dataset.id).then((reportsList) => reportsList.length),
          ]);
          return { id: dataset.id, analyses, charts, reports };
        })
      );
      const next = new Map<number, DatasetActivity>();
      for (const result of results) {
        if (result.status === "fulfilled") {
          next.set(result.value.id, {
            analyses: result.value.analyses,
            charts: result.value.charts,
            reports: result.value.reports,
          });
        }
      }
      setActivity(next);
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    load();
  }, [load]);

  const totalRows = datasets.reduce((sum, d) => sum + (d.row_count || 0), 0);
  const totalAnalyses = Array.from(activity.values()).reduce(
    (sum, a) => sum + a.analyses,
    0
  );
  const totalCharts = Array.from(activity.values()).reduce((sum, a) => sum + a.charts, 0);
  const totalReports = Array.from(activity.values()).reduce(
    (sum, a) => sum + a.reports,
    0
  );

  const firstName = user?.full_name?.trim().split(/\s+/)[0] ?? "";
  const latestDataset = datasets[0] ?? null;

  const quickActions: QuickAction[] = latestDataset
    ? [
        {
          icon: "upload",
          label: "Pakia data mpya",
          description: "Ongeza faili jipya la data",
          href: "/upload",
        },
        {
          icon: "clipboard",
          label: "Safisha data",
          description: `Fungua Data Studio la "${latestDataset.original_filename}"`,
          href: `/datasets/${latestDataset.id}/studio`,
        },
        {
          icon: "calculator",
          label: "Endesha uchambuzi",
          description: `Takwimu za "${latestDataset.original_filename}"`,
          href: `/datasets/${latestDataset.id}/statistics`,
        },
        {
          icon: "sparkles",
          label: "Msaidizi wa AI",
          description: "Uliza swali kwa lugha ya kawaida",
          href: `/datasets/${latestDataset.id}/ask`,
        },
      ]
    : [
        {
          icon: "upload",
          label: "Pakia data",
          description: "Anza kwa kupakia faili lako la kwanza",
          href: "/upload",
        },
        {
          icon: "database",
          label: "Angalia datasets",
          description: "Orodha na hali za data zako",
          href: "/datasets",
        },
        {
          icon: "sparkles",
          label: "Msaidizi wa AI",
          description: "Uliza swali kwa lugha ya kawaida",
          href: "/datasets",
        },
        {
          icon: "file-text",
          label: "Ripoti",
          description: "Tayarisha ripoti ya PDF au Excel",
          href: "/datasets",
        },
      ];

  return (
    <AppShell
      title={firstName ? `Karibu, ${firstName}` : "Dashboard"}
      description="Muhtasari wa shughuli zako na hatua zinazofuata."
      actions={
        <Link href="/upload">
          <Button>
            <Icon name="upload" size={16} />
            Pakia data mpya
          </Button>
        </Link>
      }
    >
      {/* Metrics */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          icon="database"
          tone="primary"
          label="Datasets"
          value={loading ? "…" : datasets.length}
          hint="Faili zilizopakiwa"
        />
        <MetricCard
          icon="layers"
          tone="info"
          label="Jumla ya safu"
          value={loading ? "…" : totalRows.toLocaleString()}
          hint="Rows katika datasets zote"
        />
        <MetricCard
          icon="calculator"
          tone="success"
          label="Uchambuzi"
          value={loading ? "…" : totalAnalyses + totalCharts}
          hint={`${totalAnalyses} takwimu · ${totalCharts} chati`}
        />
        <MetricCard
          icon="file-text"
          tone="warning"
          label="Ripoti"
          value={loading ? "…" : totalReports}
          hint="PDF / Excel zilizotengenezwa"
        />
      </div>

      {/* Quick actions */}
      <Card
        title="Vitendo vya haraka"
        description="Chagua hatua inayofuata kwenye mtiririko wa kazi."
      >
        <QuickActions actions={quickActions} />
      </Card>

      {/* Recent datasets */}
      <Card
        title="Datasets za hivi karibuni"
        description="Endelea na kazi uliyoiacha."
        actions={
          <Link href="/datasets">
            <Button variant="secondary" size="small">
              Ona zote
            </Button>
          </Link>
        }
      >
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-16 w-full" />
            ))}
          </div>
        ) : datasets.length === 0 ? (
          <EmptyState
            title="Hakuna dataset bado"
            description="Anza kwa kupakia faili lako la kwanza — mtiririko utakuongoza hatua kwa hatua."
            action={
              <Link href="/upload">
                <Button size="large">
                  <Icon name="upload" size={16} />
                  Pakia data
                </Button>
              </Link>
            }
          />
        ) : (
          <ul className="divide-y divide-neutral-100">
            {datasets.slice(0, 4).map((dataset) => {
              const itemActivity = activity.get(dataset.id);
              const done = completedStageCount({
                status: dataset.status,
                analysisRunCount: itemActivity?.analyses,
                chartCount: itemActivity?.charts,
                reportCount: itemActivity?.reports,
              });
              return (
                <li
                  key={dataset.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-3"
                >
                  <div className="flex min-w-[220px] items-center gap-3">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-600">
                      <Icon name="database" size={20} />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-body-lg text-neutral-900">
                        {dataset.original_filename}
                      </p>
                      <p className="text-caption text-neutral-600">
                        Safu {dataset.row_count.toLocaleString()} · Columns{" "}
                        {dataset.column_count} · {dataset.file_type.toUpperCase()} ·{" "}
                        {formatDate(dataset.uploaded_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="hidden flex-col items-end gap-1 sm:flex">
                      <span className="text-caption text-neutral-600">
                        Hatua {done}/6
                      </span>
                      <StageDots done={done} />
                    </span>
                    <Badge
                      tone={
                        dataset.status === "analyzed"
                          ? "success"
                          : dataset.status === "cleaned"
                            ? "info"
                            : "neutral"
                      }
                      withIcon
                    >
                      {dataset.status}
                    </Badge>
                    <Link href={`/datasets/${dataset.id}`}>
                      <Button size="small">Endelea</Button>
                    </Link>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      {/* Pipeline guide */}
      <Card
        title="Mtiririko wa kazi"
        description="Hatua 6 kutoka kwenye faili hadi ripoti — kila hatua inafungua ukurasa wake."
      >
        <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {PIPELINE_STAGES.map((stage) => {
            const href = latestDataset
              ? stage.hrefFor(latestDataset.id)
              : stage.step === 1
                ? "/upload"
                : "/datasets";
            return (
              <li key={stage.key}>
                <Link
                  href={href}
                  className="flex h-full flex-col rounded border border-neutral-200 p-4 transition-colors duration-200 hover:border-primary-300 hover:bg-primary-50/40"
                >
                  <span className="flex items-center gap-3">
                    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-600 text-body font-medium text-white">
                      {stage.step}
                    </span>
                    <span className="text-body-lg text-neutral-900">{stage.label}</span>
                    <span className="ml-auto text-neutral-300">
                      <Icon name="arrow-right" size={16} />
                    </span>
                  </span>
                  <p className="mt-2 text-caption text-neutral-600">
                    {stage.description}
                  </p>
                </Link>
              </li>
            );
          })}
        </ol>
      </Card>
    </AppShell>
  );
}