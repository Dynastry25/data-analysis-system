"use client";

import { useEffect, useState } from "react";

import { AdminShell } from "@/components/AdminShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { Icon, IconName } from "@/components/Icon";
import { MetricCard } from "@/components/MetricCard";
import { Skeleton } from "@/components/Skeleton";
import {
  AdminAlert,
  AdminOverview,
  adminApi,
  apiErrorMessage,
} from "@/lib/api";

const ALERT_TONE: Record<AdminAlert["level"], "danger" | "warning" | "info"> = {
  danger: "danger",
  warning: "warning",
  info: "info",
};

function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(
    units.length - 1,
    Math.floor(Math.log(bytes) / Math.log(1024))
  );
  const value = bytes / 1024 ** exponent;
  return `${value.toFixed(value >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

export default function AdminDashboardPage() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [alerts, setAlerts] = useState<AdminAlert[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [stats, panel] = await Promise.all([
        adminApi.overview(),
        adminApi.alerts(),
      ]);
      setOverview(stats);
      setAlerts(panel);
    } catch (caught) {
      setError(apiErrorMessage(caught));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const kpis: { label: string; value: string; icon: IconName; hint?: string }[] =
    overview
      ? [
          { label: "Watumiaji", value: formatNumber(overview.total_users), icon: "users" },
          {
            label: "Watumiaji wanaotumiaja",
            value: formatNumber(overview.active_last_7_days),
            icon: "trending-up",
            hint: "walio wanaotumiaja ndani ya siku 7",
          },
          {
            label: "Mashirika",
            value: formatNumber(overview.organizations),
            icon: "building",
          },
          {
            label: "Datasets",
            value: formatNumber(overview.datasets),
            icon: "database",
            hint: `${formatNumber(overview.total_rows_profiled)} rows`,
          },
          {
            label: "Uchambuzi",
            value: formatNumber(overview.analyses),
            icon: "calculator",
          },
          {
            label: "Audit Events (24h)",
            value: formatNumber(overview.audit_events_last_24h),
            icon: "shield",
            hint: "matukio ya usalama kwa saa 24",
          },
          {
            label: "Hifadhi",
            value: formatBytes(overview.storage_bytes),
            icon: "layers",
          },
          {
            label: "Wafanyakazi wa admin",
            value: formatNumber(overview.platform_staff),
            icon: "shield",
            hint: `${formatNumber(overview.suspended_users)} suspended`,
          },
        ]
      : [];

  return (
    <AdminShell
      title="Admin Dashboard"
      description="Hali ya jumla ya platform. Takwimu zinaonyeshwa kama zilivyo kwenye database, si kama viwilio."
      actions={
        <Button variant="secondary" size="small" icon="refresh" onClick={load} loading={loading}>
          Onyesha upya
        </Button>
      }
    >
      {error ? (
        <Card>
          <EmptyState
            title="Imeshindikana kupakia takwimu"
            description={error}
            icon="alert-triangle"
            action={
              <Button variant="secondary" onClick={load}>
                Jaribu tena
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="flex flex-col gap-5">
          <section aria-label="Takwimu kuu">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {loading && !overview
                ? Array.from({ length: 8 }, (_, index) => (
                    <Skeleton key={index} className="h-[92px] w-full rounded-lg" />
                  ))
                : kpis.map((kpi) => (
                    <MetricCard
                      key={kpi.label}
                      label={kpi.label}
                      value={kpi.value}
                      icon={kpi.icon}
                      hint={kpi.hint}
                    />
                  ))}
            </div>
          </section>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card
              title="Tahadhari"
              description="Mashauri yanayotokana na hali inayoweza kuthibitishwa kwenye database."
              icon="alert-triangle"
              className="lg:col-span-2"
            >
              {loading && !alerts ? (
                <div className="flex flex-col gap-2">
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-12 w-full" />
                </div>
              ) : (
                <ul className="flex flex-col gap-2">
                  {(alerts ?? []).map((alert) => (
                    <li
                      key={`${alert.title}-${alert.detail}`}
                      className="flex items-start gap-2.5 rounded-md border border-surface-border bg-surface-sunken px-3 py-2.5"
                    >
                      <Icon
                        name={
                          alert.level === "info"
                            ? "info"
                            : alert.level === "warning"
                              ? "alert-triangle"
                              : "alert-circle"
                        }
                        size={16}
                        className={`mt-0.5 shrink-0 ${
                          ALERT_TONE[alert.level] === "danger"
                            ? "text-danger-700"
                            : ALERT_TONE[alert.level] === "warning"
                              ? "text-warning-700"
                              : "text-info-700"
                        }`}
                      />
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-body font-medium text-ink">{alert.title}</p>
                          <Badge tone={ALERT_TONE[alert.level]} size="sm">
                            {alert.level}
                          </Badge>
                        </div>
                        <p className="text-caption text-ink-secondary">{alert.detail}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card
              title="Uendelevu"
              description="Hali ya kila mfumo mkuu. Mfumo bila kipimo halisi haondoiwi kuwa mzuri."
              icon="shield"
            >
              <ul className="flex flex-col gap-2">
                <ServiceRow
                  name="API"
                  state="ok"
                  detail="Maombi haya yalipokelewa"
                />
                <ServiceRow
                  name="Database"
                  state={overview !== null ? "ok" : "unknown"}
                  detail={
                    overview !== null
                      ? "Takwimu zilirejeshwa kutoka database"
                      : "Takwimu hazijapatikana"
                  }
                />
                <ServiceRow
                  name="Statistical Engine"
                  state="unknown"
                  detail="Hakuna kipimo cha afya kwa engine bado"
                />
                <ServiceRow
                  name="Job Queue"
                  state="unknown"
                  detail="Hakuna mfumo wa kazi wa asili; ripoti zinatumia background tasks za FastAPI"
                />
                <ServiceRow
                  name="Exports"
                  state={
                    overview === null
                      ? "unknown"
                      : overview.failed_reports > 0
                        ? "attention"
                        : "ok"
                  }
                  detail={
                    overview
                      ? `${overview.pending_reports} in progress, ${overview.failed_reports} failed`
                      : "—"
                  }
                />
              </ul>
              <p className="mt-3 text-caption text-ink-muted">
                &ldquo;Not measured&rdquo; inamaanisha hakuna kipimo cha afya kilichopo,
                si kwamba mfumo umeharibika.
              </p>
            </Card>
          </div>
        </div>
      )}
    </AdminShell>
  );
}

/**
 * A row in the service list. `unknown` is a real third state on purpose:
 * "we never measured it" must not be rendered as the same thing as "fine",
 * or an operator reads a green badge that nobody ever produced.
 */
type ServiceState = "ok" | "attention" | "unknown";

const SERVICE_STATE_TONE: Record<ServiceState, "success" | "warning" | "neutral"> = {
  ok: "success",
  attention: "warning",
  unknown: "neutral",
};

const SERVICE_STATE_LABEL: Record<ServiceState, string> = {
  ok: "Healthy",
  attention: "Needs attention",
  unknown: "Not measured",
};

function ServiceRow({
  name,
  state,
  detail,
}: {
  name: string;
  state: ServiceState;
  detail?: string;
}) {
  return (
    <li className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <p className="text-body text-ink">{name}</p>
        {detail && <p className="text-caption text-ink-muted">{detail}</p>}
      </div>
      <Badge tone={SERVICE_STATE_TONE[state]} size="sm">
        {SERVICE_STATE_LABEL[state]}
      </Badge>
    </li>
  );
}
