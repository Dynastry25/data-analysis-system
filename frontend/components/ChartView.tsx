"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import type { Data, Layout } from "plotly.js";

import { ChartData } from "@/lib/api";
import { CHART_PALETTE } from "@/lib/constants";
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

const GRID_COLOR = "#E5E7EB";
const AXIS_FONT = { family: "Inter, Segoe UI, sans-serif", size: 12, color: "#4B5563" };

/** Plotly chart fed by the backend's `chart_data` payload. */
export function ChartView({ data, height = 380 }: ChartViewProps) {
  const traces = useMemo<Data[]>(() => {
    if (!data?.series?.length) return [];
    return data.series.map((series, index) => {
      const color = CHART_PALETTE[index % CHART_PALETTE.length];
      if (data.chart_type === "histogram") {
        return {
          type: "histogram",
          name: series.name,
          x: series.x as (string | number)[],
          nbinsx: series.nbinsx ?? 20,
          marker: { color, line: { color: "#ffffff", width: 1 } },
          opacity: 0.85,
        } as Data;
      }
      if (data.chart_type === "scatter") {
        return {
          type: "scatter",
          mode: "markers",
          name: series.name,
          x: series.x as number[],
          y: (series.y ?? []) as number[],
          marker: { color, size: 7, opacity: 0.75 },
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
        } as Data;
      }
      return {
        type: "bar",
        name: series.name,
        x: series.x as (string | number)[],
        y: (series.y ?? []) as number[],
        marker: { color },
      } as Data;
    });
  }, [data]);

  if (!data || traces.length === 0) {
    return (
      <div className="rounded border border-dashed border-neutral-200 bg-neutral-50 p-6 text-center text-body text-neutral-600">
        Hakuna data ya kutosha kuchora chati hii — choose columns and generate the chart.
      </div>
    );
  }

  const layout: Partial<Layout> = {
    height,
    margin: { l: 64, r: 24, t: 24, b: 64 },
    paper_bgcolor: "#FFFFFF",
    plot_bgcolor: "#FFFFFF",
    font: { family: "Inter, Segoe UI, sans-serif", size: 12, color: "#111827" },
    xaxis: {
      title: { text: data.x_label, font: AXIS_FONT },
      gridcolor: GRID_COLOR,
      zeroline: false,
      automargin: true,
    },
    yaxis: {
      title: { text: data.y_label, font: AXIS_FONT },
      gridcolor: GRID_COLOR,
      zeroline: false,
      automargin: true,
    },
    showlegend: data.series.length > 1,
    legend: { orientation: "h", y: -0.2 },
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
        config={{ responsive: true, displaylogo: false, displayModeBar: false }}
        style={{ width: "100%", height }}
        useResizeHandler
      />
    </div>
  );
}

export default ChartView;
