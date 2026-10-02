import axios, { AxiosProgressEvent, AxiosRequestConfig } from "axios";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

const TOKEN_KEY = "dap_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}

export function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  clearToken();
  if (window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}

export const http = axios.create({ baseURL: API_BASE_URL });

http.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      redirectToLogin();
    }
    return Promise.reject(error);
  }
);

/** Turn an axios error into the backend's `detail` message (or a generic one). */
export function apiErrorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response
    ?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string };
    if (first?.msg) return first.msg;
  }
  if (error instanceof Error) return error.message;
  return "Something went wrong. Please try again.";
}

// ------------------------------------------------------------------ types

export interface RegisterPayload {
  full_name: string;
  email: string;
  password: string;
}

export interface UserProfile {
  id: number;
  full_name: string;
  email: string;
  created_at: string | null;
  /** Present so the UI can offer the admin link without a 403 probe. */
  system_role?: PlatformRole | null;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface ColumnProfile {
  name: string;
  data_type: string | null;
  missing_count: number;
  unique_count: number | null;
  min: unknown;
  max: unknown;
  /**
   * The question this column answers, as the file's author wrote it. Present
   * for Stata and SPSS files, which declare their own columns; null for every
   * other format, and for an unlabelled column.
   */
  variable_label?: string | null;
  /**
   * Code -> word for a labelled categorical, e.g. `{ "1": "Male", "2": "Female" }`.
   * The stored value is the code: the platform never replaces it with the word,
   * because a numeric code has to stay numeric to be analysable. null means the
   * column carries no such lookup, which is different from an empty one.
   */
  value_labels?: Record<string, string> | null;
}

/** How a stored code reads in the file's own words, or falls back to itself. */
export function labelForValue(
  value: unknown,
  valueLabels: Record<string, string> | null | undefined,
): string {
  if (!valueLabels) return String(value);
  // The backend normalises every code to a string key, so a number and a string
  // that mean the same code both land on the same entry here.
  return valueLabels[String(value)] ?? String(value);
}

export interface DatasetSummary {
  id: number;
  user_id: number;
  original_filename: string;
  file_type: string;
  project_id: number | null;
  project_name: string | null;
  status: string;
  uploaded_at: string | null;
  row_count: number;
  column_count: number;
  current_version: number | null;
}

export interface UploadResponse {
  dataset_id: number;
  original_filename: string;
  project_id: number | null;
  row_count: number;
  column_count: number;
  columns: ColumnProfile[];
  status: string;
}

export interface DatasetDetailResponse {
  dataset: DatasetSummary;
  dataset_version: number;
  columns: ColumnProfile[];
  preview_rows: Record<string, unknown>[];
}

export interface ProfileResponse {
  dataset_id: number;
  dataset_version: number;
  row_count: number;
  column_count: number;
  columns: ColumnProfile[];
}

export interface ValidationIssue {
  code: string;
  severity: "error" | "warning" | "info";
  message: string;
  column: string | null;
  detail: Record<string, unknown>;
}

/** Data-quality findings, all computed in the backend. */
export interface ValidationResponse {
  dataset_id: number;
  dataset_version: number;
  row_count: number;
  column_count: number;
  verdict: "clean" | "warnings" | "blocked";
  error_count: number;
  warning_count: number;
  info_count: number;
  summary: string;
  issues: ValidationIssue[];
}

export interface ExploreColumn {
  name: string;
  data_type: string | null;
  kind: "numeric" | "categorical" | "datetime" | "text" | "boolean";
  missing_count: number;
  missing_ratio: number;
  unique_count: number | null;
  min?: number | null;
  max?: number | null;
  mean?: number | null;
  median?: number | null;
  std?: number | null;
  quantiles?: Record<string, number>;
  top_values?: { value: unknown; count: number }[];
  histogram?: { start: number; end: number; count: number }[];
  /** As on ColumnProfile: declared by Stata/SPSS, null elsewhere. */
  variable_label?: string | null;
  /** As on ColumnProfile: the code -> word lookup, when the column has one. */
  value_labels?: Record<string, string> | null;
}

export interface ExplorePair {
  x: string;
  y: string;
  method: "pearson" | "spearman";
  coefficient: number;
  strength: "weak" | "moderate" | "strong";
  interpretation: string;
}

/** The shape of the data, before choosing a statistical method. */
export interface ExploreResponse {
  dataset_id: number;
  dataset_version: number;
  row_count: number;
  column_count: number;
  columns: ExploreColumn[];
  correlations: ExplorePair[];
  warnings: string[];
}

/**
 * One stage of the 11-stage journey, as the backend can prove it.
 *
 * `record_count` is null for a stage that leaves no record (validate, explore,
 * explain, report). Those can never be `done`, and the UI labels them as a read
 * rather than as pending work.
 */
export interface JourneyStage {
  key: string;
  step: number;
  done: boolean;
  record_count: number | null;
  reason: string;
}

export interface JourneyResponse {
  dataset_id: number;
  dataset_status: string;
  stages: JourneyStage[];
}

export type AnalysisType = string;

export interface AnalyzePayload {
  analysis_type: string;
  parameters: Record<string, unknown>;
}

export interface AnalysisRecord extends AnalysisRunRecord {}

export type ChartType = "bar" | "line" | "scatter" | "histogram";

export type ChartPaletteName = "default" | "ocean" | "sunset" | "forest";

export interface ChartFormat {
  palette?: ChartPaletteName | null;
  show_data_labels?: boolean | null;
  show_grid?: boolean | null;
  x_scale?: "linear" | "log" | null;
  y_scale?: "linear" | "log" | null;
}

export interface ChartConfig {
  x: string;
  y?: string | null;
  group_by?: string | null;
  aggregate?: string;
  bins?: number | null;
  limit?: number | null;
  format?: ChartFormat | null;
}

export interface ChartSeries {
  name: string;
  x: unknown[];
  y?: (number | null)[];
  type?: string;
  mode?: string;
  nbinsx?: number;
}

export interface ChartData {
  chart_type: ChartType;
  x_label: string;
  y_label: string;
  series: ChartSeries[];
  meta?: Record<string, any>;
}

export interface ChartPayload {
  chart_type: ChartType;
  config: ChartConfig;
  dataset_version?: number;
}

export interface ChartRecord {
  chart_id: number;
  dataset_id: number;
  dataset_version: number | null;
  chart_type: ChartType;
  config: ChartConfig;
  chart_data: ChartData;
  created_at: string | null;
}

// ---------------------------------------------------------------- Dashboards

export type DashboardWidgetType = "kpi" | "chart" | "filter" | "insight" | "text";

/** What a KPI widget is computed from. */
export interface DashboardKpiSource {
  /** "analysis" uses a metric from a saved analysis result; "column" uses a column mean. */
  kind: "analysis" | "column";
  analysis_id?: number;
  metric?: string;
  label?: string;
  column?: string;
}

export interface DashboardWidget {
  id: string;
  type: DashboardWidgetType;
  title?: string;
  // kpi
  source?: DashboardKpiSource;
  // chart
  chart_id?: number;
  // filter
  column?: string;
  operator?: "=" | ">" | "<";
  value?: string;
  // insight
  analysis_id?: number;
  // text
  content?: string;
}

export interface DashboardRecord {
  dashboard_id: number;
  dataset_id: number;
  dataset_version: number | null;
  dataset_version_id: number | null;
  name: string;
  title?: string | null;
  config: { widgets?: DashboardWidget[] };
  created_by?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DashboardCreatePayload {
  name: string;
  title?: string;
  widgets?: DashboardWidget[];
  dataset_version?: number;
}

export interface DashboardUpdatePayload {
  name?: string;
  title?: string;
  widgets?: DashboardWidget[];
}

export interface ExportPayload {
  format: "pdf" | "xlsx";
  dataset_version?: number;
  include_analysis_ids: number[];
  include_chart_ids: number[];
}

export interface ExportResponse {
  report_id: number;
  status: string;
}

export interface ReportRecord {
  id: number;
  dataset_id: number;
  dataset_version: number | null;
  file_format: string;
  status: string;
  error_message: string | null;
  created_at: string | null;
  download_url: string;
}

export interface ReportStatus {
  report_id: number;
  dataset_id: number;
  dataset_version: number | null;
  file_format: string;
  status: string;
  error_message: string | null;
  download_url: string;
  created_at: string | null;
}

export type OrgRole = "owner" | "admin" | "analyst" | "viewer";

export interface Organization {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  created_by: number | null;
  created_at: string | null;
  my_role: OrgRole | null;
  member_count: number;
  project_count: number;
}

export interface OrgMember {
  id: number;
  organization_id: number;
  user_id: number;
  full_name: string | null;
  email: string | null;
  role: string;
  joined_at: string | null;
}
export interface OrgProject {
  id: number;
  organization_id: number;
  name: string;
  description: string | null;
  created_by: number | null;
  created_at: string | null;
  dataset_count: number;
}

export interface OrgTeam {
  id: number;
  organization_id: number;
  name: string;
  description: string | null;
  created_by: number | null;
  created_at: string | null;
  member_count: number;
}

export interface TeamMember {
  id: number;
  team_id: number;
  user_id: number;
  full_name: string | null;
  email: string | null;
  joined_at: string | null;
}

// ------------------------------------------------------------ API methods

// Analysis + reports always flow through the unified engine (MVP-19+) —
// the legacy /analyze + /clean endpoints were removed in MVP-23.
export const api = {
  auth: {
    register: (payload: RegisterPayload) =>
      http.post<UserProfile>("/auth/register", payload).then((r) => r.data),
    login: (payload: LoginPayload) =>
      http.post<LoginResponse>("/auth/login", payload).then((r) => r.data),
    me: () => http.get<UserProfile>("/auth/me").then((r) => r.data),
  },
  datasets: {
    upload: (
      file: File,
      onUploadProgress?: (event: AxiosProgressEvent) => void,
      projectId?: number | null
    ) => {
      const formData = new FormData();
      formData.append("file", file);
      if (projectId) {
        formData.append("project_id", String(projectId));
      }
      return http
        .post<UploadResponse>("/datasets/upload", formData, {
          headers: { "Content-Type": "multipart/form-data" },
          onUploadProgress,
        } as AxiosRequestConfig)
        .then((r) => r.data);
    },
    list: () => http.get<DatasetSummary[]>("/datasets").then((r) => r.data),
    get: (id: number) =>
      http.get<DatasetDetailResponse>(`/datasets/${id}`).then((r) => r.data),
    setProject: (id: number, projectId: number | null) =>
      http
        .patch<DatasetSummary>(`/datasets/${id}/project`, { project_id: projectId })
        .then((r) => r.data),
    profile: (id: number) =>
    http.get<ProfileResponse>(`/datasets/${id}/profile`).then((r) => r.data),
    journey: (id: number) =>
      http.get<JourneyResponse>(`/datasets/${id}/journey`).then((r) => r.data),
    validate: (id: number) =>
      http.get<ValidationResponse>(`/datasets/${id}/validate`).then((r) => r.data),
    explore: (id: number) =>
      http.get<ExploreResponse>(`/datasets/${id}/explore`).then((r) => r.data),
    remove: (id: number) => http.delete(`/datasets/${id}`).then((r) => r.data),
  },
  charts: {
    create: (id: number, payload: ChartPayload) =>
      http.post<ChartRecord>(`/datasets/${id}/charts`, payload).then((r) => r.data),
    listForDataset: (id: number) =>
      http.get<ChartRecord[]>(`/datasets/${id}/charts`).then((r) => r.data),
    get: (chartId: number) =>
      http.get<ChartRecord>(`/charts/${chartId}`).then((r) => r.data),
  },
  dashboards: {
    create: (id: number, payload: DashboardCreatePayload) =>
      http
        .post<DashboardRecord>(`/datasets/${id}/dashboards`, payload)
        .then((r) => r.data),
    listForDataset: (id: number) =>
      http.get<DashboardRecord[]>(`/datasets/${id}/dashboards`).then((r) => r.data),
    get: (dashboardId: number) =>
      http.get<DashboardRecord>(`/dashboards/${dashboardId}`).then((r) => r.data),
    update: (dashboardId: number, payload: DashboardUpdatePayload) =>
      http
        .put<DashboardRecord>(`/dashboards/${dashboardId}`, payload)
        .then((r) => r.data),
    remove: (dashboardId: number) =>
      http.delete(`/dashboards/${dashboardId}`).then((r) => r.data),
  },
  reports: {
    create: (id: number, payload: ExportPayload) =>
      http.post<ExportResponse>(`/datasets/${id}/export`, payload).then((r) => r.data),
    status: (reportId: number) =>
      http.get<ReportStatus>(`/reports/${reportId}/status`).then((r) => r.data),
    listForDataset: (id: number) =>
      http.get<ReportRecord[]>(`/datasets/${id}/reports`).then((r) => r.data),
    downloadUrl: (reportId: number) =>
      `${API_BASE_URL}/reports/${reportId}/download`,
  },
  organizations: {
    list: () =>
      http.get<Organization[]>("/v1/organizations").then((r) => r.data),
    get: (organizationId: number) =>
      http
        .get<Organization>(`/v1/organizations/${organizationId}`)
        .then((r) => r.data),
    create: (payload: { name: string; description?: string; slug?: string }) =>
      http
        .post<Organization>("/v1/organizations", payload)
        .then((r) => r.data),
    update: (organizationId: number, payload: { name?: string; description?: string }) =>
      http
        .patch<Organization>(`/v1/organizations/${organizationId}`, payload)
        .then((r) => r.data),
    remove: (organizationId: number) =>
      http.delete(`/v1/organizations/${organizationId}`).then((r) => r.data),
    members: (organizationId: number) =>
      http
        .get<OrgMember[]>(`/v1/organizations/${organizationId}/members`)
        .then((r) => r.data),
    addMember: (organizationId: number, payload: { email: string; role: OrgRole }) =>
      http
        .post<OrgMember>(`/v1/organizations/${organizationId}/members`, payload)
        .then((r) => r.data),
    updateMember: (
      organizationId: number,
      userId: number,
      payload: { role: OrgRole }
    ) =>
      http
        .patch<OrgMember>(
          `/v1/organizations/${organizationId}/members/${userId}`,
          payload
        )
        .then((r) => r.data),
    removeMember: (organizationId: number, userId: number) =>
      http
        .delete(`/v1/organizations/${organizationId}/members/${userId}`)
        .then((r) => r.data),
    projects: (organizationId: number) =>
      http
        .get<OrgProject[]>(`/v1/organizations/${organizationId}/projects`)
        .then((r) => r.data),
    createProject: (
      organizationId: number,
      payload: { name: string; description?: string }
    ) =>
      http
        .post<OrgProject>(`/v1/organizations/${organizationId}/projects`, payload)
        .then((r) => r.data),
    updateProject: (
      organizationId: number,
      projectId: number,
      payload: { name?: string; description?: string }
    ) =>
      http
        .patch<OrgProject>(
          `/v1/organizations/${organizationId}/projects/${projectId}`,
          payload
        )
        .then((r) => r.data),
    removeProject: (organizationId: number, projectId: number) =>
      http
        .delete(`/v1/organizations/${organizationId}/projects/${projectId}`)
        .then((r) => r.data),
    teams: {
      list: (organizationId: number) =>
        http
          .get<OrgTeam[]>(`/v1/organizations/${organizationId}/teams`)
          .then((r) => r.data),
      create: (
        organizationId: number,
        payload: { name: string; description?: string }
      ) =>
        http
          .post<OrgTeam>(`/v1/organizations/${organizationId}/teams`, payload)
          .then((r) => r.data),
      update: (
        organizationId: number,
        teamId: number,
        payload: { name?: string; description?: string }
      ) =>
        http
          .patch<OrgTeam>(
            `/v1/organizations/${organizationId}/teams/${teamId}`,
            payload
          )
          .then((r) => r.data),
      remove: (organizationId: number, teamId: number) =>
        http
          .delete(`/v1/organizations/${organizationId}/teams/${teamId}`)
          .then((r) => r.data),
      members: (organizationId: number, teamId: number) =>
        http
          .get<TeamMember[]>(
            `/v1/organizations/${organizationId}/teams/${teamId}/members`
          )
          .then((r) => r.data),
      addMember: (organizationId: number, teamId: number, userId: number) =>
        http
          .post<TeamMember>(
            `/v1/organizations/${organizationId}/teams/${teamId}/members`,
            { user_id: userId }
          )
          .then((r) => r.data),
      removeMember: (organizationId: number, teamId: number, userId: number) =>
        http
          .delete(
            `/v1/organizations/${organizationId}/teams/${teamId}/members/${userId}`
          )
          .then((r) => r.data),
    },
  },
};


// ------------------------------------------- StatFlow unified API (MVP-18+)

export interface OperationCatalogEntry {
  type: string;
  group: "clean" | "transform";
  label: string;
  parameters: string[];
  /** True when the operation reads a second dataset (merge, append). */
  needs_other_dataset?: boolean;
}

export interface OperationHistoryEntry {
  sequence: number;
  version: number;
  type: string;
  group: string;
  configuration: Record<string, unknown>;
  source_version: number;
  summary: Record<string, unknown>;
  warnings: string[];
  created_at: string | null;
}

export interface VersionInfo {
  version: number;
  dataset_id: number;
  parent_version: number | null;
  file_format: string;
  row_count: number;
  column_count: number;
  is_current: boolean;
  label: string | null;
  created_by: number | null;
  created_at: string | null;
}

export interface VersionLineageEntry extends VersionInfo {
  operation: {
    type: string;
    group: string;
    configuration: Record<string, unknown>;
    summary: Record<string, unknown>;
    warnings: string[];
  } | null;
  filename: string;
}

export interface OperationsHistoryResponse {
  dataset_id: number;
  current_version: number | null;
  operations: OperationHistoryEntry[];
  versions: VersionLineageEntry[];
}

export interface ApplyOperationResponse {
  dataset_id: number;
  version: number;
  current_version: number;
  operation: OperationHistoryEntry;
  summary: Record<string, unknown>;
  warnings: string[];
  row_count: number;
  column_count: number;
}

export interface VersionDetailResponse {
  version: VersionInfo;
  preview_rows: Record<string, unknown>[];
}

export interface ResultTest {
  method?: string;
  statistic?: number | null;
  df?: number | null;
  df1?: number | null;
  df2?: number | null;
  p_value?: number | null;
  alpha?: number;
  significant?: boolean | null;
  [key: string]: unknown;
}

export interface ResultConfidenceInterval {
  level?: number;
  lower: number | null;
  upper: number | null;
  [key: string]: unknown;
}

export interface ResultEffectSize {
  name?: string;
  value: number | null;
  interpretation?: string | null;
  [key: string]: unknown;
}

export interface StandardResult {
  analysis_type: string;
  status: string;
  sample_size: number | null;
  estimate: Record<string, unknown>;
  test: ResultTest | null;
  confidence_interval: ResultConfidenceInterval | null;
  effect_size: ResultEffectSize | null;
  diagnostics: Record<string, unknown>;
  warnings: string[];
  tables: Record<string, unknown>;
  meta: Record<string, unknown>;
}

export interface AnalysisRunRecord {
  analysis_id: number;
  dataset_id: number;
  dataset_version: number;
  dataset_version_id: number | null;
  analysis_type: string;
  status: string;
  parameters: Record<string, unknown>;
  result: StandardResult;
  created_at: string | null;
}

// Backward-compatible alias (the legacy /analyze screen used this name).
export interface AnalysisRecord extends AnalysisRunRecord {}

export interface AnalysisRunResponse {
  dataset_id: number;
  dataset_version: number;
  dataset_version_id: number | null;
  analysis_type: string;
  status: string;
  result: StandardResult;
  analysis_id: number | null;
  created_at?: string | null;
}

export interface AnalysisTypeInfo {
  analysis_type: string;
  description: string;
  requires: string[];
}

export interface PlanningVariable {
  name: string;
  semantic_type: string;
  missing_count: number;
  unique_count: number;
  /** Distinct values, when the column has 20 or fewer. Drives value selects. */
  levels?: string[] | null;
  characteristics?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface PlanningIssue {
  severity: string;
  message: string;
  variable?: string | null;
}

export interface PlanningProfileResponse {
  status: string;
  sample_size: number;
  variable_count: number;
  variables: PlanningVariable[];
  variables_by_type: Record<string, string[]>;
  dataset_diagnostics: {
    rows: number;
    columns: number;
    cells_missing_percentage: number;
    complete_rows: number;
    duplicate_rows: number;
  };
  warnings: string[];
  meta: Record<string, unknown> & { dataset_id?: number; dataset_version?: number };
}

export type AssumptionStatus = "pass" | "warn" | "fail" | "not_applicable";
export interface AssumptionCheck {
  name: string;
  status: AssumptionStatus;
  detail: string;
  evidence?: string;
}

export interface Recommendation {
  question: string | null;
  intent: string | null;
  variables: {
    outcome: PlanningVariable | null;
    predictor: PlanningVariable | null;
  };
  diagnostics: Record<string, unknown>;
  candidates: Record<string, unknown>[];
  recommendation: {
    analysis_type: string;
    label: string;
    family: string;
    parameters: Record<string, unknown>;
    why: string;
    assumptions: string[];
    assumption_checks: AssumptionCheck[];
    output: string;
    alternatives: { analysis_type: string; label: string; reason: string }[];
  };
  validation: { status: string; issues: PlanningIssue[] };
  result?: StandardResult | null;
  meta: Record<string, unknown> & { dataset_id?: number; dataset_version?: number };
  analysis_id?: number;
}

export interface AssistantAnswer {
  question: string;
  intent: { intent: string | null; confidence: number; keywords: string[] };
  plan: {
    variables: {
      outcome: string | null;
      predictor: string | null;
    };
    mentions: Record<string, unknown>[];
    method: string;
    method_label: string;
    parameters: Record<string, unknown>;
    why: string;
    assumptions: string[];
    alternatives: { analysis_type: string; label: string; reason: string }[];
  };
  validation: { status: string; issues: PlanningIssue[] };
  diagnostics: Record<string, unknown>;
  result: StandardResult | null;
  explanation: string;
  meta: Record<string, unknown>;
  analysis_id?: number;
  dataset_id: number;
  dataset_version: number;
  dataset_version_id: number;
}

/**
 * One step of a method's stage plan.
 *
 * `kind` decides how the studio renders it: `input` and `run` are things the
 * reader fills in or presses, `evidence` is read from the data, `results` and
 * `interpretation` are what comes back. `gate` marks a step the run cannot
 * proceed without.
 */
export interface AnalysisStage {
  key: string;
  order: number;
  label: string;
  label_en: string;
  kind: "input" | "evidence" | "run" | "results" | "interpretation" | string;
  icon: string;
  description: string;
  fields: string[];
  gate: boolean;
  /** Present on the assumptions stage: what to actually go and check. */
  checks?: string[];
  /** Present on the run and interpretation stages: what the guide says to show. */
  outputs?: string;
  /** Present on the interpretation stage: what to switch to if a check fails. */
  alternatives?: string[];
}

/** One method from the Methods of Analysis guide. */
export interface AnalysisMethod {
  key: string;
  label: string;
  label_en: string;
  label_sw: string;
  category: string;
  family: string;
  /** When to reach for this method, in the reader's language. */
  purpose: string;
  when_to_use: string;
  /** The kind of dependent variable this method suits. */
  dv: string;
  /** The data layout it expects. */
  design: string;
  variables: string[];
  assumptions: string[];
  outputs: string;
  alternatives: string[];
  requires: string[];
  extras: string[];
  engine: string | null;
  implemented: boolean;
  notes: string;
  /** Key into `MethodCatalog.stage_plans`; the steps themselves are shared. */
  stage_plan: string;
}

export interface MethodCatalogCategory {
  key: string;
  label: string;
  label_en: string;
  description: string;
}

export interface MethodCatalog {
  questions: { question: string; hint: string }[];
  categories: MethodCatalogCategory[];
  methods: AnalysisMethod[];
  stage_plans: Record<string, AnalysisStage[]>;
  dv_guide: { dv: string; example: string; method: string; key: string }[];
  goal_guide: { goal: string; method: string; key: string }[];
  checklist: string[];
  common_mistakes: string[];
  counts: {
    methods: number;
    implemented: number;
    by_category: Record<string, number>;
    implemented_by_category: Record<string, number>;
  };
}

/** A method plus its resolved stage plan, as returned by the detail endpoint. */
export interface AnalysisMethodDetail extends AnalysisMethod {
  stages: AnalysisStage[];
}

export const statflowApi = {
  operationsCatalog: () =>
    http
      .get<OperationCatalogEntry[]>("/v1/datasets/operations/catalog")
      .then((r) => r.data),
  applyClean: (
    datasetId: number,
    payload: {
      operation_type: string;
      configuration: Record<string, unknown>;
      dataset_version?: number;
      label?: string;
    }
  ) =>
    http
      .post<ApplyOperationResponse>(`/v1/datasets/${datasetId}/clean`, payload)
      .then((r) => r.data),
  applyTransform: (
    datasetId: number,
    payload: {
      operation_type: string;
      configuration: Record<string, unknown>;
      dataset_version?: number;
      label?: string;
    }
  ) =>
    http
      .post<ApplyOperationResponse>(`/v1/datasets/${datasetId}/transform`, payload)
      .then((r) => r.data),
  /**
   * Merge or append a second dataset. The result becomes a new immutable
   * version of `datasetId`; neither input is modified, so the joined table can
   * be analysed straight away.
   */
  joinDataset: (
    datasetId: number,
    payload: {
      operation_type: "merge" | "append";
      other_dataset_id: number;
      other_dataset_version?: number;
      configuration: Record<string, unknown>;
      dataset_version?: number;
      label?: string;
    }
  ) =>
    http
      .post<ApplyOperationResponse & { other_dataset_id: number }>(
        `/v1/datasets/${datasetId}/join`,
        payload
      )
      .then((r) => r.data),
  operationsHistory: (datasetId: number) =>
    http
      .get<OperationsHistoryResponse>(`/v1/datasets/${datasetId}/operations`)
      .then((r) => r.data),
  versionDetail: (datasetId: number, version: number) =>
    http
      .get<VersionDetailResponse>(`/v1/datasets/${datasetId}/versions/${version}`)
      .then((r) => r.data),
  downloadVersion: (datasetId: number, version: number) =>
    http
      .get(`/v1/datasets/${datasetId}/versions/${version}/download`, {
        responseType: "blob",
      })
      .then((r) => r.data as Blob),
  analysisTypes: () =>
    http.get<AnalysisTypeInfo[]>("/v1/analysis/types").then((r) => r.data),
  /** The whole Methods of Analysis guide, fetched once and reused. */
  methodCatalog: () =>
    http.get<MethodCatalog>("/v1/analysis/methods").then((r) => r.data),
  /** One method with its stage plan resolved and ready to render. */
  method: (key: string) =>
    http
      .get<AnalysisMethodDetail>(`/v1/analysis/methods/${key}`)
      .then((r) => r.data),
  runAnalysis: (
    datasetId: number,
    payload: {
      analysis_type: string;
      parameters: Record<string, unknown>;
      dataset_version?: number;
      save?: boolean;
    }
  ) =>
    http
      .post<AnalysisRunResponse>(`/v1/datasets/${datasetId}/analysis`, payload)
      .then((r) => r.data),
  analysisRuns: (datasetId: number) =>
    http
      .get<AnalysisRunRecord[]>(`/v1/datasets/${datasetId}/analysis`)
      .then((r) => r.data),
  analysisRun: (analysisId: number) =>
    http.get<AnalysisRunRecord>(`/v1/analysis/${analysisId}`).then((r) => r.data),
  planningProfile: (datasetId: number, datasetVersion?: number) =>
    http
      .post<PlanningProfileResponse>("/v1/planning/profile", {
        dataset_id: datasetId,
        dataset_version: datasetVersion,
      })
      .then((r) => r.data),
  recommend: (payload: {
    dataset_id: number;
    dataset_version?: number;
    question?: string;
    intent?: "difference" | "association" | "prediction" | "distribution";
    outcome?: string;
    predictor?: string;
    method?: string;
    run?: boolean;
  }) =>
    http.post<Recommendation>("/v1/planning/recommend", payload).then((r) => r.data),
  ask: (payload: {
    dataset_id: number;
    question: string;
    dataset_version?: number;
    outcome?: string;
    predictor?: string;
  }) =>
    http.post<AssistantAnswer>("/v1/assistant/ask", payload).then((r) => r.data),
  assistantExamples: () =>
    http
      .get<{ examples: string[]; note: string }>("/v1/assistant/examples")
      .then((r) => r.data),
};

export default api;


// ---------------------------------------------------------------- Admin portal

/** Platform-wide roles. Deliberately not the same set as organization roles. */
export type PlatformRole = "super_admin" | "platform_admin" | "admin_viewer";
export type AccountStatus = "active" | "suspended";
export type AlertLevel = "danger" | "warning" | "info";

export interface AdminUser {
  id: number;
  full_name: string;
  email: string;
  system_role: PlatformRole | null;
  status: AccountStatus;
  is_suspended: boolean;
  created_at: string | null;
  last_active_at: string | null;
  suspended_reason: string | null;
  organization_count: number;
  dataset_count: number;
  analysis_count: number;
}

export interface AdminUserList {
  items: AdminUser[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminOverview {
  total_users: number;
  active_users: number;
  suspended_users: number;
  active_last_7_days: number;
  platform_staff: number;
  organizations: number;
  datasets: number;
  analyses: number;
  total_rows_profiled: number;
  storage_bytes: number;
  pending_reports: number;
  failed_reports: number;
  audit_events_last_24h: number;
  denied_last_24h: number;
}

export interface AdminAlert {
  level: AlertLevel;
  title: string;
  detail: string;
  action: string | null;
}

export interface AdminOrganization {
  id: number;
  name: string;
  slug: string;
  created_at: string | null;
  member_count: number;
  project_count: number;
  dataset_count: number;
  analysis_count: number;
}

export interface AdminOrganizationList {
  items: AdminOrganization[];
  total: number;
}

export interface AdminDataset {
  id: number;
  original_filename: string;
  file_type: string;
  status: string;
  row_count: number;
  column_count: number;
  created_at: string | null;
  owner_email: string | null;
  owner_id: number | null;
  organization_id: number | null;
  organization_name: string | null;
  latest_version: number | null;
}

export interface AdminDatasetList {
  items: AdminDataset[];
  total: number;
}

export interface AdminAuditEntry {
  id: number;
  user_id: number | null;
  actor_email: string | null;
  organization_id: number | null;
  action: string;
  resource: string | null;
  resource_id: string | null;
  result: "success" | "failure" | "denied";
  ip_address: string | null;
  metadata: Record<string, unknown>;
  created_at: string | null;
}

export interface AdminAuditList {
  items: AdminAuditEntry[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminUserUpdate {
  full_name?: string;
  /** `null` revokes the role, which is different from leaving it alone. */
  system_role?: PlatformRole | null;
  status?: AccountStatus;
  suspended_reason?: string;
}

/** The caller's own platform identity, straight from the server. */
export interface AdminMe {
  id: number;
  email: string;
  system_role: PlatformRole;
  status: AccountStatus;
}

export const adminApi = {
  me: () => http.get<AdminMe>("/v1/admin/me").then((r) => r.data),
  overview: () => http.get<AdminOverview>("/v1/admin/overview").then((r) => r.data),
  alerts: () =>
    http.get<{ alerts: AdminAlert[] }>("/v1/admin/overview/alerts").then((r) => r.data.alerts),
  users: (params: {
    search?: string;
    status?: AccountStatus;
    system_role?: PlatformRole;
    page?: number;
    page_size?: number;
  }) =>
    http.get<AdminUserList>("/v1/admin/users", { params }).then((r) => r.data),
  user: (id: number) => http.get<AdminUser>(`/v1/admin/users/${id}`).then((r) => r.data),
  updateUser: (id: number, payload: AdminUserUpdate) =>
    http.patch<AdminUser>(`/v1/admin/users/${id}`, payload).then((r) => r.data),
  suspendUser: (id: number, reason?: string) =>
    http
      .post<AdminUser>(`/v1/admin/users/${id}/suspend`, null, {
        params: reason ? { reason } : undefined,
      })
      .then((r) => r.data),
  reactivateUser: (id: number) =>
    http.post<AdminUser>(`/v1/admin/users/${id}/reactivate`).then((r) => r.data),
  organizations: (params: { search?: string; page?: number; page_size?: number }) =>
    http.get<AdminOrganizationList>("/v1/admin/organizations", { params }).then((r) => r.data),
  datasets: (params: { search?: string; status?: string; page?: number; page_size?: number }) =>
    http.get<AdminDatasetList>("/v1/admin/datasets", { params }).then((r) => r.data),
  audit: (params: {
    action?: string;
    result?: "success" | "failure" | "denied";
    user_id?: number;
    resource?: string;
    search?: string;
    page?: number;
    page_size?: number;
  }) => http.get<AdminAuditList>("/v1/admin/audit", { params }).then((r) => r.data),
};