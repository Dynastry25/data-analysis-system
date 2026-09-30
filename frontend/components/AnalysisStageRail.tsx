"use client";

import { Badge } from "./Badge";
import { Card } from "./Card";
import { Icon } from "./Icon";
import { AnalysisMethod, AnalysisStage } from "@/lib/api";

interface AnalysisStageRailProps {
  method: AnalysisMethod;
  stages: AnalysisStage[];
  /**
   * Highest stage order the reader has got past, or -1 for nothing yet.
   *
   * This is derived state, not a stored checklist: the product does not persist
   * "I read the assumptions", so the rail shows where the work is, not a
   * progress record it cannot honestly keep.
   */
  completedThrough: number;
}

/**
 * The stage plan for the chosen method, as a rail the reader works down.
 *
 * This is the part of the guide that has to change with the method: a survey
 * method gains a design step, a time-series method gains a stationarity step,
 * and a method with assumptions gains an assumptions step. The order comes from
 * the backend so there is one source of truth for it.
 */
export function AnalysisStageRail({
  method,
  stages,
  completedThrough,
}: AnalysisStageRailProps) {
  return (
    <Card
      title={`Hatua za uchambuzi: ${method.label_sw}`}
      icon="layers"
      description="Hatua hizi zinatoka kwenye mwongozo kwa method uliyochagua, si orodha ya kawaida."
    >
      <ol className="space-y-2">
        {stages.map((stage) => (
          <StageRow
            key={stage.key}
            stage={stage}
            done={stage.order <= completedThrough}
            current={stage.order === completedThrough + 1}
          />
        ))}
      </ol>
    </Card>
  );
}

function StageRow({
  stage,
  done,
  current,
}: {
  stage: AnalysisStage;
  done: boolean;
  current: boolean;
}) {
  return (
    <li
      className={`rounded-md border p-3 ${
        current ? "border-primary-200 bg-primary-50/50" : "border-surface-border"
      }`}
    >
      <div className="flex flex-wrap items-start gap-2">
        <span
          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-caption font-semibold ${
            done
              ? "bg-success-700 text-white"
              : current
                ? "bg-primary text-white"
                : "bg-surface-sunken text-ink-muted"
          }`}
        >
          {done ? <Icon name="check" size={12} /> : stage.order}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-body font-medium text-ink">{stage.label}</p>
          <p className="text-caption text-ink-muted">{stage.label_en}</p>
          <p className="mt-1 text-caption text-ink-secondary">{stage.description}</p>
          {stage.checks && stage.checks.length > 0 && (
            <ul className="mt-2 list-disc space-y-0.5 pl-4 text-caption text-ink-secondary">
              {stage.checks.map((check) => (
                <li key={check}>{check}</li>
              ))}
            </ul>
          )}
          {stage.outputs && (
            <p className="mt-2 text-caption text-ink-secondary">
              <span className="font-medium text-ink-muted">Matokeo: </span>
              {stage.outputs}
            </p>
          )}
          {stage.alternatives && stage.alternatives.length > 0 && (
            <p className="mt-1 text-caption text-ink-secondary">
              <span className="font-medium text-ink-muted">Ukichanganua: </span>
              {stage.alternatives.join(", ").replace(/_/g, " ")}
            </p>
          )}
        </div>
        {stage.gate && (
          <Badge tone="warning" size="sm">
            Inahitajika
          </Badge>
        )}
      </div>
    </li>
  );
}
