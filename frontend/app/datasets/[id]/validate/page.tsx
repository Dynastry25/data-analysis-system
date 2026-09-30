"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Card, EmptyState, Stat } from "@/components/Card";
import { Icon, IconName } from "@/components/Icon";
import { TableSkeleton } from "@/components/Skeleton";
import { api, apiErrorMessage, ValidationIssue, ValidationResponse } from "@/lib/api";

// The tone union lives in Badge.tsx but is not exported, so it is restated here
// and checked against it below rather than left to drift silently.
type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger" | "primary";

const SEVERITY: Record<
  ValidationIssue["severity"],
  { label: string; tone: BadgeTone; icon: IconName }
> = {
  error: { label: "Kosa", tone: "danger", icon: "alert-circle" },
  warning: { label: "Tahadhari", tone: "warning", icon: "alert-triangle" },
  info: { label: "Taarifa", tone: "info", icon: "info" },
};

const VERDICT: Record<
  ValidationResponse["verdict"],
  { title: string; tone: BadgeTone; icon: IconName; next: string }
> = {
  clean: {
    title: "Data iko safi",
    tone: "success",
    icon: "check",
    next: "Endelea kwenye Profile",
  },
  warnings: {
    title: "Data inaweza kutumika, kwa tahadhari",
    tone: "warning",
    icon: "alert-triangle",
    next: "Endelea kwenye Profile",
  },
  blocked: {
    title: "Data haijaweza kuendelea",
    tone: "danger",
    icon: "alert-circle",
    next: "Sahihisha makosa kisha uthibitisha tena",
  },
};

/** Where a blocked verdict sends the user next, by the code that blocked it. */
const BLOCKED_ROUTE: Record<string, string> = {
  empty_dataset: "Sahihisha faili: ina rows au la?",
  no_columns: "Sahihisha faili: ina columns au la?",
  duplicate_column_names: "Badilisha majina ya columns",
  column_all_missing: "Ondoa columns ambazo zina tupu",
};

export default function ValidateDatasetPage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params.id);

  const [report, setReport] = useState<ValidationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<ValidationIssue["severity"] | "all">("all");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.datasets
      .validate(datasetId)
      .then((response) => {
        if (!cancelled) {
          setReport(response);
          setError(null);
        }
      })
      .catch((cause) => {
        if (!cancelled) setError(apiErrorMessage(cause));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  const verdict = report ? VERDICT[report.verdict] : null;
  const shown =
    report && filter === "all"
      ? report.issues
      : (report?.issues ?? []).filter((issue) => issue.severity === filter);

  return (
    <AppShell
      title="Data Quality / Profile"
      description="Kagua schema, data quality na tabia za data kabla ya kuchambua. Kila tatizo hapa linaweza kurekebishwa na kuthibitishwa."
    >
      {loading && <TableSkeleton rows={5} />}

      {!loading && error && (
        <Card title="Imeshindikana kuangalia data">
          <p className="text-body text-danger">{error}</p>
        </Card>
      )}

      {!loading && !error && report && verdict && (
        <>
          <Card>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <span
                  className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${
                    report.verdict === "clean"
                      ? "bg-success-bg text-success"
                      : report.verdict === "warnings"
                        ? "bg-warning-bg text-warning"
                        : "bg-danger-bg text-danger"
                  }`}
                >
                  <Icon name={verdict.icon} size={20} />
                </span>
                <div>
                  <p className="text-h3 text-ink">{verdict.title}</p>
                  <p className="mt-1 max-w-2xl text-body text-ink-secondary">
                    {report.summary}
                  </p>
                </div>
              </div>
              <Badge tone={verdict.tone} size="md">
                {verdict.title}
              </Badge>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-4">
              <Stat
                label="Rows"
                value={report.row_count.toLocaleString("en-KE")}
                hint={`version ${report.dataset_version}`}
              />
              <Stat label="Columns" value={String(report.column_count)} />
              <Stat
                label="Makosa"
                value={
                  <span className={report.error_count > 0 ? "text-danger" : undefined}>
                    {String(report.error_count)}
                  </span>
                }
                hint={report.error_count > 0 ? "lazima sahihishwe" : "hakuna"}
              />
              <Stat
                label="Tahadhari"
                value={
                  <span className={report.warning_count > 0 ? "text-warning" : undefined}>
                    {String(report.warning_count)}
                  </span>
                }
              />
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Link
                href={
                  report.verdict === "blocked"
                    ? `/datasets/${datasetId}/studio?stage=clean`
                    : `/datasets/${datasetId}/studio?stage=profile`
                }
                className="flex min-h-[40px] items-center gap-2 rounded-md bg-primary-600 px-4 text-body font-medium text-white transition-colors duration-150 ease-standard hover:bg-primary-700"
              >
                {verdict.next}
                <Icon name="arrow-right" size={16} />
              </Link>
              <Link
                href={`/datasets/${datasetId}/explore`}
                className="flex min-h-[40px] items-center gap-2 rounded-md border border-surface-border px-4 text-body text-ink-secondary transition-colors duration-150 ease-standard hover:bg-surface-sunken"
              >
                Chunguza data
              </Link>
            </div>
          </Card>

          {report.error_count > 0 && (
            <Card title="Makosa ya kurekebisha kwanza" icon="alert-circle">
              <ul className="space-y-2">
                {report.issues
                  .filter((issue) => issue.severity === "error")
                  .map((issue) => (
                    <li
                      key={issue.code}
                      className="flex items-start gap-2 rounded-md border border-danger/30 bg-danger-bg px-3 py-2"
                    >
                      <Icon name="alert-circle" size={16} className="mt-0.5 text-danger" />
                      <div>
                        <p className="text-body text-ink">{issue.message}</p>
                        {BLOCKED_ROUTE[issue.code] && (
                          <p className="mt-0.5 text-caption text-ink-secondary">
                            {BLOCKED_ROUTE[issue.code]}
                          </p>
                        )}
                      </div>
                    </li>
                  ))}
              </ul>
            </Card>
          )}

          <Card
            title={`Matatizo yote (${report.issues.length})`}
            icon="clipboard"
            actions={
              <div className="flex flex-wrap items-center gap-1">
                {(["all", "error", "warning", "info"] as const).map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setFilter(value)}
                    className={`rounded-md px-2.5 py-1 text-caption transition-colors duration-150 ${
                      filter === value
                        ? "bg-primary-50 font-medium text-primary-800"
                        : "text-ink-muted hover:bg-surface-sunken"
                    }`}
                  >
                    {value === "all" ? "Zote" : SEVERITY[value].label}
                    <span className="ml-1">
                      {value === "all"
                        ? report.issues.length
                        : report.issues.filter((issue) => issue.severity === value).length}
                    </span>
                  </button>
                ))}
              </div>
            }
          >
            {report.issues.length === 0 ? (
              <EmptyState
                icon="check"
                title="Hakuna tatizo lililopatikana"
                description="Schema, data types na thamani zote zinaonekana safi. Endelea kwenye hatua inayofuata."
              />
            ) : shown.length === 0 ? (
              <p className="text-body text-ink-muted">Hakuna tatizo katika kategoria hiyo.</p>
            ) : (
              <ul className="divide-y divide-surface-border">
                {shown.map((issue) => {
                  const meta = SEVERITY[issue.severity];
                  return (
                    <li key={`${issue.code}-${issue.column ?? "all"}`} className="py-3">
                      <div className="flex items-start gap-3">
                        <Icon
                          name={meta.icon}
                          size={16}
                          className={`mt-0.5 shrink-0 ${
                            issue.severity === "error"
                              ? "text-danger"
                              : issue.severity === "warning"
                                ? "text-warning"
                                : "text-info-700"
                          }`}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge tone={meta.tone} size="sm">
                              {meta.label}
                            </Badge>
                            {issue.column && (
                              <code className="rounded bg-surface-sunken px-1.5 py-0.5 font-mono text-caption text-ink-secondary">
                                {issue.column}
                              </code>
                            )}
                          </div>
                          <p className="mt-1 text-body text-ink">{issue.message}</p>
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          <p className="text-caption text-ink-muted">
        Hatua hii haiandishi rekodi: kuwa umesoma ripoti hakuibadilishi kitu.
        Kwa hiyo hatua hii inabaki kuwa &ldquo;Soma&rdquo; badala ya &ldquo;Imekamilika&rdquo;.
          </p>
        </>
      )}
    </AppShell>
  );
}
