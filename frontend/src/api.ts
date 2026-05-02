import type { OfacRun } from "./types";

export interface AuthStatus {
  configured: boolean;
  authenticated: boolean;
  username: string | null;
}

export class AuthRequiredError extends Error {
  constructor(message = "Please sign in.") {
    super(message);
    this.name = "AuthRequiredError";
  }
}

export async function fetchAuthStatus(): Promise<AuthStatus> {
  const response = await fetch("/api/auth/status", { credentials: "include" });
  return parseResponse<AuthStatus>(response);
}

export async function login(username: string, password: string): Promise<AuthStatus> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return parseResponse<AuthStatus>(response);
}

export async function logout(): Promise<void> {
  await fetch("/api/auth/logout", {
    method: "POST",
    credentials: "include",
  });
}

export async function createRun(namesText: string, file: File | null): Promise<OfacRun> {
  const body = new FormData();
  body.append("names_text", namesText);
  if (file) body.append("file", file);

  const response = await fetch("/api/runs", {
    method: "POST",
    credentials: "include",
    body,
  });
  return parseResponse<OfacRun>(response);
}

export async function fetchRun(runId: string): Promise<OfacRun> {
  const response = await fetch(`/api/runs/${runId}`, { credentials: "include" });
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
  if (response.status === 401) {
    if (response.url.endsWith("/api/auth/login")) throw new Error(message);
    throw new AuthRequiredError(message);
  }
  throw new Error(message);
}
