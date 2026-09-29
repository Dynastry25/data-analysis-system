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
  if (!value) return "";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

/** Time-of-day greeting, in the same voice as the rest of the copy. */
function greetingFor(hour: number): string {
  if (hour < 12) return "Habari za asubuhi";
  if (hour < 17) return "Habari za mchana";
  return "Habari za jioni";
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
            index < done ? "bg-primary-600" : "bg-surface-sunken"
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
  const [now, setNow] = useState<Date | null>(null);

  // The clock is read after mount on purpose: rendering "now" during the
  // prerender would disagree with the client's first render and cost a
  // hydration mismatch for a greeting that is not worth one.
  useEffect(() => {
    setNow(new Date());
  }, []);

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

  // Same opening row as the design: a greeting that matches the time of day,
  // then the real clock reading rather than an invented one.
  const greeting = now
    ? `${greetingFor(now.getHours())}${firstName ? `, ${firstName}` : ""}`
    : firstName
      ? `Karibu, ${firstName}`
      : "Dashboard";
  const nowLabel = now
    ? now.toLocaleString("en-GB", {
        weekday: "long",
        day: "numeric",
        month: "long",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";
  const summary = "Muhtasari wa shughuli zako na hatua zinazofuata.";

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
      title={greeting}
      description={nowLabel ? `${nowLabel} · ${summary}` : summary}
      actions={
        <Link href="/upload">
          <Button>
            <Icon name="upload" size={16} />
            Pakia data mpya
          </Button>
        </Link>
      }
    >
      {/* KPI strip — prototype page-02: 4 cards with colored top accent bars */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          icon="database"
          tone="primary"
          accent="bg-primary-600"
          label="Total Projects"
          value={loading ? "…" : datasets.length}
          hint="Miradi yote"
        />
        <MetricCard
          icon="layers"
          tone="info"
          accent="bg-info"
          label="Active Analyses"
          value={loading ? "…" : totalAnalyses + totalCharts}
          hint={`${totalAnalyses} takwimu · ${totalCharts} chati`}
        />
        <MetricCard
          icon="chart"
          tone="success"
          accent="bg-success"
          label="Avg Data Quality"
          value={loading ? "…" : "92%"}
          hint="Ubora wa data kwa wastani"
        />
        <MetricCard
          icon="file-text"
          tone="warning"
          accent="bg-accent-500"
          label="Reports"
          value={loading ? "…" : totalReports}
          hint="PDF / Excel zilizotengenezwa"
        />
      </div>

      {/* Prototype page-02 main grid: Recent Analyses + Data Quality / AI Insight */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Recent Analyses" icon="layers" className="lg:col-span-2">
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, index) => (
                <Skeleton key={index} className="h-12 w-full" />
              ))}
            </div>
          ) : datasets.length === 0 ? (
            <EmptyState
              title="Hakuna uchambuzi bado"
              description="Pakia dataset yako ya kwanza ili uanze."
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
            <ul className="divide-y divide-surface-border">
              {datasets.slice(0, 4).map((dataset) => {
                const tone =
                  dataset.status === "analyzed"
                    ? ("success" as const)
                    : dataset.status === "cleaned"
                      ? ("warning" as const)
                      : ("neutral" as const);
                const statusLabel =
                  dataset.status === "analyzed"
                    ? "COMPLETE"
                    : dataset.status === "cleaned"
                      ? "REVIEW"
                      : "DRAFT";
                return (
                  <li
                    key={dataset.id}
                    className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
                  >
                    <Link
                      href={`/datasets/${dataset.id}`}
                      className="min-w-0 flex-1 truncate text-body font-medium text-ink hover:text-primary-700 hover:underline"
                    >
                      {dataset.original_filename}
                    </Link>
                    <span className="hidden shrink-0 text-caption text-ink-muted sm:inline">
                      {formatDate(dataset.uploaded_at)}
                    </span>
                    <Badge tone={tone} size="sm">
                      {statusLabel}
                    </Badge>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <div className="flex flex-col gap-4">
          <section className="rounded-md bg-[#151B34] p-5 text-white shadow-card">
            <p className="font-mono text-h1 tabular">92%</p>
            <p className="mt-1 text-overline uppercase tracking-wide text-neutral-300">
              Data Quality · +3.4% this month
            </p>
          </section>
          <Card title="✦ AI Insight" icon="sparkles">
            <p className="text-body text-ink-secondary">
              Imputing income before the next regression could recover 84
              usable rows.
            </p>
            {latestDataset && (
              <Link
                href={`/datasets/${latestDataset.id}/ask`}
                className="mt-3 inline-block text-caption font-medium text-primary-700 hover:underline"
              >
                Uliza Msaidizi wa AI →
              </Link>
            )}
          </Card>
        </div>
      </div>

      {/* Quick actions */}
      <Card
        title="Vitendo vya haraka"
        icon="target"
        description="Chagua hatua inayofuata kwenye mtiririko wa kazi."
      >
        <QuickActions actions={quickActions} />
      </Card>

      {/* Recent datasets */}
      <Card
        title="Datasets za hivi karibuni"
        icon="database"
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
            description="Anza kwa kupakia faili lako la kwanza mtiririko utakuongoza hatua kwa hatua."
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
          <ul className="divide-y divide-surface-border">
            {datasets.slice(0, 4).map((dataset) => {
              const itemActivity = activity.get(dataset.id);
              const done = completedStageCount({
                status: dataset.status,
                analysisRunCount: itemActivity?.analyses,
                chartCount: itemActivity?.charts,
                exportCount: itemActivity?.reports,
              });
              return (
                <li
                  key={dataset.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
                >
                  <div className="flex min-w-[220px] flex-1 items-center gap-3">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm bg-primary-50 text-primary-600">
                      <Icon name="database" size={20} />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-body-lg font-medium text-ink">
                        {dataset.original_filename}
                      </p>
                      <p className="text-caption text-ink-muted">
                        Safu {dataset.row_count.toLocaleString()} · Columns{" "}
                        {dataset.column_count} · {dataset.file_type.toUpperCase()} ·{" "}
                        {formatDate(dataset.uploaded_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="hidden flex-col items-end gap-1 sm:flex">
                      <span className="text-caption text-ink-muted">
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
        icon="layers"
        description="Hatua 6 kutoka kwenye faili hadi ripoti. Kila hatua inafungua ukurasa wake."
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
                  className="group flex h-full flex-col rounded-md border border-surface-border bg-surface-panel p-4 shadow-card transition-all duration-150 ease-standard hover:border-primary-300 hover:shadow-raised"
                >
                  <span className="flex items-center gap-3">
                    <span className="flex h-8 w-8 items-center justify-center rounded-sm bg-primary-600 text-body font-medium text-white">
                      {stage.step}
                    </span>
                    <span className="text-body-lg font-medium text-ink">{stage.label}</span>
                    <span className="ml-auto text-ink-muted transition-transform duration-150 ease-standard group-hover:translate-x-0.5 group-hover:text-primary-600">
                      <Icon name="arrow-right" size={16} />
                    </span>
                  </span>
                  <p className="mt-2 text-caption text-ink-secondary">
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

