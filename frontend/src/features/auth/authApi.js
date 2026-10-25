import { csrfHeaders, hasCsrfToken } from "../../services/csrf.js";
import { API_PATH } from "../../services/apiClient.js";

const AUTH_PATH = `${API_PATH}/auth`;

async function request(path, { method = "GET", body, retry = true } = {}) {
  const response = await fetch(`${AUTH_PATH}${path}`, {
    method,
    credentials: "include",
    headers: csrfHeaders(path === "/refresh" ? "refresh" : "access", body === undefined ? {} : { "Content-Type": "application/json" }),
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 401 && retry && path !== "/refresh" && path !== "/login" && hasCsrfToken("refresh")) {
    const refreshed = await request("/refresh", { method: "POST", retry: false });
    if (refreshed) return request(path, { method, body, retry: false });
  }

  const payload = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.error?.message || "The authentication request could not be completed.");
  }
  return payload;
}

export const authApi = {
  async register({ name, email, password }) {
    return request("/register", { method: "POST", body: { name, email, password }, retry: false });
  },
  async login({ email, password }) {
    return request("/login", { method: "POST", body: { email, password }, retry: false });
  },
  async logout() {
    return request("/logout", { method: "POST" });
  },
  async refresh() {
    return request("/refresh", { method: "POST", retry: false });
  },
  currentUser() {
    return request("/me");
  },
  updateProfile(profile) {
    return request("/me", { method: "PATCH", body: profile });
  },
  listAddresses() {
    return request("/me/addresses");
  },
  createAddress(address) {
    return request("/me/addresses", { method: "POST", body: address });
  },
  deleteAddress(addressId) {
    return request(`/me/addresses/${encodeURIComponent(addressId)}`, { method: "DELETE" });
  },
  notificationPreferences() {
    return request("/me/notification-preferences");
  },
  updateNotificationPreference(preference) {
    return request("/me/notification-preferences", { method: "PATCH", body: preference });
  },
  changePassword({ currentPassword, newPassword }) {
    return request("/change-password", { method: "POST", body: { currentPassword, newPassword } });
  },
  verifyOtp({ email, code }) {
    return request("/verify-otp", { method: "POST", body: { email, code }, retry: false });
  },
  resendOtp(email) {
    return request("/resend-otp", { method: "POST", body: { email }, retry: false });
  },
  requestPasswordReset(email) {
    return request("/forgot-password", { method: "POST", body: { email }, retry: false });
  },
  resetPassword({ token, password }) {
    return request("/reset-password", { method: "POST", body: { token, password }, retry: false });
  },
};
