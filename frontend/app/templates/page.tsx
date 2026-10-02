"use client";

/**
 * Templates library.
 *
 * A template here is not a stored artefact -- it is a named grouping of
 * methods that the engine actually implements. The list is filtered from the
 * live method catalogue, so a template can never advertise a method the engine
 * does not have, and a method added to the engine appears here without anyone
 * remembering to update this file.
 *
 * "Use template" takes the user to the analysis studio with the method chosen.
 * There is no template-run endpoint, so nothing pretends to execute one.
 */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, EmptyState } from "@/components/Card";
import { Icon, IconName } from "@/components/Icon";
import { TableSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";
import { apiErrorMessage, statflowApi } from "@/lib/api";

interface Template {
  key: string;
  title: string;
  summary: string;
  icon: IconName;
  /** Method keys to offer; those not implemented are dropped. */
  methods: string[];
  structure: string;
}

const TEMPLATES: Template[] = [
  {
    key: "descriptive",
    title: "Uchambuzi wa maelezo",
    summary: "Panga dataset yako kabla ya kuingia kwenye maswali mazito.",
    icon: "table",
    methods: ["descriptive", "frequency", "correlation_matrix", "normality_tests"],
    structure:
      "Safisha missing values, kisha eleza kila column na upe distribution yake.",
  },
  {
    key: "comparison",
    title: "Linganisha makundi",
    summary: "Je, kundi moja inatofautiana na nyingine?",
    icon: "filter",
    methods: ["welch_t_test", "mann_whitney", "one_way_anova", "kruskal_wallis", "chi_square"],
    structure:
      "Chagua kundi la ulinganishaji na column ya thamani, kisha pitia uzinuzi ulio chini.",
  },
  {
    key: "regression",
    title: "Urejeshaji",
    summary: "Eleza matokeo kwa vigezo, na uone kama mtiririko unafaa.",
    icon: "calculator",
    methods: [
      "linear_regression",
      "logistic_regression",
      "poisson_regression",
      "negative_binomial",
      "probit",
    ],
    structure:
      "Chagua target, chagua features, kisha angalia residuals na VIF kabla ya kueleza.",
  },
  {
    key: "association",
    title: "Ushikishano",
    summary: "Iungo kati ya mabadili bila kusema causality.",
    icon: "layers",
    methods: ["chi_square", "fisher_exact", "crosstab", "phi_cramers_v", "partial_correlation"],
    structure: "Tabua ya kila kundi, kisha hesabu kiwango cha muunganisho.",
  },
  {
    key: "reliability",
    title: "Uaminifu",
    summary: "Je, kipimo kina kurudiwa jinsi ile ile?",
    icon: "shield",
    methods: [
      "cronbach_alpha",
      "mcdonalds_omega",
      "cohens_kappa",
      "fleiss_kappa",
      "icc",
      "test_retest",
    ],
    structure: "Kila column ni kipimo; tathmini consistency yao pamoja.",
  },
  {
    key: "survival",
    title: "Uchambuzi wa muda",
    summary: "Muda hadi tukio, ukihesabiwa watu wanaosubiri.",
    icon: "clock",
    methods: ["kaplan_meier", "log_rank", "cox_ph", "parametric_survival"],
    structure:
      "Unahitaji column ya muda na column ya tukio (1 = tukio, 0 = censored).",
  },
  {
    key: "survey",
    title: "Uchambuzi wa utafiti",
    summary: "Data yenye weights, strata na makundi.",
    icon: "clipboard",
    methods: [
      "weighted_analysis",
      "design_based_estimation",
      "design_effect",
      "variance_replication",
      "sample_size",
    ],
    structure:
      "Inahitaji column ya uzito, strata na PSU. Bila hizo, kila kitu hapa hakitosheki.",
  },
];

export default function TemplatesPage() {
  const { showToast } = useToast();
  const [implemented, setImplemented] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    statflowApi
      .methodCatalog()
      .then((catalog) => {
        if (cancelled) return;
        const keys = new Set(
          catalog.methods
            .filter((method) => method.implemented && method.engine)
            .map((method) => method.engine as string)
        );
        setImplemented(keys);
      })
      .catch((caught) => showToast(apiErrorMessage(caught), "danger"))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [showToast]);

  const resolved = useMemo(
    () =>
      TEMPLATES.map((template) => ({
        template,
        // A template whose methods are all unimplemented is not offered; a
        // half-built one would promise a workflow the engine cannot finish.
        available: template.methods.filter((method) => implemented.has(method)),
      })),
    [implemented]
  ).filter((entry) => entry.available.length > 0);

  return (
    <AppShell
      title="Makadirio"
      description="Mipangilio inayoweza kutumika kwa kazi ya kawaida ya uchambuzi."
    >
      {loading ? (
        <Card>
          <TableSkeleton rows={4} columns={2} />
        </Card>
      ) : resolved.length === 0 ? (
        <Card>
          <EmptyState
            title="Hakuna makadirio"
            description="Hakuna mbinu zilizo sani kwa sasa."
            icon="clipboard"
          />
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {resolved.map(({ template, available }) => (
            <Card key={template.key} className="flex flex-col">
              <div className="flex items-start gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm bg-primary-50 text-primary-600">
                  <Icon name={template.icon} size={17} />
                </span>
                <div className="min-w-0">
                  <h2 className="text-h3 text-ink">{template.title}</h2>
                  <p className="mt-0.5 text-caption text-ink-secondary">
                    {template.summary}
                  </p>
                </div>
              </div>

              <p className="mt-3 text-caption text-ink-muted">
                {template.structure}
              </p>

              <div className="mt-3 flex flex-wrap gap-1.5">
                {available.map((method) => (
                  <Badge key={method} tone="neutral">
                    {method.replace(/_/g, " ")}
                  </Badge>
                ))}
              </div>

              <div className="mt-4 flex-1" />
              <div className="mt-4 flex flex-wrap gap-2">
                <Link href={`/datasets`}>
                  <Button variant="secondary" size="small" icon="database">
                    Chagua dataset
                  </Button>
                </Link>
                {/*
                  There is no top-level /statistics route: the analysis studio
                  lives under a dataset, because a method needs columns to run
                  against. So the template sends the user to choose a dataset,
                  which is the step that actually has to happen next.
                */}
                <Link href="/datasets">
                  <Button size="small" icon="arrow-right">
                    Tumia makadirio
                  </Button>
                </Link>
              </div>
            </Card>
          ))}
        </div>
      )}
    </AppShell>
  );
}