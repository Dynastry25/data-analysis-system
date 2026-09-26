"use client";

import {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
  useId,
} from "react";

import { Icon, IconName } from "./Icon";

interface FieldProps {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  optionalLabel?: string;
  children: (ids: { controlId: string; describedBy: string | undefined }) => ReactNode;
  className?: string;
}

export function Field({
  label,
  hint,
  error,
  required = false,
  optionalLabel,
  children,
  className = "",
}: FieldProps) {
  const controlId = useId();
  const hintId = `${controlId}-hint`;
  const errorId = `${controlId}-error`;
  const describedBy =
    [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(" ") || undefined;

  return (
    <div className={className}>
      <label htmlFor={controlId} className="mb-1.5 flex items-baseline justify-between gap-2">
        <span className="text-body font-medium text-ink">
          {label}
          {required && (
            <span className="ml-0.5 text-danger" aria-hidden="true">
              *
            </span>
          )}
        </span>
        {optionalLabel && (
          <span className="text-caption text-neutral-400">{optionalLabel}</span>
        )}
      </label>
      {children({ controlId, describedBy })}
      {hint && !error && (
        <p id={hintId} className="mt-1.5 text-caption text-ink-muted">
          {hint}
        </p>
      )}
      {error && (
        <p
          id={errorId}
          role="alert"
          className="mt-1.5 flex items-start gap-1.5 text-caption text-danger"
        >
          <Icon name="alert-circle" size={14} className="mt-0.5 shrink-0" />
          {error}
        </p>
      )}
    </div>
  );
}

interface SelectInputProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  optionalLabel?: string;
  placeholder?: string;
  options: { value: string; label: string; disabled?: boolean }[];
  selectClassName?: string;
}

export function SelectInput({
  label,
  hint,
  error,
  required = false,
  optionalLabel,
  placeholder,
  options,
  selectClassName = "",
  ...rest
}: SelectInputProps) {
  return (
    <Field
      label={label}
      hint={hint}
      error={error}
      required={required}
      optionalLabel={optionalLabel}
    >
      {({ controlId, describedBy }) => (
        <select
          id={controlId}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          className={`control cursor-pointer ${selectClassName}`}
          {...rest}
        >
          {placeholder !== undefined && <option value="">{placeholder}</option>}
          {options.map((option) => (
            <option key={option.value} value={option.value} disabled={option.disabled}>
              {option.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}

interface TextInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  optionalLabel?: string;
  inputClassName?: string;
}

export function TextInput({
  label,
  hint,
  error,
  required = false,
  optionalLabel,
  inputClassName = "",
  ...rest
}: TextInputProps) {
  return (
    <Field
      label={label}
      hint={hint}
      error={error}
      required={required}
      optionalLabel={optionalLabel}
    >
      {({ controlId, describedBy }) => (
        <input
          id={controlId}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          className={`control ${inputClassName}`}
          {...rest}
        />
      )}
    </Field>
  );
}

interface TextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  optionalLabel?: string;
}

export function TextArea({
  label,
  hint,
  error,
  required = false,
  optionalLabel,
  className = "",
  ...rest
}: TextAreaProps) {
  return (
    <Field
      label={label}
      hint={hint}
      error={error}
      required={required}
      optionalLabel={optionalLabel}
    >
      {({ controlId, describedBy }) => (
        <textarea
          id={controlId}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          className={`control control-textarea ${className}`}
          {...rest}
        />
      )}
    </Field>
  );
}

interface CheckboxGroupProps {
  label: string;
  hint?: string;
  options: string[];
  selected: string[];
  onToggle: (value: string) => void;
  emptyLabel?: string;
  maxHeightClassName?: string;
}

export function CheckboxGroup({
  label,
  hint,
  options,
  selected,
  onToggle,
  emptyLabel = "Hakuna columns",
  maxHeightClassName = "max-h-40",
}: CheckboxGroupProps) {
  const groupId = useId();
  return (
    <fieldset>
      <legend className="mb-1.5 text-body font-medium text-ink">{label}</legend>
      {hint && <p className="mb-2 text-caption text-ink-muted">{hint}</p>}
      {options.length === 0 ? (
        <p className="rounded border border-dashed border-surface-border bg-surface-sunken px-3 py-4 text-center text-caption text-ink-muted">
          {emptyLabel}
        </p>
      ) : (
        <div
          id={groupId}
          className={`flex flex-wrap gap-1.5 overflow-y-auto rounded border border-surface-border bg-white p-2 ${maxHeightClassName}`}
        >
          {options.map((option) => {
            const active = selected.includes(option);
            return (
              <label
                key={option}
                className={`inline-flex min-h-[28px] cursor-pointer items-center gap-1.5 rounded-pill border px-2.5 py-0.5 text-caption transition-colors duration-150 ease-standard ${
                  active
                    ? "border-primary-200 bg-primary-50 font-medium text-primary-800"
                    : "border-surface-border bg-white text-ink-secondary hover:border-surface-border-strong hover:bg-surface-sunken"
                }`}
              >
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5 shrink-0 rounded border-neutral-300 text-primary-600 accent-primary-600 focus:ring-2 focus:ring-primary-500/40"
                  checked={active}
                  onChange={() => onToggle(option)}
                />
                {option}
              </label>
            );
          })}
        </div>
      )}
    </fieldset>
  );
}

interface FeatureCardProps {
  icon: IconName;
  title: string;
  description: string;
  children: ReactNode;
  className?: string;
}

export function FeatureCard({
  icon,
  title,
  description,
  children,
  className = "",
}: FeatureCardProps) {
  return (
    <section
      className={`rounded-lg border border-surface-border bg-surface-panel p-5 shadow-card ${className}`}
    >
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary-50 text-primary-600">
          <Icon name={icon} size={18} />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-h3 text-ink">{title}</h3>
          <p className="mt-1 text-body text-ink-secondary">{description}</p>
        </div>
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}
