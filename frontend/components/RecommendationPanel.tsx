"use client";

import { useEffect, useRef, useState } from "react";

import { Badge } from "./Badge";
import { Button } from "./Button";
import { Card } from "./Card";
import { Icon, IconName } from "./Icon";
import { Skeleton } from "./Skeleton";
import {
  apiErrorMessage,
  AssumptionCheck,
  AssumptionStatus,
  Recommendation,
  statflowApi,
} from "@/lib/api";

const STATUS_META: Record<
  AssumptionStatus,
  { label: string; tone: "neutral" | "success" | "warning" | "danger"; icon: IconName }
> = {
  pass: { label: "Pass", tone: "success", icon: "check" },
  warn: { label: "Warn", tone: "warning", icon: "alert-triangle" },
  fail: { label: "Fail", tone: "danger", icon: "alert-circle" },
  not_applicable: { label: "Not needed", tone: "neutral", icon: "info" },
};

interface RecommendationPanelProps {
  datasetId: number;
  datasetVersion?: number | null;
  outcome: string | null;
  predictor: string | null;
  /** The method currently selected in the configure form, used to flag agreement. */
  selectedAnalysisType: string | null;
  onApply: (recommendation: Recommendation["recommendation"]) => void;
  className?: string;
}

/**
 * Live method recommendation for the selected variable pair.
 *
 * Every verdict here comes from the statistical engine (`assumption_checks`),
 * so the panel never decides for itself whether an assumption holds.
 */
export function RecommendationPanel({
  datasetId,
  datasetVersion,
  outcome,
  predictor,
  selectedAnalysisType,
  onApply,
  className = "",
}: RecommendationPanelProps) {
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef(0);

  const ready = Boolean(outcome && predictor) && Number.isFinite(datasetId);

  useEffect(() => {
    if (!ready || !outcome || !predictor) {
      setRecommendation(null);
      setError(null);
      return;
    }
    const token = ++requestRef.current;
    const timer = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await statflowApi.recommend({
          dataset_id: datasetId,
          dataset_version: datasetVersion ?? undefined,
          outcome,
          predictor,
          run: false,
        });
        if (token === requestRef.current) setRecommendation(response);
      } catch (caught) {
        if (token === requestRef.current) {
          setRecommendation(null);
          setError(apiErrorMessage(caught));
        }
      } finally {
        if (token === requestRef.current) setLoading(false);
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [ready, datasetId, datasetVersion, outcome, predictor]);

  if (!ready) {
    return (
      <Card
        title="Recommended Method"
        icon="sparkles"
        className={className}
        description="Chagua kundi na kutofautisha ili kupendekezwa njia sahihi."
      >
        <p className="text-body text-ink-secondary">
          Pale utakapochagua kundi na kutofautisha, mfumo huu utapendekeza njia ya uchambuzi
          inayofaa na kuonyesha mahusiano yake.
        </p>
      </Card>
    );
  }

  if (loading && !recommendation) {
    return (
      <Card title="Recommended Method" icon="sparkles" className={className}>
        <div className="flex flex-col gap-2">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="mt-2 h-20 w-full" />
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card
        title="Recommended Method"
        icon="sparkles"
        className={className}
        tone="warning"
      >
        <div className="flex items-start gap-2 text-body text-ink-secondary">
          <Icon name="alert-triangle" size={16} className="mt-0.5 shrink-0" />
          <p>{error}</p>
        </div>
      </Card>
    );
  }

  if (!recommendation) return null;

  const current = recommendation.recommendation;
  const checks = current.assumption_checks ?? [];
  const blocking = checks.filter((check) => check.status === "fail");
  const warnings = checks.filter((check) => check.status === "warn");
  const inUse = selectedAnalysisType === current.analysis_type;

  return (
    <Card
      title="Recommended Method"
      icon="sparkles"
      className={className}
      actions={
        inUse ? (
          <Badge tone="info" size="sm">
            Unatumia hii
          </Badge>
        ) : null
      }
    >
      <div className="flex flex-col gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-h3 text-ink">{current.label}</h3>
            <Badge tone="primary" size="sm">
              {current.family}
            </Badge>
          </div>
          <p className="mt-1 text-body text-ink-secondary">{current.why}</p>
          <p className="mt-1 text-caption text-ink-muted">
            Hutoka: {current.output}
          </p>
        </div>

        <div>
          <h4 className="text-overline uppercase tracking-wide text-ink-muted">
            Vigezo vya kuchambua
          </h4>
          <ul className="mt-2 flex flex-col gap-1.5">
            {checks.map((check) => (
              <AssumptionRow key={check.name} check={check} />
            ))}
          </ul>
        </div>

        {blocking.length > 0 && (
          <div className="rounded-md border border-danger/30 bg-danger-bg px-3 py-2">
            <div className="flex items-start gap-2">
              <Icon name="alert-circle" size={16} className="mt-0.5 shrink-0 text-danger-700" />
              <p className="text-body text-danger-700">
                Vigezo {blocking.length} havipotikani na data hii. Chagua njia mwingine au
                badilisha vigezo vilivyochaguliwa.
              </p>
            </div>
          </div>
        )}

        {current.alternatives.length > 0 && (
          <div>
            <h4 className="text-overline uppercase tracking-wide text-ink-muted">
              Njia mbadala
            </h4>
            <ul className="mt-2 flex flex-col gap-1.5">
              {current.alternatives.map((alternative) => (
                <li key={alternative.analysis_type} className="text-body text-ink-secondary">
                  <span className="font-medium text-ink">{alternative.label}</span>
                  {" — "}
                  {alternative.reason}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <Button
            variant="primary"
            size="small"
            icon="sparkles"
            disabled={blocking.length > 0}
            onClick={() => onApply(current)}
          >
            Tumia njia hii
          </Button>
          <p className="self-center text-caption text-ink-muted">
            {warnings.length > 0
              ? `${warnings.length} kivio cha tahadhari kinaeleweka vizuri.`
              : "Unaweza kubadilisha vigezo vyako mwenyewe."}
          </p>
        </div>
      </div>
    </Card>
  );
}

function AssumptionRow({ check }: { check: AssumptionCheck }) {
  const meta = STATUS_META[check.status] ?? STATUS_META.not_applicable;
  return (
    <li className="flex items-start gap-2">
      <Badge tone={meta.tone} size="sm" icon={meta.icon} className="mt-0.5 shrink-0">
        <span className="sr-only">{meta.label}: </span>
        {meta.label}
      </Badge>
      <div className="min-w-0">
        <p className="text-body font-medium text-ink">{check.name}</p>
        <p className="text-caption text-ink-secondary">{check.detail}</p>
        {check.evidence && (
          <p className="text-caption text-ink-muted">Ushahidi: {check.evidence}</p>
        )}
      </div>
    </li>
  );
}

export default RecommendationPanel;
