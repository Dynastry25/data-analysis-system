"use client";

import Link from "next/link";

import { Icon } from "./Icon";
import { PIPELINE_STAGES } from "@/lib/pipeline";

interface PipelineStepperProps {
  datasetId: number | null;
  currentStage: number | null;
}

/**
 * Horizontal 6-stage workflow stepper, rendered above every dataset page.
 * Completed stages show a check, the current one is filled blue, future ones
 * stay neutral. Every stage is clickable so the user can jump forward/back.
 */
export function PipelineStepper({ datasetId, currentStage }: PipelineStepperProps) {
  if (currentStage === null) return null;

  return (
    <nav
      aria-label="Mtiririko wa kazi"
      className="mb-6 overflow-x-auto rounded border border-neutral-200 bg-white p-2"
    >
      <ol className="flex min-w-max items-center gap-1">
        {PIPELINE_STAGES.map((stage) => {
          const done = currentStage > stage.step;
          const current = currentStage === stage.step;
          const href =
            datasetId !== null ? stage.hrefFor(datasetId) : "/upload";
          return (
            <li key={stage.key} className="flex items-center gap-1">
              <Link
                href={href}
                aria-current={current ? "step" : undefined}
                className={`flex items-center gap-2 rounded px-2 py-1.5 text-caption transition-colors duration-150 ${
                  current
                    ? "bg-primary-50 text-primary-900"
                    : done
                      ? "text-neutral-600 hover:bg-neutral-100"
                      : "text-neutral-400 hover:bg-neutral-50"
                }`}
              >
                <span
                  className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-caption transition-colors duration-150 ${
                    done
                      ? "bg-success-bg text-success"
                      : current
                        ? "bg-primary-600 text-white"
                        : "bg-neutral-100 text-neutral-400"
                  }`}
                >
                  {done ? <Icon name="check" size={12} /> : stage.step}
                </span>
                <span className="font-medium">{stage.label}</span>
              </Link>
              {stage.step < PIPELINE_STAGES.length && (
                <Icon
                  name="chevron-right"
                  size={14}
                  className="shrink-0 text-neutral-300"
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