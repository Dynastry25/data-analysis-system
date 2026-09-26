"use client";

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
} from "react";

import { Icon, IconName } from "./Icon";

export type ToastVariant = "success" | "warning" | "danger" | "info";

interface ToastItem {
  id: number;
  message: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  showToast: (message: string, variant?: ToastVariant) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const VARIANT_STYLES: Record<ToastVariant, string> = {
  success: "border-success/30 bg-success-bg text-success-700",
  warning: "border-warning/40 bg-warning-bg text-warning-700",
  danger: "border-danger/30 bg-danger-bg text-danger-700",
  info: "border-info/30 bg-info-bg text-info-700",
};

const VARIANT_ICONS: Record<ToastVariant, IconName> = {
  success: "check",
  warning: "alert-triangle",
  danger: "alert-circle",
  info: "info",
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const idRef = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, variant: ToastVariant = "info") => {
      const id = idRef.current++;
      setToasts((prev) => [...prev, { id, message, variant }]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 4000);
    },
    []
  );

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div
        className="pointer-events-none fixed right-4 top-4 z-50 flex flex-col gap-2"
        aria-live="polite"
        aria-atomic="true"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={`toast-enter pointer-events-auto flex w-[min(22rem,calc(100vw-2rem))] items-start gap-2.5 rounded-lg border px-3.5 py-3 text-body shadow-overlay ${VARIANT_STYLES[t.variant]}`}
          >
            <Icon name={VARIANT_ICONS[t.variant]} size={16} className="mt-0.5 shrink-0" />
            <p className="min-w-0 flex-1">{t.message}</p>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              aria-label="Funga ujumbe"
              className="-mr-1 -mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded transition-colors hover:bg-black/5"
            >
              <Icon name="close" size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}
