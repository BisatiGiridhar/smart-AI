export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const TOKEN_KEY = "saiha.token";
const WS_KEY = "saiha.workspace";

const RAW_BASE = import.meta.env.VITE_API_URL;
const API_BASE = (typeof RAW_BASE === "string" ? RAW_BASE.trim() : "").replace(/\/+$/, "");

export function resolveUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  if (!API_BASE) return path;
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${cleanPath}`;
}

export const session = {
  get token() { return sessionStorage.getItem(TOKEN_KEY); },
  set token(v: string | null) { v ? sessionStorage.setItem(TOKEN_KEY, v) : sessionStorage.removeItem(TOKEN_KEY); },
  get workspace() { return sessionStorage.getItem(WS_KEY); },
  set workspace(v: string | null) { v ? sessionStorage.setItem(WS_KEY, v) : sessionStorage.removeItem(WS_KEY); },
};

function detailToMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: string }).msg) : String(d))).join("; ");
  return "The request failed.";
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (session.token) headers.set("Authorization", `Bearer ${session.token}`);
  if (session.workspace) headers.set("X-Workspace-Id", session.workspace);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  const url = resolveUrl(path);
  const res = await fetch(url, { ...init, headers, body });
  if (res.status === 401 && session.token) {
    session.token = null;
    window.dispatchEvent(new Event("saiha:unauthorized"));
  }
  const type = res.headers.get("content-type") ?? "";
  const data = type.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) throw new ApiError(res.status, detailToMessage((data as { detail?: unknown })?.detail ?? data));
  return data as T;
}

export async function download(path: string, filename: string) {
  const headers = new Headers();
  if (session.token) headers.set("Authorization", `Bearer ${session.token}`);
  if (session.workspace) headers.set("X-Workspace-Id", session.workspace);
  const targetUrl = resolveUrl(path);
  const res = await fetch(targetUrl, { headers });
  if (!res.ok) throw new ApiError(res.status, "Download failed.");
  const blobUrl = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(blobUrl);
}
