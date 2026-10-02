"use client";

import dynamic from "next/dynamic";
import { useCallback, useMemo, useRef, useState } from "react";
import type { Data, Layout } from "plotly.js";

import Plotly from "plotly.js";

import { ChartData, ChartFormat } from "@/lib/api";
import { paletteFor } from "@/lib/constants";
import { Button } from "./Button";
import { Icon } from "./Icon";
import { ChartSkeleton } from "./Skeleton";

// Plotly touches `window`, so it is loaded on the client only.
const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => <ChartSkeleton />,
});

/** What the chart was drawn from, so a reader can check it. */
interface ChartSource {
  dataset_name?: string;
  dataset_version?: number;
  rows_total?: number;
}

interface ChartViewProps {
  data: ChartData | null;
  height?: number;
  /** Saved presentation choices (Visualization Studio). */
  format?: ChartFormat | null;
  /** Overrides the auto title when the surrounding card already names it. */
  title?: string;
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
export function ChartView({ data, height = 380, format, title }: ChartViewProps) {
  const traces = useMemo<Data[]>(() => {
    if (!data?.series?.length) return [];
    const palette = paletteFor(format?.palette);
    return data.series.map((series, index) => {
      const color = palette[index % palette.length];
      const isNumericY = data.chart_type !== "histogram";
      const showLabels =
        format?.show_data_labels !== false && isNumericY && data.chart_type !== "scatter";
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
        text: showLabels
          ? ((series.y ?? []) as number[]).map((value) => formatNumber(value))
          : undefined,
        textposition: "outside",
        textfont: VALUE_FONT,
        cliponaxis: false,
        hovertemplate: `%{x}<br>${data.y_label}: %{y}<extra>${series.name}</extra>`,
      } as Data;
    });
  }, [data, format]);

  const [showTable, setShowTable] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const hostRef = useRef<HTMLDivElement>(null);

  // Source attribution travels in `meta`; a chart that cannot name the version
  // it came from cannot be checked against the data.
  const source = (data?.meta ?? undefined) as ChartSource | undefined;
  const pointsAvailable =
    data?.series?.reduce((total, series) => total + (series.x?.length ?? 0), 0) ?? 0;
  const pointsDrawn = pointsAvailable;

  const exportImage = useCallback(async () => {
    const graph = hostRef.current?.firstElementChild as any;
    if (!graph || typeof Plotly === "undefined") return;
    try {
      const url = await Plotly.toImage(graph, {
        format: "png",
        height,
        width: graph.clientWidth || 900,
      });
      // toImage resolves to a data URL; the download name lives on the anchor,
      // because plotly has no filename option of its own.
      const link = document.createElement("a");
      link.href = url;
      link.download = "statflow-chart.png";
      link.click();
    } catch {
      // Export is a convenience: a failure here must not take the chart down.
    }
  }, [height]);

  const tableRows = useMemo(() => {
    if (!data?.series?.length) return [];
    const first = data.series[0];
    return (first.x ?? []).map((x, index) => [
      x,
      ...data.series.map((series) => {
        const value = series.y?.[index];
        return value === null || value === undefined ? null : value;
      }),
    ]);
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

  const showGrid = format?.show_grid !== false;
  const xType = format?.x_scale === "log" ? "log" : undefined;
  const yType = format?.y_scale === "log" ? "log" : undefined;

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
      gridcolor: showGrid ? GRID_COLOR : "rgba(0,0,0,0)",
      type: xType,
      linecolor: AXIS_LINE_COLOR,
      zeroline: false,
      automargin: true,
    },
    yaxis: {
      title: { text: data.y_label, font: AXIS_FONT, standoff: 10 },
      gridcolor: showGrid ? GRID_COLOR : "rgba(0,0,0,0)",
      type: yType,
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
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-body font-medium text-ink">
            {title || `${data.y_label} by ${data.x_label}`}
          </p>
          <p className="text-caption text-ink-muted">
            {data.chart_type}
            {pointsDrawn > 0 && ` · ${pointsDrawn} points plotted`}
            {pointsDrawn < pointsAvailable && ` · ${pointsAvailable - pointsDrawn} not shown`}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="small"
            icon="table"
            onClick={() => setShowTable((current) => !current)}
            aria-pressed={showTable}
          >
            Data
          </Button>
          <Button
            variant="ghost"
            size="small"
            icon="download"
            onClick={exportImage}
            aria-label="Pakua chati kama picha"
          >
            PNG
          </Button>
          <Button
            variant="ghost"
            size="small"
            icon={expanded ? "close" : "eye"}
            onClick={() => setExpanded((current) => !current)}
            aria-pressed={expanded}
            aria-label={expanded ? "Fungua chati" : "Onyesha chati nzima"}
          />
        </div>
      </div>

      <div
        role="img"
        aria-label={description}
        className={expanded ? "fixed inset-0 z-50 overflow-auto bg-surface-panel p-6" : ""}
      >
        <div ref={hostRef} className="h-full w-full">
        <Plot
          data={traces}
          layout={layout}
          config={{
            responsive: true,
            displaylogo: false,
            // Plotly's own modebar is off: it duplicates the toolbar above and
            // the design rules ask for a clean surface. The buttons that are
            // kept are the ones the rules require -- export and zoom -- and
            // they are provided deliberately rather than inherited.
            displayModeBar: false,
            modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines"],
          }}
          style={{ width: "100%", height: expanded ? Math.max(height, 520) : height }}
          useResizeHandler
        />
        </div>
      </div>

      {showTable && (
        <div className="max-h-64 overflow-auto rounded-md border border-surface-border">
          <table className="w-full text-caption">
            <thead className="sticky top-0 bg-surface-sunken text-left">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium text-ink-secondary">
                  {data.x_label}
                </th>
                {data.series.map((series) => (
                  <th key={series.name} scope="col" className="px-3 py-2 font-medium text-ink-secondary">
                    {series.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tableRows.map((row, index) => (
                <tr key={index} className="border-t border-surface-border">
                  <td className="px-3 py-1.5 text-ink-secondary">{String(row[0])}</td>
                  {data.series.map((series) => (
                    <td key={series.name} className="px-3 py-1.5 font-mono text-ink">
                      {row[1] === null || row[1] === undefined ? "—" : String(row[1])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {source && (
        <p className="text-caption text-ink-muted">
          Chanzo: {source.dataset_name}
          {source.dataset_version ? ` · version v${source.dataset_version}` : ""}
          {source.rows_total ? ` · ${source.rows_total} rows` : ""}
        </p>
      )}
    </div>
  );
}
export default ChartView;
