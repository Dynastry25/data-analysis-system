"use client";

import Link from "next/link";

import { Icon } from "./Icon";
import { PIPELINE_PHASES, phaseFromStep } from "@/lib/pipeline";

interface PipelineStepperProps {
  datasetId: number | null;
  currentStage: number | null;
}

/**
 * The compact indicator: the 6 phases the design spec asks for in section 12.
 *
 * Eleven stages do not fit in a bar on a laptop, and the phases are what a
 * returning user navigates by. The full 11-stage journey lives in JourneyRail,
 * which sits inside the workspace rather than above it.
 *
 * A phase is only marked done when every stage inside it is done, so a partial
 * phase reads as partial.
 */
export function PipelineStepper({ datasetId, currentStage }: PipelineStepperProps) {
  if (currentStage === null) return null;
  const currentPhase = phaseFromStep(currentStage);

  return (
    <nav aria-label="Hatua za kazi" className="mb-6">
      <ol className="flex min-w-max items-center gap-1 overflow-x-auto rounded-lg border border-surface-border bg-surface-panel p-1.5 shadow-card">
        {PIPELINE_PHASES.map((phase, index) => {
          const active = currentPhase?.key === phase.key;
          const passed =
            currentPhase !== null && currentStage >= phase.to && !active;
          const href = datasetId !== null
            ? hrefForPhase(phase.key, datasetId)
            : "/upload";
          return (
            <li key={phase.key} className="flex items-center gap-1">
              <Link
                href={href}
                aria-current={active ? "step" : undefined}
                title={`Hatua ${phase.from}–${phase.to}`}
                className={`flex items-center gap-2 rounded-md px-2.5 py-1.5 text-caption transition-colors duration-150 ease-standard ${
                  active
                    ? "bg-primary-50 font-medium text-primary-800"
                    : passed
                      ? "text-ink-secondary hover:bg-surface-sunken"
                      : "text-ink-muted hover:bg-surface-sunken hover:text-ink-secondary"
                }`}
              >
                <span
                  className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-caption ${
                    active
                      ? "bg-primary-600 text-white"
                      : passed
                        ? "bg-success-bg text-success"
                        : "bg-surface-sunken text-ink-muted"
                  }`}
                >
                  {passed ? <Icon name="check" size={12} /> : index + 1}
                </span>
                <span className="whitespace-nowrap font-medium">{phase.label}</span>
                <span className="whitespace-nowrap text-ink-muted">
                  {phase.from}–{phase.to}
                </span>
              </Link>
              {index < PIPELINE_PHASES.length - 1 && (
                <Icon
                  name="chevron-right"
                  size={14}
                  className="shrink-0 text-surface-border-strong"
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/** The first stage of a phase is where you enter that phase. */
function hrefForPhase(
  phaseKey: (typeof PIPELINE_PHASES)[number]["key"],
  datasetId: number
): string {
  const entry: Record<string, string> = {
    data: `/datasets/${datasetId}/validate`,
    prepare: `/datasets/${datasetId}/studio?stage=clean`,
    analyze: `/datasets/${datasetId}/statistics`,
    visualize: `/datasets/${datasetId}/charts`,
    explain: `/datasets/${datasetId}/ask`,
    report: `/datasets/${datasetId}/export?stage=report`,
  };
  return entry[phaseKey];
}

export default PipelineStepper;
