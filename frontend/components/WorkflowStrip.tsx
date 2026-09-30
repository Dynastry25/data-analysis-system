"use client";

import Link from "next/link";

import { Icon } from "./Icon";
import { PIPELINE_PHASES, hrefForPhase, phaseFromStep } from "@/lib/pipeline";

interface WorkflowStripProps {
  /** Dataset the phase links act on — the one in the URL, or the latest one. */
  datasetId: number | null;
  /** Stage of the current URL, so the active phase can light up. */
  currentStage: number | null;
  /** What the links act on, shown on the right so the bar never hides it. */
  contextLabel: string;
}

/**
 * The workflow bar: DATA → PREPARE → ANALYZE → VISUALIZE → EXPLAIN → REPORT.
 *
 * This replaces the old numbered pill stepper so the six phases the product is
 * organised around read the same on every screen. Two deliberate choices:
 *
 * - A phase marked "behind you" is a *cursor* reading, not evidence. Real
 *   evidence lives in `JourneyRail`, which counts the records each of the 11
 *   stages actually left behind. Keeping that split means the strip can stay a
 *   navigation aid while the rail stays the honest report.
 * - The bar follows the route, not the studio's `?stage=` sub-view. The Data
 *   Studio is one page holding three stages (profile, clean, transform) and it
 *   shows its own stage tabs, so the bar pointing at the page is not a lie.
 */
export function WorkflowStrip({
  datasetId,
  currentStage,
  contextLabel,
}: WorkflowStripProps) {
  const currentPhase = phaseFromStep(currentStage);

  return (
    <nav
      aria-label="Mtiririko wa kazi"
      className="border-b border-surface-border bg-surface-panel"
    >
      <div className="mx-auto flex max-w-content items-center gap-4 px-4 py-2 sm:px-6 lg:px-8">
        <ol className="flex min-w-max flex-1 items-center gap-1 overflow-x-auto">
          {PIPELINE_PHASES.map((phase, index) => {
            const active = currentPhase?.key === phase.key;
            const passed = currentPhase !== null && currentStage !== null &&
              currentStage >= phase.to && !active;
            const href = hrefForPhase(phase.key, datasetId);
            return (
              <li key={phase.key} className="flex items-center gap-1">
                <Link
                  href={href}
                  aria-current={active ? "step" : undefined}
                  title={
                    datasetId === null
                      ? `${phase.label} · pakia data kwanza`
                      : `${phase.label} · hatua ${phase.from}–${phase.to}`
                  }
                  className={`flex items-center gap-1.5 whitespace-nowrap rounded-sm px-2 py-1 text-overline uppercase tracking-wide transition-colors duration-150 ease-standard ${
                    active
                      ? "bg-primary-600 font-semibold text-white"
                      : passed
                        ? "font-medium text-primary-700 hover:bg-primary-50"
                        : "text-ink-muted hover:bg-surface-sunken hover:text-ink-secondary"
                  }`}
                >
                  {passed && <Icon name="check" size={12} className="shrink-0" />}
                  {phase.label}
                </Link>
                {index < PIPELINE_PHASES.length - 1 && (
                  <Icon
                    name="arrow-right"
                    size={13}
                    className="shrink-0 text-surface-border-strong"
                  />
                )}
              </li>
            );
          })}
        </ol>
        <p
          className="hidden max-w-[22rem] shrink-0 truncate text-caption text-ink-muted lg:block"
          title={contextLabel}
        >
          {contextLabel}
        </p>
      </div>
    </nav>
  );
}

export default WorkflowStrip;
