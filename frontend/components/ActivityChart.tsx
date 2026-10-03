"use client";

import { useMemo, useState } from "react";

import { Icon } from "./Icon";

const RANGES = ["4W", "12W", "6M"] as const;
type Range = (typeof RANGES)[number];

const RANGE_WEEKS: Record<Range, number> = { "4W": 4, "12W": 12, "6M": 26 };

const W = 600;
const H = 190;
const PAD = 16;

interface ActivityChartProps {
  /** ISO timestamps of every analysis run in the workspace. */
  dates: string[];
  loading?: boolean;
}

/**
 * Weekly analysis activity, matching the prototype's line chart.
 *
 * Plain SVG rather than Plotly: this is one series with no interaction beyond
 * the range switch, and Plotly is already the heaviest thing in the bundle (it
 * is also the source of the production `buffer/` polyfill failure). A
 * hand-rolled polyline is a fraction of the payload.
 */
export function ActivityChart({ dates, loading = false }: ActivityChartProps) {
  const [range, setRange] = useState<Range>("12W");

  const series = useMemo(() => {
    const weeks = RANGE_WEEKS[range];
    const weekMs = 7 * 24 * 60 * 60 * 1000;
    const start = Date.now() - (weeks - 1) * weekMs;
    const buckets = new Array<number>(weeks).fill(0);

    for (const raw of dates) {
      const parsed = new Date(raw);
      if (Number.isNaN(parsed.getTime())) continue;
      const offset = Math.floor((parsed.getTime() - start) / weekMs);
      if (offset >= 0 && offset < weeks) buckets[offset] += 1;
    }
    return buckets;
  }, [dates, range]);

  const total = series.reduce((sum, value) => sum + value, 0);
  const max = Math.max(1, ...series);

  const span = W - PAD * 2;
  const usable = H - 34;
  const points = series.map((value, index) => {
    const x =
      series.length === 1
        ? PAD + span / 2
        : PAD + (index * span) / (series.length - 1);
    // Inset the scale so the peak never touches the panel edge.
    const y = 8 + usable - (value / max) * usable;
    return { x, y, value };
  });

  const line = points.map((p) => `${p.x},${p.y}`).join(" ");
  const area =
    points.length > 0
      ? `M${points[0].x},${H - 26} L${points
          .map((p) => `${p.x},${p.y}`)
          .join(" L")} L${points[points.length - 1].x},${H - 26} Z`
      : "";

  const gridValues = [max, max * 0.75, max * 0.5, max * 0.25, 0];
  const rangeLabel = range === "6M" ? "6 months" : `${range.slice(0, -1)} weeks`;

  return (
    <article className="flex min-h-[307px] flex-col rounded-lg border border-surface-border bg-surface-panel p-5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display text-body font-semibold text-ink">
            Analysis activity
          </h2>
          <p className="mt-0.5 text-caption text-ink-muted">
            Completed analyses across your workspace
          </p>
        </div>
        <div
          className="flex shrink-0 gap-0.5 rounded-[7px] border border-surface-border bg-surface-sunken p-0.5"
          role="group"
          aria-label="Chart range"
        >
          {RANGES.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setRange(item)}
              aria-pressed={range === item}
              className={`h-[23px] min-w-[30px] rounded-[5px] px-2 text-[11px] font-semibold transition-all duration-150 ease-standard focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500 ${
                range === item
                  ? "bg-surface-panel text-ink shadow-card"
                  : "text-ink-muted hover:text-ink"
              }`}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 flex items-baseline gap-2">
        {loading ? (
          <span className="font-display text-h1 font-bold text-ink-faint">&hellip;</span>
        ) : (
          <>
            <strong className="tabular font-display text-h1 font-bold tracking-[-0.02em] text-ink">
              {total}
            </strong>
            <span className="text-caption text-ink-muted">in the last {rangeLabel}</span>
          </>
        )}
      </div>

      <div className="mt-3 flex-1">{loading ? (
          <div className="h-[190px] w-full animate-pulse rounded-md bg-surface-sunken" />
        ) : total === 0 ? (
          <div className="flex h-[190px] flex-col items-center justify-center gap-2 text-center">
            <Icon name="chart-line" size={22} className="text-ink-faint" />
            <p className="text-caption text-ink-muted">
              No analyses in this period yet.
            </p>
          </div>
        ) : (
          <div className="relative h-[190px] w-full">
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-y-0 left-0 flex flex-col justify-between pb-[26px]"
            >
              {gridValues.map((value, index) => (
                <span
                  key={index}
                  className="tabular text-[10px] leading-none text-ink-faint"
                >
                  {Math.round(value)}
                </span>
              ))}
            </div>
            <svg
              viewBox={`0 0 ${W} ${H}`}
              preserveAspectRatio="none"
              className="h-[190px] w-full pl-7"
              role="img"
              aria-label={`${total} analyses over the last ${rangeLabel}`}
            >
              <defs>
                <linearGradient id="activity-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6C4BF4" stopOpacity="0.18" />
                  <stop offset="100%" stopColor="#6C4BF4" stopOpacity="0" />
                </linearGradient>
              </defs>
              <path d={area} fill="url(#activity-fill)" />
              <polyline
                points={line}
                fill="none"
                stroke="#6C4BF4"
                strokeWidth="2"
                strokeLinejoin="round"
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
              />
              {points.map((point, index) =>
                point.value === 0 ? null : (
                  <circle
                    key={index}
                    cx={point.x}
                    cy={point.y}
                    r="3"
                    fill="#FFFFFF"
                    stroke="#6C4BF4"
                    strokeWidth="2"
                    vectorEffect="non-scaling-stroke"
                  >
                    <title>{`${point.value} analyses`}</title>
                  </circle>
                )
              )}
            </svg>
          </div>
        )}</div>
    </article>
  );
}

export default ActivityChart;