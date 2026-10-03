"use client";

import { useMemo, useState } from "react";

import { Badge } from "./Badge";
import { Card } from "./Card";
import { Icon } from "./Icon";
import { AnalysisMethod, MethodCatalog } from "@/lib/api";

interface MethodPickerProps {
  catalog: MethodCatalog;
  /** The engine analysis_type currently chosen, if any. */
  selected: string;
  onSelect: (method: AnalysisMethod) => void;
  /** For embedding the picker as a column of a connected workspace. */
  className?: string;
}

/**
 * Browse the guide by the question the reader actually has.
 *
 * The guide opens with three questions — what is the goal, what kind of
 * dependent variable is it, how was the data collected — so the filter starts
 * there rather than with a flat list of 151 method names. Each row shows the
 * method's own "when to use this" line, because that is what decides between
 * two methods that look alike in a menu.
 *
 * Methods the engine cannot yet run are still listed and still readable: the
 * guide has to describe the whole territory, and hiding the unimplemented part
 * would make the catalogue look complete when it is not.
 */

/** Rows are capped so a filter that matches everything stays scrollable. */
const MAX_ROWS = 40;

export function MethodPicker({
  catalog,
  selected,
  onSelect,
  className = "",
}: MethodPickerProps) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [goal, setGoal] = useState("all");
  const [onlyImplemented, setOnlyImplemented] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const goalRow = catalog.goal_guide.find((row) => row.key === goal);
    return catalog.methods.filter((method) => {
      if (category !== "all" && method.category !== category) return false;
      if (onlyImplemented && !method.implemented) return false;
      // A goal filter matches when the guide names this method for that goal,
      // either directly or as one of the alternatives it points at.
      if (goalRow && goalRow.key !== "all") {
        const related = [goalRow.key, ...goalRow.method.split(/,\s*/)];
        const haystack = [method.key, ...method.alternatives];
        if (!related.some((entry) => haystack.includes(entry.trim()))) return false;
      }
      if (!needle) return true;
      return [
        method.label,
        method.label_sw,
        method.purpose,
        method.dv,
        method.design,
        ...method.assumptions,
      ]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [catalog, query, category, goal, onlyImplemented]);

  return (
    <Card
      className={className}
      title="Chagua method ya uchambuzi"
      icon="sliders"
      description={`Mwongozo kamili: ${catalog.counts.methods} methods katika ${catalog.categories.length} makundi. ${catalog.counts.implemented} zina hesabu inayofanyika kwenye data yako sasa hivi.`}
    >
      <ol className="mb-4 space-y-2">
        {catalog.questions.map((item, index) => (
          <li key={item.question} className="flex gap-2 text-caption text-ink-secondary">
            <span className="font-medium text-ink-muted">{index + 1}.</span>
            <span>
              <span className="font-medium text-ink">{item.question}</span> — {item.hint}
            </span>
          </li>
        ))}
      </ol>

      <PickerFilters
        query={query}
        onQuery={setQuery}
        goal={goal}
        onGoal={setGoal}
        category={category}
        onCategory={setCategory}
        onlyImplemented={onlyImplemented}
        onOnlyImplemented={setOnlyImplemented}
        catalog={catalog}
      />

      <p className="mb-2 text-caption text-ink-muted">
        {filtered.length} method zinaonyeshwa
      </p>

      <ul className="space-y-2">
        {filtered.slice(0, MAX_ROWS).map((method) => (
          <MethodRow
            key={method.key}
            method={method}
            isSelected={method.engine === selected}
            isOpen={expanded === method.key}
            onToggle={() => setExpanded(expanded === method.key ? null : method.key)}
            onSelect={() => onSelect(method)}
          />
        ))}
      </ul>

      {filtered.length > MAX_ROWS && (
        <p className="mt-3 text-caption text-ink-muted">
          Inaonyesha method {MAX_ROWS} za {filtered.length}. Narrow down kwa vichujio hapo
          juu.
        </p>
      )}
      {filtered.length === 0 && (
        <p className="text-caption text-ink-muted">
          Hakuna method inayolingana. Ongeza neno lingine la utafutaji au ondoa vichujio.
        </p>
      )}
    </Card>
  );
}

interface PickerFiltersProps {
  query: string;
  onQuery: (value: string) => void;
  goal: string;
  onGoal: (value: string) => void;
  category: string;
  onCategory: (value: string) => void;
  onlyImplemented: boolean;
  onOnlyImplemented: (value: boolean) => void;
  catalog: MethodCatalog;
}

function PickerFilters({
  query,
  onQuery,
  goal,
  onGoal,
  category,
  onCategory,
  onlyImplemented,
  onOnlyImplemented,
  catalog,
}: PickerFiltersProps) {
  const control =
    "w-full rounded-md border border-surface-border bg-surface px-3 py-2 text-body text-ink";
  const caption =
    "mb-1 block text-overline uppercase tracking-wide text-ink-muted";
  return (
    <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <label className="block">
        <span className={caption}>Tafuta</span>
        <input
          type="search"
          value={query}
          onChange={(event) => onQuery(event.target.value)}
          placeholder="mfano: odds ratio, survival, survey"
          className={`${control} placeholder:text-ink-muted`}
        />
      </label>
      <label className="block">
        <span className={caption}>Lengo</span>
        <select value={goal} onChange={(event) => onGoal(event.target.value)} className={control}>
          <option value="all">Lengo lolote</option>
          {catalog.goal_guide.map((row) => (
            <option key={row.key} value={row.key}>
              {row.goal}
            </option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className={caption}>Ukundi</span>
        <select
          value={category}
          onChange={(event) => onCategory(event.target.value)}
          className={control}
        >
          <option value="all">Ukundi wowote</option>
          {catalog.categories.map((row) => (
            <option key={row.key} value={row.key}>
              {row.label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex items-end gap-2 pb-2 text-caption text-ink-secondary">
        <input
          type="checkbox"
          checked={onlyImplemented}
          onChange={(event) => onOnlyImplemented(event.target.checked)}
        />
        Nionyeshe zinazoweza kufanyika
      </label>
    </div>
  );
}

interface MethodRowProps {
  method: AnalysisMethod;
  isSelected: boolean;
  isOpen: boolean;
  onToggle: () => void;
  onSelect: () => void;
}

function MethodRow({ method, isSelected, isOpen, onToggle, onSelect }: MethodRowProps) {
  return (
    <li className="rounded-md border border-surface-border">
      <div className="flex flex-wrap items-start gap-3 p-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="text-body font-semibold text-ink">{method.label_sw}</span>
            <span className="text-caption text-ink-muted">{method.label}</span>
            <Badge tone={method.implemented ? "success" : "neutral"} size="sm">
              {method.implemented ? "Inaweza kufanyika" : "Maelezo tu"}
            </Badge>
            {method.dv && (
              <Badge tone="info" size="sm" icon={null}>
                {method.dv}
              </Badge>
            )}
          </div>
          <p className="text-caption text-ink-secondary">{method.purpose}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={onToggle}
            className="rounded-md border border-surface-border px-2 py-1 text-caption text-ink-secondary hover:bg-surface-sunken"
          >
            {isOpen ? "Funga" : "Maelezo"}
          </button>
          {method.implemented && (
            <button
              type="button"
              onClick={onSelect}
              className={`rounded-md px-2 py-1 text-caption font-medium ${
                isSelected
                  ? "bg-primary text-white"
                  : "bg-primary-50 text-primary-800 hover:bg-primary-100"
              }`}
            >
              {isSelected ? "Imechosenwa" : "Chagua"}
            </button>
          )}
        </div>
      </div>
      {isOpen && <MethodDetail method={method} />}
    </li>
  );
}

type DetailIcon = "lightbulb" | "alert-triangle" | "chart" | "arrow-right";

/** The guide's four columns for one method: when to use, assumptions, outputs, alternatives. */
function MethodDetail({ method }: { method: AnalysisMethod }) {
  return (
    <div className="grid gap-4 border-t border-surface-border p-3 sm:grid-cols-2 lg:grid-cols-4">
      <DetailBlock title="Lini kuitumia" icon="lightbulb">
        <p>{method.when_to_use}</p>
        <p className="mt-1 text-ink-muted">
          DV: {method.dv} · muundo: {method.design}
        </p>
      </DetailBlock>
      <DetailBlock title="Assumptions" icon="alert-triangle">
        <ul className="list-disc space-y-0.5 pl-4">
          {method.assumptions.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </DetailBlock>
      <DetailBlock title="Matokeo" icon="chart">
        <p>{method.outputs}</p>
        {method.variables.length > 0 && (
          <p className="mt-1 text-ink-muted">Vigezo: {method.variables.join(", ")}</p>
        )}
      </DetailBlock>
      <DetailBlock title="Mbadala" icon="arrow-right">
        {method.alternatives.length > 0 ? (
          <ul className="list-disc space-y-0.5 pl-4">
            {method.alternatives.map((item) => (
              <li key={item}>{item.replace(/_/g, " ")}</li>
            ))}
          </ul>
        ) : (
          <p className="text-ink-muted">Hakuna mbadala maalum.</p>
        )}
        {method.notes && <p className="mt-1 text-ink-muted">{method.notes}</p>}
      </DetailBlock>
    </div>
  );
}

function DetailBlock({
  title,
  icon,
  children,
}: {
  title: string;
  icon: DetailIcon;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="mb-1.5 flex items-center gap-1.5 text-overline uppercase tracking-wide text-ink-muted">
        <Icon name={icon} size={12} className="shrink-0" />
        {title}
      </p>
      <div className="text-caption text-ink-secondary">{children}</div>
    </div>
  );
}


