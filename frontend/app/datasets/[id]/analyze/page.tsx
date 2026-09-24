"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

import { AppShell } from "@/components/AppShell";
import { Card } from "@/components/Card";
import { Skeleton } from "@/components/Skeleton";

/**
 * The legacy /analyze screen was a duplicate of the unified statistics
 * studio (MVP-23 consolidation). It now redirects to /statistics, which
 * runs every analysis through the unified engine and shows the versioned
 * analysis history.
 */
export default function AnalyzeRedirectPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();

  useEffect(() => {
    router.replace(`/datasets/${params?.id}/statistics`);
  }, [params?.id, router]);

  return (
    <AppShell
      title="Anaelekezwa kwenye takwimu…"
      description="Ukurasa wa uchambuzi umeunganishwa na ukurasa wa takwimu."
    >
      <Card>
        <div className="space-y-2">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-40 w-full" />
        </div>
      </Card>
    </AppShell>
  );
}
