"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge } from "./Badge";
import { Icon, IconName } from "./Icon";
import {
  PIPELINE_PHASES,
  PIPELINE_STAGES,
  StageProgressInput,
  StageState,
  isStageTransient,
  phaseOfStage,
  resolveStageStates,
  suggestedNextStage,
} from "@/lib/pipeline";

interface JourneyRailProps {
  datasetId: number;
  currentStage: number | null;
  progress: StageProgressInput;
  /** Start collapsed so it does not crowd the workspace it describes. */
  defaultOpen?: boolean;
}

const STATE_TONE: Record<StageState, "success" | "primary" | "neutral"> = {
  done: "success",
  current: "primary",
  available: "neutral",
};

const STATE_ICON: Record<StageState, IconName> = {
  done: "check",
  current: "arrow-right",
  available: "chevron-right",
};

/**
 * The full 11-stage journey, which the compact 6-phase bar cannot show.
 *
 * Three honesty rules run through this component:
 *
 * - A stage that shares a page with another stage says so, instead of
 *   pretending Profile, Clean and Transform are three separate screens.
 * - A stage with no artifact is labelled as a read, never as unfinished work,
 *   because nothing in the product stores the fact that you read it.
 * - Nothing is called blocked. The product does not enforce an order, so a
 *   blocked badge would describe a gate that is not there.
 */
export function JourneyRail({
  datasetId,
  currentStage,
  progress,
  defaultOpen = false,
}: JourneyRailProps) {
  const [open, setOpen] = useState(defaultOpen);
  const states = resolveStageStates(progress, currentStage);
  const next = suggestedNextStage(progress);

  const doneCount = [...states.values()].filter((s) => s === "done").length;

  return (
    <section className="mb-6 rounded-lg border border-surface-border bg-surface-panel shadow-card">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <div className="min-w-0">
          <p className="text-body font-medium text-ink">Safari kamili ya kazi</p>
          <p className="text-caption text-ink-muted">
            Hatua {PIPELINE_STAGES.length} · {doneCount} zimekamilika
            {next ? (
              <>
                {" "}· inayofuata{" "}
                <span className="font-medium text-ink-secondary">
                  {next.fullLabel} ({phaseOfStage(next).label})
                </span>
              </>
            ) : (
              " · safari imekamilika"
            )}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <div
            className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-sunken"
            role="progressbar"
            aria-valuenow={doneCount}
            aria-valuemin={0}
            aria-valuemax={PIPELINE_STAGES.length}
            aria-label="Hatua zilizokamilika"
          >
            <div
              className="h-full bg-success"
              style={{
                width: `${(doneCount / PIPELINE_STAGES.length) * 100}%`,
              }}
            />
          </div>
          <Icon name={open ? "chevron-up" : "chevron-down"} size={16} className="text-ink-muted" />
        </div>
      </button>

      {open && (
        <ol className="border-t border-surface-border px-4 py-3">
          {PIPELINE_PHASES.map((phase) => (
            <li key={phase.key} className="mb-4 last:mb-0">
              <p className="mb-2 text-overline uppercase tracking-wide text-ink-muted">
                {phase.label}
                <span className="ml-2 normal-case tracking-normal text-ink-muted">
                  ({phase.labelEn}) · hatua {phase.from}–{phase.to}
                </span>
              </p>
              <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {PIPELINE_STAGES.filter((stage) => stage.phase === phase.key).map(
                  (stage) => {
                    const state = states.get(stage.key) ?? "available";
                    const sharedWith = stage.sharesTargetWith
                      ? PIPELINE_STAGES.find((s) => s.key === stage.sharesTargetWith)
                      : null;
                    const read = isStageTransient(stage);
                    return (
                      <li key={stage.key}>
                        <div
                          className={`flex h-full flex-col gap-1.5 rounded-md border p-2.5 ${
                            state === "current"
                              ? "border-primary-200 bg-primary-50"
                              : "border-surface-border bg-surface-panel"
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <span
                              className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] ${
                                state === "done"
                                  ? "bg-success-bg text-success"
                                  : state === "current"
                                    ? "bg-primary-600 text-white"
                                    : "bg-surface-sunken text-ink-muted"
                              }`}
                            >
                              <Icon name={STATE_ICON[state]} size={11} />
                            </span>
                            <span className="truncate text-caption font-medium text-ink">
                              {stage.step}. {stage.fullLabel}
                            </span>
                          </div>
                          <p className="text-caption text-ink-muted">
                            {stage.description}
                          </p>
                          <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-1">
                            <Badge tone={STATE_TONE[state]} size="sm">
                              {state === "done"
                                ? "Imekamilika"
                                : state === "current"
                                  ? "Hapa sasa"
                                  : read
                                    ? "Soma"
                                    : "Inapatikana"}
                            </Badge>
                            {read && state !== "done" && (
                              <span className="text-caption text-ink-muted">
                                hakuna rekodi
                              </span>
                            )}
                            {sharedWith && (
                              <span className="text-caption text-ink-muted">
                                <span className="font-medium">
                                  {sharedWith.fullLabel}
                                </span>{" "}
                                ukurasa mmoja
                              </span>
                            )}
                            <Link
                              href={stage.hrefFor(datasetId)}
                              className="ml-auto text-caption font-medium text-primary-700 hover:underline"
                            >
                              Fungua
                            </Link>
                          </div>
                        </div>
                      </li>
                    );
                  }
                )}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/** Compact one-line summary for pages that have no room for the rail. */
export function JourneySummary({ progress }: { progress: StageProgressInput }) {
  const next = suggestedNextStage(progress);
  if (!next) {
    return (
      <p className="text-caption text-success">
        Safari kamili imekamilika hatua zote {PIPELINE_STAGES.length}.
      </p>
    );
  }
  const phase = phaseOfStage(next);
  return (
    <p className="text-caption text-ink-muted">
      Hatua inayofuata:{" "}
      <span className="font-medium text-ink-secondary">
        {next.fullLabel} ({phase.label})
      </span>{" "}
      · {next.description}
    </p>
  );
}

export default JourneyRail;
