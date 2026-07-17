import { getTokens, setTokens, clearTokens } from "../auth/tokenStore";

export const API_URL =
  process.env.EXPO_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  // Gom các 401 đồng thời về 1 lần refresh duy nhất
  if (!refreshing) {
    refreshing = (async () => {
      const tokens = await getTokens();
      if (!tokens?.refresh_token) return false;
      const resp = await fetch(`${API_URL}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: tokens.refresh_token }),
      });
      if (!resp.ok) {
        await clearTokens();
        return false;
      }
      const pair = await resp.json();
      await setTokens({ access_token: pair.access_token, refresh_token: pair.refresh_token });
      return true;
    })().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

export async function apiFetch<T>(
  path: string,
  opts: { method?: string; body?: unknown; auth?: boolean } = {},
): Promise<T> {
  const { method = "GET", body, auth = true } = opts;
  // FormData (upload multipart): để fetch tự đặt Content-Type kèm boundary
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  const doFetch = async (): Promise<Response> => {
    const headers: Record<string, string> = isForm ? {} : { "Content-Type": "application/json" };
    if (auth) {
      const tokens = await getTokens();
      if (tokens?.access_token) headers.Authorization = `Bearer ${tokens.access_token}`;
    }
    return fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
    });
  };

  let resp = await doFetch();
  if (resp.status === 401 && auth && (await tryRefresh())) {
    resp = await doFetch();
  }
  if (!resp.ok) {
    let detail: unknown = resp.statusText;
    try {
      detail = (await resp.json()).detail ?? detail;
    } catch {}
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  const text = await resp.text();
  return (text ? JSON.parse(text) : undefined) as T;
}
