"use client";

/**
 * Activity centre.
 *
 * There is no activity endpoint, and inventing one would mean storing
 * something the backend does not currently record. Instead this composes a
 * real feed from what *is* stored, per dataset:
 *
 * - uploads          from the dataset's own `uploaded_at`
 * - cleaning         from `/v1/datasets/{id}/operations` (the audit trail)
 * - analyses         from `/v1/datasets/{id}/analysis`
 *
 * So every row here is something that actually happened to the user's own
 * data, with a timestamp the server produced. Only the ordering is done here.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Card, EmptyState } from "@/components/Card";
import { Icon, IconName } from "@/components/Icon";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import { api, apiErrorMessage, statflowApi } from "@/lib/api";

type Kind = "upload" | "operation" | "analysis";

interface Event {
  id: string;
  kind: Kind;
  at: string;
  title: string;
  detail: string;
  datasetId: number;
  datasetName: string;
}

const KIND_META: Record<Kind, { label: string; icon: IconName }> = {
  upload: { label: "Upakiaji", icon: "upload" },
  operation: { label: "Usafishaji", icon: "sliders" },
  analysis: { label: "Uchambuzi", icon: "calculator" },
};

function stamp(value: string | null | undefined): string {
  if (!value) return "";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "" : parsed.toISOString();
}

export default function ActivityPage() {
  const { showToast } = useToast();
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Kind | "all">("all");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const datasets = await api.datasets.list();
      const collected: Event[] = [];

      for (const dataset of datasets) {
        const uploadedAt = stamp(dataset.uploaded_at);
        if (uploadedAt) {
          collected.push({
            id: `upload-${dataset.id}`,
            kind: "upload",
            at: uploadedAt,
            title: "Dataset imewekwa",
            detail: `${dataset.original_filename} · ${dataset.row_count?.toLocaleString("en-GB") ?? 0} rows`,
            datasetId: dataset.id,
            datasetName: dataset.original_filename,
          });
        }

        // The per-dataset calls are independent; one failing must not lose the
        // rest of the feed, so each is settled independently and any rejection
        // simply contributes no rows for that dataset.
        const [history, runs] = await Promise.allSettled([
          statflowApi.operationsHistory(dataset.id),
          statflowApi.analysisRuns(dataset.id),
        ]);

        if (history.status === "fulfilled") {
          for (const operation of history.value.operations) {
            const at = stamp(operation.created_at);
            if (!at) continue;
            collected.push({
              id: `op-${dataset.id}-${operation.sequence}`,
              kind: "operation",
              at,
              title: operation.type.replace(/_/g, " "),
              detail: `v${operation.source_version} → v${operation.version}`,
              datasetId: dataset.id,
              datasetName: dataset.original_filename,
            });
          }
        }
        if (runs.status === "fulfilled") {
          for (const run of runs.value) {
            const at = stamp(run.created_at);
            if (!at) continue;
            collected.push({
              id: `run-${run.analysis_id}`,
              kind: "analysis",
              at,
              title: run.analysis_type.replace(/_/g, " "),
              detail: `${run.result?.sample_size ?? "?"} rows · ${run.status}`,
              datasetId: dataset.id,
              datasetName: dataset.original_filename,
            });
          }
        }
      }

      collected.sort((a, b) => b.at.localeCompare(a.at));
      setEvents(collected);
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    load();
  }, [load]);

  const shown = useMemo(
    () => (filter === "all" ? events : events.filter((event) => event.kind === filter)),
    [events, filter]
  );

  const counts = useMemo(() => {
    const base = { all: events.length, upload: 0, operation: 0, analysis: 0 };
    for (const event of events) base[event.kind] += 1;
    return base;
  }, [events]);

  return (
    <AppShell
      eyebrow="Historia"
      title="Kituo cha shughuli"
      description="Kila kitu kilichofanyika kwenye data yako, kwa mpangilio wa muda."
    >
      <Card>
        <div className="flex flex-wrap items-center gap-2">
          {(["all", "upload", "operation", "analysis"] as const).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              aria-pressed={filter === key}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-caption font-medium transition-colors duration-150 ease-standard ${
                filter === key
                  ? "bg-primary-50 text-primary-800"
                  : "text-ink-secondary hover:bg-surface-sunken"
              }`}
            >
              {key === "all" ? "Zote" : KIND_META[key].label}
              <span className="tabular text-ink-muted">{counts[key]}</span>
            </button>
          ))}
        </div>
      </Card>

      <div className="mt-4">
        {loading ? (
          <Card>
            <TableSkeleton rows={6} columns={2} />
          </Card>
        ) : shown.length === 0 ? (
          <Card>
            <EmptyState
              title={events.length === 0 ? "Bado hakuna shughuli" : "Hakuna katika kichujio"}
              description={
                events.length === 0
                  ? "Ingiza dataset, usafishe data auendesha uchambuzi -- vitu vyote vitatokea hapa."
                  : "Badilisha kichujio ili kuona shughuli nyingine."
              }
              icon="history"
            />
          </Card>
        ) : (
          <Card>
            <ol className="space-y-1">
              {shown.map((event) => (
                <li key={event.id}>
                  <Link
                    href={`/datasets/${event.datasetId}`}
                    className="flex flex-wrap items-center gap-3 rounded-md px-2 py-2.5 transition-colors duration-150 ease-standard hover:bg-surface-sunken"
                  >
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-sm bg-primary-50 text-primary-600">
                      <Icon name={KIND_META[event.kind].icon} size={15} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-body text-ink">
                        {event.title}
                      </span>
                      <span className="block truncate text-caption text-ink-muted">
                        {event.datasetName} · {event.detail}
                      </span>
                    </span>
                    <Badge tone="neutral">{KIND_META[event.kind].label}</Badge>
                    <time
                      dateTime={event.at}
                      className="tabular shrink-0 text-caption text-ink-muted"
                    >
                      {new Date(event.at).toLocaleString("en-GB", {
                        dateStyle: "short",
                        timeStyle: "short",
                      })}
                    </time>
                  </Link>
                </li>
              ))}
            </ol>
          </Card>
        )}
      </div>
    </AppShell>
  );
}