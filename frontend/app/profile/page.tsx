"use client";

/**
 * The signed-in user's own account.
 *
 * Everything here is fed by endpoints that exist: `/auth/me` for identity,
 * `GET /datasets` for what they have produced, and the organizations they
 * belong to for their role. Nothing is invented -- there is no avatar upload,
 * no password change and no notification-preference endpoint on the server, so
 * those are not offered as if they worked.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { Icon } from "@/components/Icon";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import {
  DatasetSummary,
  Organization,
  UserProfile,
  api,
  apiErrorMessage,
} from "@/lib/api";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((part) => part.charAt(0).toUpperCase()).join("") || "?";
}

function formatDate(value: string | null): string {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString("en-GB");
}

export default function ProfilePage() {
  const { showToast } = useToast();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [me, mine, orgs] = await Promise.all([
        api.auth.me(),
        api.datasets.list(),
        api.organizations.list().catch(() => [] as Organization[]),
      ]);
      setUser(me);
      setDatasets(mine);
      setOrganizations(orgs);
    } catch (caught) {
      const message = apiErrorMessage(caught);
      setError(message);
      showToast(message, "danger");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    load();
  }, [load]);

  const rows = useMemo(
    () => datasets.reduce((sum, item) => sum + (item.row_count ?? 0), 0),
    [datasets]
  );
  const recent = useMemo(
    () =>
      [...datasets]
        .sort((a, b) => (b.uploaded_at ?? "").localeCompare(a.uploaded_at ?? ""))
        .slice(0, 6),
    [datasets]
  );

  return (
    <AppShell title="Wasifu wangu" description="Taarifa za akaunti yako na kile umekikiri.">
      {loading ? (
        <Card>
          <TableSkeleton rows={4} columns={2} />
        </Card>
      ) : error ? (
        <Card>
          <EmptyState title="Imeshindikana kupakia wasifu" description={error} />
        </Card>
      ) : (
        <div className="space-y-4">
          <Card>
            <div className="flex flex-wrap items-center gap-4">
              <span
                aria-hidden="true"
                className="flex h-16 w-16 items-center justify-center rounded-full bg-primary-600 text-h2 font-semibold text-white"
              >
                {initials(user?.full_name ?? "")}
              </span>
              <div className="min-w-0 flex-1">
                <h2 className="text-h2 text-ink">{user?.full_name}</h2>
                <p className="text-body text-ink-secondary">{user?.email}</p>
                <p className="mt-1 text-caption text-ink-muted">
                  Akaunti imeundwa {formatDate(user?.created_at ?? null)}
                </p>
              </div>
              {user?.system_role ? <Badge tone="primary">{user.system_role}</Badge> : null}
            </div>
          </Card>

          <div className="grid gap-4 sm:grid-cols-3">
            {[
              { label: "Datasets", value: datasets.length, icon: "database" as const },
              { label: "Rows", value: rows, icon: "table" as const },
              { label: "Mashirika", value: organizations.length, icon: "building" as const },
            ].map((stat) => (
              <Card key={stat.label}>
                <div className="flex items-center gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-sm bg-primary-50 text-primary-600">
                    <Icon name={stat.icon} size={17} />
                  </span>
                  <div>
                    <p className="text-caption text-ink-muted">{stat.label}</p>
                    <p className="tabular text-h2 font-semibold text-ink">
                      {stat.value.toLocaleString("en-GB")}
                    </p>
                  </div>
                </div>
              </Card>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card
              title="Datasets za hivi karibuni"
              icon="database"
              description="Maanafali ya mwisho uliyoingiza."
            >
              {recent.length === 0 ? (
                <EmptyState
                  title="Bado huna dataset"
                  description="Ingiza dataset ili kuanza kuchambuli takwimu."
                  icon="database"
                />
              ) : (
                <ul className="divide-y divide-surface-border">
                  {recent.map((dataset) => (
                    <li key={dataset.id}>
                      <Link
                        href={`/datasets/${dataset.id}`}
                        className="flex items-center justify-between gap-3 py-2.5 transition-colors duration-150 ease-standard hover:text-primary-700"
                      >
                        <span className="min-w-0 truncate text-body text-ink">
                          {dataset.original_filename}
                        </span>
                        <span className="shrink-0 text-caption text-ink-muted">
                          {formatDate(dataset.uploaded_at)}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card
              title="Mashirika"
              icon="building"
              description="Mashirika uliojiunga nayo."
            >
              {organizations.length === 0 ? (
                <EmptyState
                  title="Hujajiunga na mashirika"
                  description="Unaendesha akaunti yako mwenyewe kwa sasa."
                  icon="building"
                />
              ) : (
                <ul className="divide-y divide-surface-border">
                  {organizations.map((organization) => (
                    <li key={organization.id}>
                      <Link
                        href={`/organizations/${organization.id}`}
                        className="flex items-center justify-between gap-3 py-2.5 transition-colors duration-150 ease-standard hover:text-primary-700"
                      >
                        <span className="min-w-0 truncate text-body text-ink">
                          {organization.name}
                        </span>
                        <Icon name="arrow-right" size={14} className="shrink-0 text-ink-muted" />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <Card>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-h3 text-ink">Mipango</h2>
                <p className="mt-0.5 text-body text-ink-secondary">
                  Mandhari, uwamadili wa data na maana ya kuingia.
                </p>
              </div>
              <Link href="/settings">
                <Button variant="secondary" icon="sliders">
                  Fungua mipango
                </Button>
              </Link>
            </div>
          </Card>
        </div>
      )}
    </AppShell>
  );
}