"use client";

import { ButtonHTMLAttributes, forwardRef } from "react";

import { Icon, IconName } from "./Icon";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "small" | "medium" | "large";

/**
 * Variants follow the StatFlow design system: a violet primary with a soft
 * brand shadow, and flat bordered secondaries. The shadow on the primary is
 * what separates it from the secondary at a glance -- two same-weight filled
 * shapes with no shadow difference read as a pair of equals.
 */
const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "border border-primary-700 bg-primary-600 text-white shadow-[0_4px_12px_rgba(108,75,244,0.22)] hover:bg-primary-700 hover:shadow-[0_6px_18px_rgba(108,75,244,0.30)] hover:-translate-y-px active:translate-y-0 disabled:hover:translate-y-0",
  secondary:
    "border border-surface-border bg-surface-panel text-ink-secondary hover:bg-[#FAF9FC] hover:border-[#D6D2DD] hover:-translate-y-px active:translate-y-0 disabled:hover:translate-y-0",
  ghost:
    "text-ink-secondary hover:bg-surface-sunken active:bg-surface-sunken disabled:hover:bg-transparent",
  danger:
    "border border-danger/70 bg-danger text-white shadow-[0_4px_12px_rgba(223,91,91,0.22)] hover:bg-danger-700",
};

const SIZE_CLASSES: Record<Size, string> = {
  small: "h-9 px-3 text-caption",
  medium: "h-9 px-3.5 text-body",
  large: "h-11 px-5 text-body-lg",
};

const ICON_SIZE: Record<Size, number> = {
  small: 14,
  medium: 16,
  large: 18,
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: IconName;
}

/** Design-system button: primary / secondary / ghost / danger with all states. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "primary",
    size = "medium",
    loading = false,
    disabled,
    icon,
    className = "",
    children,
    ...rest
  },
  ref
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      aria-busy={loading}
      className={`inline-flex select-none items-center justify-center gap-2 rounded-sm font-semibold transition-all duration-150 ease-standard focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-panel active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-45 disabled:active:scale-100 ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
      {...rest}
    >
      {loading && (
        <span
          aria-hidden="true"
          className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      {!loading && icon && <Icon name={icon} size={ICON_SIZE[size]} />}
      {children}
    </button>
  );
});

export default Button;


