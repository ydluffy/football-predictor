export type WorkbenchBasicAuth = {
  username: string;
  password: string;
};

const STORAGE_KEY = "workbench_basic_auth_b64";

function canUseStorage() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function getStoredAuthBase64(): string | null {
  if (!canUseStorage()) return null;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v && v.trim() ? v.trim() : null;
  } catch {
    return null;
  }
}

export function setStoredAuth(username: string, password: string) {
  if (!canUseStorage()) return;
  const u = String(username || "").trim();
  const p = String(password || "");
  if (!u || !p) return;
  const b64 = btoa(`${u}:${p}`);
  window.localStorage.setItem(STORAGE_KEY, b64);
}

export function clearStoredAuth() {
  if (!canUseStorage()) return;
  window.localStorage.removeItem(STORAGE_KEY);
}

export function getAuthorizationHeaderValue(): string | null {
  const b64 = getStoredAuthBase64();
  if (!b64) return null;
  return `Basic ${b64}`;
}

export async function workbenchFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const auth = getAuthorizationHeaderValue();
  const headers = new Headers(init?.headers || undefined);
  if (auth && !headers.has("authorization")) headers.set("authorization", auth);
  return fetch(input, { ...init, headers });
}

