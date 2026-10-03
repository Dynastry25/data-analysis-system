"use client";

import { useMemo } from "react";

import { Badge } from "./Badge";
import { Icon } from "./Icon";
import { colorForIndex } from "@/lib/constants";

/** One binned point from the engine's residual plot. */
export interface ResidualPoint {
  predicted: number;
  residual: number;
  residual_sd?: number | null;
  count?: number;
}

export interface ResidualPattern {
  status?: "pass" | "warn" | "insufficient";
  detail?: string;
  slope?: number | null;
  spread_growth?: number | null;
}

const PATTERN_META: Record<
  NonNullable<ResidualPattern["status"]>,
  { label: string; tone: "success" | "warning" | "neutral"; icon: "check" | "alert-triangle" | "info" }
> = {
  pass: { label: "Inapatikana", tone: "success", icon: "check" },
  warn: { label: "Tazama", tone: "warning", icon: "alert-triangle" },
  insufficient: { label: "Hakuna data", tone: "neutral", icon: "info" },
};

const WIDTH = 640;
const HEIGHT = 220;
const PAD_LEFT = 52;
const PAD_RIGHT = 16;
const PAD_TOP = 12;
const PAD_BOTTOM = 34;

function niceTicks(low: number, high: number, count = 5): number[] {
  if (!Number.isFinite(low) || !Number.isFinite(high) || high <= low) return [low];
  const raw = (high - low) / (count - 1);
  const magnitude = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? magnitude * 10;
  const start = Math.ceil(low / step) * step;
  const ticks: number[] = [];
  for (let value = start; value <= high + step * 0.001; value += step) {
    ticks.push(Number(value.toFixed(10)));
  }
  return ticks;
}

function shortNumber(value: number): string {
  const magnitude = Math.abs(value);
  if (magnitude === 0) return "0";
  if (magnitude < 0.001 || magnitude >= 1e6) return value.toExponential(1);
  if (magnitude < 1) return value.toFixed(3);
  if (magnitude < 100) return value.toFixed(2);
  return value.toLocaleString("en-KE", { maximumFractionDigits: 0 });
}

interface ResidualDiagnosticProps {
  points: ResidualPoint[];
  pattern?: ResidualPattern | null;
  className?: string;
}

/**
 * Predicted versus residual, the way the prototype shows it.
 *
 * The points are the engine's binned means, not a scatter of individual rows.
 * Two things have to be readable here: where the points sit relative to zero,
 * and whether they curve or fan out. So zero is drawn as a real axis, the
 * spread per band is drawn as a vertical range, and the pattern verdict is
 * printed under the chart rather than left to the eye.
 */
export function ResidualDiagnostic({
  points,
  pattern = null,
  className = "",
}: ResidualDiagnosticProps) {
  const geometry = useMemo(() => {
    if (points.length === 0) return null;

    const xValues = points.map((point) => point.predicted);
    const xLow = Math.min(...xValues);
    const xHigh = Math.max(...xValues);

    // The residual range must include zero: a residual plot where zero is off
    // the chart is the one mistake that hides the only thing it can show.
    const residualValues = points.flatMap((point) => {
      const centre = point.residual;
      const spread = point.residual_sd ?? 0;
      return [centre - spread, centre, centre + spread];
    });
    const yLow = Math.min(0, ...residualValues);
    const yHigh = Math.max(0, ...residualValues);
    const yPad = (yHigh - yLow) * 0.08 || 1;

    const plotWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
    const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
    const sx = (value: number) =>
      PAD_LEFT + ((value - xLow) / (xHigh - xLow || 1)) * plotWidth;
    const sy = (value: number) =>
      PAD_TOP + (1 - (value - (yLow - yPad)) / (yHigh - yLow + yPad * 2 || 1)) * plotHeight;

    return {
      xLow,
      xHigh,
      yLow: yLow - yPad,
      yHigh: yHigh + yPad,
      sx,
      sy,
      xTicks: niceTicks(xLow, xHigh),
      yTicks: niceTicks(yLow - yPad, yHigh + yPad),
    };
  }, [points]);

  const meta = pattern?.status ? PATTERN_META[pattern.status] : null;

  return (
    <div className={className}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-overline uppercase tracking-wide text-ink-muted">
          Residual diagnostic
        </p>
        {meta && (
          <Badge tone={meta.tone} size="sm" icon={meta.icon}>
            {meta.label}
          </Badge>
        )}
      </div>

      {geometry === null ? (
        <p className="mt-3 flex items-center gap-2 rounded-md border border-dashed border-surface-border-strong bg-surface-sunken px-3 py-6 text-center text-caption text-ink-muted">
          <Icon name="info" size={14} className="shrink-0" />
          Engine hajatuma vitu vya kuonyesha chati hii. Inaweza kutumika kwa
          regression ya kawaida tu.
        </p>
      ) : (
        <>
          <div className="mt-2 overflow-x-auto">
            <svg
              viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
              className="h-auto w-full min-w-[30rem]"
              role="img"
              aria-label={`Chati ya predicted dhidi ya residual. ${points.length} vipindi, kuanzia ${shortNumber(geometry.xLow)} hadi ${shortNumber(geometry.xHigh)}.`}
            >
              {/* Horizontal gridlines and the y axis */}
              {geometry.yTicks.map((tick) => (
                <g key={`y-${tick}`}>
                  <line
                    x1={PAD_LEFT}
                    x2={WIDTH - PAD_RIGHT}
                    y1={geometry.sy(tick)}
                    y2={geometry.sy(tick)}
                    stroke={tick === 0 ? "#A6A3AD" : "#E7E5EB"}
                    strokeWidth={tick === 0 ? 1.5 : 1}
                    strokeDasharray={tick === 0 ? "4 3" : undefined}
                  />
                  <text
                    x={PAD_LEFT - 8}
                    y={geometry.sy(tick) + 4}
                    textAnchor="end"
                    className="fill-ink-muted"
                    style={{ fontSize: 11, fontFamily: "ui-monospace, monospace" }}
                  >
                    {shortNumber(tick)}
                  </text>
                </g>
              ))}

              {/* The zero line is the reference the whole chart is read against */}
              <text
                x={PAD_LEFT - 8}
                y={geometry.sy(0) - 6}
                textAnchor="end"
                className="fill-ink-secondary"
                style={{ fontSize: 10, fontWeight: 600 }}
              >
                0
              </text>

              {/* Per-band spread, so a funnel is visible and not just implied */}
              {points.map((point) => {
                const spread = point.residual_sd ?? 0;
                if (spread <= 0) return null;
                const top = geometry.sy(point.residual + spread);
                const bottom = geometry.sy(point.residual - spread);
                return (
                  <line
                    key={`spread-${point.predicted}`}
                    x1={geometry.sx(point.predicted)}
                    x2={geometry.sx(point.predicted)}
                    y1={top}
                    y2={bottom}
                    stroke={colorForIndex(0)}
                    strokeWidth={2}
                    strokeOpacity={0.28}
                    strokeLinecap="round"
                  />
                );
              })}

              {/* The binned mean residuals */}
              {points.map((point) => (
                <circle
                  key={`point-${point.predicted}`}
                  cx={geometry.sx(point.predicted)}
                  cy={geometry.sy(point.residual)}
                  r={3.5}
                  fill={colorForIndex(0)}
                  fillOpacity={0.85}
                >
                  <title>
                    {`predicted ${shortNumber(point.predicted)} · residual ${shortNumber(
                      point.residual
                    )}${point.residual_sd ? ` · ±${shortNumber(point.residual_sd)}` : ""}${
                      point.count ? ` · n=${point.count}` : ""
                    }`}
                  </title>
                </circle>
              ))}

              {/* x axis */}
              <line
                x1={PAD_LEFT}
                x2={WIDTH - PAD_RIGHT}
                y1={HEIGHT - PAD_BOTTOM}
                y2={HEIGHT - PAD_BOTTOM}
                stroke="#CBD5E1"
              />
              {geometry.xTicks.map((tick) => (
                <text
                  key={`x-${tick}`}
                  x={geometry.sx(tick)}
                  y={HEIGHT - PAD_BOTTOM + 16}
                  textAnchor="middle"
                  className="fill-ink-muted"
                  style={{ fontSize: 11, fontFamily: "ui-monospace, monospace" }}
                >
                  {shortNumber(tick)}
                </text>
              ))}

              <text
                x={(PAD_LEFT + WIDTH - PAD_RIGHT) / 2}
                y={HEIGHT - 4}
                textAnchor="middle"
                className="fill-ink-secondary"
                style={{ fontSize: 11 }}
              >
                Predicted
              </text>
              <text
                x={12}
                y={HEIGHT / 2}
                textAnchor="middle"
                className="fill-ink-secondary"
                style={{ fontSize: 11 }}
                transform={`rotate(-90 12 ${HEIGHT / 2})`}
              >
                Residual
              </text>
            </svg>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-caption text-ink-muted">
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: colorForIndex(0) }}
              />
              wastani wa residual kwa kila kundi
            </span>
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block h-3 w-0.5 rounded"
                style={{ backgroundColor: colorForIndex(0), opacity: 0.4 }}
              />
              ±1 SD
            </span>
            <span>
              Mstari wa sifuri ndio kitu cha kuangalia: makundi yaliyo juu yake
              yanapotiwa, yaliyo chini yake yanakosewa.
            </span>
          </div>
        </>
      )}

      {pattern?.detail && (
        <p
          className={`mt-3 flex items-start gap-2 rounded-md border px-3 py-2.5 text-caption ${
            pattern.status === "warn"
              ? "border-warning/30 bg-warning-bg text-warning-700"
              : pattern.status === "pass"
                ? "border-success/30 bg-success-bg text-success-700"
                : "border-surface-border bg-surface-sunken text-ink-secondary"
          }`}
        >
          <Icon name="info" size={14} className="mt-0.5 shrink-0" />
          <span>{pattern.detail}</span>
        </p>
      )}
    </div>
  );
}

export default ResidualDiagnostic;
