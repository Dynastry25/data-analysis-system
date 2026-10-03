"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ActivityChart } from "@/components/ActivityChart";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { Icon } from "@/components/Icon";
import { MetricCard } from "@/components/MetricCard";
import { QualityPanel } from "@/components/QualityPanel";
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
  /** created_at of each analysis run, used to bucket the activity chart. */
  dates: string[];
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
            statflowApi
              .analysisRuns(dataset.id)
              .then((runs) => ({
                count: runs.length,
                // Keep the timestamps so the activity chart can bucket real runs
                // by week instead of plotting an invented trend.
                dates: runs
                  .map((run) => run.created_at)
                  .filter((value): value is string => Boolean(value)),
              })),
            api.charts.listForDataset(dataset.id).then((chartsList) => chartsList.length),
            api.reports.listForDataset(dataset.id).then((reportsList) => reportsList.length),
          ]);
          return {
            id: dataset.id,
            analyses: analyses.count,
            charts,
            reports,
            dates: analyses.dates,
          };
        })
      );
      const next = new Map<number, DatasetActivity>();
      for (const result of results) {
        if (result.status === "fulfilled") {
          next.set(result.value.id, {
              analyses: result.value.analyses,
              charts: result.value.charts,
              reports: result.value.reports,
              dates: result.value.dates,
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

  // Trend figures are derived from the data we already hold, not invented:
  // the dashboard previously carried a hardcoded "92%" quality score.
  // Quality is derived from how far each dataset has actually progressed, rather
  // than asserted. The prototype hardcodes 91/94/86, which would be fiction here.
  const quality = useMemo(() => {
    const total = datasets.length;
    if (total === 0) return { score: 0, complete: 0, valued: 0, unique: 0 };
    const analyzed = datasets.filter((d) => d.status === "analyzed").length;
    const cleaned = datasets.filter((d) => d.status === "cleaned").length;
    const withRows = datasets.filter((d) => d.row_count > 0).length;
    const staged = analyzed + cleaned;
    const complete = Math.round((staged / total) * 100);
    const valued = Math.round((withRows / total) * 100);
    return {
      score: Math.round((complete + valued + staged) / 3),
      complete,
      valued,
      unique: staged,
    };
  }, [datasets]);

  const nowMs = Date.now();
  const addedThisMonth = datasets.filter((dataset) => {
    if (!dataset.uploaded_at) return false;
    const parsed = new Date(dataset.uploaded_at).getTime();
    return !Number.isNaN(parsed) && nowMs - parsed <= 30 * 24 * 60 * 60 * 1000;
  }).length;

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
      eyebrow="Muhtasari wa kazi"
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
          label="Datasets"
          value={loading ? "…" : datasets.length}
          hint={addedThisMonth > 0 ? `${addedThisMonth} added this month` : "Zote zilizo hivi karibuni"}
          trend={
            addedThisMonth > 0 ? { value: `+${addedThisMonth}` } : undefined
          }
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
          icon="file-text"
          tone="warning"
          accent="bg-accent-500"
          label="Reports"
          value={loading ? "…" : totalReports}
          hint="PDF / Excel zilizotengenezwa"
        />
      </div>

      {/* Prototype main grid: activity chart (2fr) beside data health (1fr). */}
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ActivityChart
            loading={loading}
            dates={Array.from(activity.values()).flatMap((entry) => entry.dates)}
          />
        </div>

        <QualityPanel
          score={quality.score}
          caption={
            datasets.length === 0
              ? "Hakuna data"
              : quality.score >= 80
                ? "Inazofanya vizuri"
                : quality.score >= 50
                  ? "Inahitaji kazi"
                  : "Haijalianishwa"
          }
          subtitle={`Kati ya datasets ${datasets.length} zinazoendelea`}
          bars={[
            { label: "Kamili", value: quality.complete, color: "#24A36A" },
            { label: "Ina thamani", value: quality.valued, color: "#6C4BF4" },
            { label: "Imefanywa kazi", value: quality.unique, color: "#3B82F6" },
          ]}
          action={
            <Link
              href="/datasets"
              className="inline-flex shrink-0 items-center gap-0.5 text-caption font-semibold text-primary-600 hover:text-primary-700"
            >
              Ripoti
              <Icon name="chevron-right" size={13} />
            </Link>
          }
        />

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

        {/*
          Replaces two cards that were here before: a dark navy "92%" tile, the
          last element still carrying the old indigo palette, and an "AI Insight"
          card asserting a specific recoverable row count that nothing computed.
          This shows the one real next step instead.
        */}
        <Card title="Hatua inayofuata" icon="target" className="lg:col-span-3">
          {latestDataset ? (
            <ul className="flex flex-col gap-2.5">
              {[
                {
                  done: latestDataset.status === "analyzed",
                  label: "Kukagua na kusafisha data",
                  href: `/datasets/${latestDataset.id}/studio`,
                  detail: latestDataset.original_filename,
                },
                {
                  done: (activity.get(latestDataset.id)?.analyses ?? 0) > 0,
                  label: "Kuendesha takwimu",
                  href: `/datasets/${latestDataset.id}/statistics`,
                  detail: `${activity.get(latestDataset.id)?.analyses ?? 0} takwimu zimekamilika`,
                },
                {
                  done: (activity.get(latestDataset.id)?.charts ?? 0) > 0,
                  label: "Kutengeneza chati",
                  href: `/datasets/${latestDataset.id}/charts`,
                  detail: `${activity.get(latestDataset.id)?.charts ?? 0} chati zimeundwa`,
                },
              ].map((step) => (
                <li key={step.label}>
                  <Link
                    href={step.href}
                    className="group flex items-start gap-3 rounded-md p-2 transition-colors hover:bg-surface-sunken focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500"
                  >
                    <span
                      className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full border ${
                        step.done
                          ? "border-success bg-success-bg text-success"
                          : "border-surface-border bg-surface-sunken text-ink-faint"
                      }`}
                    >
                      <Icon name={step.done ? "check" : "chevron-right"} size={12} />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-body font-medium text-ink group-hover:text-primary-700">
                        {step.label}
                      </span>
                      <span className="block text-caption text-ink-muted">
                        {step.detail}
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              title="Hakuna hatua bado"
              description="Pakia dataset ili mtiririko wa kazi uanze."
              action={
                <Link href="/upload">
                  <Button>
                    <Icon name="upload" size={16} />
                    Pakia data
                  </Button>
                </Link>
              }
            />
          )}
        </Card>
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

