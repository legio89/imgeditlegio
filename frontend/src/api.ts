import type { Asset, Generation, IntentAnalysis, Job, Profile, Project } from "./types";

// En desarrollo con Vite se usa el proxy /api; en producción se puede
// fijar VITE_API_URL a la URL del backend local.
const API_BASE: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export function assetFileUrl(assetId: number): string {
  return `${API_BASE}/assets/${assetId}/file`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Error ${response.status}: ${detail || response.statusText}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function jsonBody(data: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  };
}

export const api = {
  health: () => request<{ status: string; engine: string }>("/health"),
  engine: () =>
    request<{ engine: string; status: string; note?: string; error?: string }>(
      "/engine",
    ),

  listProfiles: () => request<Profile[]>("/profiles"),
  createProfile: (name: string, notes?: string) =>
    request<Profile>("/profiles", jsonBody({ name, notes: notes ?? null })),
  deleteProfile: (id: number) => request<void>(`/profiles/${id}`, { method: "DELETE" }),
  uploadReference: (
    profileId: number,
    category: string,
    file: File,
    label?: string,
  ) => {
    const form = new FormData();
    form.append("category", category);
    if (label) form.append("label", label);
    form.append("file", file);
    return request<Profile["references"][number]>(`/profiles/${profileId}/references`, {
      method: "POST",
      body: form,
    });
  },

  listProjects: () => request<Project[]>("/projects"),
  createProject: (name: string, description?: string) =>
    request<Project>("/projects", jsonBody({ name, description: description ?? null })),
  deleteProject: (id: number) => request<void>(`/projects/${id}`, { method: "DELETE" }),

  uploadAsset: (file: File, kind: string, projectId?: number) => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    if (projectId !== undefined) form.append("project_id", String(projectId));
    return request<Asset>("/assets", { method: "POST", body: form });
  },
  listAssets: (params?: { kind?: string; project_id?: number }) => {
    const query = new URLSearchParams();
    if (params?.kind) query.set("kind", params.kind);
    if (params?.project_id !== undefined)
      query.set("project_id", String(params.project_id));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<Asset[]>(`/assets${suffix}`);
  },

  parseIntent: (text: string) =>
    request<IntentAnalysis>("/intent/parse", jsonBody({ text })),

  createJob: (data: {
    project_id: number;
    intent_text: string;
    input_asset_id: number;
    profile_ids: number[];
    operation?: string;
    parameters?: Record<string, unknown>;
  }) => request<Job>("/jobs", jsonBody(data)),
  listJobs: (projectId?: number) =>
    request<Job[]>(projectId ? `/jobs?project_id=${projectId}` : "/jobs"),
  getJob: (id: number) => request<Job>(`/jobs/${id}`),
  cancelJob: (id: number) => request<Job>(`/jobs/${id}/cancel`, { method: "POST" }),

  listGenerations: (projectId?: number) =>
    request<Generation[]>(
      projectId ? `/generations?project_id=${projectId}` : "/generations",
    ),
};
