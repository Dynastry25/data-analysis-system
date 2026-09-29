/**
 * Design system constants — Data Analysis Platform
 * Keep in sync with ui_ux_design_system.md
 */

// Okabe-Ito colorblind-safe palette for chart series.
// Rule: reuse the same color for the same category across every chart of a dataset.
export const CHART_PALETTE: string[] = [
  "#0072B2",
  "#E69F00",
  "#009E73",
  "#CC79A7",
  "#56B4E9",
  "#D55E00",
  "#F0E442",
  "#999999",
];

// Visualization Studio palettes. "default" must stay the Okabe-Ito palette so
// every existing chart renders unchanged.
export const CHART_PALETTES: Record<string, { label: string; colors: string[] }> = {
  default: {
    label: "Default (Okabe-Ito)",
    colors: CHART_PALETTE,
  },
  ocean: {
    label: "Ocean",
    colors: ["#0369A1", "#0EA5E9", "#38BDF8", "#7DD3FC", "#BAE6FD", "#0C4A6E"],
  },
  sunset: {
    label: "Sunset",
    colors: ["#EA580C", "#F97316", "#FB923C", "#FDBA74", "#431407", "#9A3412"],
  },
  forest: {
    label: "Forest",
    colors: ["#166534", "#22C55E", "#4ADE80", "#86EFAC", "#14532D", "#15803D"],
  },
};

export function paletteFor(name?: string | null): string[] {
  return CHART_PALETTES[name ?? "default"]?.colors ?? CHART_PALETTE;
}

export const SPACING = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  "2xl": 32,
  "3xl": 48,
  "4xl": 64,
} as const;

export const SEMANTIC_COLORS = {
  success: { base: "#16A34A", bg: "#F0FDF4" },
  warning: { base: "#D97706", bg: "#FFFBEB" },
  danger: { base: "#DC2626", bg: "#FEF2F2" },
  info: { base: "#0284C7", bg: "#F0F9FF" },
} as const;

export const CHART_TYPES = ["bar", "line", "scatter", "histogram"] as const;
export type ChartType = (typeof CHART_TYPES)[number];

export const ANALYSIS_TYPES = [
  "descriptive_stats",
  "correlation",
  "regression",
] as const;
export type AnalysisType = (typeof ANALYSIS_TYPES)[number];

export function colorForIndex(index: number): string {
  return CHART_PALETTE[index % CHART_PALETTE.length];
}
