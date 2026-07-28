import { getTokens, setTokens, clearTokens } from "../auth/tokenStore";
import { addBreadcrumb } from "../errors/breadcrumbs";
import { report } from "../errors/crashReporter";
import { computeFingerprint } from "../errors/fingerprint";

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

export async function tryRefresh(): Promise<boolean> {
  // Gom các 401 đồng thời về 1 lần refresh duy nhất
  if (!refreshing) {
    refreshing = (async () => {
      const tokens = await getTokens();
      if (!tokens?.refresh_token) return false;
      let resp: Response;
      try {
        resp = await fetch(`${API_URL}/api/v1/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: tokens.refresh_token }),
        });
      } catch {
        // Lỗi mạng (không phải server từ chối) — GIỮ token, để lần sau thử lại;
        // xóa token ở đây là đá người dùng ra ngoài chỉ vì mất sóng thoáng qua.
        return false;
      }
      if (!resp.ok) {
        // CHỈ xóa token khi server thực sự từ chối refresh token (401/403). 5xx/429
        // (VPS restart lúc deploy, lỗi thoáng qua) → refresh token vẫn còn hiệu lực,
        // giữ lại để lần sau thử; xóa ở đây gây logout oan.
        if (resp.status === 401 || resp.status === 403) await clearTokens();
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

  // --- Gửi request và bắt lỗi network/timeout ---
  let resp: Response;
  try {
    resp = await doFetch();
  } catch (netErr: any) {
    // Lỗi network (TypeError: "Network request failed") hoặc timeout (AbortError)
    addBreadcrumb({
      type: "api",
      message: `${method} ${path} → ${netErr?.name ?? "NetworkError"}: ${netErr?.message ?? ""}`,
      timestamp: new Date().toISOString(),
    });
    // Ghi crash log cho lỗi mạng/timeout — dùng "fe_network" (có sẵn trong CrashSource)
    if (netErr instanceof TypeError || netErr?.name === "AbortError") {
      void report({
        source: "fe_network",
        severity: "error",
        message: netErr?.message ?? "Network request failed",
        fingerprint: computeFingerprint("fe_network", `${method}:${path}`),
        occurred_at: new Date().toISOString(),
        client_event_id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        request_method: method,
        request_path: path,
        stack: netErr?.stack,
      });
    }
    throw netErr;
  }

  // --- Breadcrumb cho mỗi response (cả thành công lẫn lỗi HTTP) ---
  addBreadcrumb({
    type: "api",
    message: `${method} ${path} → ${resp.status}`,
    timestamp: new Date().toISOString(),
  });

  // GIỮ NGUYÊN luồng refresh token: 401 → tryRefresh() → thử lại 1 lần
  if (resp.status === 401 && auth && (await tryRefresh())) {
    resp = await doFetch();
    addBreadcrumb({
      type: "api",
      message: `${method} ${path} → ${resp.status} (retry after token refresh)`,
      timestamp: new Date().toISOString(),
    });
  }

  if (!resp.ok) {
    let detail: unknown = resp.statusText;
    try {
      detail = (await resp.json()).detail ?? detail;
    } catch {}

    // Chỉ ghi crash log cho 5xx (lỗi hệ thống) — 4xx là lỗi nghiệp vụ bình thường
    if (resp.status >= 500) {
      void report({
        // "fe_api" đúng về nghiệp vụ; chưa có trong CrashSource → cast tạm thời
        source: "fe_network" as "fe_network",
        severity: "error",
        message: `API ${resp.status}: ${method} ${path}`,
        fingerprint: computeFingerprint("fe_network", `${method}:${path}:${resp.status}`),
        occurred_at: new Date().toISOString(),
        client_event_id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        request_method: method,
        request_path: path,
        response_status: resp.status,
      });
    }

    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  const text = await resp.text();
  return (text ? JSON.parse(text) : undefined) as T;
}
