import { Icon, IconName } from "./Icon";
import { ChartType } from "@/lib/api";

export interface ChartTypeOption {
  value: ChartType;
  label: string;
  /** One line on what this chart is for, shown under the label. */
  use: string;
}

interface ChartTypeGridProps {
  options: ChartTypeOption[];
  value: ChartType;
  onChange: (value: ChartType) => void;
}

/**
 * A distinct glyph per chart type, so the grid is scannable without reading.
 *
 * This icon set has no per-chart-type glyphs, so the mapping borrows the four
 * shapes that genuinely differ: a column, a line, a scatter field and a
 * histogram. Rather than inventing six near-identical icons that would read as
 * noise, the two remaining types reuse the nearest honest shape.
 */
const TYPE_ICON: Record<string, IconName> = {
  bar: "chart",
  line: "chart-line",
  scatter: "grid",
  histogram: "trending-up",
};

/**
 * The prototype's chart-type picker: a grid of tiles rather than a select.
 *
 * This is the one control where the prototype's choice is clearly better than
 * ours. A dropdown hides the options behind a click and shows one line of text;
 * a grid shows every type at once with an icon, so picking a chart is a
 * comparison rather than a recall task. The options also carry their own hint,
 * which the select had to concatenate into the label.
 */
export function ChartTypeGrid({ options, value, onChange }: ChartTypeGridProps) {
  return (
    <div
      role="radiogroup"
      aria-label="Aina ya chati"
      className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4"
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            title={option.use}
            className={`flex min-h-[68px] flex-col items-center justify-center gap-1.5 rounded-lg border px-2 py-2.5 text-center transition-colors duration-150 ease-standard focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500 ${
              active
                ? "border-primary-600 bg-primary-50 text-primary-700"
                : "border-surface-border bg-surface-panel text-ink-secondary hover:border-primary-300 hover:bg-primary-50/50"
            }`}
          >
            <Icon name={TYPE_ICON[option.value] ?? "chart"} size={18} />
            <span className="text-caption font-semibold leading-tight">
              {option.label}
            </span>
            <span className="text-[10px] leading-tight text-ink-muted">
              {option.use}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export default ChartTypeGrid;