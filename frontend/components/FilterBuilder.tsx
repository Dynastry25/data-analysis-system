"use client";

import { Icon } from "./Icon";
import { SelectInput, TextInput } from "./Field";
import type { ColumnProfile } from "@/lib/api";

/**
 * One condition in a filter. `id` is client-side only: it is what React keys
 * the row on and what Remove uses to find its row again, so it must stay
 * stable while the condition itself is edited. Nothing is sent under this name.
 */
export interface FilterCondition {
  id: string;
  column: string;
  operator: string;
  value: string;
}

export type FilterLogic = "and" | "or";

interface OperatorSpec {
  value: string;
  label: string;
  /** How many values the operator consumes. */
  arity: "none" | "one" | "two" | "many";
}

/**
 * The operators the engine implements, with the arity each one needs.
 *
 * This list mirrors `FILTER_OPERATORS` in the backend. It is duplicated here
 * rather than fetched because the catalogue endpoint reports parameter *names*,
 * not which operator takes how many values — and getting that wrong means a
 * filter that silently keeps the wrong rows. It stays in step with the tests,
 * which assert both lists agree.
 */
export const FILTER_OPERATORS: OperatorSpec[] = [
  { value: "eq", label: "equals", arity: "one" },
  { value: "ne", label: "does not equal", arity: "one" },
  { value: "gt", label: "is greater than", arity: "one" },
  { value: "gte", label: "is greater than or equal", arity: "one" },
  { value: "lt", label: "is less than", arity: "one" },
  { value: "lte", label: "is less than or equal", arity: "one" },
  { value: "between", label: "is between (inclusive)", arity: "two" },
  { value: "in", label: "is one of", arity: "many" },
  { value: "not_in", label: "is none of", arity: "many" },
  { value: "contains", label: "text contains", arity: "one" },
  { value: "startswith", label: "text starts with", arity: "one" },
  { value: "endswith", label: "text ends with", arity: "one" },
  { value: "is_null", label: "is missing", arity: "none" },
  { value: "not_null", label: "is not missing", arity: "none" },
];

export function operatorArity(operator: string): OperatorSpec["arity"] {
  return FILTER_OPERATORS.find((entry) => entry.value === operator)?.arity ?? "one";
}

let sequence = 0;
function nextId(): string {
  sequence += 1;
  return `condition-${sequence}`;
}

export function emptyCondition(columns: ColumnProfile[]): FilterCondition {
  return { id: nextId(), column: columns[0]?.name ?? "", operator: "eq", value: "" };
}

/**
 * Turn the builder rows into the configuration the operation endpoint expects.
 *
 * `between` needs two limits and `in`/`not_in` need a list, so a single value
 * field is split here rather than in the form. Returns the condition list plus
 * any row that could not be built, so the caller can name the row that is wrong
 * instead of sending a filter that quietly matches nothing.
 */
export function buildFilterConfig(conditions: FilterCondition[]): {
  config: Record<string, unknown> | null;
  error: string | null;
} {
  const built: { column: string; operator: string; value?: unknown; values?: unknown[] }[] = [];

  for (const [index, condition] of conditions.entries()) {
    const label = `Condition ${index + 1}`;
    if (!condition.column) {
      return { config: null, error: `${label}: choose a column.` };
    }
    const arity = operatorArity(condition.operator);
    if (arity === "none") {
      built.push({ column: condition.column, operator: condition.operator });
      continue;
    }
    const parts = condition.value
      .split(",")
      .map((part) => part.trim())
      .filter((part) => part !== "");
    if (parts.length === 0) {
      return { config: null, error: `${label}: enter a value for "${condition.operator}".` };
    }
    if (arity === "two" && parts.length < 2) {
      return { config: null, error: `${label}: "between" needs two limits, e.g. 18 and 65.` };
    }
    if (arity === "many") {
      built.push({ column: condition.column, operator: condition.operator, values: parts });
    } else {
      built.push({ column: condition.column, operator: condition.operator, value: parts[0] });
    }
  }

  if (built.length === 0) {
    return { config: null, error: "Add at least one condition." };
  }
  return { config: { conditions: built }, error: null };
}

interface FilterBuilderProps {
  columns: ColumnProfile[];
  conditions: FilterCondition[];
  logic: FilterLogic;
  onChange: (conditions: FilterCondition[]) => void;
  onLogicChange: (logic: FilterLogic) => void;
  /** Set once the user has tried to apply, so the error names the failing row. */
  attempted: boolean;
  error?: string | null;
}

/**
 * A filter over the whole dataset, built out of any number of conditions.
 *
 * The engine already accepted `conditions` joined by `and`/`or`; the old form
 * only ever sent one condition, so that capability was unreachable from the UI.
 * One condition remains the common case, so it is the starting point rather
 * than making the user build a list in order to filter by one column.
 *
 * The value input changes with the operator: `between` takes two limits, `in`
 * takes a list, and `is missing` takes nothing. Asking for a value the operator
 * ignores is how a filter ends up looking configured and not being so.
 */
export function FilterBuilder({
  columns,
  conditions,
  logic,
  onChange,
  onLogicChange,
  attempted,
  error,
}: FilterBuilderProps) {
  const columnOptions = columns.map((column) => ({
    value: column.name,
    label: column.name,
  }));
  const operatorOptions = FILTER_OPERATORS.map((entry) => ({
    value: entry.value,
    label: entry.label,
  }));

  function update(id: string, patch: Partial<FilterCondition>) {
    onChange(
      conditions.map((condition) =>
        condition.id === id ? { ...condition, ...patch } : condition,
      ),
    );
  }

  function remove(id: string) {
    // The last condition *is* the filter. Removing it would leave nothing to
    // apply, so the button is disabled rather than allowed to empty the form.
    if (conditions.length <= 1) return;
    onChange(conditions.filter((condition) => condition.id !== id));
  }

  const showLogic = conditions.length > 1;

  return (
    <div className="rounded-md border border-surface-border bg-surface-sunken p-3 sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-body font-medium text-ink">Conditions</p>
          <p className="text-caption text-ink-muted">
            A row is kept when it satisfies the conditions below.
          </p>
        </div>
        {showLogic && (
          <div
            role="group"
            aria-label="How conditions are combined"
            className="inline-flex items-center gap-0.5 rounded-sm border border-surface-border bg-surface-panel p-0.5"
          >
            {(["and", "or"] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => onLogicChange(option)}
                aria-pressed={logic === option}
                className={`min-h-[28px] rounded-[3px] px-3 text-caption font-medium uppercase transition-colors duration-150 ease-standard ${
                  logic === option
                    ? "bg-primary-50 text-primary-800"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        )}
      </div>

      {showLogic && (
        <p className="mt-2 text-caption text-ink-secondary">
          {logic === "and"
            ? "A row is kept only when it matches every condition."
            : "A row is kept when it matches at least one condition."}
        </p>
      )}

      <ul className="mt-3 space-y-3">
        {conditions.map((condition, index) => {
          const arity = operatorArity(condition.operator);
          return (
            <li
              key={condition.id}
              className="rounded-md border border-surface-border bg-surface-panel p-3"
            >
              <div className="flex items-start gap-2">
                <span
                  className="mt-2 flex h-6 min-w-6 shrink-0 items-center justify-center rounded-full bg-surface-sunken px-1.5 font-mono text-caption text-ink-muted"
                  aria-hidden="true"
                >
                  {index + 1}
                </span>
                <div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  <SelectInput
                    label="Column"
                    required
                    value={condition.column}
                    options={columnOptions}
                    onChange={(event) => update(condition.id, { column: event.target.value })}
                  />
                  <SelectInput
                    label="Operator"
                    required
                    value={condition.operator}
                    options={operatorOptions}
                    onChange={(event) =>
                      update(condition.id, { operator: event.target.value, value: "" })
                    }
                  />
                  <ValueInput
                    arity={arity}
                    value={condition.value}
                    onChange={(next) => update(condition.id, { value: next })}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => remove(condition.id)}
                  disabled={conditions.length <= 1}
                  aria-label={`Remove condition ${index + 1}`}
                  className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-sm text-ink-muted transition-colors duration-150 ease-standard hover:bg-danger-bg hover:text-danger disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
                >
                  <Icon name="trash" size={15} />
                </button>
              </div>
            </li>
          );
        })}
      </ul>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => onChange([...conditions, emptyCondition(columns)])}
          className="inline-flex min-h-[36px] items-center gap-1.5 rounded-md border border-surface-border-strong bg-surface-panel px-3 text-body font-medium text-ink transition-colors duration-150 ease-standard hover:bg-surface-sunken"
        >
          <Icon name="plus" size={15} />
          Add condition
        </button>
        {error && attempted && (
          <p className="flex items-center gap-1.5 text-caption text-danger">
            <Icon name="alert-circle" size={13} className="shrink-0" />
            {error}
          </p>
        )}
      </div>
    </div>
  );
}

/** The value control, chosen by what the operator actually consumes. */
function ValueInput({
  arity,
  value,
  onChange,
}: {
  arity: "none" | "one" | "two" | "many";
  value: string;
  onChange: (value: string) => void;
}) {
  if (arity === "none") {
    return (
      <p className="flex items-end pb-2 text-caption text-ink-muted">
        <Icon name="info" size={13} className="mr-1.5 shrink-0" />
        This operator needs no value.
      </p>
    );
  }
  if (arity === "many") {
    return (
      <TextInput
        label="Values"
        required
        hint="Comma separated, e.g. Dar, Dodoma, Arusha"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }
  if (arity === "two") {
    return (
      <TextInput
        label="From and to"
        required
        hint="Two limits, e.g. 18 and 65"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }
  return (
    <TextInput
      label="Value"
      required
      hint="e.g. 18 or Dar"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

export default FilterBuilder;
