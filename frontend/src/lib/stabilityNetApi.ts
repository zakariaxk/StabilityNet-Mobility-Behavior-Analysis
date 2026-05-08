export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export interface StabilityNetHealth {
  status: string;
}

export interface AnalysisCreateRequest {
  video_path: string;
}

export interface AnalysisVideoMetadata {
  path?: string;
  annotated_video_url?: string;
  fps?: number;
  frame_count?: number;
  width?: number;
  height?: number;
  duration_s?: number;
  [key: string]: unknown;
}

export interface TrackSummary {
  track_id: number;
  observations?: number;
  first_timestamp_s?: number;
  last_timestamp_s?: number;
  is_confirmed?: boolean;
  features?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface BehaviorEvent {
  event_id?: string;
  track_id: number;
  event_type: string;
  severity: string;
  score?: number;
  timestamp_s: number;
  reason: string;
  feature_snapshot?: Record<string, JsonValue>;
}

export interface AnalysisResult {
  analysis_version?: string;
  created_at?: string;
  annotated_video_url?: string;
  output_video_url?: string;
  processing_fps?: number;
  video?: AnalysisVideoMetadata;
  frames_processed?: number;
  frames?: unknown[];
  tracks?: TrackSummary[];
  events?: BehaviorEvent[];
  [key: string]: unknown;
}

export interface AnalysisRecord {
  analysis_id: string;
  status: string;
  video_path: string;
  result_path: string;
  source?: string;
  original_filename?: string;
  annotated_video_url?: string;
  output_video_url?: string;
  video_url?: string;
  summary?: Record<string, unknown>;
  result: AnalysisResult;
}

const API_BASE_PATH = "/api/stabilitynet";

export class StabilityNetApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "StabilityNetApiError";
    this.status = status;
  }
}

export async function checkHealth(): Promise<StabilityNetHealth> {
  return requestJson<StabilityNetHealth>("/health");
}

export async function createAnalysis(
  payload: AnalysisCreateRequest
): Promise<AnalysisRecord> {
  return requestJson<AnalysisRecord>("/analyses", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function uploadAnalysis(file: File): Promise<AnalysisRecord> {
  const formData = new FormData();
  formData.set("file", file);

  return requestJson<AnalysisRecord>("/analyses/upload", {
    method: "POST",
    body: formData
  });
}

export async function getAnalysis(analysisId: string): Promise<AnalysisRecord> {
  return requestJson<AnalysisRecord>(`/analyses/${encodeURIComponent(analysisId)}`);
}

export function analysisVideoUrl(record: AnalysisRecord): string | null {
  const videoUrl =
    record.annotated_video_url ??
    record.output_video_url ??
    record.result.annotated_video_url ??
    record.result.output_video_url ??
    record.result.video?.annotated_video_url ??
    record.video_url;

  return videoUrl ? apiAssetUrl(videoUrl) : null;
}

function apiAssetUrl(url: string): string {
  if (/^https?:\/\//i.test(url)) {
    return url;
  }

  const normalizedPath = url.startsWith("/") ? url : `/${url}`;
  return `${API_BASE_PATH}${normalizedPath}`;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (typeof init?.body === "string" && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }

  const response = await fetch(`${API_BASE_PATH}${path}`, {
    ...init,
    headers
  });

  if (!response.ok) {
    throw new StabilityNetApiError(await readErrorMessage(response), response.status);
  }

  return (await response.json()) as T;
}

async function readErrorMessage(response: Response): Promise<string> {
  const fallback = `Request failed with status ${response.status}.`;
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    const payload = await response.json().catch(() => null);
    if (isRecord(payload)) {
      const detail = payload.detail;
      if (typeof detail === "string") {
        return detail;
      }
      if (Array.isArray(detail)) {
        return detail.map(String).join(", ");
      }
      const nestedError = payload.error;
      if (typeof nestedError === "string") {
        return nestedError;
      }
    }
    return fallback;
  }

  const text = await response.text().catch(() => "");
  return text.trim() || fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
