import type { IconName } from "@/components/Icon";

/**
 * The StatFlow journey, as one source of truth.
 *
 * There are two different things here and conflating them caused the old
 * six-step version to hide half the workflow:
 *
 * 1. The 11 **stages**, the real work. Profile, Clean and Transform share one
 *    page but are three separate pieces of work with three separate results, so
 *    they get their own stage and their own deep link. Export is not the same
 *    act as composing a report, so it is not folded into Report.
 * 2. The 6 **phases**, the compact indicator the design spec asks for in
 *    section 12: Data -> Prepare -> Analyze -> Visualize -> Explain -> Report.
 *    Eleven items do not fit in the top bar on a laptop, and the phases are
 *    what a returning user actually navigates by.
 *
 * `sharesTargetWith` is the honest bit: it marks a stage whose link lands on a
 * page another stage also uses. Hiding that would make the progress bar claim
 * more than the product can do.
 */

export type PipelinePhaseKey =
  | "data"
  | "prepare"
  | "analyze"
  | "visualize"
  | "explain"
  | "report";

export interface PipelineStage {
  key: string;
  step: number;
  /** Short label for the compact phase indicator. */
  label: string;
  /** The stage's own name, used by the full journey rail. */
  fullLabel: string;
  /** The English name from the design spec, kept so the mapping is checkable. */
  labelEn: string;
  description: string;
  phase: PipelinePhaseKey;
  icon: IconName;
  hrefFor: (datasetId: number | string) => string;
  /**
   * Another stage key that links to the same page, or null when this stage has
   * a screen of its own. The journey rail shows this instead of pretending.
   */
  sharesTargetWith: string | null;
  /**
   * What has to be true for the stage to count as finished. A stage with no
   * artifact has nothing to complete, which is why `null` is a valid answer
   * and not an oversight.
   */
  completion: StageCompletion;
}

export type StageCompletion =
  | { kind: "always" }
  | { kind: "profiled" }
  | { kind: "cleanOperations" }
  | { kind: "transformOperations" }
  | { kind: "analysisRuns" }
  | { kind: "charts" }
  | { kind: "none" }
  | { kind: "exports" };

export const PIPELINE_STAGES: PipelineStage[] = [
  {
    key: "upload",
    step: 1,
    label: "Pakia",
    fullLabel: "Pakia",
    labelEn: "Upload",
    description: "Pakia faili (CSV, Excel, JSON, TSV, TXT, Parquet)",
    phase: "data",
    icon: "upload",
    hrefFor: () => "/upload",
    sharesTargetWith: null,
    completion: { kind: "always" },
  },
  {
    key: "validate",
    step: 2,
    label: "Thibitisha",
    fullLabel: "Thibitisha data",
    labelEn: "Validate",
    description: "Kagua schema, data types, encoding na duplikati kabla ya kuendelea",
    phase: "data",
    icon: "check",
    hrefFor: (datasetId) => `/datasets/${datasetId}/validate`,
    sharesTargetWith: null,
    completion: { kind: "none" },
  },
  {
    key: "profile",
    step: 3,
    label: "Profile",
    fullLabel: "Profile ya columns",
    labelEn: "Profile",
    description: "Muundo, distributions, missing na outliers za kila column",
    phase: "data",
    icon: "table",
    hrefFor: (datasetId) => `/datasets/${datasetId}/studio?stage=profile`,
    sharesTargetWith: "clean",
    completion: { kind: "profiled" },
  },
  {
    key: "clean",
    step: 4,
    label: "Safisha",
    fullLabel: "Safisha data",
    labelEn: "Clean",
    description: "Ondoa au kaza missing values na safisha rows",
    phase: "prepare",
    icon: "clipboard",
    hrefFor: (datasetId) => `/datasets/${datasetId}/studio?stage=clean`,
    sharesTargetWith: "transform",
    completion: { kind: "cleanOperations" },
  },
  {
    key: "transform",
    step: 5,
    label: "Badilisha",
    fullLabel: "Badilisha data",
    labelEn: "Transform",
    description: "Tengeneza dataset version mpya kwa operations",
    phase: "prepare",
    icon: "layers",
    hrefFor: (datasetId) => `/datasets/${datasetId}/studio?stage=transform`,
    sharesTargetWith: "profile",
    completion: { kind: "transformOperations" },
  },
  {
    key: "explore",
    step: 6,
    label: "Chunguza",
    fullLabel: "Chunguza data",
    labelEn: "Explore",
    description: "Distributions na correlations kabla ya kuchagua mbinu",
    phase: "prepare",
    icon: "chart",
    hrefFor: (datasetId) => `/datasets/${datasetId}/explore`,
    sharesTargetWith: null,
    completion: { kind: "none" },
  },
  {
    key: "analyze",
    step: 7,
    label: "Uchambuzi",
    fullLabel: "Endesha uchambuzi",
    labelEn: "Analyze",
    description: "Endesha uchambuzi wa takwimu na uangalie assumptions",
    phase: "analyze",
    icon: "calculator",
    hrefFor: (datasetId) => `/datasets/${datasetId}/statistics`,
    sharesTargetWith: null,
    completion: { kind: "analysisRuns" },
  },
  {
    key: "visualize",
    step: 8,
    label: "Chora",
    fullLabel: "Chora data",
    labelEn: "Visualize",
    description: "Buni grafu na taswira za data",
    phase: "visualize",
    icon: "chart",
    hrefFor: (datasetId) => `/datasets/${datasetId}/charts`,
    sharesTargetWith: null,
    completion: { kind: "charts" },
  },
  {
    key: "explain",
    step: 9,
    label: "Eleza",
    fullLabel: "Eleza matokeo",
    labelEn: "Explain",
    description: "Uliza swali kuhusu matokeo yenye kuthibitishwa",
    phase: "explain",
    icon: "sparkles",
    hrefFor: (datasetId) => `/datasets/${datasetId}/ask`,
    sharesTargetWith: null,
    // The ask page holds the conversation in component state and stores no
    // message row, so there is nothing to count and nothing to prove.
    completion: { kind: "none" },
  },
  {
    key: "report",
    step: 10,
    label: "Ripoti",
    fullLabel: "Tunga ripoti",
    labelEn: "Report",
    description: "Panga ripoti yenye muhtasari, methodology na matokeo",
    phase: "report",
    icon: "file-text",
    hrefFor: (datasetId) => `/datasets/${datasetId}/export?stage=report`,
    sharesTargetWith: "export",
    // Composing a report writes nothing; only the export leaves a record. So
    // Report has no completion of its own and Export carries the whole phase.
    completion: { kind: "none" },
  },
  {
    key: "export",
    step: 11,
    label: "Hamisha",
    fullLabel: "Hamisha na pakua",
    labelEn: "Export / Share",
    description: "Pakua ripoti au isambele kwa mtu mwingine",
    phase: "report",
    icon: "download",
    hrefFor: (datasetId) => `/datasets/${datasetId}/export?stage=export`,
    sharesTargetWith: "report",
    completion: { kind: "exports" },
  },
];

export interface PipelinePhase {
  key: PipelinePhaseKey;
  label: string;
  labelEn: string;
  /** First and last stage step of this phase. */
  from: number;
  to: number;
}

export const PIPELINE_PHASES: PipelinePhase[] = [
  { key: "data", label: "Data", labelEn: "Data", from: 1, to: 3 },
  { key: "prepare", label: "Prepare", labelEn: "Prepare", from: 4, to: 6 },
  { key: "analyze", label: "Analyze", labelEn: "Analyze", from: 7, to: 7 },
  { key: "visualize", label: "Visualize", labelEn: "Visualize", from: 8, to: 8 },
  { key: "explain", label: "Explain", labelEn: "Explain", from: 9, to: 9 },
  { key: "report", label: "Report", labelEn: "Report", from: 10, to: 11 },
];

const PHASE_BY_KEY = new Map(PIPELINE_PHASES.map((phase) => [phase.key, phase]));

export function phaseOfStage(stage: PipelineStage): PipelinePhase {
  const phase = PHASE_BY_KEY.get(stage.phase);
  if (!phase) {
    throw new Error(`Unknown phase "${stage.phase}" on stage "${stage.key}"`);
  }
  return phase;
}

/** The phase a stage number belongs to, used to light up the compact bar. */
export function phaseFromStep(step: number | null): PipelinePhase | null {
  if (step === null) return null;
  return (
    PIPELINE_PHASES.find((phase) => step >= phase.from && step <= phase.to) ?? null
  );
}

/** Section → pipeline stage for the nested `/datasets/{id}/...` routes. */
const SECTION_STAGE: Record<string, number> = {
  validate: 2,
  studio: 3,
  explore: 6,
  analyze: 7,
  statistics: 7,
  ask: 9,
  charts: 8,
  export: 10,
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
  if (!section) return { stage: 3, datasetId };
  return { stage: SECTION_STAGE[section] ?? null, datasetId };
}

export interface StageProgressInput {
  status: string;
  profiledColumnCount?: number;
  /** Operations logged with `operation_group = 'clean'`. */
  cleanOperationCount?: number;
  /** Operations logged with `operation_group = 'transform'`. */
  transformOperationCount?: number;
  analysisRunCount?: number;
  chartCount?: number;
  exportCount?: number;
}
export type StageState = "done" | "current" | "available";

/**
 * A stage that leaves no record behind can never be reported done.
 *
 * Reading a validation report, exploring a distribution, asking the assistant
 * and composing a report all produce output but no row to count. Calling those
 * stages done would be a progress bar that flatters the product, and calling
 * them pending would never clear, so the UI says what they are: a read.
 */
export function isStageTransient(stage: PipelineStage): boolean {
  return stage.completion.kind === "none";
}

/**
 * Whether one stage is finished, from real records only.
 */
export function isStageDone(
  stage: PipelineStage,
  input: StageProgressInput
): boolean {
  switch (stage.completion.kind) {
    case "always":
      return true;
    case "none":
      return false;
    case "profiled":
      return (input.profiledColumnCount ?? 0) > 0;
    case "cleanOperations":
      return (input.cleanOperationCount ?? 0) > 0 || input.status === "cleaned";
    case "transformOperations":
      return (input.transformOperationCount ?? 0) > 0;
    case "analysisRuns":
      return (input.analysisRunCount ?? 0) > 0 || input.status === "analyzed";
    case "charts":
      return (input.chartCount ?? 0) > 0;
    case "exports":
      return (input.exportCount ?? 0) > 0;
    default:
      return false;
  }
}

/**
 * Resolve each stage's state against one dataset's real records.
 *
 * There is deliberately no "blocked" state. Nothing in the product stops a user
 * opening the analysis page before cleaning, so labelling a later stage blocked
 * would describe a gate that does not exist.
 */
export function resolveStageStates(
  input: StageProgressInput,
  currentStage: number | null
): Map<string, StageState> {
  const states = new Map<string, StageState>();
  for (const stage of PIPELINE_STAGES) {
    if (isStageDone(stage, input)) {
      states.set(stage.key, "done");
    } else if (stage.step === currentStage) {
      states.set(stage.key, "current");
    } else {
      states.set(stage.key, "available");
    }
  }
  return states;
}

/**
 * The stage worth suggesting next.
 *
 * Read-only stages are skipped, because a stage that can never be recorded as
 * done would otherwise be suggested forever and block the real next step. They
 * are only suggested when nothing else is left.
 */
export function suggestedNextStage(input: StageProgressInput): PipelineStage | null {
  const pending = PIPELINE_STAGES.filter((stage) => !isStageDone(stage, input));
  return (
    pending.find((stage) => !isStageTransient(stage)) ??
    pending[0] ??
    null
  );
}

/** Highest stage a record can prove, for compact indicators. */
export function furthestReachedStage(input: StageProgressInput): number {
  let last = 1;
  for (const stage of PIPELINE_STAGES) {
    if (isStageDone(stage, input)) last = stage.step;
  }
  return last;
}

/** How many stages a dataset has completed, for the datasets list. */
export function completedStageCount(input: StageProgressInput): number {
  return PIPELINE_STAGES.filter((stage) => isStageDone(stage, input)).length;
}
