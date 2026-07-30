export type ApiMode = "demo" | "real";

export type HealthResponse = {
  status: "ok";
  adapter: string;
  storage: string;
  durable_storage: boolean;
};

export type ProjectResponse = {
  id: string;
  name: string;
  target_duration: number;
  status: string;
  created_at: string | null;
  updated_at: string | null;
};

export type ProjectSnapshot = ProjectResponse & {
  audio: {
    id: string;
    filename: string;
    content_type: string | null;
    size_bytes: number;
  } | null;
};

export type ProjectListResponse = {
  items: ProjectSnapshot[];
  total: number;
};

export type AssetVersion = {
  id: number;
  project_id: string;
  kind: string;
  payload: Record<string, unknown>;
  version: number;
  status: "draft" | "active" | "archived" | "failed";
  is_active: boolean;
  parent_asset_id: number | null;
  provider: string | null;
  model: string | null;
  prompt: string | null;
  input_snapshot: Record<string, { asset_id: number; version: number }>;
  validation_errors: unknown[];
  created_at: string;
  updated_at: string | null;
};

export type AssetDependencyWarning = {
  asset_id: number;
  kind: string;
  version: number;
  upstream_kind: string;
  expected_asset_id: number;
  active_asset_id: number;
  message: string;
};

export type AssetVersionsResponse = {
  project_id: string;
  groups: Record<string, AssetVersion[]>;
  warnings: AssetDependencyWarning[];
};

export type KeyframeTask = {
  shot_id: string;
  provider_task_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  provider: string;
  model: string;
  prompt: string;
  attempt: number;
  confirmed: boolean;
  error: string | null;
  result: {
    storage_path: string;
    content_type: string;
    width: number;
    height: number;
    sha256: string;
  } | null;
  source: Record<string, unknown>;
};

export type KeyframeMutationResponse = {
  asset: AssetVersion;
  progress: {
    total: number;
    queued: number;
    running: number;
    succeeded: number;
    failed: number;
    confirmed: number;
  };
  consistency_warnings: string[];
};

export type SegmentCandidate = {
  category: "highlight" | "turn" | "stable";
  label: string;
  start: number;
  end: number;
  duration: number;
  score: number;
  reason: string;
};

export type SegmentRecommendationsResponse = {
  project_id: string;
  target_duration: number;
  audio_duration: number;
  candidates: SegmentCandidate[];
};

export type UploadResponse = {
  project_id: string;
  audio_id: string;
  filename: string;
  size: number;
  status: "uploaded";
};

export class ApiError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

const configuredBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim().replace(/\/+$/, "") ?? "";

export function getApiMode(): ApiMode {
  return configuredBaseUrl ? "real" : "demo";
}

export function apiAssetUrl(path: string): string {
  return configuredBaseUrl ? `${configuredBaseUrl}${path}` : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!configuredBaseUrl) {
    throw new ApiError("未配置 API 地址，当前使用 Demo 模式。");
  }

  let response: Response;
  try {
    response = await fetch(`${configuredBaseUrl}${path}`, {
      ...init,
      signal: init?.signal ?? AbortSignal.timeout(15_000),
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown network error";
    throw new ApiError(`无法连接导演 API，请检查网络或稍后重试（${detail}）。`);
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail || detail;
    } catch {
      // Keep the HTTP status text when the response is not JSON.
    }
    throw new ApiError(`导演 API 请求失败：${detail}`, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function checkHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export function createProject(name: string, targetDuration = 30): Promise<ProjectResponse> {
  return request<ProjectResponse>("/project/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, target_duration: targetDuration }),
  });
}

export function uploadAudio(projectId: string, file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("project_id", projectId);
  form.append("audio", file);
  return request<UploadResponse>("/audio/upload", { method: "POST", body: form });
}

export function analyzeAudio(projectId: string): Promise<{
  project_id: string;
  kind: "audio_analysis";
  payload: Record<string, unknown>;
  asset_id: number;
  version: number;
  status: string;
  is_active: boolean;
}> {
  return request("/audio/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId }),
  });
}

export function fetchProject(projectId: string): Promise<ProjectSnapshot> {
  return request<ProjectSnapshot>(`/projects/${encodeURIComponent(projectId)}`);
}

export function fetchProjects(): Promise<ProjectListResponse> {
  return request<ProjectListResponse>("/projects");
}

export function updateProject(
  projectId: string,
  values: { name?: string; target_duration?: number },
): Promise<ProjectSnapshot> {
  return request<ProjectSnapshot>(`/projects/${encodeURIComponent(projectId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
}

export function deleteProject(projectId: string): Promise<void> {
  return request<void>(`/projects/${encodeURIComponent(projectId)}`, {
    method: "DELETE",
  });
}

export function fetchAssetVersions(projectId: string): Promise<AssetVersionsResponse> {
  return request<AssetVersionsResponse>(
    `/projects/${encodeURIComponent(projectId)}/assets`,
  );
}

export function activateAssetVersion(
  projectId: string,
  kind: string,
  selector: { asset_id: number } | { version: number },
): Promise<{ asset: AssetVersion; warnings: AssetDependencyWarning[] }> {
  return request(
    `/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(kind)}/activate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(selector),
    },
  );
}

export function fetchSegmentRecommendations(
  projectId: string,
): Promise<SegmentRecommendationsResponse> {
  return request(
    `/projects/${encodeURIComponent(projectId)}/segments/recommendations`,
  );
}

export function confirmSegment(
  projectId: string,
  values: {
    start: number;
    end: number;
    category: SegmentCandidate["category"] | "custom";
    label: string;
  },
): Promise<{ asset: AssetVersion; warnings: AssetDependencyWarning[] }> {
  return request(
    `/projects/${encodeURIComponent(projectId)}/segments/confirm`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    },
  );
}

export function createWorld(projectId: string): Promise<{
  project_id: string;
  kind: "world";
  payload: Record<string, unknown>;
  asset_id: number;
  version: number;
  status: string;
  is_active: boolean;
}> {
  return request("/world/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId }),
  });
}

export function updateWorld(
  projectId: string,
  values: {
    expected_version: number;
    changes: Record<string, unknown>;
    locked_fields: string[];
  },
): Promise<{ asset: AssetVersion; warnings: AssetDependencyWarning[] }> {
  return request(`/projects/${encodeURIComponent(projectId)}/world`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
}

export function createCharacter(projectId: string): Promise<{
  project_id: string;
  kind: "character";
  payload: Record<string, unknown>;
  asset_id: number;
  version: number;
  status: string;
  is_active: boolean;
}> {
  return request("/character/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId, count: 1 }),
  });
}

export function generateCharacterReferences(
  projectId: string,
  expectedVersion: number,
): Promise<{
  asset: AssetVersion;
  warnings: AssetDependencyWarning[];
  consistency_risk: string | null;
}> {
  return request(`/projects/${encodeURIComponent(projectId)}/characters/references/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_version: expectedVersion }),
  });
}

export function selectCharacterReferences(
  projectId: string,
  values: {
    expected_version: number;
    selected_reference_ids: string[];
    locked: boolean;
  },
): Promise<{
  asset: AssetVersion;
  warnings: AssetDependencyWarning[];
  consistency_risk: string | null;
}> {
  return request(`/projects/${encodeURIComponent(projectId)}/characters/references`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
}

export function characterReferenceUrl(
  projectId: string,
  assetId: number,
  referenceId: string,
  download = false,
): string {
  if (!configuredBaseUrl) return "";
  const path = (
    `/projects/${encodeURIComponent(projectId)}/character-assets/${assetId}` +
    `/references/${encodeURIComponent(referenceId)}`
  );
  return `${configuredBaseUrl}${path}${download ? "?download=true" : ""}`;
}

export function createStory(projectId: string): Promise<{
  project_id: string;
  kind: "story";
  payload: Record<string, unknown>;
  asset_id: number;
  version: number;
  status: string;
  is_active: boolean;
}> {
  return request("/story/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId }),
  });
}

export function createShots(projectId: string): Promise<{
  project_id: string;
  kind: "shots";
  payload: Record<string, unknown>;
  asset_id: number;
  version: number;
  status: string;
  is_active: boolean;
}> {
  return request("/shots/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId }),
  });
}

export function updateShots(
  projectId: string,
  expectedVersion: number,
  shots: Array<Record<string, unknown>>,
): Promise<{ asset: AssetVersion; warnings: AssetDependencyWarning[] }> {
  return request(`/projects/${encodeURIComponent(projectId)}/shots`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      expected_version: expectedVersion,
      shots,
    }),
  });
}

export function regenerateShot(
  projectId: string,
  shotId: string,
  expectedVersion: number,
): Promise<{ asset: AssetVersion; warnings: AssetDependencyWarning[] }> {
  return request(
    `/projects/${encodeURIComponent(projectId)}/shots/${encodeURIComponent(shotId)}/regenerate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
  );
}

export function startKeyframes(
  projectId: string,
  expectedShotsVersion: number,
): Promise<KeyframeMutationResponse> {
  return request(`/projects/${encodeURIComponent(projectId)}/keyframes/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_shots_version: expectedShotsVersion }),
  });
}

export function retryKeyframe(
  projectId: string,
  shotId: string,
  expectedVersion: number,
): Promise<KeyframeMutationResponse> {
  return request(
    `/projects/${encodeURIComponent(projectId)}/keyframes/${encodeURIComponent(shotId)}/retry`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
  );
}

export function retryFailedKeyframes(
  projectId: string,
  expectedVersion: number,
): Promise<KeyframeMutationResponse> {
  return request(`/projects/${encodeURIComponent(projectId)}/keyframes/retry-failed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_version: expectedVersion }),
  });
}

export function confirmKeyframe(
  projectId: string,
  shotId: string,
  expectedVersion: number,
  confirmed: boolean,
): Promise<KeyframeMutationResponse> {
  return request(
    `/projects/${encodeURIComponent(projectId)}/keyframes/${encodeURIComponent(shotId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: expectedVersion, confirmed }),
    },
  );
}

export function keyframeImageUrl(
  projectId: string,
  shotId: string,
  download = false,
): string {
  return apiAssetUrl(
    `/projects/${encodeURIComponent(projectId)}/keyframes/${encodeURIComponent(shotId)}/image${download ? "?download=true" : ""}`,
  );
}

export function keyframeExportUrl(
  projectId: string,
  kind: "zip" | "json" | "pdf",
): string {
  const suffix = kind === "zip" ? "export.zip" : `manifest.${kind}`;
  return apiAssetUrl(`/projects/${encodeURIComponent(projectId)}/keyframes/${suffix}`);
}

export function jianyingAssistantExportUrl(projectId: string): string {
  return apiAssetUrl(
    `/projects/${encodeURIComponent(projectId)}/exports/jianying-assistant.zip`,
  );
}
