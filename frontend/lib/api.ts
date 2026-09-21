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
}

export interface DatasetSummary {
  id: number;
  original_filename: string;
  file_type: string;
  status: string;
  uploaded_at: string | null;
  row_count: number;
  column_count: number;
}

export interface UploadResponse {
  dataset_id: number;
  original_filename: string;
  row_count: number;
  column_count: number;
  columns: ColumnProfile[];
  status: string;
}

export interface DatasetDetailResponse {
  dataset: DatasetSummary;
  columns: ColumnProfile[];
  preview_rows: Record<string, unknown>[];
}

export interface ProfileResponse {
  dataset_id: number;
  row_count: number;
  column_count: number;
  columns: ColumnProfile[];
}

export interface CleanActionPayload {
  action_type: "drop_duplicates" | "fill_missing" | "drop_column" | "convert_type";
  parameters: Record<string, unknown>;
}

export interface CleanResponse {
  dataset_id: number;
  status: string;
  row_count: number;
  column_count: number;
  applied_action: Record<string, unknown>;
}

export interface CleaningHistoryItem {
  id: number;
  action_type: string;
  parameters: Record<string, unknown>;
  created_at: string | null;
}

export type AnalysisType =
  | "descriptive_stats"
  | "correlation"
  | "regression"
  | "hypothesis_test";

export interface AnalyzePayload {
  analysis_type: AnalysisType;
  parameters: Record<string, unknown>;
}

export interface AnalysisRecord {
  analysis_id: number;
  dataset_id: number;
  analysis_type: AnalysisType;
  parameters: Record<string, unknown>;
  result_data: Record<string, any>;
  created_at: string | null;
}

export type ChartType = "bar" | "line" | "scatter" | "histogram";

export interface ChartConfig {
  x: string;
  y?: string | null;
  group_by?: string | null;
  aggregate?: string;
  bins?: number | null;
  limit?: number | null;
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
}

export interface ChartRecord {
  chart_id: number;
  dataset_id: number;
  chart_type: ChartType;
  config: ChartConfig;
  chart_data: ChartData;
  created_at: string | null;
}

export interface ExportPayload {
  format: "pdf" | "xlsx";
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
  file_format: string;
  status: string;
  error_message: string | null;
  created_at: string | null;
  download_url: string;
}

export interface ReportStatus {
  report_id: number;
  dataset_id: number;
  file_format: string;
  status: string;
  error_message: string | null;
  download_url: string;
  created_at: string | null;
}

// ------------------------------------------------------------ API methods

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
      onUploadProgress?: (event: AxiosProgressEvent) => void
    ) => {
      const formData = new FormData();
      formData.append("file", file);
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
    profile: (id: number) =>
      http.get<ProfileResponse>(`/datasets/${id}/profile`).then((r) => r.data),
    remove: (id: number) => http.delete(`/datasets/${id}`).then((r) => r.data),
  },
  cleaning: {
    apply: (id: number, payload: CleanActionPayload) =>
      http.post<CleanResponse>(`/datasets/${id}/clean`, payload).then((r) => r.data),
    history: (id: number) =>
      http
        .get<CleaningHistoryItem[]>(`/datasets/${id}/cleaning-history`)
        .then((r) => r.data),
  },
  analysis: {
    run: (id: number, payload: AnalyzePayload) =>
      http.post<AnalysisRecord>(`/datasets/${id}/analyze`, payload).then((r) => r.data),
    listForDataset: (id: number) =>
      http.get<AnalysisRecord[]>(`/datasets/${id}/analysis`).then((r) => r.data),
    get: (analysisId: number) =>
      http.get<AnalysisRecord>(`/analysis/${analysisId}`).then((r) => r.data),
  },
  charts: {
    create: (id: number, payload: ChartPayload) =>
      http.post<ChartRecord>(`/datasets/${id}/charts`, payload).then((r) => r.data),
    listForDataset: (id: number) =>
      http.get<ChartRecord[]>(`/datasets/${id}/charts`).then((r) => r.data),
    get: (chartId: number) =>
      http.get<ChartRecord>(`/charts/${chartId}`).then((r) => r.data),
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
};

export default api;

