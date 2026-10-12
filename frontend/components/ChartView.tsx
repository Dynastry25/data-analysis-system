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

/*
 * Chart colours are hardcoded rather than themed: a canvas SVG cannot read a
 * Tailwind class, and a chart whose axes match neither the page nor the data
 * palette is worse than one that at least matches the page. These mirror the
 * StatFlow design tokens.
 */
const GRID_COLOR = "#E7E5EB";
const AXIS_LINE_COLOR = "#D4D1DA";
const AXIS_FONT = { family: "DM Sans, Segoe UI, sans-serif", size: 12, color: "#777482" };
const VALUE_FONT = { family: "IBM Plex Mono, ui-monospace, monospace", size: 11, color: "#334155" };

function formatNumber(value: unknown): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "";
  if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (Math.abs(value) >= 1e3) return `${(value / 1e3).toFixed(1)}k`;
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

const HOVER = {
  bgcolor: "#17151F",
  bordercolor: "#17151F",
  font: { family: "DM Sans, Segoe UI, sans-serif", size: 12, color: "#F5F6FA" },
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
      if (data.chart_type === "pie") {
        return {
          type: "pie",
          name: series.name,
          labels: (series.labels ?? []) as (string | number)[],
          values: (series.values ?? []) as number[],
          marker: { colors: palette },
          textinfo: "label+percent",
          textposition: "inside",
          insidetextorientation: "auto",
          hovertemplate: `%{label}<br>%{value} (%{percent})<extra></extra>`,
        } as Data;
      }
      if (data.chart_type === "heatmap") {
        return {
          type: "heatmap",
          name: series.name,
          x: (series.x ?? []) as (string | number)[],
          y: (series.y ?? []) as (string | number)[],
          z: (series.z ?? []) as number[][],
          colorscale: "Blues",
          showscale: true,
          hovertemplate: `%{x} · %{y}<br>%{z}<extra>${series.name}</extra>`,
        } as Data;
      }
      if (data.chart_type === "box") {
        return {
          type: "box",
          name: series.name,
          y: (series.y ?? []) as number[],
          marker: { color },
          boxpoints: "outliers",
          hovertemplate: `${series.name}<br>Median: %{median}<br>Q1: %{q1} · Q3: %{q3}<extra></extra>`,
        } as Data;
      }
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
        // size_by arrives as raw values; Plotly wants pixel diameters, so the
        // mapping is linear from the observed range to a readable 6–22px.
        const rawSizes = series.sizes ?? [];
        const finite = rawSizes.filter(
          (value): value is number => typeof value === "number" && Number.isFinite(value)
        );
        const minSize = finite.length ? Math.min(...finite) : 0;
        const maxSize = finite.length ? Math.max(...finite) : 0;
        const span = maxSize - minSize || 1;
        const markerSizes = rawSizes.map((value) =>
          typeof value === "number" && Number.isFinite(value)
            ? 6 + (16 * (value - minSize)) / span
            : 7
        );
        return {
          type: "scatter",
          mode: "markers",
          name: series.name,
          x: series.x as number[],
          y: (series.y ?? []) as number[],
          marker: {
            color,
            size: markerSizes.length ? markerSizes : 7,
            sizemode: "diameter",
            opacity: 0.75,
            line: { color: "#ffffff", width: 0.5 },
          },
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
  // Plotly's zoom buttons live in the modebar; the studio keeps its own small
  // toolbar (fixedZoomIn / fixedZoomOut / reset) instead so zoom is one tap on
  // touch screens, where the modebar's drag-zoom is unreliable.
  const [zoomLevel, setZoomLevel] = useState(1);
  const hostRef = useRef<HTMLDivElement>(null);

  // Source attribution travels in `meta`; a chart that cannot name the version
  // it came from cannot be checked against the data.
  const source = (data?.meta ?? undefined) as ChartSource | undefined;
  const pointsAvailable =
    data?.series?.reduce((total, series) => total + (series.x?.length ?? 0), 0) ?? 0;
  const pointsDrawn = pointsAvailable;

  const exportImage = useCallback(
    async (imageFormat: "png" | "svg" | "pdf" = "png") => {
      const graph = hostRef.current?.firstElementChild as any;
      if (!graph || typeof Plotly === "undefined") return;
      try {
        // Plotly's types list the raster formats only, but `toImage` takes a
        // "pdf" value at runtime and it has been offered since the studio added
        // the download menu. The cast keeps that feature rather than deleting it
        // over a typing gap.
        const url = await Plotly.toImage(graph, {
          format: imageFormat as "png" | "svg" | "jpeg" | "webp",
          height,
          width: graph.clientWidth || 900,
        });
        const link = document.createElement("a");
        link.href = url;
        link.download = `statflow-chart.${imageFormat}`;
        link.click();
      } catch {
        // Export is a convenience: a failure here must not take the chart down.
      }
    },
    [height]
  );

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

  // Zoom is a camera on fixed data: narrowing the visible window never changes
  // the series. Ranges are recomputed from the drawn points, so zooming works
  // identically for bars, lines, scatters, histograms and boxes. Pie and
  // heatmap have no meaningful cartesian window, so the buttons stay hidden
  // for them rather than doing nothing.
  //
  // These sit above the early return below on purpose: hooks must run in the
  // same order on every render, and "no data yet" is a render like any other.
  const zoomable = data?.chart_type !== "pie" && data?.chart_type !== "heatmap";
  const numericExtent = useMemo(() => {
    const xs: number[] = [];
    const ys: number[] = [];
    for (const series of data?.series ?? []) {
      for (const value of series.x ?? []) {
        if (typeof value === "number" && Number.isFinite(value)) xs.push(value);
      }
      for (const value of series.y ?? []) {
        if (typeof value === "number" && Number.isFinite(value)) ys.push(value);
      }
    }
    return { xs, ys };
  }, [data]);
  const zoomWindow = useMemo(() => {
    if (!zoomable || zoomLevel === 1 || data?.chart_type === "box") {
      return { xRange: undefined as undefined | number[], yRange: undefined as undefined | number[] };
    }
    const focus = (values: number[]) => {
      if (values.length === 0) return undefined;
      const low = Math.min(...values);
      const high = Math.max(...values);
      const span = high - low || Math.abs(high) || 1;
      const pad = span * 0.05;
      const window = span / zoomLevel;
      const centre = (low + high) / 2;
      return [centre - window / 2 - pad, centre + window / 2 + pad];
    };
    return { xRange: focus(numericExtent.xs), yRange: focus(numericExtent.ys) };
  }, [zoomable, zoomLevel, numericExtent, data?.chart_type]);

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
    font: { family: "DM Sans, Segoe UI, sans-serif", size: 12, color: "#17151F" },
    hovermode: "closest",
    hoverlabel: HOVER,
    xaxis: {
      title: { text: data.x_label, font: AXIS_FONT, standoff: 10 },
      gridcolor: showGrid ? GRID_COLOR : "rgba(0,0,0,0)",
      type: xType,
      linecolor: AXIS_LINE_COLOR,
      zeroline: false,
      automargin: true,
      ...(zoomWindow.xRange ? { range: zoomWindow.xRange } : {}),
    },
    yaxis: {
      title: { text: data.y_label, font: AXIS_FONT, standoff: 10 },
      gridcolor: showGrid ? GRID_COLOR : "rgba(0,0,0,0)",
      type: yType,
      linecolor: AXIS_LINE_COLOR,
      zeroline: false,
      automargin: true,
      ...(zoomWindow.yRange ? { range: zoomWindow.yRange } : {}),
    },
    showlegend: data.series.length > 1,
    legend: { orientation: "h", y: -0.2, font: AXIS_FONT },
    bargap: 0.25,
    transition: { duration: 400, easing: "cubic-out" },
    annotations: (data.annotations ?? []).map((annotation) => ({
      text: annotation.text,
      x: annotation.x as string | number,
      y: (annotation.y ?? "") as string | number,
      xref: "x",
      yref: "y",
      showarrow: true,
      arrowhead: 2,
      arrowcolor: "#17151F",
      bgcolor: "rgba(245,246,250,0.92)",
      bordercolor: "#D4D1DA",
      font: { family: "DM Sans, Segoe UI, sans-serif", size: 11, color: "#17151F" },
    })),
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
          {zoomable && (
            <>
              <Button
                variant="ghost"
                size="small"
                icon="plus"
                onClick={() => setZoomLevel((level) => Math.min(level * 1.5, 8))}
                disabled={zoomLevel >= 8}
                aria-label="Zoom in"
              />
              <Button
                variant="ghost"
                size="small"
                icon="minus"
                onClick={() => setZoomLevel((level) => Math.max(level / 1.5, 1))}
                disabled={zoomLevel <= 1}
                aria-label="Zoom out"
              />
              <Button
                variant="ghost"
                size="small"
                icon="refresh"
                onClick={() => setZoomLevel(1)}
                disabled={zoomLevel === 1}
                aria-label="Reset zoom"
              />
            </>
          )}
          <Button
            variant="ghost"
            size="small"
            icon="download"
            onClick={() => void exportImage("png")}
            aria-label="Pakua chati kama picha"
          >
            PNG
          </Button>
          <Button
            variant="ghost"
            size="small"
            icon="download"
            onClick={() => void exportImage("svg")}
            aria-label="Download chart as vector graphic"
          >
            SVG
          </Button>
          <Button
            variant="ghost"
            size="small"
            icon="download"
            onClick={() => void exportImage("pdf")}
            aria-label="Download chart as PDF"
          >
            PDF
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
