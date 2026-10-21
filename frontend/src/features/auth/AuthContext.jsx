import { createContext, useContext, useMemo, useState } from "react";
import { mockAuthService } from "./mockAuthService.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [pendingEmail, setPendingEmail] = useState("");
  const [resetEmail, setResetEmail] = useState("");

  const value = useMemo(() => ({
    user,
    pendingEmail,
    resetEmail,
    register: async (values) => {
      const result = await mockAuthService.register(values);
      setPendingEmail(result.email);
      return result;
    },
    login: async (values) => {
      const account = await mockAuthService.login(values);
      setUser(account);
      return account;
    },
    logout: () => setUser(null),
    requestPasswordReset: async (email) => {
      const result = await mockAuthService.requestPasswordReset(email);
      setResetEmail(result.email);
      return result;
    },
    resetPassword: (values) => mockAuthService.resetPassword(values),
    verifyOtp: (code) => mockAuthService.verifyOtp({ code }),
    resendOtp: () => mockAuthService.resendOtp(),
    verifyEmail: () => mockAuthService.verifyEmail(),
    clearPendingEmail: () => setPendingEmail(""),
  }), [pendingEmail, resetEmail, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}
