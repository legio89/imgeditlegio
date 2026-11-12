export interface Asset {
  id: number;
  kind: "original" | "processed" | "result";
  filename: string;
  content_type: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  project_id: number | null;
  profile_id: number | null;
  created_at: string;
}

export interface Reference {
  id: number;
  profile_id: number;
  asset_id: number;
  category: "face" | "skin" | "body";
  label: string | null;
  created_at: string;
  asset: Asset;
}

export interface Profile {
  id: number;
  name: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
  references: Reference[];
}

export interface Project {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobEvent {
  id: number;
  job_id: number;
  event_type: string;
  message: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface Job {
  id: number;
  project_id: number;
  operation: string;
  intent_text: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  engine: string;
  parameters: Record<string, unknown>;
  profile_ids: number[];
  input_asset_id: number;
  output_asset_id: number | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  events: JobEvent[];
}

export interface Generation {
  id: number;
  job_id: number;
  project_id: number;
  operation: string;
  parameters: Record<string, unknown>;
  input_asset_id: number;
  output_asset_id: number;
  engine: string;
  created_at: string;
}

export interface IntentAnalysis {
  operation: string;
  confidence: number;
  targets: string[];
  clarification_questions: string[];
  summary: string;
}

export const OPERATION_LABELS: Record<string, string> = {
  outfit_change: "Cambiar vestimenta",
  outfit_remove: "Quitar prenda",
  pose_change: "Cambiar pose",
  background_change: "Cambiar fondo",
  enhance: "Mejorar fotografía",
  multi_model: "Varios modelos",
  unknown: "Sin identificar",
};

export const CATEGORY_LABELS: Record<string, string> = {
  face: "Rostro",
  skin: "Piel",
  body: "Cuerpo",
};
