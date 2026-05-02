import type { OfacRun } from "./types";

export async function createRun(namesText: string, file: File | null): Promise<OfacRun> {
  const body = new FormData();
  body.append("names_text", namesText);
  if (file) body.append("file", file);

  const response = await fetch("/api/runs", { method: "POST", body });
  return parseResponse<OfacRun>(response);
}

export async function fetchRun(runId: string): Promise<OfacRun> {
  const response = await fetch(`/api/runs/${runId}`);
  return parseResponse<OfacRun>(response);
}

export function pdfUrl(runId: string, resultId: number): string {
  return `/api/runs/${runId}/results/${resultId}/pdf`;
}

export function zipUrl(runId: string): string {
  return `/api/runs/${runId}/zip`;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) return response.json() as Promise<T>;
  let message = "Request failed.";
  try {
    const payload = await response.json();
    message = payload.detail ?? message;
  } catch {
    message = response.statusText || message;
  }
  throw new Error(message);
}
