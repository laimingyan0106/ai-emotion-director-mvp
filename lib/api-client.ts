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
};

export type ProjectSnapshot = ProjectResponse & {
  audio: {
    id: string;
    filename: string;
    content_type: string | null;
    size_bytes: number;
  } | null;
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

export function fetchProject(projectId: string): Promise<ProjectSnapshot> {
  return request<ProjectSnapshot>(`/project/${encodeURIComponent(projectId)}`);
}
