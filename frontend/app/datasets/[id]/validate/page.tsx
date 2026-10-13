"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Card, EmptyState, Stat } from "@/components/Card";
import { Icon, IconName } from "@/components/Icon";
import { TableSkeleton } from "@/components/Skeleton";
import {
  api,
  apiErrorMessage,
  AppliedRemediation,
  RemediationResponse,
  statflowApi,
  ValidationIssue,
  ValidationResponse,
} from "@/lib/api";

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

/** One line saying what a fix did, from the summary the engine recorded. */
function describeFix(fix: AppliedRemediation): string {
  const summary = fix.summary;
  if (typeof summary.duplicate_rows_removed === "number") {
    return `${summary.duplicate_rows_removed} rows zinazojirudia ziliondolewa`;
  }
  if (Array.isArray(summary.renamed)) {
    const renames = summary.renamed as { from: string; to: string }[];
    return renames.map((item) => `${item.from} → ${item.to}`).join(", ");
  }
  if (Array.isArray(summary.casts)) {
    const casts = summary.casts as {
      column: string;
      values_became_missing: number;
    }[];
    return casts
      .map(
        (item) =>
          `${item.column} ni namba sasa (thamani ${item.values_became_missing} hazikusomwa)`
      )
      .join(", ");
  }
  if (Array.isArray(summary.dropped_columns)) {
    const dropped = summary.dropped_columns as string[];
    return dropped.length ? `Ziliondolewa: ${dropped.join(", ")}` : "Hakuna column iliyobaki";
  }
  return "Imefanyika";
}

export default function ValidateDatasetPage() {
  const params = useParams<{ id: string }>();
  const datasetId = Number(params.id);

  const [report, setReport] = useState<ValidationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<ValidationIssue["severity"] | "all">("all");
  const [busy, setBusy] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<RemediationResponse | null>(null);
  const [remediationError, setRemediationError] = useState<string | null>(null);

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

  const reload = () => {
    api.datasets
      .validate(datasetId)
      .then((response) => {
        setReport(response);
        setError(null);
      })
      .catch((cause) => setError(apiErrorMessage(cause)));
  };

  const runRemediation = async (
    fixes?: { code: string; column?: string | null }[]
  ) => {
    const key = fixes ? fixes.map((fix) => `${fix.code}:${fix.column ?? ""}`).join("+") : "all";
    setBusy(key);
    setRemediationError(null);
    try {
      const response = await statflowApi.remediate(datasetId, fixes);
      setResult(response);
      // The response carries the new version's report, but the page
      // re-reads it so the version number and the remaining findings
      // are the server's truth, not a copy carried through a click.
      reload();
    } catch (cause) {
      setRemediationError(apiErrorMessage(cause));
    } finally {
      setBusy(null);
      setConfirming(false);
    }
  };

  const verdict = report ? VERDICT[report.verdict] : null;
  const shown =
    report && filter === "all"
      ? report.issues
      : (report?.issues ?? []).filter((issue) => issue.severity === filter);
  const remediable = report?.remediable ?? [];
  const defaultFixes = remediable.filter((fix) => fix.default);

  // The version the remediation started from, taken from the operation
  // the history recorded rather than assumed from the new number.
  const resultSourceVersion =
    result !== null && result.version !== null
      ? ((result.operation as { source_version?: number } | undefined)
          ?.source_version ?? result.version - 1)
      : null;

  const fixFor = (issue: ValidationIssue) =>
    remediable.find(
      (fix) =>
        fix.code === issue.code &&
        (fix.column ?? null) === (issue.column ?? null)
    );

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
              {defaultFixes.length > 0 && !confirming && (
                <button
                  type="button"
                  onClick={() => setConfirming(true)}
                  className="flex min-h-[40px] items-center gap-2 rounded-md bg-primary-600 px-4 text-body font-medium text-white transition-colors duration-150 ease-standard hover:bg-primary-700"
                >
                  <Icon name="sparkles" size={16} />
                  Sahihisha yote kiotomatiki ({defaultFixes.length})
                </button>
              )}
              <Link
                href={
                  report.verdict === "blocked"
                    ? `/datasets/${datasetId}/studio?stage=clean`
                    : `/datasets/${datasetId}/studio?stage=profile`
                }
                className="flex min-h-[40px] items-center gap-2 rounded-md border border-surface-border px-4 text-body text-ink-secondary transition-colors duration-150 ease-standard hover:bg-surface-sunken"
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

            {confirming && (
              <div className="mt-3 rounded-md border border-warning/40 bg-warning-bg p-3.5">
                <p className="flex items-center gap-1.5 text-body font-medium text-warning-700">
                  <Icon name="alert-triangle" size={16} />
                  Thibitisha usafishaji wa {defaultFixes.length} matatizo
                </p>
                <p className="mt-1 text-caption text-warning-700">
                  Itaandika toleo jipya la data (v{report.dataset_version + 1}); faili
                  ya awali haibadiliki na historia inaonyesha kila hatua. Baada ya
                  usafishaji, ripoti inapitiwa upya.
                </p>
                <div className="mt-2.5 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => runRemediation()}
                    disabled={busy !== null}
                    className="flex min-h-[36px] items-center gap-2 rounded-md bg-primary-600 px-3.5 text-caption font-medium text-white transition-colors duration-150 ease-standard hover:bg-primary-700 disabled:opacity-60"
                  >
                    {busy === "all" ? "Inafanya kazi…" : "Thibitisha"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirming(false)}
                    className="flex min-h-[36px] items-center rounded-md border border-surface-border px-3.5 text-caption text-ink-secondary transition-colors duration-150 ease-standard hover:bg-surface-sunken"
                  >
                    Ghairi
                  </button>
                </div>
              </div>
            )}
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

          {remediationError && (
            <Card title="Usafishaji haujafanikiwa" icon="alert-circle">
              <p className="text-body text-danger">{remediationError}</p>
            </Card>
          )}

          {result !== null && result.remediated && result.version !== null && (
            <Card title="Usafishaji umekamilika" icon="check">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="success" size="md">
                  Toleo jipya: v{result.version}
                </Badge>
                <span className="text-caption text-ink-muted">
                  kutoka v{resultSourceVersion}
                  {" · "}
                  {result.row_count.toLocaleString("en-KE")} rows
                  {" · "}
                  {result.column_count} columns
                </span>
              </div>

              {result.applied.length > 0 && (
                <ul className="mt-3 space-y-2">
                  {result.applied.map((fix) => (
                    <li
                      key={`${fix.code}-${fix.column ?? "all"}`}
                      className="flex items-start gap-2 rounded-md border border-surface-border bg-surface-panel px-3 py-2"
                    >
                      <Icon name="check" size={16} className="mt-0.5 text-success" />
                      <div className="min-w-0">
                        <p className="text-body text-ink">{describeFix(fix)}</p>
                        {fix.warnings.map((warning) => (
                          <p key={warning} className="mt-0.5 text-caption text-warning-700">
                            {warning}
                          </p>
                        ))}
                      </div>
                    </li>
                  ))}
                </ul>
              )}

              {result.skipped.length > 0 && (
                <div className="mt-3 rounded-md border border-warning/40 bg-warning-bg p-3">
                  <p className="text-caption font-semibold text-warning-700">
                    Zilirukwa ({result.skipped.length})
                  </p>
                  <ul className="mt-1 space-y-1">
                    {result.skipped.map((item) => (
                      <li key={`${item.code}-${item.column ?? "all"}`} className="text-caption text-warning-700">
                        {item.column ? `${item.code} (${item.column}): ` : `${item.code}: `}
                        {item.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="mt-3 text-caption text-ink-secondary">
                Baada ya usafishaji: {result.validation_after.verdict === "clean"
                  ? "data iko safi"
                  : result.validation_after.verdict === "warnings"
                    ? "bado kuna tahadhari"
                    : "bado kuna makosa"}{" "}
                — {result.validation_after.summary}
              </p>
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
                  const fix = fixFor(issue);
                  const fixKey = `${issue.code}:${issue.column ?? ""}`;
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
                        {fix && (
                          <button
                            type="button"
                            onClick={() =>
                              runRemediation([
                                { code: fix.code, column: fix.column ?? null },
                              ])
                            }
                            disabled={busy !== null}
                            className={`flex min-h-[32px] shrink-0 items-center gap-1.5 rounded-md px-3 text-caption transition-colors duration-150 ease-standard disabled:opacity-60 ${
                              fix.default
                                ? "border border-surface-border text-ink-secondary hover:bg-surface-sunken"
                                : "border border-warning/50 font-medium text-warning-700 hover:bg-warning-bg"
                            }`}
                            title={
                              fix.default
                                ? "Sahihisha tatizo hili (linashirikiwa na kitufe cha 'sahihisha yote')"
                                : "Chaguo lako: hatua hii inaandika toleo jipya la data"
                            }
                          >
                            {busy === fixKey ? "…" : <Icon name="sparkles" size={13} />}
                            {fix.label}
                          </button>
                        )}
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
