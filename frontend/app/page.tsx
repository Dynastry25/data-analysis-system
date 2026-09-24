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
    <main className="flex min-h-screen items-center justify-center bg-neutral-50">
      <p className="text-body text-neutral-600">Inapakia…</p>
    </main>
  );
}
