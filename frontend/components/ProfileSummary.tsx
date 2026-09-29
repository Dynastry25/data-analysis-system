"use client";

import { ColumnProfile } from "@/lib/api";

interface ProfileSummaryProps {
  columns: ColumnProfile[];
  rowCount: number;
}

function formatNumber(value: number): string {
  return value.toLocaleString("en-GB");
}

/** Share of a whole, as a 0–100 bar length. A whole of 0 has no share. */
function share(part: number, whole: number): number {
  if (whole <= 0) return 0;
  return (part / whole) * 100;
}

interface BarItem {
  key: string;
  label: string;
  /** Bar length, 0–100. */
  share: number;
  /** The number printed next to the bar — the bar is decoration for this. */
  value: string;
  tone?: "primary" | "warning";
  title?: string;
}

/**
 * A list of labelled bars with the value printed on every row.
 *
 * The bars are `aria-hidden` on purpose: the number beside each one already
 * carries the meaning, so a screen reader gets the figures as text instead of
 * a decorative shape. That is also why every bar keeps a minimum width — a
 * 0.3% share must still be visible, and the printed number keeps it honest.
 */
function BarList({ items }: { items: BarItem[] }) {
  return (
    <ul className="mt-2 space-y-1.5">
      {items.map((item) => (
        <li
          key={item.key}
          className="grid grid-cols-[minmax(3.5rem,6rem)_1fr_auto] items-center gap-2"
        >
          <span
            className="truncate font-mono text-caption text-ink"
            title={item.title ?? item.label}
          >
            {item.label}
          </span>
          <span
            className="h-2 overflow-hidden rounded-full bg-surface-sunken"
            aria-hidden="true"
          >
            <span
              className={`bar-grow block h-full rounded-full ${
                item.tone === "warning" ? "bg-warning" : "bg-primary-500"
              }`}
              style={{ width: `${Math.max(item.share, 1.5)}%` }}
            />
          </span>
          <span className="tabular whitespace-nowrap font-mono text-caption text-ink-secondary">
            {item.value}
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * The dataset profile, drawn.
 *
 * Everything here is computed from the profile the backend already returned.
 * Nothing is invented, and no figure exists only as a bar: every value is
 * printed beside its bar, so the picture is a reading aid and the "Muundo wa
 * columns" table below stays the exact record.
 *
 * Bars are plain divs rather than Plotly for the same reason the Explore page
 * draws its histograms that way: this is a summary to read, not an interactive
 * chart, and it has to stay readable on a phone.
 */
export function ProfileSummary({ columns, rowCount }: ProfileSummaryProps) {
  // An empty profile must not read as "0.0% complete with 0 columns filled":
  // there is nothing to summarise yet, and the page should say so.
  if (columns.length === 0) {
    return (
      <p className="text-body text-ink-secondary">
        Profile ya columns bado haijatolewa kwa dataset hii, hivyo muhtasari hauwezi
        kuonyeshwa. Fungua Data Studio, kisha angalia ukurasa huu tena.
      </p>
    );
  }

  const totalCells = rowCount * columns.length;
  const totalMissing = columns.reduce(
    (sum, column) => sum + (column.missing_count || 0),
    0
  );
  const filledCells = Math.max(totalCells - totalMissing, 0);
  const completeness = share(filledCells, totalCells);
  const numericCount = columns.filter(
    (column) => column.data_type === "numeric"
  ).length;
  const otherCount = columns.length - numericCount;
  const columnsWithMissing = columns.filter((column) => column.missing_count > 0);
  const uniqueColumns = columns
    .filter(
      (column): column is ColumnProfile & { unique_count: number } =>
        typeof column.unique_count === "number"
    )
    .sort((a, b) => b.unique_count - a.unique_count);

  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-2">
        <section>
          <p className="text-overline uppercase tracking-wide text-ink-muted">
            Ukamilifu wa data
          </p>
          <p className="tabular mt-1 font-mono text-display text-ink">
            {completeness.toFixed(1)}%
          </p>
          <div
            className="mt-2 h-2 overflow-hidden rounded-full bg-surface-sunken"
            role="progressbar"
            aria-valuenow={Math.round(completeness)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Ukamilifu wa data"
          >
            <div
              className={`bar-grow h-full rounded-full ${
                totalMissing === 0 ? "bg-success" : "bg-primary-600"
              }`}
              style={{ width: `${completeness}%` }}
            />
          </div>
          <p className="mt-1.5 text-caption text-ink-muted">
            Cells <span className="font-mono">{formatNumber(filledCells)}</span> kati ya{" "}
            <span className="font-mono">{formatNumber(totalCells)}</span> zimejaa
            {totalMissing === 0
              ? " · hakuna missing values"
              : ` · ${formatNumber(totalMissing)} hazipo katika columns ${columnsWithMissing.length}`}
          </p>

          <div className="mt-5">
            <p className="text-overline uppercase tracking-wide text-ink-muted">
              Muundo wa aina
            </p>
            <div
              className="mt-2 flex h-3 overflow-hidden rounded-full bg-surface-sunken"
              aria-hidden="true"
            >
              {numericCount > 0 && (
                <div
                  className="bar-grow bg-primary-600"
                  style={{ width: `${share(numericCount, columns.length)}%` }}
                />
              )}
              {otherCount > 0 && (
                <div
                  className="bar-grow bg-neutral-300"
                  style={{ width: `${share(otherCount, columns.length)}%` }}
                />
              )}
            </div>
            <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-caption text-ink-secondary">
              <li className="flex items-center gap-1.5">
                <span
                  aria-hidden="true"
                  className="h-2.5 w-2.5 rounded-sm bg-primary-600"
                />
                namba <span className="font-mono font-medium">{numericCount}</span>
              </li>
              <li className="flex items-center gap-1.5">
                <span
                  aria-hidden="true"
                  className="h-2.5 w-2.5 rounded-sm bg-neutral-300"
                />
                nyingine <span className="font-mono font-medium">{otherCount}</span>
              </li>
              <li className="text-ink-muted">
                Safu{" "}
                <span className="font-mono text-ink-secondary">
                  {formatNumber(rowCount)}
                </span>
              </li>
            </ul>
          </div>
        </section>

        <section>
          <p className="text-overline uppercase tracking-wide text-ink-muted">
            Thamani unique kwa column
          </p>
          {uniqueColumns.length === 0 ? (
            <p className="mt-2 text-body text-ink-muted">
              Profile haijatoa unique values kwa columns hizi bado.
            </p>
          ) : (
            <>
              <BarList
                items={uniqueColumns.map((column) => {
                  const looksLikeId = column.unique_count === rowCount && rowCount > 0;
                  return {
                    key: column.name,
                    label: column.name,
                    share: share(column.unique_count, rowCount),
                    value: looksLikeId
                      ? `${formatNumber(column.unique_count)} ID?`
                      : formatNumber(column.unique_count),
                    title: looksLikeId
                      ? `${column.name}: kila safu ina thamani tofauti — huenda ni kitambulisho`
                      : `${column.name}: thamani unique ${formatNumber(
                          column.unique_count
                        )} kati ya safu ${formatNumber(rowCount)}`,
                  };
                })}
              />
              <p className="mt-2 text-caption text-ink-muted">
                Bar ni sehemu ya safu zenye thamani tofauti (unique ÷ safu). Column yenye
                &ldquo;ID?&rdquo; ina thamani tofauti kwa kila safu, hivyo huenda ni
                kitambulisho na si kigezo cha uchambuzi.
              </p>
            </>
          )}
        </section>
      </div>

      <section>
        <p className="text-overline uppercase tracking-wide text-ink-muted">
          Missing values kwa column
        </p>
        {columnsWithMissing.length === 0 ? (
          <p className="mt-2 flex items-center gap-2 text-body text-success-700">
            <span aria-hidden="true">✓</span>
            Columns zote {columns.length} zimejaa: hakuna missing values ya kusafisha.
          </p>
        ) : (
          <>
            <BarList
              items={[...columnsWithMissing]
                .sort((a, b) => b.missing_count - a.missing_count)
                .map((column) => ({
                  key: column.name,
                  label: column.name,
                  share: share(column.missing_count, rowCount),
                  value: `${formatNumber(column.missing_count)} · ${share(
                    column.missing_count,
                    rowCount
                  ).toFixed(1)}%`,
                  tone: "warning" as const,
                  title: `${column.name}: ${formatNumber(
                    column.missing_count
                  )} kati ya safu ${formatNumber(rowCount)} hazina thamani`,
                }))}
            />
            <p className="mt-2 text-caption text-ink-muted">
              Asilimia ni sehemu ya safu ambazo hazina thamani kwenye column husika.
              Safisha kwenye Data Studio kabla ya kuchambua.
            </p>
          </>
        )}
      </section>
    </div>
  );
}

export default ProfileSummary;

