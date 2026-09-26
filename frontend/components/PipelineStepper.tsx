"use client";

import Link from "next/link";

import { Icon } from "./Icon";
import { PIPELINE_STAGES } from "@/lib/pipeline";

interface PipelineStepperProps {
  datasetId: number | null;
  currentStage: number | null;
}

export function PipelineStepper({ datasetId, currentStage }: PipelineStepperProps) {
  if (currentStage === null) return null;

  return (
    <nav aria-label="Mtiririko wa kazi" className="mb-6">
      <ol className="flex min-w-max items-center gap-1 overflow-x-auto rounded-lg border border-surface-border bg-surface-panel p-1.5 shadow-card">
        {PIPELINE_STAGES.map((stage) => {
          const done = currentStage > stage.step;
          const current = currentStage === stage.step;
          const href = datasetId !== null ? stage.hrefFor(datasetId) : "/upload";
          return (
            <li key={stage.key} className="flex items-center gap-1">
              <Link
                href={href}
                aria-current={current ? "step" : undefined}
                className={`flex items-center gap-2 rounded-md px-2.5 py-1.5 text-caption transition-colors duration-150 ease-standard ${
                  current
                    ? "bg-primary-50 font-medium text-primary-800"
                    : done
                      ? "text-ink-secondary hover:bg-surface-sunken"
                      : "text-ink-muted hover:bg-surface-sunken hover:text-ink-secondary"
                }`}
              >
                <span
                  className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-caption ${
                    done
                      ? "bg-success-bg text-success"
                      : current
                        ? "bg-primary-600 text-white"
                        : "bg-surface-sunken text-ink-muted"
                  }`}
                >
                  {done ? <Icon name="check" size={12} /> : stage.step}
                </span>
                <span className="whitespace-nowrap font-medium">{stage.label}</span>
              </Link>
              {stage.step < PIPELINE_STAGES.length && (
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

export default PipelineStepper;




