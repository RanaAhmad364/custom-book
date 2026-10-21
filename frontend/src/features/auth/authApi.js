const notConfigured = () =>
  Promise.reject(new Error("Authentication API is not configured."));

export const authApi = {
  login: notConfigured,
  register: notConfigured,
  requestPasswordReset: notConfigured,
  resetPassword: notConfigured,
  verifyOtp: notConfigured,
  resendOtp: notConfigured,
  verifyEmail: notConfigured,
  logout: notConfigured,
};
