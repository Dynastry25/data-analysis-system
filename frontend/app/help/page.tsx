"use client";

/**
 * Help and documentation.
 *
 * The methods reference is generated from the live catalogue rather than
 * written out, so it can only ever describe what the engine actually offers,
 * including which of the guide's methods are implemented. A hand-written list
 * would drift the first time a method was added.
 */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { Icon, IconName } from "@/components/Icon";
import { InlineSearch } from "@/components/InlineSearch";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import { apiErrorMessage, statflowApi } from "@/lib/api";

const GUIDES: { title: string; icon: IconName; steps: string[] }[] = [
  {
    title: "Kuanza",
    icon: "sparkles",
    steps: [
      "Ingiza dataset (.csv, .xlsx, .sav, .dta) ukibonyeza Data kwenye upande wa kushoto.",
      "Fungua Preparation Studio ili kuona profile ya kila column.",
      "Safisha: ondoa missing values, toa duplicates, badilisha aina.",
      "Endesha uchambuzi kwenye Statistical Analysis Studio.",
      "Tengeneza chati, kisha pakua matokeo.",
    ],
  },
  {
    title: "Kupanga dataset",
    icon: "sliders",
    steps: [
      "Kila operation hufanya VERSION MPYA. Asili hubadiliki kamwe.",
      "Unganisha dataset nyingine kwa key kwenye 'Unganisha datasets'.",
      "Baada ya kusafisha, dataset iliyosafishwa ndiyo inayotumika kwenye analysis.",
      "History inaonyesha mpangilio wa kila hatua uliofanya.",
    ],
  },
  {
    title: "Kuchagua mbinu",
    icon: "calculator",
    steps: [
      "Anza na swali la utafiti: unataka kujua nini?",
      "DV inaamua mbinu: binary, count, continuous, ordinal au time-to-event.",
      "Angalia Vigezo vya mbinu kabla ya kuamua -- zinaeleza kwa nini.",
      "Soma majibu: effect size ni muhimu kuliko p-value pekee.",
    ],
  },
];

const FAQ: { q: string; a: string }[] = [
  {
    q: "Kwa nini dataset yangu haibadilikiwi?",
    a: "Kila operation inaunda version mpya. Version asili hubaki pale uliyoacha, kwa hivyoUnaweza kurudi wakati wowote.",
  },
  {
    q: "Nini maana ya missing values?",
    a: "Zinaweza kuwa 'hakuna data' au 'jibu lililokosewa'. Tofautia hii inaathiri njia unayochagua ya kuzibadilisha, kwa hivyo chagua kwa makini.",
  },
  {
    q: "p-value ndogo inamaanisha nini?",
    a: "Inamaanisha data hazipingani na hakuna mbinu iliyochaguliwa -- si kwamba mbinu hiyo ni 'sahihi'. Effect size ndiyo inakuonyesha ukubwa wa athari.",
  },
  {
    q: "Naweza kuamini majibu ya AI?",
    a: "AI huwaeleza matokeo yaliyokweliwa na engine ya takwimu. Hakuna jibu la takwimu lililotokana na AI peke yake.",
  },
  {
    q: "Nini maana ya version?",
    a: "Version ni snapshot ya dataset baada ya hatua fulani. Uchambuzi wowote unarekodi kwa version iliyoitumia, hivyo matokeo yanaweza kuthibitishwa.",
  },
];

export default function HelpPage() {
  const { showToast } = useToast();
  const [catalog, setCatalog] = useState<Awaited<
    ReturnType<typeof statflowApi.methodCatalog>
  > | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    statflowApi
      .methodCatalog()
      .then((value) => {
        if (!cancelled) setCatalog(value);
      })
      .catch((caught) => showToast(apiErrorMessage(caught), "danger"))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [showToast]);

  const byCategory = useMemo(() => {
    const grouped = new Map<string, { implemented: number; total: number }>();
    for (const method of catalog?.methods ?? []) {
      const entry = grouped.get(method.category) ?? { implemented: 0, total: 0 };
      entry.total += 1;
      if (method.implemented) entry.implemented += 1;
      grouped.set(method.category, entry);
    }
    return [...grouped.entries()].sort((a, b) => b[1].total - a[1].total);
  }, [catalog]);

  const [query, setQuery] = useState("");

  /**
   * Filters the guides and the method list together. A help page whose search
   * only covers half its content is worse than none, because it looks like the
   * whole page is searchable and quietly returns nothing for a valid term.
   */
  const needle = query.trim().toLowerCase();
  const visibleGuides = useMemo(
    () =>
      needle
        ? GUIDES.filter(
            (guide) =>
              guide.title.toLowerCase().includes(needle) ||
              guide.steps.some((step) => step.toLowerCase().includes(needle))
          )
        : GUIDES,
    [needle]
  );
  const visibleMethods = useMemo(() => {
    const all = catalog?.methods ?? [];
    if (!needle) return all;
    return all.filter((method) =>
      [method.label, method.label_en, method.purpose]
        .join(" ")
        .toLowerCase()
        .includes(needle)
    );
  }, [catalog, needle]);

  return (
    <AppShell
      eyebrow="Kituo cha msaada"
      title="Msaada na nyaraka"
      description="Jinsi ya kutumia StatFlow, na mbinu zake zote."
    >
      {/* The prototype's help search. Placed above the guides because it is the
          thing people arrive here to use, not a per-section filter. */}
      <div className="mb-4">
        <InlineSearch
          value={query}
          onChange={setQuery}
          placeholder="Tafuta miongozo, vipengele na mbinu za takwimu..."
          label="Tafuta msaada"
        />
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {visibleGuides.map((guide) => (
          <Card key={guide.title}>
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-sm bg-primary-50 text-primary-600">
                <Icon name={guide.icon} size={16} />
              </span>
              <h2 className="text-h3 text-ink">{guide.title}</h2>
            </div>
            <ol className="mt-3 space-y-2">
              {guide.steps.map((step, index) => (
                <li key={step} className="flex gap-2.5 text-body text-ink-secondary">
                  <span className="tabular flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-sunken text-caption font-medium text-ink-muted">
                    {index + 1}
                  </span>
                  {step}
                </li>
              ))}
            </ol>
          </Card>
        ))}
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card
          title="Mbinu zinazopatikana"
          icon="calculator"
          description="Zinatokana na katalogi ya moja kwa moja, hivyo hazitapotoshwa."
        >
          {loading ? (
            <TableSkeleton rows={5} columns={2} />
          ) : needle ? (
            /* With a search term the category counts would be unchanged and so
               would look unresponsive, so the card lists the matching methods
               instead. The counts stay meaningful when nothing is searched. */
            visibleMethods.length === 0 ? (
              <p className="text-body text-ink-muted">
                Hakuna mbinu inayolingana na &ldquo;{query.trim()}&rdquo;.
              </p>
            ) : (
              <ul className="divide-y divide-surface-border">
                {visibleMethods.map((method) => (
                  <li key={method.key} className="py-2">
                    <p className="text-body font-medium text-ink">
                      {method.label}
                    </p>
                    <p className="mt-0.5 text-caption text-ink-muted">
                      {method.purpose}
                    </p>
                  </li>
                ))}
              </ul>
            )
          ) : (
            <ul className="divide-y divide-surface-border">
              {byCategory.map(([category, counts]) => (
                <li
                  key={category}
                  className="flex items-center justify-between gap-3 py-2"
                >
                  <span className="text-body capitalize text-ink">
                    {category.replace(/_/g, " ")}
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="tabular text-caption text-ink-muted">
                      {counts.implemented} / {counts.total}
                    </span>
                    <Badge
                      tone={counts.implemented === counts.total ? "success" : "neutral"}
                    >
                      {counts.implemented === counts.total ? "kamili" : "sehemu"}
                    </Badge>
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-caption text-ink-muted">
            Mbinu zilizobaki zimeandikwa lakini bado hazijasambuliwa. Zinahitaji kipimo
            cha kipekee kabla ya kuaminika.
          </p>
        </Card>

        <Card title="Maswali yanayoulizwa mara kwa mara" icon="info">
          <dl className="space-y-4">
            {FAQ.map((item) => (
              <div key={item.q}>
                <dt className="text-body font-medium text-ink">{item.q}</dt>
                <dd className="mt-1 text-body text-ink-secondary">{item.a}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 text-caption text-ink-muted">
            Tatua lingine? Anza kwenye{" "}
            <Link href="/templates" className="text-primary-700 underline">
              makadirio
            </Link>{" "}
            au{" "}
            <Link href="/datasets" className="text-primary-700 underline">
              datasets zako
            </Link>
            .
          </p>
        </Card>
      </div>
    </AppShell>
  );
}