"use client";

/**
 * Settings.
 *
 * Written so every control either works now or says plainly that it cannot.
 *
 * The application renders in light mode only, so there is no theme switch to
 * offer: a control that changed nothing would be worse than its absence.
 *
 * Data management is real -- it lists the user's own datasets and deletes
 * through an endpoint that exists. Sections whose backend does not exist yet
 * (password change, notification delivery, AI preferences) are shown as
 * unavailable rather than wired to a control that silently does nothing. A
 * settings page full of dead switches is worse than an honest short list.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { Icon, IconName } from "@/components/Icon";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import { DatasetSummary, api, apiErrorMessage } from "@/lib/api";
import { useLanguage } from "@/lib/i18n";

type SectionKey = "appearance" | "data" | "account" | "unavailable";

const SECTIONS: { key: SectionKey; label: string; icon: IconName }[] = [
  { key: "appearance", label: "Mwonekano", icon: "eye" },
  { key: "data", label: "Data", icon: "database" },
  { key: "account", label: "Akaunti", icon: "user" },
  { key: "unavailable", label: "Zilizobaki", icon: "info" },
];

export default function SettingsPage() {
  const { showToast } = useToast();
  const { t } = useLanguage();
  const [section, setSection] = useState<SectionKey>("appearance");
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDatasets(await api.datasets.list());
    } catch (caught) {
      showToast(apiErrorMessage(caught), "danger");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    load();
  }, [load]);

  const removeDataset = useCallback(
    async (dataset: DatasetSummary) => {
      if (
        !window.confirm(
          `Futa "${dataset.original_filename}"? Kitendo hiki hakiwezi kutenduliwa.`
        )
      ) {
        return;
      }
      setBusy(dataset.id);
      try {
        await api.datasets.remove(dataset.id);
        setDatasets((current) => current.filter((item) => item.id !== dataset.id));
        showToast("Dataset imefutwa.", "success");
      } catch (caught) {
        showToast(apiErrorMessage(caught), "danger");
      } finally {
        setBusy(null);
      }
    },
    [showToast]
  );

  const totalRows = useMemo(
    () => datasets.reduce((sum, item) => sum + (item.row_count ?? 0), 0),
    [datasets]
  );

  return (
    <AppShell title="Mipango" description="Mwonekano, data na akaunti yako.">
      <div className="grid gap-4 lg:grid-cols-[14rem_1fr]">
        <nav aria-label="Sehemu za mipango">
          <ul className="space-y-1">
            {SECTIONS.map((entry) => {
              const active = section === entry.key;
              return (
                <li key={entry.key}>
                  <button
                    type="button"
                    onClick={() => setSection(entry.key)}
                    aria-current={active ? "true" : undefined}
                    className={`flex min-h-[44px] w-full items-center gap-2.5 rounded-sm px-3 text-left text-body transition-colors duration-150 ease-standard ${
                      active
                        ? "bg-primary-50 font-medium text-primary-800"
                        : "text-ink-secondary hover:bg-surface-sunken"
                    }`}
                  >
                    <Icon name={entry.icon} size={16} />
                    {entry.label}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        {section === "appearance" && (
          <>
            <Card
              title={t("language.label")}
              icon="globe"
              description={t("language.switch")}
            >
              <LanguageSwitcher className="w-full [&>button]:flex-1 [&>button]:px-4 [&>button]:py-2" />
              <p className="mt-3 text-caption text-ink-muted">
                {t("language.appliesTo")}
              </p>
            </Card>

            <Card
              title={t("appearance.title")}
              icon="eye"
              description={t("appearance.description")}
            >
              <p className="text-body text-ink-secondary">
                {t("appearance.bodyOne")}
              </p>
              <p className="mt-3 text-body text-ink-secondary">
                {t("appearance.bodyTwo")}
              </p>
            </Card>
          </>
        )}

        {section === "data" && (
          <Card
            title="Data yako"
            icon="database"
            description={`${datasets.length} datasets, ${totalRows.toLocaleString("en-GB")} rows.`}
          >
            {loading ? (
              <TableSkeleton rows={3} columns={3} />
            ) : datasets.length === 0 ? (
              <EmptyState
                title="Bado huna dataset"
                description="Ingiza dataset ili kuiweka hapa."
                icon="database"
              />
            ) : (
              <ul className="divide-y divide-surface-border">
                {datasets.map((dataset) => (
                  <li
                    key={dataset.id}
                    className="flex flex-wrap items-center justify-between gap-3 py-2.5"
                  >
                    <div className="min-w-0">
                      <Link
                        href={`/datasets/${dataset.id}`}
                        className="truncate text-body text-ink transition-colors duration-150 ease-standard hover:text-primary-700"
                      >
                        {dataset.original_filename}
                      </Link>
                      <p className="text-caption text-ink-muted">
                        {dataset.row_count?.toLocaleString("en-GB")} rows ·{" "}
                        {dataset.column_count} columns
                      </p>
                    </div>
                    <Button
                      variant="secondary"
                      size="small"
                      icon="trash"
                      loading={busy === dataset.id}
                      onClick={() => removeDataset(dataset)}
                    >
                      Futa
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )}

        {section === "account" && (
          <Card
            title="Akaunti"
            icon="user"
            description="Taarifa za akaunti. Sasa zinarekodiwa kwenye /auth/me."
          >
            <p className="text-body text-ink-secondary">
              Jina na barua pepe vinatokana na akaunti uliyotumia kuingia. Hubadilishi
              huhitaji backend ambayo bado haipo.
            </p>
          </Card>
        )}

        {section === "unavailable" && (
          <Card
            title="Zilizobaki"
            icon="info"
            description="Vipengele hivi bado havina backend, kwa hivyo hazionyeswi kama vinalo."
          >
            <ul className="space-y-3">
              {[
                {
                  title: "Badilisha nenosiri",
                  why: "Hakuna endpoint ya kubadilisha nenosiri kwenye /auth.",
                },
                {
                  title: "Arifa za barua pepe",
                  why: "Hakuna mfumo wa arifa; hakuna kitu kinachotuma.",
                },
                {
                  title: "Mapendeleo ya AI",
                  why: "Hakuna mipango ya AI kwenye mfano wa data.",
                },
                {
                  title: "Lugha",
                  why: "Mvigezi wa lugha bado ni Kiswahili tu.",
                },
              ].map((item) => (
                <li
                  key={item.title}
                  className="flex items-start gap-2.5 rounded-md border border-surface-border px-3 py-2.5"
                >
                  <Icon name="info" size={15} className="mt-0.5 shrink-0 text-ink-muted" />
                  <div>
                    <p className="text-body text-ink">{item.title}</p>
                    <p className="text-caption text-ink-muted">{item.why}</p>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </AppShell>
  );
}