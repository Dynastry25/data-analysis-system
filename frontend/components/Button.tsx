"use client";

import { ButtonHTMLAttributes, forwardRef } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "small" | "medium" | "large";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "bg-primary-600 text-white hover:bg-primary-700 active:bg-primary-900 disabled:hover:bg-primary-600",
  secondary:
    "border border-neutral-200 bg-white text-neutral-600 hover:bg-neutral-100 disabled:hover:bg-white",
  ghost:
    "text-neutral-600 hover:bg-neutral-100 disabled:hover:bg-transparent",
  danger: "bg-danger text-white hover:brightness-90 disabled:hover:brightness-100",
};

const SIZE_CLASSES: Record<Size, string> = {
  small: "h-8 px-3 text-[13px]",
  medium: "h-10 px-4 text-body",
  large: "h-12 px-5 text-body-lg",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

/** Design-system button: primary / secondary / ghost / danger with all states. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "primary",
    size = "medium",
    loading = false,
    disabled,
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
      className={`inline-flex items-center justify-center gap-2 rounded font-medium transition-colors duration-150 ease-out active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40 ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
      {...rest}
    >
      {loading && (
        <span
          aria-hidden="true"
          className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  );
});

export default Button;
