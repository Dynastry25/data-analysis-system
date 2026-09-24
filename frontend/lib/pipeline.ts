import type { IconName } from "@/components/Icon";

/**
 * The 6-stage StatFlow pipeline: upload → preview → clean → analyse → charts
 * → report. The same stages drive the sidebar flow, the top PipelineStepper,
 * the dataset list progress and the dashboard guide, so one source of truth
 * lives here. Keep in sync with the routes in the backend "journey".
 */
export interface PipelineStage {
  key: string;
  step: number;
  label: string;
  description: string;
  icon: IconName;
  hrefFor: (datasetId: number | string) => string;
}

export const PIPELINE_STAGES: PipelineStage[] = [
  {
    key: "upload",
    step: 1,
    label: "Pakia",
    description: "Pakia faili (CSV, Excel, JSON, TSV, TXT, Parquet)",
    icon: "upload",
    hrefFor: () => "/upload",
  },
  {
    key: "preview",
    step: 2,
    label: "Angalia",
    description: "Tazama muundo, columns na preview ya data",
    icon: "table",
    hrefFor: (datasetId) => `/datasets/${datasetId}`,
  },
  {
    key: "clean",
    step: 3,
    label: "Safisha",
    description: "Ondoa kasoro kwenye Data Studio (versions)",
    icon: "clipboard",
    hrefFor: (datasetId) => `/datasets/${datasetId}/studio`,
  },
  {
    key: "analyze",
    step: 4,
    label: "Chambua",
    description: "Endesha uchambuzi wa takwimu",
    icon: "calculator",
    hrefFor: (datasetId) => `/datasets/${datasetId}/statistics`,
  },
  {
    key: "chart",
    step: 5,
    label: "Chati",
    description: "Buni grafu na taswira za data",
    icon: "chart",
    hrefFor: (datasetId) => `/datasets/${datasetId}/charts`,
  },
  {
    key: "report",
    step: 6,
    label: "Ripoti",
    description: "Tengeneza ripoti ya PDF au Excel",
    icon: "file-text",
    hrefFor: (datasetId) => `/datasets/${datasetId}/export`,
  },
];

/** Section → pipeline stage for the nested `/datasets/{id}/...` routes. */
const SECTION_STAGE: Record<string, number> = {
  studio: 3,
  statistics: 4,
  analyze: 4,
  ask: 4,
  charts: 5,
  export: 6,
};

/** Which stage the current URL belongs to (and the dataset id, if any). */
export function pipelineStageFromPathname(pathname: string): {
  stage: number | null;
  datasetId: number | null;
} {
  if (pathname === "/upload") return { stage: 1, datasetId: null };
  const match = pathname.match(/^\/datasets\/(\d+)(?:\/([^/]+))?/);
  if (!match) return { stage: null, datasetId: null };
  const datasetId = Number(match[1]);
  const section = match[2];
  if (!section) return { stage: 2, datasetId };
  return { stage: SECTION_STAGE[section] ?? null, datasetId };
}

export interface StageProgressInput {
  status: string;
  analysisRunCount?: number;
  chartCount?: number;
  reportCount?: number;
}

/**
 * How many of the 6 stages a dataset has completed (1 = just uploaded).
 * Uses the backend status plus the counts already loaded by pages that know
 * them (dashboard loads analyses/charts/reports per dataset; the datasets
 * list falls back to the status alone — same source of truth).
 */
export function completedStageCount({
  status,
  analysisRunCount = 0,
  chartCount = 0,
  reportCount = 0,
}: StageProgressInput): number {
  let done = 1;
  if (status === "cleaned" || status === "analyzed") done = 3;
  if (analysisRunCount > 0 || status === "analyzed") done = Math.max(done, 4);
  if (chartCount > 0) done = Math.max(done, 5);
  if (reportCount > 0) done = 6;
  return done;
}