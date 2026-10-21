const wait = () => new Promise((resolve) => window.setTimeout(resolve, 350));

export const mockAuthService = {
  async login({ email, password }) {
    await wait();
    if (!email || !password) throw new Error("Enter your email and password.");
    return { id: "mock-user", email: email.trim().toLowerCase(), name: email.split("@")[0] };
  },

  async register({ name, email, password }) {
    await wait();
    if (!name.trim() || !email.trim() || password.length < 8) {
      throw new Error("Check your details and use a password with at least 8 characters.");
    }
    return { email: email.trim().toLowerCase() };
  },

  async requestPasswordReset(email) {
    await wait();
    if (!email.trim()) throw new Error("Enter the email address for your account.");
    return { email: email.trim().toLowerCase() };
  },

  async resetPassword({ password, confirmPassword }) {
    await wait();
    if (password.length < 8) throw new Error("Use at least 8 characters for your password.");
    if (password !== confirmPassword) throw new Error("Those passwords don’t match.");
    return { success: true };
  },

  async verifyOtp({ code }) {
    await wait();
    if (code !== "123456") throw new Error("That demo code didn’t match. Use 123456.");
    return { success: true };
  },

  async resendOtp() {
    await wait();
    return { success: true };
  },

  async verifyEmail() {
    await wait();
    return { success: true };
  },
};
