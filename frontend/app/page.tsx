"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { getToken } from "@/lib/api";

/** Entry point: send the user to the dashboard or to the login screen. */
export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    router.replace(getToken() ? "/dashboard" : "/login");
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-surface-canvas">
      <div
        role="status"
        aria-live="polite"
        className="flex items-center gap-2.5 text-body text-ink-muted"
      >
        <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-primary-600 border-t-transparent" />
        <span>Inapakia…</span>
      </div>
    </main>
  );
}
