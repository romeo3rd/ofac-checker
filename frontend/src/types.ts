export type ResultStatus = "pending" | "checking" | "no_hit" | "hit_found" | "error";
export type RunStatus = "queued" | "running" | "completed" | "completed_with_errors" | "error";

export interface OfacResult {
  id: number;
  run_id: string;
  position: number;
  name: string;
  status: ResultStatus;
  result_text: string | null;
  pdf_path: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface OfacRun {
  id: string;
  created_at: string;
  updated_at: string;
  status: RunStatus;
  total_count: number;
  completed_count: number;
  hit_count: number;
  no_hit_count: number;
  error_count: number;
  results?: OfacResult[];
}
