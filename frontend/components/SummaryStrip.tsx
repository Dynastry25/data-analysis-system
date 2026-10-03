import { Icon, IconName } from "./Icon";

export interface SummaryItem {
  label: string;
  value: React.ReactNode;
  icon?: IconName;
  /** Optional accent under the value, used for a status word. */
  hint?: string;
}

interface SummaryStripProps {
  items: SummaryItem[];
}

/**
 * The prototype's connected summary strip: one bordered panel divided into cells,
 * not four separate floating cards.
 *
 * Keeping it a single element is the point. As four independent cards the row
 * reads as four unrelated figures with four shadows and four hover states;
 * sharing one border makes it read as one total, which is what it is.
 *
 * The divider is drawn on every cell but the last via `divide-x`, so it sits on
 * the shared border and cannot double up with the container edge.
 */
export function SummaryStrip({ items }: SummaryStripProps) {
  return (
    <section
      aria-label="Muhtasari"
      className="mb-4 grid grid-cols-2 overflow-hidden rounded-xl border border-surface-border bg-surface-panel shadow-card lg:grid-cols-4"
    >
      {items.map((item) => (
        <div
          key={item.label}
          className="border-b border-r border-surface-border px-4 py-3.5 last:border-r-0 lg:border-b-0 [&:nth-last-child(-n+2)]:border-b-0 lg:[&:nth-last-child(-n+2)]:border-b"
        >
          <div className="flex items-baseline gap-2">
            <strong className="tabular font-display text-[17px] font-bold tracking-[-0.02em] text-ink">
              {item.value}
            </strong>
            {item.hint && (
              <span className="truncate text-caption font-medium text-success">
                {item.hint}
              </span>
            )}
          </div>
          <p className="mt-1 flex items-center gap-1.5 text-caption text-ink-muted">
            {item.icon && <Icon name={item.icon} size={12} className="shrink-0" />}
            {item.label}
          </p>
        </div>
      ))}
    </section>
  );
}

export default SummaryStrip;