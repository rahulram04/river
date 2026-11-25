import type { User } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (method !== "GET" && method !== "HEAD" &&
      !["/api/auth/login", "/api/auth/register"].includes(path)) {
    const identity = await fetch(API_BASE + "/api/auth/me", { credentials: "include", cache: "no-store" });
    if (!identity.ok) throw new ApiError(identity.status, "You must log in before making changes.");
    const user = await identity.json() as User;
    headers.set("X-CSRF-Token", user.csrf_token);
  }
  let response: Response;
  try {
    response = await fetch(API_BASE + path, {
      ...init, method, headers, credentials: "include", cache: "no-store"
    });
  } catch {
    throw new ApiError(0, "Unable to reach Workbet. Check that the backend is running.");
  }
  const data = await response.json().catch(() => ({})) as { detail?: string | Array<{msg: string}> };
  if (!response.ok) {
    const detail = data.detail;
    const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map(x => x.msg).join("; ") : `HTTP ${response.status}`;
    throw new ApiError(response.status, message);
  }
  return data as T;
}

export function post<T>(path: string, payload: unknown, extras?: HeadersInit): Promise<T> {
  return request<T>(path, { method: "POST", headers: extras, body: JSON.stringify(payload) });
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {dateStyle: "medium", timeStyle: "short"});
}
export function formatCredits(value: string | number): string {
  return Number(value).toLocaleString(undefined, {maximumFractionDigits: 4});
}
export function pct(n: number): string { return `${(n * 100).toFixed(1)}%`; }
