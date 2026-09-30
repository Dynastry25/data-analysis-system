"use client";

import { ButtonHTMLAttributes, forwardRef } from "react";

import { Icon, IconName } from "./Icon";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "small" | "medium" | "large";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "bg-primary-600 text-white shadow-sm hover:bg-primary-700 active:bg-primary-800 disabled:hover:bg-primary-600",
  secondary:
    "border border-surface-border bg-surface-panel text-ink-secondary hover:border-surface-border-strong hover:bg-surface-sunken active:bg-surface-sunken disabled:hover:bg-surface-panel",
  ghost:
    "text-ink-secondary hover:bg-surface-sunken active:bg-surface-sunken disabled:hover:bg-transparent",
  danger:
    "bg-danger text-white shadow-sm hover:bg-danger-700 active:bg-danger-700 disabled:hover:bg-danger",
};

const SIZE_CLASSES: Record<Size, string> = {
  small: "h-8 px-3 text-caption",
  medium: "h-10 px-4 text-body",
  large: "h-12 px-5 text-body-lg",
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
      className={`inline-flex select-none items-center justify-center gap-2 rounded-sm font-medium transition-all duration-150 ease-standard focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-panel active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40 disabled:active:scale-100 ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
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


