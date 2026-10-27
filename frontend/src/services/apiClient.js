import { csrfHeaders, hasCsrfToken } from "./csrf.js";

const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || "").replace(/\/+$/, "");
export const API_PATH = /\/api\/v1$/i.test(API_BASE_URL)
  ? API_BASE_URL
  : `${API_BASE_URL}/api/v1`;

const AUTH_PATHS_WITHOUT_REFRESH = new Set([
  "/auth/login",
  "/auth/register",
  "/auth/refresh",
  "/auth/verify-email",
  "/auth/verify-otp",
  "/auth/resend-otp",
  "/auth/forgot-password",
  "/auth/reset-password",
]);

let refreshInFlight;

export class ApiError extends Error {
  constructor(message, { status, code, details } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function refreshSession() {
  if (!hasCsrfToken("refresh")) return Promise.resolve(false);
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_PATH}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: csrfHeaders("refresh"),
    })
      .then((response) => response.ok)
      .catch(() => false)
      .finally(() => {
        refreshInFlight = undefined;
      });
  }
  return refreshInFlight;
}

function redirectToLogin() {
  if (typeof window === "undefined" || window.location.pathname === "/login") return;
  const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  const query = new URLSearchParams({ expired: "1", returnTo });
  window.location.assign(`/login?${query.toString()}`);
}

export async function apiRequest(path, {
  method = "GET",
  body,
  headers = {},
  retry = true,
} = {}) {
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  const requestHeaders = {
    ...csrfHeaders("access", headers),
    ...(body !== undefined && !isForm ? { "Content-Type": "application/json" } : {}),
  };
  const response = await fetch(`${API_PATH}${path}`, {
    method,
    credentials: "include",
    headers: requestHeaders,
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  });

  if (response.status === 401 && retry && !AUTH_PATHS_WITHOUT_REFRESH.has(path)) {
    const refreshed = await refreshSession();
    if (refreshed) return apiRequest(path, { method, body, headers, retry: false });
    if (path !== "/auth/me") redirectToLogin();
  }

  const payload = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      payload?.error?.message || "The request could not be completed.",
      {
        status: response.status,
        code: payload?.error?.code,
        details: payload?.error?.details,
      },
    );
  }
  return { data: payload, etag: response.headers.get("ETag") };
}

export function apiUrl(path) {
  return `${API_PATH}${path}`;
}
