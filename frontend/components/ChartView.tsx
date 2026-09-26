"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import type { Data, Layout } from "plotly.js";

import { ChartData } from "@/lib/api";
import { CHART_PALETTE } from "@/lib/constants";
import { Icon } from "./Icon";
import { ChartSkeleton } from "./Skeleton";

// Plotly touches `window`, so it is loaded on the client only.
const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => <ChartSkeleton />,
});

interface ChartViewProps {
  data: ChartData | null;
  height?: number;
}

const GRID_COLOR = "#E2E8F0";
const AXIS_LINE_COLOR = "#CBD5E1";
const AXIS_FONT = { family: "Inter, Segoe UI, sans-serif", size: 12, color: "#475569" };
const VALUE_FONT = { family: "IBM Plex Mono, ui-monospace, monospace", size: 11, color: "#334155" };

function formatNumber(value: unknown): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "";
  if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (Math.abs(value) >= 1e3) return `${(value / 1e3).toFixed(1)}k`;
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

const HOVER = {
  bgcolor: "#0F172A",
  bordercolor: "#0F172A",
  font: { family: "Inter, Segoe UI, sans-serif", size: 12, color: "#F8FAFC" },
  namelength: -1,
} as const;

/** Plotly chart fed by the backend's `chart_data` payload. */
export function ChartView({ data, height = 380 }: ChartViewProps) {
  const traces = useMemo<Data[]>(() => {
    if (!data?.series?.length) return [];
    return data.series.map((series, index) => {
      const color = CHART_PALETTE[index % CHART_PALETTE.length];
      const isNumericY = data.chart_type !== "histogram";
      if (data.chart_type === "histogram") {
        return {
          type: "histogram",
          name: series.name,
          x: series.x as (string | number)[],
          nbinsx: series.nbinsx ?? 20,
          marker: { color, line: { color: "#ffffff", width: 1 } },
          opacity: 0.85,
          hovertemplate: `%{x}<br>Count: %{y}<extra>${series.name}</extra>`,
        } as Data;
      }
      if (data.chart_type === "scatter") {
        return {
          type: "scatter",
          mode: "markers",
          name: series.name,
          x: series.x as number[],
          y: (series.y ?? []) as number[],
          marker: { color, size: 7, opacity: 0.75, line: { color: "#ffffff", width: 0.5 } },
          hovertemplate: `%{x}, %{y}<extra>${series.name}</extra>`,
        } as Data;
      }
      if (data.chart_type === "line") {
        return {
          type: "scatter",
          mode: "lines+markers",
          name: series.name,
          x: series.x as (string | number)[],
          y: (series.y ?? []) as number[],
          line: { color, width: 2 },
          marker: { color, size: 6 },
          hovertemplate: `%{x}<br>${data.y_label}: %{y}<extra>${series.name}</extra>`,
        } as Data;
      }
      return {
        type: "bar",
        name: series.name,
        x: series.x as (string | number)[],
        y: (series.y ?? []) as number[],
        marker: { color, line: { color: "rgba(255,255,255,0.6)", width: 0.5 } },
        text: isNumericY
          ? ((series.y ?? []) as number[]).map((value) => formatNumber(value))
          : undefined,
        textposition: "outside",
        textfont: VALUE_FONT,
        cliponaxis: false,
        hovertemplate: `%{x}<br>${data.y_label}: %{y}<extra>${series.name}</extra>`,
      } as Data;
    });
  }, [data]);

  if (!data || traces.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-surface-border-strong bg-surface-sunken px-6 py-10 text-center">
        <Icon name="chart" size={22} className="text-ink-muted" />
        <p className="text-body text-ink-secondary">
          Hakuna data ya kutosha kuchora chati hii.
        </p>
        <p className="max-w-sm text-caption text-ink-muted">
          Chagua columns kwenye dataset yako kisha bonyeza &ldquo;Tengeneza chati&rdquo; ili
          kuona data hapa.
        </p>
      </div>
    );
  }

  const layout: Partial<Layout> = {
    height,
    margin: { l: 64, r: 24, t: 28, b: 64 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Inter, Segoe UI, sans-serif", size: 12, color: "#0F172A" },
    hovermode: "closest",
    hoverlabel: HOVER,
    xaxis: {
      title: { text: data.x_label, font: AXIS_FONT, standoff: 10 },
      gridcolor: GRID_COLOR,
      linecolor: AXIS_LINE_COLOR,
      zeroline: false,
      automargin: true,
    },
    yaxis: {
      title: { text: data.y_label, font: AXIS_FONT, standoff: 10 },
      gridcolor: GRID_COLOR,
      linecolor: AXIS_LINE_COLOR,
      zeroline: false,
      automargin: true,
    },
    showlegend: data.series.length > 1,
    legend: { orientation: "h", y: -0.2, font: AXIS_FONT },
    bargap: 0.25,
    transition: { duration: 400, easing: "cubic-out" },
  };

  const description =
    `Chart: ${data.chart_type} chart. ${data.y_label} by ${data.x_label}. ` +
    `${data.series.length} series, ${data.series[0]?.x?.length ?? 0} points.`;

  return (
    <div role="img" aria-label={description}>
      <Plot
        data={traces}
        layout={layout}
        config={{
          responsive: true,
          displaylogo: false,
          displayModeBar: false,
          modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines"],
        }}
        style={{ width: "100%", height }}
        useResizeHandler
      />
    </div>
  );
}

export default ChartView;
