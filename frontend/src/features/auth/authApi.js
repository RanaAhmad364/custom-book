import { apiRequest } from "../../services/apiClient.js";

async function request(path, options = {}) {
  const result = await apiRequest(`/auth${path}`, options);
  return result.data;
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
