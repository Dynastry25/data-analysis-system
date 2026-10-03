"use client";

import { Icon } from "./Icon";
import { ScoreRing } from "./ScoreRing";

export interface QualityBar {
  label: string;
  value: number;
  color: string;
}

interface QualityPanelProps {
  score: number;
  caption: string;
  bars: QualityBar[];
  /** Small delta shown next to the caption, e.g. "4 points this month". */
  change?: string;
  /** Line under the panel title, e.g. "Across 8 active datasets". */
  subtitle?: string;
  /** Rendered in the header on the right. */
  action?: React.ReactNode;
}

/**
 * The prototype's "Data health" panel. This replaced a dark navy tile that had
 * survived the restyle; it was the one element on the page still carrying the
 * old indigo palette, and a near-black block read as heavier than the four
 * light KPI cards around it.
 */
export function QualityPanel({
  score,
  caption,
  bars,
  change,
  subtitle,
  action,
}: QualityPanelProps) {
  return (
    <article className="flex min-h-[307px] flex-col rounded-lg border border-surface-border bg-surface-panel p-5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display text-body font-semibold text-ink">
            Data health
          </h2>
          {subtitle && (
            <p className="mt-0.5 text-caption text-ink-muted">{subtitle}</p>
          )}
        </div>
        {action}
      </div>

      <div className="my-5 flex items-center gap-4">
        <ScoreRing score={score} caption={caption} />
        <div className="min-w-0">
          <strong className="block font-display text-[15px] font-semibold text-ink">
            {caption}
          </strong>
          <p className="my-1 text-caption text-ink-muted">Workspace quality score</p>
          {change && (
            <span className="inline-flex items-center gap-1 text-caption font-medium text-success">
              <Icon name="chevron-up" size={11} />
              {change}
            </span>
          )}
        </div>
      </div>

      <div className="mt-auto flex flex-col gap-3">
        {bars.map((bar) => (
          <div key={bar.label}>
            <div className="mb-1.5 flex items-center justify-between text-caption">
              <span className="text-ink-muted">{bar.label}</span>
              <strong className="tabular font-semibold text-ink">{bar.value}%</strong>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken">
              <span
                className="block h-full rounded-full transition-[width] duration-500 ease-standard"
                style={{ width: `${bar.value}%`, backgroundColor: bar.color }}
              />
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}

export default QualityPanel;